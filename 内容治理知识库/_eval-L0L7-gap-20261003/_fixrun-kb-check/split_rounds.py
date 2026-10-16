#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「一次 workflow 跑完 3 轮」的会话按**每条用例的 createdAt 顺序**切成 3 个轮次文件。

为什么可以这么切：workflow 的 `parallel()` 是屏障 —— 第 N+1 轮的 53 个会话
**必然在第 N 轮 53 个全部 settle 之后**才创建。故对任一条用例，其 3 个会话按
createdAt 升序 = 第 1/2/3 轮。切完做一致性校验：每条用例必须恰好 3 个会话，
且每个轮次覆盖的用例集合必须完全相同。
"""
from __future__ import annotations
import json, os, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
src = json.load(open(os.path.join(HERE, sys.argv[1]), encoding="utf-8"))
rounds = [collections.defaultdict(dict) for _ in range(3)]
bad = []
for cid, recs in src.items():
    if len(recs) != 3:
        bad.append((cid, len(recs)))
        continue
    for i, r in enumerate(recs):
        rounds[i][cid] = [r]
if bad:
    print("!! 会话数不等于 3 的用例：", bad); sys.exit(2)
sets = [set(r) for r in rounds]
assert sets[0] == sets[1] == sets[2], "三轮覆盖的用例集合不一致"
for i, r in enumerate(rounds, 1):
    out = f"rounds/a-round{i}.json"
    json.dump(dict(r), open(os.path.join(HERE, out), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"-> {out}  {len(r)} 条用例  (校验：集合一致 ✓)")
print("切轮完成：每条用例恰好 3 个会话，按 createdAt 升序对应第 1/2/3 轮")
