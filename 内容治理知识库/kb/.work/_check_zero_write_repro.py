#!/usr/bin/env python3
"""只读复现：kb_pipeline.py:191-213 snapshot_mtimes() 的 4000 上限到底漏掉了哪些层。
不改任何库文件；仅 import 编排器的函数并在内存里跑一遍。"""
import os, sys, json, collections

KB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.dirname(KB)          # kb/ 的上一级
sys.path.insert(0, os.path.join(KB, 'l7', 'scripts'))

import importlib.util
spec = importlib.util.spec_from_file_location("kbp", os.path.join(KB, 'l7', 'scripts', 'kb_pipeline.py'))
kbp = importlib.util.module_from_spec(spec)
# 只加载模块定义，不执行 main（kb_pipeline.py 靠 __main__ 守卫）
spec.loader.exec_module(kbp)

import yaml
reg = os.path.join(KB, 'l7', 'registry', 'layers.yaml')
doc = yaml.safe_load(open(reg, encoding='utf-8'))
layers = doc['layers'] if isinstance(doc, dict) and 'layers' in doc else doc

# 逐层单独快照，看每层自己能贡献多少 —— 以及被 4000 截断时谁被吃掉
def snap_one(layer):
    return kbp.snapshot_mtimes([layer])

print("=" * 78)
print("逐层单独调用 snapshot_mtimes()（看每层自身的产出规模）")
print("=" * 78)
per = {}
for x in layers:
    s = snap_one(x)
    per[x['layer']] = len(s)
    print(f"  {x['layer']:4s} 快照文件数 {len(s):5d}  outputs={len(x.get('outputs') or [])}")

print()
print("=" * 78)
print("全层一起调用（编排器 --check 的真实行为）")
print("=" * 78)
allf = kbp.snapshot_mtimes(layers)
print(f"  全链快照文件数 = {len(allf)}   （上限 4000，>4000 即提前 return）")

# 判定每一层有多少产出文件真的进了快照
print()
print("=" * 78)
print("逐层实际覆盖（该层产出的路径有多少落进最终快照）")
print("=" * 78)
covered = collections.Counter()
total = collections.Counter()
for x in layers:
    lay = x['layer']
    own = snap_one(x)
    for p in own:
        total[lay] += 1
        if p in allf:
            covered[lay] += 1

print(f"  {'层':4s} {'该层产出':>8s} {'进快照':>8s}  覆盖")
for x in layers:
    lay = x['layer']
    t, c = total[lay], covered[lay]
    pct = (100.0 * c / t) if t else 100.0
    flag = "✅ 全覆盖" if (t and c == t) else ("⚠️ 部分" if c else "❌ 零覆盖")
    print(f"  {lay:4s} {t:8d} {c:8d}  {flag} ({pct:.1f}%)")

print()
zero = [x['layer'] for x in layers if total[x['layer']] and covered[x['layer']] == 0]
print(f"  ★ 零覆盖的层 = {zero if zero else '（无）'}")
print(f"  → 这些层的写入，--check 的 zero_write 检测不到。")
