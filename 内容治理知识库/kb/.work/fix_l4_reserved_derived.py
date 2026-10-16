#!/usr/bin/env python3
"""修 kb/l4/registry/l4.json 的 numbering.totals.reserved_unused_segments —— 从硬编码字面量残留改成派生值。

【缺陷】同一份 totals 里自相矛盾：
    segments_used            = [E-1, E-2, S-1, W-1, W-2, W-3]     ← E-2 在「已用」
    reserved_unused_segments = [W-4, W-5, W-6, S-2, E-2, P-1]     ← E-2 又在「未用」
  E-2 的权威状态是 block_by_library.external_standard.E-2.state == "issued"
  （20261001-1015 的 e2_ledger_patch 加了 123 条），所以「未用」那侧是错的。

【病根】该键原是 batch9_assign.py 里的一张**硬编码字面量**
  （"W-4"…"E-2"/"external_standard"…"P-1"），写成时 E-2 确实还预留；
  10-01 改 state 时没人同步它，而 l4_article.py 的 totals 是**整块承接**
  （prev_totals = dict(旧 totals)）⇒ 错值每跑一次就被原样重发进 run 快照。
  ⇒ 已在 kb/.work/l4_article.py 里把它改成**派生**（真源 = block_by_library 的 state）。
  本脚本只负责把**已经存下来的那个错值**就地订正，不留半成品。

【口径】与 l4_article.py 改后、以及 kb/.work/l7_article_source_refresh.py 的 reserved 段一致：
  取段键短名（block 号跨库不唯一）、state == "reserved_unused"、sorted()。
  ★ 本脚本**不自创口径**：它断言的期望值 = 真引擎在镜像沙箱里 --apply 后的产物
    （/tmp/e2fix-20261012 那次），对不上就拒绝写。

【幂等】已是派生值 ⇒ 零写入。
【预演】默认预演；加 --apply 才落盘。
"""
import json, os, sys, shutil, hashlib, time

KB = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))   # kb/.work/x.py → kb
REG = os.path.join(KB, "l4/registry/l4.json")
ARCH_DIR = os.path.join(KB, "l4/_archive")
APPLY = "--apply" in sys.argv


def derive(numbering):
    """真源 = block_by_library[*][*].state。与 l4_article.py 改后逐字同式。"""
    return sorted(
        seg for _lib, segs in (numbering.get("block_by_library") or {}).items()
        for seg, info in (segs or {}).items()
        if (info or {}).get("state") == "reserved_unused"
    )


def main():
    reg = json.load(open(REG, encoding="utf-8"))
    numbering = reg.get("numbering") or {}
    totals = numbering.get("totals") or {}
    old = totals.get("reserved_unused_segments")
    want = derive(numbering)
    used = sorted(numbering.get("totals", {}).get("segments_used") or [])

    print(f"台账：{REG}")
    print(f"  现值（stored）  = {old}")
    print(f"  应值（derived） = {want}")

    # 判据 ①：应值必须与真引擎产物一致（不是本脚本自己另算一套）
    ENGINE_EXPECT = ["P-1", "S-2", "W-4", "W-5", "W-6"]
    if want != ENGINE_EXPECT:
        print(f"\n✗ 拒绝写：派生值 {want} != 真引擎产物 {ENGINE_EXPECT}。")
        print("  说明 ledger 的 block_by_library 变了 —— 先重跑引擎核对，别照本脚本写。")
        return 2

    # 判据 ②：修完不许再与 segments_used 相交（自相矛盾的定义）
    clash = sorted(set(want) & set(used))
    if clash:
        print(f"\n✗ 拒绝写：修完仍与 segments_used 相交：{clash}")
        return 2

    if old == want:
        print("\n✓ 已是派生值，零写入（幂等）。")
        return 0

    print(f"\n将把该键订正为派生态。segments_used 与派生态无交集 ✅（{used} vs {want}）")
    if not APPLY:
        print("[dry-run] 加 --apply 才落盘。")
        return 0

    os.makedirs(ARCH_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    arch = os.path.join(ARCH_DIR, f"l4.json.before-reserved-derived-{stamp}")
    shutil.copy2(REG, arch)
    before_sha = hashlib.sha256(open(REG, "rb").read()).hexdigest()
    after_arch_sha = hashlib.sha256(open(arch, "rb").read()).hexdigest()
    if before_sha != after_arch_sha:
        print("✗ 归档 sha 不一致，拒绝写。")
        return 2
    print(f"归档 → {arch}\n  sha256 {before_sha[:16]}…（归档 == 原件 ✅）")

    totals["reserved_unused_segments"] = want
    numbering["totals"] = totals
    reg["numbering"] = numbering
    tmp = REG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8"))          # 回读校验，坏就不替换
    os.replace(tmp, REG)

    back = json.load(open(REG, encoding="utf-8"))
    got = back["numbering"]["totals"]["reserved_unused_segments"]
    if got != want:
        print(f"✗ 回读不一致：{got} != {want}")
        return 2
    print(f"回读 ✅ reserved_unused_segments = {got}")
    print(f"落盘完成｜新 sha256 {hashlib.sha256(open(REG,'rb').read()).hexdigest()[:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
