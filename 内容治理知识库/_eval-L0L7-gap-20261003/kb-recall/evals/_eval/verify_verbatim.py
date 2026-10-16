#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 5.4 第 3–4 步的机器核验：**全部**用例 × **每一轮**的「回复」是否与会话归档逐字相同。

做法：results-*.json 里的每条回复，重新从该轮会话归档（session.jsonl.zstd 的最后一个
assistant/message）里取一次，逐字节比对；不一致就打印差异位置与长度，供人工改回原文。

用法：python3 verify_verbatim.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_session as rs  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
ROUNDS = os.path.join(EV, "rounds")


def main():
    bad = []
    tot = 0
    for paper in ("a", "b"):
        res = json.load(open(os.path.join(EV, f"results-{paper}.json"), encoding="utf-8"))
        idx = {}
        for rnd in (1, 2, 3):
            p = os.path.join(ROUNDS, f"{paper}-round{rnd}.jsonl")
            if os.path.exists(p):
                for line in open(p, encoding="utf-8"):
                    if line.strip():
                        rec = json.loads(line)
                        idx[(str(rec["id"]), rnd)] = rec
        for cid, case in res.items():
            for i, rt in enumerate(case["轮次"], start=1):
                tot += 1
                rec = idx.get((str(cid), i))
                if rec is None:
                    bad.append((paper, cid, i, "该轮无记录"))
                    continue
                live = ""
                for aid, fp in rs.session_files(os.path.dirname(os.path.dirname(rec["cwd"]))):
                    if os.path.abspath(fp) == os.path.abspath(rec["session_path"]):
                        live = rs.analyse(fp, "kb-recall")["reply"]
                        break
                if not live:
                    live = rs.analyse(rec["session_path"], "kb-recall")["reply"]
                if live != (rt["回复"] or ""):
                    bad.append((paper, cid, i, f"不一致 归档{len(live)}c vs 报告{len(rt['回复'] or '')}c"))
                if not (rt["回复"] or "").strip():
                    bad.append((paper, cid, i, "空回复"))
    print(f"逐字核验：{tot} 条回复（用例 × 轮次）")
    if bad:
        print("不一致/异常：", len(bad))
        for x in bad[:40]:
            print("   ", x)
    else:
        print("✅ 全部与会话归档逐字一致，无空回复")
    json.dump({"checked": tot, "mismatch": bad},
              open(os.path.join(HERE, "verbatim-check.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
