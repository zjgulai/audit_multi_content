#!/usr/bin/env python3
"""batch9 件6：幂等 + 对账 + 越权核查。"""
import json,os,hashlib,collections,subprocess
B=json.load(open("kb/.work/batch9_baseline.json",encoding="utf-8"))
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def lines(p): return sum(1 for l in open(p,encoding="utf-8") if l.strip())

print("=== 1. 基线未动的文件（l0/l1/l2 全部 + l3 候选与台账）===")
untouched=["kb/l0/manifest.jsonl","kb/l0/index/l0.jsonl","kb/l1/manifest_l1.jsonl","kb/l1/index/l1.jsonl",
 "kb/l2/manifest_l2.jsonl","kb/l2/index/l2.jsonl","kb/l3/manifest_l3.jsonl","kb/l3/candidates/rules.jsonl",
 "kb/l3/candidates/sample_cases.jsonl","kb/l3/candidates/scoped_clauses.jsonl","kb/l3/rejected.jsonl"]
drift=0
for f in untouched:
    b=B["files"][f]; now=sha(f)
    ok = now==b["sha256"] and lines(f)==b["lines"]
    drift += 0 if ok else 1
    print(f"  {'OK ' if ok else 'DRIFT'} {f}  {b['lines']} 行 {b['sha256'][:12]} → {lines(f)} 行 {now[:12]}")
print("  漂移文件数:",drift)

print("\n=== 2. 条款号覆盖：missing / duplicate ===")
reg=json.load(open("kb/l4/registry/l4.json",encoding="utf-8")); AM=reg["assignments"]
def load(p): return [json.loads(l) for l in open(p,encoding="utf-8") if l.strip()]
R=load("kb/l3/candidates/rules.jsonl"); SC=load("kb/l3/candidates/sample_cases.jsonl"); CL=load("kb/l3/candidates/scoped_clauses.jsonl")
rows=[("rule",r["rule_id"]) for r in R]+[("sample",c["case_id"]) for c in SC]+[("clause",c["clause_id"]) for c in CL]
missing=[k for _,k in rows if not AM.get(k)]
print("  候选行:",len(rows),"  取不到号码的行(missing):",len(missing))
inv=collections.defaultdict(set)
for t,k in rows: inv[AM.get(k)].add(k)
dup={a:ks for a,ks in inv.items() if a and len(ks)>1}
print("  一个号码发给多个 id(duplicate):",len(dup))
# 内容层面：同号的行内容是否逐字相同
byt=collections.defaultdict(set)
for x in SC: byt[AM[x["case_id"]]].add(json.dumps(x,sort_keys=True,ensure_ascii=False))
for x in CL: byt[AM[x["clause_id"]]].add(json.dumps(x,sort_keys=True,ensure_ascii=False))
for x in R:  byt[AM[x["rule_id"]]].add(json.dumps(x,sort_keys=True,ensure_ascii=False))
nc={a:s for a,s in byt.items() if len(s)>1}
print("  同号但内容不同的(真冲突):",len(nc))
print("  唯一号码数:",len({v for v in AM.values() if v}),"  台账里的号码数:",len(set(AM.values())))

print("\n=== 3. 已发 W-1/W-2 漂移 ===")
art=json.load(open("kb/.work/l4_article.json",encoding="utf-8"))["mapping"]
same=all(AM.get(k)==v for k,v in art.items())
print("  509 条与 20260923-1445 台账逐号一致:",same,"  不一致条数:",sum(1 for k,v in art.items() if AM.get(k)!=v))

print("\n=== 4. canonical 三件套与正文 ===")
tot=0;bad=0;miss=0
for name in ("wording_entry","wording_revision_pair","sample_case","scoped_clause"):
    for l in open(f"kb/l4/canonical/{name}.jsonl",encoding="utf-8"):
        x=json.loads(l); tot+=1
        if not x.get("article_no"): miss+=1
        refs=([{"a":e.get("anchor"),"s":e.get("source_sha256"),"u":e.get("unit_id")} for e in x["evidence_units"]]
              if x.get("evidence_units") else [{"a":x.get("anchor"),"s":x.get("source_sha256"),"u":x.get("unit_id")}])
        bad+=sum(1 for r in refs if not(r["a"] and r["s"] and r["u"]))
print(f"  canonical 记录 {tot}  无条款号 {miss}  引用三件套不全(bad_cite) {bad}")

print("\n=== 5. 版本纪律 ===")
v=[json.loads(l) for l in open("kb/versions/versions.jsonl",encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
print("  versions.jsonl 版本行:",len(v),"  kb_version:",set(x.get("kb_version") for x in R)|{reg["kb_version"]})
print("  canonical 全为 v0:",all(json.loads(l)["kb_version"]=="v0" for n in ("wording_entry","wording_revision_pair","sample_case","scoped_clause") for l in open(f"kb/l4/canonical/{n}.jsonl",encoding="utf-8")))
print("\n漂移 %d / missing %d / duplicate %d / 真冲突 %d"%(drift,len(missing),len(dup),len(nc)))
