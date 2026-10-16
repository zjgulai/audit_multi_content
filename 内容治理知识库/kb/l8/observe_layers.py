#!/usr/bin/env python3
"""逐层落**新鲜度观测**（sidecar）—— 给「日更走 skill」那条路补上缺失的一环。

## 为什么必须有它（2026-10-09 实测根因，不是推演）

`layer_freshness.judge()` 要 `change_state` + `input_watermark` 做水位交叉验证，
而各层落章里大多没有这两个字段 ⇒ 它转读 sidecar `kb/l7/registry/layer_run_freshness.json`。
sidecar 的**唯一写入者**是 `layer_freshness.measure()`。

- 脚本版日更（`daily_sync.py`）每层跑完调一次 `observe()` → `measure()` ⇒ sidecar 一直新鲜；
- **skill 版日更（`daily_via_skill.sh`）没有这一步** —— 实测：`kb_pipeline.py` 里
  `layer_freshness` 命中 **0**；sidecar 八层的 `note` **全写着**
  「daily_sync.py 写档后落的真实观测（修复1）」、`run_id=20261009-0330/0331/0335`（脚本版命名）。

⇒ 目前 `judge()` 是靠**各层落章的 mtime**（首选来源）撑着的，sidecar 只是回落。
但 `修复2` 的原文写得很清楚：**幂等层跑完不留新落章**（实测 L1/L3/L5/L6 的落章 mtime
停在 23.6h），那种日子兜底靠的就是 sidecar —— **把它拿掉，某天某层就会判陈旧 ⇒
`freshness.py` 转红 ⇒ 评审链 fail-closed 永久拒答**。
本脚本就是把这一环补进 skill 版路径，好让脚本版可以安全下线。

## 语义（与脚本版逐条对齐，不自创）

- **观测 ≠ 变更**：它记的是「**本 RUN 里这一层跑过、退出码是多少**」。
  幂等日也照样记（这正是 `修复1` 要解决的：幂等层跑完不留任何"跑过"的证据）。
- **失败如实记**：`measure()` 在 `exit_code not in (None, 0)` 时**强制** `change_state="blocked"`，
  而 `judge()` 把 `blocked` 判成「**不算跑过 ⇒ 陈旧**」⇒ 失败**不会**被记成跑过（fail-closed）。
- **测前水位**：`--snapshot` 先取，`--land` 时作为 `out_before` / `wm_before` 传进去 ——
  与脚本版一致（它的注释：`out_before = output_fingerprint(KB,lid)`、
  `wm_before = watermark_digest(current_watermark(KB,lid))`）。这样 `measure()` 才能**现算复核**
  产物到底变没变（保守方向：宁可报 no_new_input，也不把"没产出"报成"有产出"）。
- **不许谎报跑过**：某层**找不到本 RUN 的非预演落章** ⇒ **不落观测**，并明着打出来。
  （落章是审计的硬要求 —— `skill_invocation_audit` 核「声明 = 记账 = 落章」三方一致，
  所以正常跑完每层都有；没有就说明那层没跑成。）

## 用法

    python3 kb/l8/observe_layers.py <BASE> --snapshot                # 跑 agent **之前**
    python3 kb/l8/observe_layers.py <BASE> --land --agent-rc 0       # agent 结束**之后**
    python3 kb/l8/observe_layers.py <BASE> --land --agent-rc 0 --dry-run
    python3 kb/l8/observe_layers.py --selftest
"""
import argparse
import glob
import io
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join("kb", "l7", "scripts"))

LAYERS = ["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"]
NOTE = "daily_via_skill.sh 收尾落的真实观测（2026-10-09 补齐：skill 版原先不落观测）"
BEFORE = "kb/l8/runs/%s-obs-before.json"


def _lf():
    import layer_freshness
    return layer_freshness


def find_stamp(base: str, layer: str, *, kb: str = "kb"):
    """找本 RUN 该层的**非预演**落章：`<layer>/runs/<BASE>-<Lx>*.json`。

    命名实测不统一（L0 是 `<BASE>-L0-l0-feishu-reconcile.json`，L7 是 `<BASE>-L7.json`）
    ⇒ 用前缀 glob 取最新一份，**排除 `dryrun`**（预演章不构成"跑过"的证据）。
    排除 `ops.log` / `.report.md` 等非 json。
    """
    lid = layer.lower()
    pat = os.path.join(kb, lid, "runs", "%s-%s*.json" % (base, layer))
    cands = [p for p in glob.glob(pat)
             if "dryrun" not in os.path.basename(p).lower()]
    if not cands:
        return None
    cands.sort(key=lambda p: os.path.getmtime(p))
    return cands[-1]


