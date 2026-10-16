import json,os,re,collections
d=json.load(open("kb/view/_meta/derivation.json",encoding="utf-8"))
rows=[json.loads(l) for l in open("kb/l3/candidates/rules.jsonl",encoding="utf-8") if l.strip()]
g=collections.OrderedDict()
for r in rows: g.setdefault(r["rule_id"],[]).append(r)
def head(rid):
    rs=g[rid]; return next((r for r in rs if r.get("article_no")), rs[0])
FM=re.compile(r"^---\n(.*?)\n---\n",re.S)
def fmf(fm,f):
    m=re.search(rf"^{f}:\s*(.*)$",fm,re.M); return (m.group(1).strip().strip('"').strip("'") if m else None)
mdp=collections.Counter(); l3p=collections.Counter()
mdr=collections.Counter(); l3r=collections.Counter()
mdown=collections.Counter(); l3own=collections.Counter()
for e in d["entries"]:
    p=os.path.join("kb/view",e["path"])
    if not os.path.isfile(p): continue
    m=FM.match(open(p,encoding="utf-8").read()); fm=m.group(1) if m else ""
    h=head(e["rule_id"])
    mdp[fmf(fm,"p_level")]+=1; l3p[str(h.get("p_level"))]+=1
    mdr[fmf(fm,"risk_level")]+=1; l3r[str(h.get("risk_level"))]+=1
    mdown[fmf(fm,"owner")]+=1; l3own[str(h.get("owner"))]+=1
def show(t,a,b):
    print(f"  {t}:\n     视图 kb/view : {dict(a.most_common(6))}\n     权威 L3 head : {dict(b.most_common(6))}")
print("== 509 条目 · 视图 vs 权威（head 行）实质分布 ==")
show("p_level",mdp,l3p); show("risk_level",mdr,l3r); show("owner",mdown,l3own)
print("\n== 视图 md 的 valid_until / half_life_days 分布 ==")
vu=collections.Counter(); vh=collections.Counter()
for e in d["entries"]:
    p=os.path.join("kb/view",e["path"])
    if not os.path.isfile(p): continue
    m=FM.match(open(p,encoding="utf-8").read()); fm=m.group(1) if m else ""
    vu[fmf(fm,"valid_until")]+=1; vh[fmf(fm,"half_life_days")]+=1
print("  valid_until :",dict(vu.most_common(8)))
print("  half_life   :",dict(vh.most_common(8)))
