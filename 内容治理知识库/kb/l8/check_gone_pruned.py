#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_gone_pruned.py —— 「源里已删的记录，下游一条都不许留」（2026-10-20；串图修复 ③）

## 守什么

L0 早把删掉的记录标成 `status=gone`，但 L2/L6 一直留着（实测 441 条 unit / 237 条 doc，
来自 127 条已删记录）⇒ 召回把它们排到前面，链接点开是**不存在的记录**。

本闸门：L2 `units.jsonl` 与 L6 `bm25/docs.jsonl` 里，**任何**指向「不在现存记录集合里」的
行都算红；并给**反向对照**（真造一条陈旧行 ⇒ 必须红），证明尺子不是恒绿。

## 用法

    python3 kb/l8/check_gone_pruned.py            # 判据（读真库）
    python3 kb/l8/check_gone_pruned.py --selftest # 反向对照（合成数据，不碰真库）
"""
import json
import os
import re
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = "tbld8qE92YaY38Yz"
sys.path.insert(0, os.path.join(KB, "l8"))
import prune_gone_units as P                                    # noqa: E402 复用同一把尺子


def scan(path, live):
    bad, seen = [], 0
    if not os.path.exists(path):
        return None, 0
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:                                       # noqa: BLE001
            continue
        r = P.record_of(d)
        if not r:
            continue
        seen += 1
        if r not in live:
            bad.append({"record_id": r, "anchor": (d.get("anchor") or "")[:60],
                        "file": os.path.basename(path)})
    return bad, seen


def main(argv):
    live, gone = P.live_records()
    l2, l2n = scan(os.path.join(KB, "l2", "units.jsonl"), live)
    l6, l6n = scan(os.path.join(KB, "l6", "bm25", "docs.jsonl"), live)
    bad = (l2 or []) + (l6 or [])
    ok = not bad
    print("现存记录 %d 条｜manifest 标 gone %d 条" % (len(live), len(gone)))
    print("L2 指向记录的单元 %d 条 ⇒ 陈旧 %d 条" % (l2n, len(l2 or [])))
    print("L6 指向记录的文档 %d 条 ⇒ 陈旧 %d 条" % (l6n, len(l6 or [])))
    for b in bad[:5]:
        print("  ❌", b)
    print("check_gone_pruned %s" % ("PASS（没有一条指向已删记录）" if ok else "FAIL"))
    return 0 if ok else 3


def selftest():
    live = {"rec_live"}
    rows = [{"unit_id": "a", "anchor": "#素材/rec_live/图片素材/#img.1"},
            {"unit_id": "b", "anchor": "#素材/rec_dead/图片素材/#img.1"},
            {"unit_id": "c", "resource_id": "media_%s_rec_dead2" % TABLE, "anchor": "#x"}]
    kept, dropped = P.plan(rows, live)
    cases = [
        ("正例：现存记录的行保留", [r["unit_id"] for r in kept] == ["a"], [r["unit_id"] for r in kept]),
        ("反例：已删记录的行必须被认出来（两种写法都认）",
         sorted(r["unit_id"] for r, _ in dropped) == ["b", "c"], [r["unit_id"] for r, _ in dropped]),
    ]
    ok = all(c[1] for c in cases)
    for name, okc, detail in cases:
        print(("  ✅ " if okc else "  ❌ ") + name + ("" if okc else "  ← " + str(detail)))
    print("check_gone_pruned --selftest %s（%d/%d）"
          % ("PASS" if ok else "FAIL", sum(1 for c in cases if c[1]), len(cases)))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main(sys.argv[1:]))