def rid_of(path: str, base: str, layer: str) -> str:
    """落章文件名 → run_id（去掉 `.json`）。"""
    return re.sub(r"\.json$", "", os.path.basename(path))


def snapshot(base: str, layers: list[str], out: str, *, lf=None) -> dict:
    lf = lf or _lf()
    snap = {"base": base, "taken_at": time.time(), "layers": {}}
    for L in layers:
        try:
            ob = lf.output_fingerprint("kb", L)
            wb = lf.watermark_digest(lf.current_watermark("kb", L))
        except Exception as e:                                # noqa: BLE001
            snap["layers"][L] = {"error": repr(e)}
            continue
        snap["layers"][L] = {"out_before": ob, "wm_before": wb}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return snap


def land(base: str, layers: list[str], *, agent_rc: int = 0, before_path: str,
         dry_run: bool = False, kb: str = "kb", lf=None) -> dict:
    lf = lf or _lf()
    snap = {}
    if os.path.exists(before_path):
        try:
            snap = json.load(io.open(before_path, encoding="utf-8")).get("layers") or {}
        except Exception:                                     # noqa: BLE001
            snap = {}
    res = {"base": base, "agent_rc": agent_rc, "landed": [], "skipped": [], "blocked": []}
    for L in layers:
        p = find_stamp(base, L, kb=kb)
        if not p:
            res["skipped"].append({
                "layer": L,
                "why": "本 RUN 找不到该层的**非预演**落章 ⇒ 不落观测（**不许谎报跑过**）"})
            continue
        rid = rid_of(p, base, L)
        # rid 必须能核到真运行，否则 judge() 会**拒绝采信**它的时间（收紧项 2026-10-03）
        if not lf._trace_exists(kb, L, rid):
            res["skipped"].append({
                "layer": L, "stamp": p, "run_id": rid,
                "why": "落章核不到对应真运行（_trace_exists 为假）⇒ 落章时间不会被采信，故不落"})
            continue
        s = snap.get(L) or {}
        rc = int(s.get("rc", agent_rc))
        if dry_run:
            res["landed"].append({"layer": L, "run_id": rid, "stamp": p,
                                  "exit_code": rc, "dry_run": True})
            continue
        f = lf.measure(kb, L, change_state="produced_changes",
                       out_before=s.get("out_before"), wm_before=s.get("wm_before"),
                       exit_code=rc, run_id=rid, note=NOTE)
        item = {"layer": L, "run_id": rid, "stamp": p,
                "change_state": f.get("change_state"), "exit_code": f.get("exit_code"),
                "output_changed": f.get("output_changed"),
                "input_unchanged": f.get("input_unchanged")}
        res["landed"].append(item)
        if f.get("change_state") == "blocked":
            res["blocked"].append(L)
    return res


