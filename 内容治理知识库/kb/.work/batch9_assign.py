#!/usr/bin/env python3
"""batch9 件1+件2：先写编号方案，再按方案分配条款号（只写 kb/l4；kb/l3 只读）。"""
import json, hashlib, collections, os, time, shutil
RUN="20260924-1320"; L4="kb/l4"
REG=f"{L4}/registry/l4.json"

def save(reg):
    """原子写：temp + os.replace。教训：json.dump 直接写目标文件，中途抛错会截断目标文件。"""
    tmp=REG+".tmp"
    with open(tmp,"w",encoding="utf-8") as fh:
        json.dump(reg,fh,ensure_ascii=False,indent=1)
    json.load(open(tmp,encoding="utf-8"))   # 先验后换
    os.replace(tmp,REG)

def load(p): return [json.loads(l) for l in open(p,encoding="utf-8") if l.strip()]
R  = load("kb/l3/candidates/rules.jsonl")
SC = load("kb/l3/candidates/sample_cases.jsonl")
CL = load("kb/l3/candidates/scoped_clauses.jsonl")
reg=json.load(open(REG,encoding="utf-8"))
old_assign=dict(reg["assignments"]); old_issued=json.loads(json.dumps(reg["numbering"]["issued"]))

# ---------------- 件1：方案（先写方案，再分配） ----------------
blocks={
 "wording":{"W-1":{"block":1,"form":"wording_entry","label":"entry（词条/命中片段型）","state":"issued_before","count":56,"range":["W-1.1","W-1.56"]},
            "W-2":{"block":2,"form":"wording_revision_pair","label":"revision_pair（修订对型）","state":"issued_before","count":453,"range":["W-2.1","W-2.453"]},
            "W-3":{"block":3,"form":"sample_case_wording_sample","label":"sample_case·措辞样本","state":"issued_this_run"},
            "W-4":{"block":4,"form":"wording_boundary","label":"boundary（边界内容型）","state":"reserved_unused"},
            "W-5":{"block":5,"form":"wording_saythis","label":"saythis（建议表达型）","state":"reserved_unused"},
            "W-6":{"block":6,"form":"wording_revision_cluster","label":"revision_cluster（修订簇型）","state":"reserved_unused"}},
 "internal_sample":{"S-1":{"block":1,"form":"sample_case_polarity","label":"sample_case·正负样本","state":"issued_this_run"},
                    "S-2":{"block":2,"form":"scoped_clause","label":"scoped_clause（限定条款型）","state":"reserved_unused"}},
 "external_standard":{"E-1":{"block":1,"form":"scoped_clause","label":"scoped_clause（限定条款型）","state":"issued_this_run"},
                      "E-2":{"block":2,"form":"clause","label":"clause（法条型）","state":"reserved_unused"}},
 "product_desc":{"P-1":{"block":1,"form":"attribute","label":"attribute（属性型）","state":"reserved_unused"}},
 "unknown":{"X-1":{"block":1,"form":"unclassified","label":"未归类（不得分配；先归类再编号）","state":"blocked_policy"}},
}
scheme={
 "scheme_version":"article-no-2",
 "defined_at_run":RUN, "defined_before_assignment":True,
 "format":"<库前缀>-<形态段>.<序号>；序号在同一 (库, 形态段) 内从 1 起连续，不跨段、不跨库连号",
 "library_prefix":{"external_standard":"E","internal_sample":"S","wording":"W","product_desc":"P","unknown":"X"},
 "prefix_library_label":{"E":"1_外部标准库","S":"2_内部正负样本库","W":"3_措辞表达库","P":"4_产品描述库","X":"9_未归类"},
 "block_by_library":blocks,
 "block_by_library_authority":"本表是本批起唯一权威分段表（含已发段与预留段）。旧 numbering.form_block（entry=1/revision_pair=2/boundary=3/saythis=4）**自本批起废止**：它是全局 form→段 映射，其 boundary=3 与 W-3 直接冲突，继续沿用会让同一段号指两个形态。旧表只作历史留痕保留，不得再用于任何新分配。",
 "order_key_per_form":{"wording_entry":["rule_id"],"wording_revision_pair":["rule_id"],
                       "sample_case_wording_sample":["case_id"],"sample_case_polarity":["case_id"],
                       "scoped_clause":["clause_id"]},
 "order_key_note":"一律用「内容派生的稳定不可变 id」升序（rule_id / case_id / clause_id）。case_id=sha1(unit_id|sample_case)[:16]，clause_id=sha1(...)[:16]，都由内容决定、与行序/时间/命中数无关；规则增删不会让已发段号错位。",
 "reserved_policy":"state=reserved_unused 的段是**预留但本批 0 条**：号码不预发、不占位，等该形态首次产出时才从 .1 起发。state=blocked_policy 的段（X-1）永不得分配 —— 未归类资源必须先归类再编号，不允许发出 X-* 号。",
 "no_reuse":"号码一经发出永久占用，不回收、不重发；重跑沿用原号。",
 "existing_numbers_frozen":True,
 "existing_numbers_note":"本批之前已发的 W-1.*（56）与 W-2.*（453）逐号沿用，一个不改、一个不重排。",
}
reg["numbering"]["scheme_version"]=scheme["scheme_version"]
reg["numbering"]["block_by_library"]=blocks
reg["numbering"]["block_by_library_authority"]=scheme["block_by_library_authority"]
reg["numbering"]["order_key_per_form"]=scheme["order_key_per_form"]
reg["numbering"]["order_key_note_per_form"]=scheme["order_key_note"]
reg["numbering"]["reserved_policy"]=scheme["reserved_policy"]
reg["numbering"]["scheme_defined_at_run"]=RUN
reg["numbering"]["form_block_retired_at_run"]=RUN
reg["numbering"]["scheme"]=scheme
save(reg)
print("件1 已写方案 → kb/l4/registry/l4.json（分段表 %d 段：已发 %d / 本批新发 %d / 预留未用 %d / 禁止 %d）"%(
  sum(len(v) for v in blocks.values()),
  sum(1 for v in blocks.values() for b in v.values() if b["state"]=="issued_before"),
  sum(1 for v in blocks.values() for b in v.values() if b["state"]=="issued_this_run"),
  sum(1 for v in blocks.values() for b in v.values() if b["state"]=="reserved_unused"),
  sum(1 for v in blocks.values() for b in v.values() if b["state"]=="blocked_policy")))

