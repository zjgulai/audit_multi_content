import json,hashlib
def h(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
reg=json.load(open("kb/l4/registry/l4.json",encoding="utf-8"))
sh=json.load(open("kb/.work/batch9/shadow_r1.json",encoding="utf-8"))
print("shadow 分布:",sh["new_kb_type_dist"],"新增单元:",sh["expected_new_units_total"])
print("canonical:",{k:(v["lines"],v["bytes"],v["sha256"]) for k,v in reg["canonical"]["files"].items()})
print("totals:",json.dumps(reg["numbering"]["totals"],ensure_ascii=False))
print("promotion status:",reg["promotion_rule"]["status"],reg["promotion_rule"]["criteria_passed"])
print("l4.json sha256:",h("kb/l4/registry/l4.json"))
for p in ("kb/l3/registry/l3.json","kb/l7/registry/l7.json","kb/view/_meta/GUIDE.md","kb/view/_meta/acceptance.yaml"):
    print(f"  {h(p)[:16]}  {p}")
