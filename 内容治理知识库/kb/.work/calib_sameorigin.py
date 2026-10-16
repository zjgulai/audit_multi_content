#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同源判据的门限标定（2026-10-08，第二版）

★ 第一版**量错了对象**，记在这里：我拿**整条条款正文**配对，得到
  「阴性最大 R=746 / 阳性最小 R=90」—— 两个分布完全重叠，R 一点用没有。
  原因是条款正文很长、且共用大量套话（「【审核 · 日期】」这类），
  公共子串自然很长。**而合并时要比的是「命中片段」**（「限时」「静音」），
  不是整篇条款。量错对象 ⇒ 标定出来的是另一个问题的答案。

  这一版比的是 `forbidden_expression`（命中表达）—— 与线上合并时用的同一个东西。

判据：最长公共子串 R（归一化：NFKC + 小写 + 只留汉字/数字/字母）。
  · **阴性**：不同规则的命中表达两两配对（不该合并）
  · **阳性**：**同一个命中表达写了多遍**的规则对（该合并 —— 同一件事、不同条款号）
门限取在阴性分布之上：低了会把两条不同的问题并成一条（**漏报**），比多报严重。
"""
import json, os, re, random, unicodedata
from collections import defaultdict
KB = '/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理'

def norm(s):
    s = unicodedata.normalize('NFKC', str(s or '')).lower()
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', s)

def lcs_len(a, b):
    if not a or not b: return 0
    if len(a) > len(b): a, b = b, a
    prev = [0] * (len(a) + 1); best = 0
    for ch in b:
        cur = [0] * (len(a) + 1)
        for i in range(1, len(a) + 1):
            if a[i-1] == ch:
                cur[i] = prev[i-1] + 1
                if cur[i] > best: best = cur[i]
        prev = cur
    return best

rules = [json.loads(l) for l in open(os.path.join(KB,'kb/l3/candidates/rules.jsonl'),encoding='utf-8') if l.strip()]
exps = []
for r in rules:
    e = str(r.get('forbidden_expression') or '').strip()
    if e: exps.append((norm(e), e, r))
exps = [(n, e) for n, e, _ in exps if len(n) >= 2]
print(f"命中表达可用 {len(exps)} 条（原始规则 {len(rules)} 条）")

random.seed(20261008)
neg = sorted(lcs_len(*random.sample([n for n, _ in exps], 2)) for _ in range(20000))
def pct(a, p): return a[min(len(a)-1, int(len(a)*p))]
print("\n【阴性·不同表达随机配对 n=%d】R 分布：" % len(neg))
for p in (0.5, 0.9, 0.99, 0.999, 0.9999):
    print(f"   p{str(round(p*100,2)):<7} = {pct(neg, p)}")
print(f"   最大 = {neg[-1]}")

# 阳性：同一个（归一化后的）命中表达出现多次 ⇒ 同一件事写了多遍
by = defaultdict(list)
for n, e in exps: by[n].append(e)
groups = [v for v in by.values() if len(v) >= 2]
print(f"\n【阳性·同一表达写了多遍】组数 {len(groups)}（共 {sum(len(g) for g in groups)} 条规则）")
pos = []
for g in groups:
    for i in range(len(g)):
        for j in range(i+1, len(g)):
            a, b = norm(g[i]), norm(g[j])
            pos.append((lcs_len(a, b), min(len(a), len(b))))
pos.sort()
print(f"   对数 {len(pos)}；R 最小 = {pos[0][0] if pos else '—'}｜R 中位 = {pos[len(pos)//2][0] if pos else '—'}")
for r, m in pos[:5]:
    print(f"   R={r:<4} 短边={m} 比值={r/m:.3f}")

lo = neg[-1] + 1
print("\n── 建议门限 ──")
print(f"   阴性最大 R = {neg[-1]} ／ p99.99 = {pct(neg, 0.9999)}")
if pos:
    print(f"   阳性最小 R = {pos[0][0]}")
    for cand in (neg[-1] + 1, pct(neg, 0.9999) + 1, 4, 6, 8, 10):
        okp = sum(1 for r, _ in pos if r >= cand)
        print(f"   R ≥ {cand:<4} → 阳性收进 {okp}/{len(pos)}（{okp/len(pos):.1%}）"
              + ("   ✅" if okp == len(pos) else "   ⚠ 会漏"))