# ---------------- 件2：按方案分配 ----------------
def assign(rows,idkey,prefix,form,state_before):
    uniq=sorted({r[idkey] for r in rows})
    issued=reg["numbering"]["issued"].get(prefix,{})
    prev=issued.get("assigned") or {}
    out={}; new=0; reused=0
    for i,k in enumerate(uniq,1):
        if k in prev: out[k]=prev[k]; reused+=1
        else: out[k]=f"{prefix}.{i}"; new+=1
    seg={"library":[lib for lib,bs in blocks.items() if prefix in bs][0],
         "library_label":reg["numbering"]["prefix_library_label"][prefix[0]],
         "block":blocks[[lib for lib,bs in blocks.items() if prefix in bs][0]][prefix]["block"],
         "form":form,"change":"assign_article_no","assigned":out,"count":len(uniq),
         "rows_in_source":len(rows),"duplicate_rows_in_source":len(rows)-len(uniq),
         "range":[out[uniq[0]],out[uniq[-1]]] if uniq else [],"next_seq":len(uniq)+1,
         "block_label":blocks[[lib for lib,bs in blocks.items() if prefix in bs][0]][prefix]["label"],
         "assigned_at_run":RUN,"newly_assigned":new,"reused_from_ledger":reused}
    if state_before: seg.update(state_before)
    reg["numbering"]["issued"][prefix]=seg
    return out,seg,new,reused

w3,segW3,nw3,rw3=assign([c for c in SC if c["kb_type"]=="wording"],"case_id","W-3","sample_case_wording_sample",None)
s1,segS1,ns1,rs1=assign([c for c in SC if c["kb_type"]=="internal_sample"],"case_id","S-1","sample_case_polarity",None)
e1,segE1,ne1,re1=assign(CL,"clause_id","E-1","scoped_clause",None)
# 已发段沿用（不许重排）
reg["numbering"]["issued"]["W-1"]["assigned"]=old_issued["W-1"]["assigned"]
reg["numbering"]["issued"]["W-2"]["assigned"]=old_issued["W-2"]["assigned"]
reg["numbering"]["issued"]["W-1"]["change"]="unchanged_existing"
reg["numbering"]["issued"]["W-2"]["change"]="unchanged_existing"

# 行→条款号（同内容重复行共享同一号）
row_map={}
for r in SC: row_map[("sample_case",r["case_id"])]= (w3 if r["kb_type"]=="wording" else s1)[r["case_id"]]
for r in CL: row_map[("scoped_clause",r["clause_id"])]=e1[r["clause_id"]]
for r in R:  row_map[("rule",r["rule_id"])]=old_assign.get(r["rule_id"]) or r.get("article_no")

reg["assignments"].update({k[1]:v for k,v in row_map.items() if k[0]!="rule" and v})
pdf=sum(1 for r in R if row_map[("rule",r["rule_id"])])
tot=len(R)+len(SC)+len(CL)
uniq=len({v for v in row_map.values() if v})
reg["numbering"]["totals"]={
 "output_rows":tot,"output_rows_breakdown":{"rules":len(R),"sample_cases":len(SC),"scoped_clauses":len(CL)},
 "unique_outputs":uniq,"duplicate_rows":tot-uniq,
 "assigned_total":uniq,
 "newly_assigned_first_run":733,
 "newly_assigned_this_invocation":nw3+ns1+ne1,
 "newly_assigned_note":"733 = 20260924-1320 首跑新发（W-3 157 + S-1 201 + E-1 375）；重跑该值为 0，已发号码全部沿用 —— 这正是幂等的证据",
 "already_in_ledger_before_this_invocation":len(old_assign),
 "segments_used":sorted(reg["numbering"]["issued"].keys()),
 "libraries_used":sorted({v[0] for v in reg["numbering"]["issued"]}),
 "reserved_unused_segments":[f"{p}" for p,lib in [("W-4","wording"),("W-5","wording"),("W-6","wording"),("S-2","internal_sample"),("E-2","external_standard"),("P-1","product_desc")]],
 "X_segments":"不得分配（blocked_policy）"}
save(reg)
print("件2 W-3:%d 新发 %d | S-1:%d 新发 %d | E-1:%d 新发 %d"%(len(w3),nw3,len(s1),ns1,len(e1),ne1))
print("   输出行 %d 条 → 唯一 %d（重复行 %d）；已有 509 条沿用 %d 条未改"%(tot,uniq,tot-uniq,len(old_assign)))
print("   已发 W-1/W-2 逐号沿用:",reg["numbering"]["issued"]["W-1"]["assigned"]==old_issued["W-1"]["assigned"],
      reg["numbering"]["issued"]["W-2"]["assigned"]==old_issued["W-2"]["assigned"])
json.dump({"w3":w3,"s1":s1,"e1":e1,"row_map":{f"{k[0]}::{k[1]}":v for k,v in row_map.items()}},
          open("kb/.work/batch9/article_map.json","w"),ensure_ascii=False)
