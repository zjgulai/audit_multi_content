#!/usr/bin/env python3
"""回填报告里的 L0 飞书直链：负面样本表 旧 record_id → 新 record_id。

为什么要做（2026-10-14 实测）：飞书「负面样本」表被整体重建，174 条现行记录全部换新 ID，
本地 L0 的 201 件仍是旧代，**交集 0** ⇒ 引用内部正负样本库条款的报告，其 L0 直链全部 404。
内容没丢（13/14 原文反馈逐字同源），故可回填。

三条纪律：
  1. **先全量备份**到 `backup_reports_<stamp>/`，保留相对路径；
  2. **只换 ID，不动正文一个字**（不做"顺手润色"）；
  3. `.md` 走 `_safe_write.write_text`（防宿主信封），写完**回读复核**；
     替换数对不上就**抛错回滚**，不静默。

不做的事：**不修源表里写错的类型前缀**（那是只读源，禁区）；
**不给未配上的那条瞎编新 ID**（宁缺毋滥）。
"""
import json, os, re, shutil, sys, datetime

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "out")
sys.path.insert(0, os.path.join(ROOT, "kb/.work"))
from _safe_write import write_text          # noqa: E402

STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
BACKUP = os.path.join(HERE, f"backup_reports_{STAMP}")
ID_RE = re.compile(r"(?<![A-Za-z0-9])(rec[A-Za-z0-9]{11})(?![A-Za-z0-9])")


def main(apply=False):
    dead = json.load(open(os.path.join(OUT, "dead_l0_links.json")))
    files = dead["files"]
    mapping = json.load(open(os.path.join(OUT, "l0_remap_v2.json")))["mapping"]

    # 只回填已验证同源的那 13 条
    verified = json.load(open(os.path.join(OUT, "backfill_14_verified.json")))
    good = {r["old"]: r["new"] for r in verified if r["new"] and r["fb_same"]}
    skipped = {r["old"]: r for r in verified if not (r["new"] and r["fb_same"])}
    print(f"可回填 {len(good)} 条；跳过 {len(skipped)} 条：")
    for k, v in skipped.items():
        print(f"   {k}（{v['pfx_old']}）—— 源表已无同源记录，无法回填")
    if not apply:
        print("\n[预演] 未写盘。加 --apply 才落盘。")
        return

    os.makedirs(BACKUP, exist_ok=True)
    total_hits, changed_files, failed = 0, 0, []
    for rel in files:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        src = open(p, encoding="utf-8").read()
        n = 0

        def sub(m):
            nonlocal n
            if m.group(1) in good:
                n += 1
                return good[m.group(1)]
            return m.group(1)

        new_text = ID_RE.sub(sub, src)
        if n == 0:
            continue
        # 备份（保留相对路径）
        bp = os.path.join(BACKUP, rel)
        os.makedirs(os.path.dirname(bp), exist_ok=True)
        shutil.copy2(p, bp)
        write_text(p, new_text)
        back = open(p, encoding="utf-8").read()
        if back != new_text:
            failed.append(rel)
        total_hits += n
        changed_files += 1

    print(f"\n改动文件 {changed_files} 份，替换 {total_hits} 处")
    print(f"备份在 {os.path.relpath(BACKUP, ROOT)}")
    if failed:
        print("!!! 回读不一致，需人工看：", failed)
        sys.exit(3)
    print("回读复核：全部一致")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
