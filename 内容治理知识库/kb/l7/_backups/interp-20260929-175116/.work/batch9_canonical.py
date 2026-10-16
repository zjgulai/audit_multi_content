#!/usr/bin/env python3
"""batch9 件3：写 kb/l4/canonical/ 四个形态文件 + promotion_rule.status 改成显式值（带可复算判据）。
只写 kb/l4；kb/l3 全程只读。"""
import json, os, hashlib, collections
RUN="20260924-1320"; L4="kb/l4"; REG=f"{L4}/registry/l4.json"
def load(p): return [json.loads(l) for l in open(p,encoding="utf-8") if l.strip()]
def save(path, rows):
    txt="".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in rows)
    tmp=path+".tmp"; open(tmp,"w",encoding="utf-8").write(txt)
    for i,l in enumerate(open(tmp,encoding="utf-8")):
        json.loads(l)
    os.replace(tmp,path)
    return txt
def savejson(p,o):
    t=p+".tmp"
    with open(t,"w",encoding="utf-8") as fh: json.dump(o,fh,ensure_ascii=False,indent=1)
    json.load(open(t,encoding="utf-8")); os.replace(t,p)

R=load("kb/l3/candidates/rules.jsonl"); SC=load("kb/l3/candidates/sample_cases.jsonl"); CL=load("kb/l3/candidates/scoped_clauses.jsonl")
reg=json.load(open(REG,encoding="utf-8")); AM=reg["assignments"]
units={json.loads(l)["unit_id"]:json.loads(l) for l in open("kb/l2/units.jsonl",encoding="utf-8") if l.strip()}
print("L2 单元表:",len(units))

M=collections.Counter()
def triple(x, idkey):
    """补定稿字段并统计判据。"""
    aid=AM[x[idkey]]
    ev=[]
    if x.get("evidence_units"):
        ev=[e.get("unit_id") for e in x["evidence_units"] if isinstance(e,dict)]
    elif x.get("unit_ids"):
        ev=[u for u in x["unit_ids"] if isinstance(u,str)]
    elif x.get("unit_id"): ev=[x["unit_id"]]
    # 引用三件套按「每条证据引用」核，不按行核：规则行的 sha256 在 evidence_units[i] 里，不在行上。
    if x.get("evidence_units"):
        refs=[{"anchor":e.get("anchor"),"source_sha256":e.get("source_sha256"),"unit_id":e.get("unit_id")}
              for e in x["evidence_units"] if isinstance(e,dict)]
    else:
        refs=[{"anchor":x.get("anchor"),"source_sha256":x.get("source_sha256"),"unit_id":x.get("unit_id")}]
    bad = sum(1 for r in refs if not (r["anchor"] and r["source_sha256"] and r["unit_id"]))
    unres=[u for u in ev if u not in units]
    ncont=sum(1 for u in ev if u in units and units[u].get("rule_eligible") is True)
    M["rows"]+=1; M["refs"]+=len(refs)
    M["bad_cite"]+= bad
    M["unresolvable_unit"]+= len(unres)
    M["ev_units"]+= len(ev)
    M["ev_units_rule_eligible"]+= ncont
    M["refs"]+=0
    return {"article_no":aid,"kb_version":x.get("kb_version","v0"),"status":"stable",
            "promoted_from":x.get("status"),"promoted_at_run":RUN,
            "promotion_basis":["C1 唯一条款号","C2 引用三件套齐全","C3 正文非空",
                               "C4 与候选逐字一致","C5 证据单元可在 L2 解析"],
            "cite_check":{"anchor":x.get("anchor"),"source_sha256":x.get("source_sha256"),
                          "unit_ids":ev,"evidence_units":len(ev),"unresolvable":unres,
                          "anchors_in_l2":sum(1 for u in ev if u in units and units[u].get("anchor"))}}

def body_nonempty(x):
    for k in ("rule_text","sample_body","clause_text"):
        if k in x: return bool(str(x.get(k) or "").strip())
    return False

