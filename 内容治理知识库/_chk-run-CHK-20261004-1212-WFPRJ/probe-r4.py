import json,os,hashlib,re,collections
rows=[json.loads(l) for l in open("kb/l3/candidates/rules.jsonl",encoding="utf-8") if l.strip()]
g=collections.OrderedDict()
for r in rows: g.setdefault(r["rule_id"],[]).append(r)
def head(rid):
    rs=g[rid]; return next((r for r in rs if r.get("article_no")), rs[0])
d=json.load(open("kb/view/_meta/derivation.json",encoding="utf-8"))
GOV=["owner","half_life_days","valid_until","effective_from"]
FM=re.compile(r"^---\n(.*?)\n---\n",re.S)
def fmf(fm,f):
    m=re.search(rf"^{f}:\s*(.*)$",fm,re.M)
    return (m.group(1).strip().strip('"').strip("'") if m else "")
print("== L3 行是否真带这 4 个治理字段（前 3 行）==")
for r in rows[:3]:
    print(" ",r["rule_id"],{f:r.get(f) for f in GOV})
print()
print("== 抽样对照：视图 md vs 权威库当前行 ==")
for e in d["entries"][:3]:
    rid=e["rule_id"]; p=os.path.join("kb/view",e["path"]); txt=open(p,encoding="utf-8").read()
    m=FM.match(txt); fm=m.group(1) if m else ""
    h=head(rid)
    print(f"\n-- {e['id']}  ({p})")
    print("   md-frontmatter GOV :", {f:fmf(fm,f) for f in GOV})
    print("   L3 当前行 GOV      :", {f:str(h.get(f)) if h.get(f) is not None else '' for f in GOV})
    for f in ["article_no","p_level","rule_code","risk_level","support_count","half_life_days","owner"]:
        print(f"     · {f}: md={fmf(fm,f)!r}  L3={h.get(f)!r}")
