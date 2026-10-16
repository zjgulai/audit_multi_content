#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 A 卷（100 条 + 调用 3 条）只按「序号 + 提示词」列切成发送清单分片（盲测用）。

被测会话只能看到提示词列；类型/标题/预期结果/标签/优先级一律不写进分片文件。
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SH = HERE / "shards"
SH.mkdir(exist_ok=True)

A = json.loads((HERE / "cases_a.json").read_text(encoding="utf-8"))
allc = A["cases"] + A["call_cases"]
SIZE = 10
index = {}
n = 0
for i in range(0, len(allc), SIZE):
    n += 1
    part = allc[i:i + SIZE]
    lines = []
    for c in part:
        lines.append(f"【消息 {c['id']}】")
        lines.append(c["prompt"] if c["prompt"].strip() else "（本条用户没有输入任何内容）")
        lines.append("")
    (SH / f"shard_{n:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    index[f"shard_{n:02d}"] = [c["id"] for c in part]

(SH / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"生成 {n} 个分片，共 {len(allc)} 条；分片大小 {SIZE}（末片 {len(allc) % SIZE or SIZE}）")
for k, v in index.items():
    print(" ", k, v[:3], "...", v[-1])
