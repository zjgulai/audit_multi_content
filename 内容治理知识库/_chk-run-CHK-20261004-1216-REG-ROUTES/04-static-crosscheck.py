import yaml, os, re
R='kb/l7/registry/'
sk=yaml.safe_load(open(R+'skills.yaml'))
rt=yaml.safe_load(open(R+'routes.yaml'))
ly=yaml.safe_load(open(R+'layers.yaml'))
rows=sk['skills']
ids={r.get('id') for r in rows}
byid={r.get('id'):r for r in rows}
print("skills.yaml 顶层 skills 条数:",len(rows))
def chk(label,v):
    ok = v in ids
    print(("  OK   " if ok else "  MISS ")+f"{label}: {v!r}"+("" if ok else "  <-- 不在 skills.yaml"))
print("\n[1] routes.yaml routes[].to")
for r in rt['routes']: chk("to(intent=%s)"%r['intent'], r['to'])
print("\n[2] routes.yaml chains[] entry/members")
for c in rt['chains']:
    chk("chain=%s entry"%c['id'], c['entry'])
    for m in c['members']: chk("chain=%s member"%c['id'], m)
print("\n[3] routes.yaml mutual_not_for pairs")
for p in rt['mutual_not_for']:
    for m in p['pair']: chk("pair", m)
print("\n[4] routes.yaml frozen_expectation.dir_name_map keys")
for k in rt['frozen_expectation']['dir_name_map']: chk("dir_name_map key", k)
print("\n[5] layers.yaml 各层 skill:")
for L in ly.get('layers',[]):
    s=L.get('skill')
    if isinstance(s,list):
        for x in s: chk("layer=%s skill"%L.get('id'), x)
    else: chk("layer=%s skill"%L.get('id'), s)
print("\n[6] dir_name_map 值 vs 装载位真实目录")
base=os.path.expanduser('~/.dsh/skills')
for k,v in rt['frozen_expectation']['dir_name_map'].items():
    p=os.path.join(base,v)
    print(("  OK   " if os.path.isdir(p) else "  MISS ")+f"{k} -> {v}")
