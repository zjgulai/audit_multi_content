#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F7 前置：核对 rules.jsonl 的序列化风格与字段现状。只读。"""
import json

P = "l3/candidates/rules.jsonl"
lines = open(P, encoding="utf-8").read().split("\n")
rows = [json.loads(l) for l in lines if l.strip()]
raw = [l for l in lines if l.strip()]
print(f"行数 {len(raw)}（rules 文件）")

d = rows[0]
for label, s in [
    ("ensure_ascii=False 默认", json.dumps(d, ensure_ascii=False)),
    ("sort_keys=True", json.dumps(d, ensure_ascii=False, sort_keys=True)),
    ("compact separators", json.dumps(d, ensure_ascii=False, separators=(",", ":"))),
]:
    print(f"  {label:26} 与原始行逐字节一致: {s == raw[0]}")

print("\n键顺序（原始）:", list(d.keys()))

# 三个目标字段：是「键不存在」还是「键存在但空」？
targets = ["half_life_days", "valid_until", "owner", "effective_from", "effective_to", "created_at"]
key_exists = {t: sum(1 for r in rows if t in r) for t in targets}
nonempty = {t: sum(1 for r in rows if r.get(t) not in (None, "", [], {})) for t in targets}
print("\n字段现状（509 行）：")
for t in targets:
    print(f"  {t:18} 键存在 {key_exists[t]:4}  非空 {nonempty[t]:4}")
