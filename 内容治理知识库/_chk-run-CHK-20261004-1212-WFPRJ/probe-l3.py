import json,collections,os
rows=[json.loads(l) for l in open("kb/l3/candidates/rules.jsonl",encoding="utf-8") if l.strip()]
print("L3 总行数:",len(rows),"| 唯一 rule_id:",len({r['rule_id'] for r in rows}))
print("每 rule_id 行数分布:",collections.Counter(collections.Counter(r['rule_id'] for r in rows).values()))
print()
print("== 全库治理字段填充率（全部 1018 行）==")
for f in ["owner","half_life_days","valid_until","effective_from"]:
    ne=sum(1 for r in rows if r.get(f) not in (None,""))
    print(f"  {f:18s} 非空 {ne}/{len(rows)}")
print()
print("== 全库 p_level / risk_level 分布（按行）==")
print("  p_level :",collections.Counter(str(r.get("p_level")) for r in rows).most_common())
print("  risk    :",collections.Counter(str(r.get("risk_level")) for r in rows).most_common())
print()
print("== 同一 rule_id 的多行是否互补（抽样 2 组，看谁带治理字段）==")
g=collections.OrderedDict()
for r in rows: g.setdefault(r["rule_id"],[]).append(r)
for rid in list(g)[:2]:
    print(f"  rule_id={rid}  {len(g[rid])} 行")
    for i,r in enumerate(g[rid]):
        print(f"    行{i}: article_no={r.get('article_no')!r} p_level={r.get('p_level')!r} risk={r.get('risk_level')!r} "
              f"owner={r.get('owner')!r} half_life={r.get('half_life_days')!r} form={r.get('form')!r} keys={sorted(r.keys())[:14]}")
print()
print("== 是否存在携带治理字段的其他 L3 产物 ==")
for p in ["kb/l3/registry/half-life-policy.json","kb/l3/registry"]:
    if os.path.isfile(p): print("  存在:",p)
    elif os.path.isdir(p): print("  目录:",p,"->",sorted(os.listdir(p))[:12])
