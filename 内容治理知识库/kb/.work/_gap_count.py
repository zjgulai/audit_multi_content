#!/usr/bin/env python3
# 只读：统计「条款号缺口」到底有多少条
import json, os, collections, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
os.chdir(ROOT)

def rows(p):
    out = []
    with open(p, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append((i, json.loads(line)))
            except Exception as e:
                out.append((i, {'_parse_error': str(e)}))
    return out

def idof(r):
    for k in ('rule_id', 'case_id', 'clause_id', 'unit_id', 'id'):
        if r.get(k):
            return r[k]
    return None

print("=" * 80)
print("A. L3 候选件（发号的来源）")
print("=" * 80)
for p in ['kb/l3/candidates/rules.jsonl', 'kb/l3/candidates/external_standard.jsonl',
          'kb/l3/candidates/sample_cases.jsonl', 'kb/l3/candidates/scoped_clauses.jsonl']:
    if not os.path.exists(p):
        print(f"  {p:48s} 不存在")
        continue
    rs = rows(p)
    has = [r for _, r in rs if r.get('article_no')]
    no = [r for _, r in rs if not r.get('article_no')]
    ids = [idof(r) for _, r in rs]
    uid = set(x for x in ids if x)
    print(f"  {p}")
    print(f"      行 {len(rs):5d} | 唯一id {len(uid):5d} | 有号 {len(has):5d} | 无号 {len(no):5d}")

print()
print("=" * 80)
print("B. L4 canonical（号已落盘处）")
print("=" * 80)
tot = 0
allsn = []
for fn in sorted(os.listdir('kb/l4/canonical')):
    p = os.path.join('kb/l4/canonical', fn)
    rs = rows(p)
    has = [r for _, r in rs if r.get('article_no')]
    tot += len(has)
    segs = collections.Counter(str(r.get('article_no')).split('.')[0] for _, r in rs if r.get('article_no'))
    allsn += [r.get('article_no') for _, r in rs if r.get('article_no')]
    print(f"  {fn:32s} 行 {len(rs):5d} | 有号 {len(has):5d} | 段 {dict(segs)}")
print(f"  canonical 有号合计 = {tot} | 去重 {len(set(allsn))}")

print()
print("=" * 80)
print("C. 台账 kb/l4/registry/l4.json")
print("=" * 80)
reg = json.load(open('kb/l4/registry/l4.json', encoding='utf-8'))
num = reg.get('numbering', {})
iss = num.get('issued', {})
print("  numbering 顶层键:", sorted(num.keys()))
print("  issued 段:", {k: (len(v) if isinstance(v, list) else v) for k, v in iss.items()})
print("  台账 issued 合计 =", sum(len(v) for v in iss.values() if isinstance(v, list)))

print()
print("=" * 80)
print("D. 缺口定义核对：L3 规则里没有号的，分几类")
print("=" * 80)
rl = rows('kb/l3/candidates/rules.jsonl')
es = rows('kb/l3/candidates/external_standard.jsonl')

# rules.jsonl 去重后
byid = {}
for ln, r in rl:
    k = idof(r)
    byid.setdefault(k, []).append((ln, r))
dup_ids = {k: v for k, v in byid.items() if len(v) > 1}
uniq_rules = {k: v[0] for k, v in byid.items()}
r_has = sum(1 for k, (ln, r) in uniq_rules.items() if r.get('article_no'))
r_no = sum(1 for k, (ln, r) in uniq_rules.items() if not r.get('article_no'))
print(f"  rules.jsonl  : 行 {len(rl)} → 唯一 rule_id {len(uniq_rules)}（重复 id {len(dup_ids)} 组，多出 {len(rl)-len(uniq_rules)} 行）")
print(f"                 其中有号 {r_has} / 无号 {r_no}")

e_has = sum(1 for _, r in es if r.get('article_no'))
e_no = sum(1 for _, r in es if not r.get('article_no'))
print(f"  external_standard.jsonl : 行 {len(es)} | 有号 {e_has} / 无号 {e_no}")

# 交集
rid = set(uniq_rules.keys())
eid = set(idof(r) for _, r in es)
print(f"  rules.jsonl ∩ external_standard.jsonl （按 id）= {len(rid & eid)}")

print()
print("  external_standard 无号条的 form 分布:")
print("   ", dict(collections.Counter(r.get('form') for _, r in es if not r.get('article_no'))))
print("  external_standard 无号条的 kb_type 分布:")
print("   ", dict(collections.Counter(r.get('kb_type') for _, r in es if not r.get('article_no'))))
print("  external_standard 字段样例:")
if es:
    print("   ", sorted(es[0][1].keys()))