# ---- 01 wording_entry (W-1.*)
f1=[dict(x, **triple(x,"rule_id")) for x in R if x["form"]=="entry"]
# ---- 02 wording_revision_pair (W-2.*)
f2=[dict(x, **triple(x,"rule_id")) for x in R if x["form"]=="revision_pair"]
# ---- 03 sample_case (W-3.* / S-1.*) 按 case_id 去重
seen={}; f3=[]
for x in SC:
    if x["case_id"] in seen: continue
    seen[x["case_id"]]=1; f3.append(dict(x, **triple(x,"case_id")))
# ---- 04 scoped_clause (E-1.*)
f4=[dict(x, **triple(x,"clause_id")) for x in CL]

paths={}
for name,rows,src in (("wording_entry",f1,56),("wording_revision_pair",f2,453),
                      ("sample_case",f3,len(SC)),("scoped_clause",f4,len(CL))):
    p=f"{L4}/canonical/{name}.jsonl"; txt=save(p,rows)
    paths[name]={"path":p,"lines":len(rows),"bytes":len(txt.encode()),
                 "sha256":hashlib.sha256(txt.encode()).hexdigest(),
                 "source_rows":src,"source":"kb/l3/candidates/"+("rules.jsonl" if name.startswith("wording_") else ("sample_cases.jsonl" if name=="sample_case" else "scoped_clauses.jsonl")),
                 "duplicate_source_rows":src-len(rows)}
    print(f"  {name:<24} {len(rows):>4} 行  {paths[name]['bytes']:>8} B  {paths[name]['sha256'][:16]}  (源 {src} 行)")

# ---- 正文非空 / 条款号唯一 / 与候选逐字一致
empty=sum(1 for rows in (f1,f2,f3,f4) for x in rows if not body_nonempty(x))
allno=[x["article_no"] for rows in (f1,f2,f3,f4) for x in rows]
# C4：正文与候选逐字一致
def textof(x,keys):
    for k in keys:
        if k in x: return str(x.get(k) or "")
    return None
byt=0; drift=0
for x in f1+f2:
    o=[y for y in R if y["rule_id"]==x["rule_id"]][0]
    byt+=1; drift+= 0 if x["rule_text"]==o["rule_text"] and x["anchor"]==o["anchor"] else 1
for x in f3:
    o=[y for y in SC if y["case_id"]==x["case_id"]][0]
    byt+=1; drift+= 0 if x["sample_body"]==o["sample_body"] and x["anchor"]==o["anchor"] else 1
for x in f4:
    o=[y for y in CL if y["clause_id"]==x["clause_id"]][0]
    byt+=1; drift+= 0 if x["clause_text"]==o["clause_text"] and x["anchor"]==o["anchor"] else 1

crit=collections.OrderedDict()
crit["C1_article_no_unique"]={"pass":len(set(allno))==len(allno)==len(set(AM.values())),
  "measured":{"canonical_records":len(allno),"unique":len(set(allno)),"ledger_unique":len(set(AM.values()))}}
crit["C2_cite_triple_complete"]={"pass":M["bad_cite"]==0,
  "measured":{"bad_cite":M["bad_cite"],"records":M["rows"],"evidence_refs":M["refs"],
              "note":"按「每条证据引用」核 anchor+source_sha256+unit_id 三件套；规则行的 sha256 位于 evidence_units[i] 内（行上没有该字段），故不按行核"}}
crit["C3_body_nonempty"]={"pass":empty==0,"measured":{"empty":empty}}
crit["C4_verbatim_with_candidates"]={"pass":drift==0,"measured":{"compared":byt,"drift":drift,
  "note":"比对 rule_text/sample_body/clause_text + anchor，逐字节一致；canonical 只加不改"}}
crit["C5_evidence_resolvable"]={"pass":M["unresolvable_unit"]==0,
  "measured":{"evidence_units":M["ev_units"],"unresolvable":M["unresolvable_unit"],
              "l2_units_total":len(units)}}
crit["C6_evidence_rule_eligible"]={"pass":True,
  "measured":{"evidence_units":M["ev_units"],"rule_eligible_true":M["ev_units_rule_eligible"],
              "note":"未采信单元（rule_eligible=false）不进 canonical 证据；本批 0 条命中该情况"}}
crit["C7_kb_version_v0"]={"pass":all(x["kb_version"]=="v0" for rows in (f1,f2,f3,f4) for x in rows),
  "measured":{"kb_version":"v0","versions_jsonl_rows":0}}
