#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把密封重跑的结果并回 rounds/*.jsonl（同 (paper,id,round) 以重跑记录为准）。"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
ROUNDS = os.path.join(EV, "rounds")
SRC = "/tmp/kbrecall-rerun-out.jsonl"


def main():
    new = {}
    for line in open(SRC, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            new[(r["paper"], str(r["id"]), r["round"])] = r
    if not new:
        print("没有重跑结果")
        return 1
    changed = 0
    for p in ("a", "b"):
        for rnd in (1, 2, 3):
            fp = os.path.join(ROUNDS, f"{p}-round{rnd}.jsonl")
            if not os.path.exists(fp):
                continue
            rows = []
            for line in open(fp, encoding="utf-8"):
                if not line.strip():
                    continue
                r = json.loads(line)
                k = (p, str(r["id"]), rnd)
                if k in new:
                    rows.append(new.pop(k))
                    changed += 1
                else:
                    rows.append(r)
            with open(fp, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"替换 {changed} 条；未匹配 {len(new)} 条", list(new)[:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