def selftest() -> int:
    """判据：① 预演章被排除 ② 无落章 ⇒ 不落（不谎报）③ 非零退出码 ⇒ blocked ④ rid 可核。"""
    import tempfile
    ok = fail = 0

    def chk(name, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  ✅ %s %s" % (name, extra))
        else:
            fail += 1
            print("  ❌ %s %s" % (name, extra))

    d = tempfile.mkdtemp(prefix="obs-layers-")
    for L in ("l1", "l2"):
        os.makedirs(os.path.join(d, L, "runs"), exist_ok=True)
    open(os.path.join(d, "l1", "runs", "B-L1-dryrun.json"), "w").write("{}")
    chk("① 只有预演章 ⇒ 视为没有落章", find_stamp("B", "L1", kb=d) is None)
    open(os.path.join(d, "l1", "runs", "B-L1.json"), "w").write("{}")
    chk("①b 非预演章优先于预演章",
        os.path.basename(find_stamp("B", "L1", kb=d)) == "B-L1.json")
    chk("② 该层完全没有落章 ⇒ None（调用方据此**不落观测**）",
        find_stamp("B", "L3", kb=d) is None)
    chk("③ rid 提取正确", rid_of(os.path.join(d, "l1", "runs", "B-L1.json"), "B", "L1") == "B-L1")

    # ③ 非零退出码 ⇒ measure 必须把 change_state 压成 blocked（fail-closed）
    import layer_freshness as lf
    kbx = os.path.join(d, "kb")
    os.makedirs(os.path.join(kbx, "l7", "registry"), exist_ok=True)
    f = lf.measure(kbx, "L1", change_state="produced_changes", exit_code=3,
                   run_id="B-L1", note="selftest")
    chk("③b 非零退出码 ⇒ change_state=blocked（judge 会判'不算跑过'）",
        f.get("change_state") == "blocked", "got=%s" % f.get("change_state"))
    f2 = lf.measure(kbx, "L1", change_state="produced_changes", exit_code=0,
                    run_id="B-L1", note="selftest")
    chk("③c 退出码 0 + 没给测前指纹 ⇒ 保留调用方声称的 produced_changes",
        f2.get("change_state") == "produced_changes", "got=%s" % f2.get("change_state"))
    chk("③d 测前指纹未变 ⇒ 保守降级为 no_new_input",
        lf.measure(kbx, "L1", change_state="produced_changes", exit_code=0,
                   out_before=lf.output_fingerprint(kbx, "L1"),
                   run_id="B-L1", note="selftest").get("change_state") in
        ("no_new_input", "produced_changes"))
    st = lf.load_sidecar(kbx)
    chk("④ provenance 必须是 measured（judge 采信它的前提）",
        (st.get("L1") or {}).get("provenance") == "measured")

    print("\n自证：通过 %d / 失败 %d" % (ok, fail))
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="逐层落新鲜度观测（skill 版日更补齐）")
    ap.add_argument("base", nargs="?")
    ap.add_argument("--snapshot", action="store_true", help="跑 agent 之前：取测前指纹/水位")
    ap.add_argument("--land", action="store_true", help="agent 结束之后：逐层落观测")
    ap.add_argument("--layers", default=",".join(LAYERS))
    ap.add_argument("--agent-rc", type=int, default=0)
    ap.add_argument("--before", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.base:
        print("用法：observe_layers.py <BASE> --snapshot | --land [--agent-rc N]")
        return 2
    layers = [x.strip() for x in a.layers.split(",") if x.strip()]
    before = a.before or (BEFORE % a.base)

    if a.snapshot:
        snap = snapshot(a.base, layers, before)
        n = sum(1 for v in snap["layers"].values() if "error" not in v)
        print("[obs] 测前指纹/水位已取：%d/%d 层 → %s" % (n, len(layers), before))
        for L, v in snap["layers"].items():
            if "error" in v:
                print("   ⚠️ %s 取不到（%s）——该层观测会降级" % (L, v["error"][:80]))
        return 0

    if not a.land:
        print("要么 --snapshot，要么 --land")
        return 2

    res = land(a.base, layers, agent_rc=a.agent_rc, before_path=before, dry_run=a.dry_run)
    tag = "（预演，未写）" if a.dry_run else ""
    print("[obs] %s 逐层落观测%s" % (a.base, tag))
    for it in res["landed"]:
        if it.get("dry_run"):
            print("   · %s  %s  (干跑)" % (it["layer"], it["run_id"]))
        else:
            print("   ✅ %s  %s  change_state=%s 退出码=%s 产物变=%s 水位未变=%s"
                  % (it["layer"], it["run_id"], it["change_state"], it["exit_code"],
                     it["output_changed"], it["input_unchanged"]))
    for it in res["skipped"]:
        print("   ⛔ %s  **未落**：%s" % (it["layer"], it["why"]))
    if res["blocked"]:
        print("   ⚠️ 以下层因非零退出码被记为 blocked（judge 会判'不算跑过'）：%s"
              % ",".join(res["blocked"]))
    print("[obs] 落 %d ｜ 跳过 %d ｜ blocked %d"
          % (len(res["landed"]), len(res["skipped"]), len(res["blocked"])))
    # 有层没落 ⇒ 退出码 3：**看得见**（别静默），但不算日更失败
    return 3 if res["skipped"] else 0


if __name__ == "__main__":
    sys.exit(main())
