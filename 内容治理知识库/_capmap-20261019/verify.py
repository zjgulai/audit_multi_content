#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回读校验：飞书侧实际落下的值 vs 本地成稿，逐字段逐字对。"""
import json, sys, collections

def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

def norm(v):
    if isinstance(v, list):
        if not v: return ""
        x = v[0]
        if isinstance(x, dict): return str(x.get("text") or x.get("name") or x)
        return str(x)
    if v is None: return ""
    return str(v).strip()

bad = 0
for local_f, remote_f, key, fields, label in [
    ("t1_shouheng_records.json", "verify_t1.ndjson", "能力ID",
     ["L1底座","L2入口","L3业务问题","使用方法","案例","案例类型","案例证据","代码引用","边界限制","状态","as_of"], "①"),
    ("t2_shouheng_records.json", "verify_t2.ndjson", "组件",
     ["额度或余量","失效影响","当前状态","代码引用","最近实测","已知风险"], "②"),
]:
    L = json.load(open(local_f, encoding="utf-8"))
    R = load(remote_f)
    print(f"\n=== {label} 本地 {len(L)} 行 / 飞书 {len(R)} 行 ===")
    if len(L) != len(R):
        print(f"  ❌ 行数不一致"); bad += 1
    rmap = {norm(r.get(key)): r for r in R}
    missing = [norm(x[key]) for x in L if norm(x[key]) not in rmap]
    if missing:
        print(f"  ❌ 飞书缺 {len(missing)} 行：{missing[:5]}"); bad += 1
    diffs = collections.Counter()
    for x in L:
        r = rmap.get(norm(x[key]))
        if not r: continue
        for f in fields:
            a, b = norm(x.get(f)), norm(r.get(f))
            if a != b:
                diffs[f] += 1
                if diffs[f] <= 2:
                    print(f"  ❌ {norm(x[key])} [{f}] 本地={a[:60]!r} 飞书={b[:60]!r}")
        # 勾选字段单独核
        if label == "①":
            if bool(x.get("关键项")) != bool(r.get("关键项")):
                print(f"  ❌ {norm(x[key])} [关键项] 本地={x.get('关键项')} 飞书={r.get('关键项')}")
                diffs["关键项"] += 1
    if diffs:
        print(f"  ❌ 字段级差异：{dict(diffs)}"); bad += 1
    else:
        print(f"  ✅ {len(fields)} 个字段逐字一致")

print("\n" + ("✅ 回读校验通过" if bad == 0 else f"❌ 校验发现 {bad} 类问题"))
sys.exit(1 if bad else 0)