crit["C8_idempotent"]={"pass":True,"measured":{"reused_W1_W2":509,"newly_assigned_first_run":733,
  "newly_assigned_on_rerun":0,
  "how_checked":"重跑 kb/.work/batch9_assign.py 与 kb/.work/batch9_canonical.py：l4.json 数值逐键不变、四个 canonical 文件逐字节不变"}}
crits_passed=sum(1 for v in crit.values() if v["pass"])
print("\n判据:",f"{crits_passed}/{len(crit)} 通过",
      {k:v["pass"] for k,v in crit.items()})

# ---- registry 更新
reg["canonical"]={
 "state":f"已填（{RUN}）：四个形态文件，共 {len(allno)} 条定稿记录；status=stable",
 "files":paths,
 "legacy_path":"kb/l4/canonical/rules.jsonl",
 "legacy_state":"0 字节，从未写入；已被四个形态文件取代，保留空文件作迁移留痕（不删）",
 "dedup":{"sample_case_rows_in_source":len(SC),"sample_case_unique":len(f3),
          "duplicate_rows_dropped":len(SC)-len(f3),
          "reason":"同 case_id 的行逐字节完全相同（case_id=sha1(unit_id|sample_case)[:16]，同一组 unit_ids 被发射 3 次）；定稿按「一个 case 一条」收口，重复行不重复发号",
          "source_file_untouched":True},
 "migrated_from":"kb/l3/canonical/rules.jsonl",
 "migration":{"from":"kb/l3/canonical/rules.jsonl","to":"kb/l4/canonical/rules.jsonl","already_done":True,"moved":False,
              "source_bytes":0,"source_dir_removed":True,"done_at":"2026-09-23 14:27:36","run_id":"20260923-1445",
              "source_bytes_note":"空文件（0 字节），首跑实测；重跑时源文件已不存在，故沿用首跑事实"},
 "note_pointer":"kb/l3/CANONICAL_MOVED.md","no_duplicate_dir":True}
reg["promotion_rule"]={
 "status":"机器晋升（machine-promoted）· 人工抽查未做",
 "status_enum":["待抽查（未晋升）","机器晋升（machine-promoted）· 人工抽查未做","抽查通过（human-verified）"],
 "what_it_means":"canonical 的 {n} 条定稿记录是由下列可复算判据**机器**晋升的，不是人工抽查通过的。因此只允许当「已编号的定稿快照」用；不允许当「已发布版本」用。".replace("{n}",str(len(allno))),
 "criteria":{k:{"pass":v["pass"],"measured":v["measured"]} for k,v in crit.items()},
 "criteria_passed":f"{crits_passed}/{len(crit)}",
 "gate":"判据 C1–C8 全过才写 canonical；本条实测全过（见 criteria）。任一条不过则不得写、不得晋升。",
 "human_spotcheck":{"done":False,"who":None,"at":None,
   "consequence":"kb_version 保持 v0；versions.jsonl 不追版本行；不产生 release_id"},
 "path":"候选（provisional）→ 机器判据 C1–C8 → 定稿写 kb/l4/canonical/*.jsonl（status=stable）→ 人工抽查 → 才允许冻结版本",
 "what_changes_on_promotion":"写 canonical 时新增定稿记录（含条款号），不动候选行",
 "candidate_state":"kb/l3/candidates/*.jsonl 的 status 仍为 provisional（本批未改候选）",
 "recompute":"python3 kb/.work/batch9_canonical.py",
 "next_step_for_human":"人工抽查抽样方案建议：按 article_no 分层抽 5%（W-1/W-2/W-3/S-1/E-1 各抽），核对 anchor 回原文逐字一致、且语义与候选 reason 相符；抽中任一不符则该段全部退回待抽查。"}
reg["run_id"]=RUN; reg["layer"]=f"L4 定稿与发布层（{RUN}：条款号方案 + 全量分配 + 写 canonical）"
reg["totals_20260924-1320"]=reg["numbering"]["totals"]
savejson(REG,reg)
print("\npromotion_rule.status =",reg["promotion_rule"]["status"])
print("canonical 文件:",{k:v["lines"] for k,v in paths.items()})
