#!/usr/bin/env python3
"""只读：条款号缺口全库普查。
口径：一条「规则」= 一个稳定内容 id（rule_id / case_id / clause_id）。
问：这个 id 在**任何地方**有没有拿到 article_no？
"""
import json, os, collections

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
os.chdir(ROOT)

def rows(p):
    out = []
    if not os.path.exists(p):
        return out
    with open(p, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    out.append((i, json.loads(line)))
                except Exception:
                    pass
    return out

def idof(r):
    for k in ('rule_id', 'case_id', 'clause_id'):
        if r.get(k):
            return k, r[k]
    return None, None

# ── 第一遍：把所有出现过的 (id → article_no) 收集起来（全库任何文件）──
numbered = {}          # id -> article_no
where = collections.defaultdict(set)
scanned = []

for dirpath, dirnames, filenames in os.walk('kb'):
    dirnames[:] = [d for d in dirnames if d not in ('__pycache__', '_pre-rebuild-20260930-1550')]
    for fn in filenames:
        if not fn.endswith('.jsonl'):
            continue
        p = os.path.join(dirpath, fn)
        scanned.append(p)
        for _, r in rows(p):
            k, v = idof(r)
            if k and v and r.get('article_no'):
                numbered[v] = r['article_no']
                where[v].add(p)

print("=" * 80)
print(f"扫描 {len(scanned)} 个 .jsonl；全库带条款号的唯一 id = {len(numbered)}")
print("=" * 80)

# ── 第二遍：逐个「规则源」问 —— 这个源里的规则，号发齐了没 ──
SOURCES = [
    ('kb/l3/candidates/rules.jsonl',            'wording',           'W-1/W-2'),
    ('kb/l3/candidates/external_standard.jsonl','external_standard', 'E-2（本轮新发）'),
    ('kb/l3/candidates/sample_cases.jsonl',     'sample_case',       'W-3/S-1'),
    ('kb/l3/candidates/scoped_clauses.jsonl',   'scoped_clause',     'E-1'),
]

print()
print(f"{'源':52s} {'唯一规则':>8s} {'已发号':>8s} {'未发号':>8s}")
print("-" * 80)
tot_u = tot_h = tot_n = 0
gaps = {}
for p, label, seg in SOURCES:
    rs = rows(p)
    ids = {}
    for _, r in rs:
        k, v = idof(r)
        if k and v:
            ids.setdefault(v, r)
    has = [i for i in ids if i in numbered]
    no = [i for i in ids if i not in numbered]
    tot_u += len(ids); tot_h += len(has); tot_n += len(no)
    if no:
        gaps[p] = no
    print(f"{p:52s} {len(ids):8d} {len(has):8d} {len(no):8d}   ← {seg}")

print("-" * 80)
print(f"{'合计':52s} {tot_u:8d} {tot_h:8d} {tot_n:8d}")

print()
print("=" * 80)
print("缺口明细（如果还有）")
print("=" * 80)
if not gaps:
    print("  ★ 无缺口：上面每个源里的每一条规则，都已拿到条款号。")
else:
    for p, no in gaps.items():
        print(f"  {p}: 未发号 {len(no)} 条，例：{no[:3]}")

# ── canonical 侧 ──
print()
print("=" * 80)
print("canonical（定稿层）落盘情况")
print("=" * 80)
canon = collections.Counter()
for fn in sorted(os.listdir('kb/l4/canonical')):
    for _, r in rows('kb/l4/canonical/' + fn):
        if r.get('article_no'):
            canon[str(r['article_no']).split('.')[0]] += 1
print("  canonical 各段条数:", dict(canon), "合计", sum(canon.values()))

reg = json.load(open('kb/l4/registry/l4.json', encoding='utf-8'))
iss = reg['numbering']['issued']
print("  台账 issued 各段:", {k: v.get('count') for k, v in iss.items()},
      "合计", sum(v.get('count') or 0 for v in iss.values()))

print()
print("  台账 vs canonical 差额（= 已发号但还没定稿的）:")
for seg, info in sorted(iss.items()):
    a = info.get('count') or 0
    c = canon.get(seg, 0)
    if a != c:
        print(f"    {seg}: 台账 {a} 条 ｜ canonical {c} 条 ｜ ★差 {a - c} 条未定稿")
