#!/usr/bin/env python3
import json,os,re,hashlib,collections
L0,L1,L2,L3="kb/l0","kb/l1","kb/l2","kb/l3"; RUN="20260924-1730"
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def atomic(p,t):
    x=p+".tmp"; open(x,"w",encoding="utf-8").write(t); open(x,encoding="utf-8").read(); os.replace(x,p)
B=json.load(open("kb/.work/batch16/baseline_at_1730.json",encoding="utf-8"))
R2=json.load(open("kb/.work/batch16/l2_result.json",encoding="utf-8"))

# ================= §5 登记 L1 两个缺陷（只登记不修）=================
units=[json.loads(l) for l in open(f"{L2}/units.jsonl",encoding="utf-8") if l.strip()]
l1man=[json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl",encoding="utf-8") if l.strip()]
lat={}
for r in l1man: lat[r["resource_id"]]=r
idx=[json.loads(l) for l in open(f"{L1}/index/l1.jsonl",encoding="utf-8") if l.strip()]
Bset={r["resource_id"] for r in idx if r.get("resource_id")}
A={rid for rid,r in lat.items() if (r.get("segment_count") or 0)>0}
d1=sorted(A-Bset); d2=sorted(Bset-A)
ok131=[r for r in d1 if lat[r]["status"]=="ok"]
inv77=[r for r in d2 if lat[r]["status"]=="invalidated"]
reg=json.load(open(f"{L0}/registry/kb.json",encoding="utf-8"))
reg["open_issues"]=[
 {"id":"OI-L1-001","severity":"high","title":"L1 index/l1.jsonl 少 131 条有效资源的段",
  "evidence":{"index_minus_ledger":len(d1),"of_which_ok":len(ok131),
    "sample_resource_keys":[lat[r]["resource_key"] for r in ok131[:5]],
    "claimed_segments":sum(lat[r].get("segment_count") or 0 for r in ok131),
    "observed_at_of_these":"20260924-1200","kb_type":"internal_sample"},
  "impact":"L2 不受影响（splitter 读 L1 产物）；但 **L6 检索读 index → 会漏这 131 条的段**。",
  "fix_by":"L6 重建前（必须）","status":"open","recorded_at":RUN,
  "not_fixed_this_batch":{"reason":"修 index 需单独一批（本批 L1 只读）","index_sha256":B["files"]["kb/l1/index/l1.jsonl"]["sha256"]}},
 {"id":"OI-L1-002","severity":"medium","title":"L1 index/l1.jsonl 含 77 条 invalidated 残留行",
  "evidence":{"rows":len(inv77),"all_invalidated":True,
    "sample_resource_keys":[lat[r]["resource_key"] for r in inv77[:5]],
    "cause":"上游 gone 记录撤回后，L1 台账标 invalidated，但 index 行未同步移除"},
  "impact":"检索会召回已失效内容。","fix_by":"L6 重建前（必须）","status":"open","recorded_at":RUN,
  "not_fixed_this_batch":{"reason":"同上","index_sha256":B["files"]["kb/l1/index/l1.jsonl"]["sha256"]}}]
reg["open_issues_note"]="只登记不修：修 L1 index 属越界（本批 L1 只读），应单独一批。"
atomic(f"{L0}/registry/kb.json", json.dumps(reg,ensure_ascii=False,indent=1)+"\n")
for p,rows in ((f"{L0}/manifest.jsonl",None),(f"{L1}/manifest_l1.jsonl",None)):
    with open(p,"a",encoding="utf-8") as fh:
        fh.write(json.dumps({"change":"register_l1_index_defects","resource_key":f"audit:l1-index-defects:{RUN}",
          "source_kind":None,"status":"audit_note","depth":0,"observed_at":RUN,"scanner_version":"0.7",
          "kb_type":None,"matched_rule":None,"entry_url":None,"path":None,"record_id":None,"field_name":None,
          "field_id":None,"sha256":None,"sha256_input":None,"sha256_state":None,"revision":None,"dup_of":None,
          "moved_from":None,"downstream_invalidated":False,"table_id":None,"table_name":None,
          "rule_eligible":None,"rule_eligible_source":None,"rule_eligible_run":None,
          "status_reason":f"登记 L1 两个缺陷（OI-L1-001 少 131 条有效段 / OI-L1-002 含 77 条 invalidated 残留行）；"
            f"**本批未修**，详见 kb/l0/registry/kb.json 的 open_issues。index 哈希 {B['files']['kb/l1/index/l1.jsonl']['sha256'][:16]} 未变。"},
          ensure_ascii=False,sort_keys=True)+"\n")
print("§5 登记完成：OI-L1-001 / OI-L1-002；L0 台账与 L1 台账各 +1 行")

# ================= 9_未归类 处置（只登记结论，不改 kb_type）=================
UNK=[]
for d in ("9_未归类",):
    for f in sorted(os.listdir(f"{L0}/{d}")):
        UNK.append(f)
print("9_未归类 目录项:",len(UNK))
unk_rows=[]
for f in UNK:
    rid=f[:-5]
    r=lat.get(rid) or {}
    kind=r.get("source_kind"); kt=r.get("kb_type"); st=r.get("status")
    if r.get("record_id"):
        concl="记录级：源侧「知识库分类=其它」→ R5 兜底 unknown（按规则求值结果，**不动**）"
    elif kind=="feishu_bitable_table": concl="表骨架：容器，按既有口径 unknown（不动）"
    elif kind=="feishu_bitable_base": concl="Base 基座：容器，按既有口径 unknown（不动）"
    elif kind=="feishu_file": concl="附件文件：无分类字段可求值 → 保持 unknown（不动）；补分类需 L0 批改判"
    elif kind=="feishu_doc": concl="docx：源侧无分类字段 → 保持 unknown（不动）"
    else: concl="无归属依据 → 保持 unknown"
    unk_rows.append({"file":f,"resource_id":rid,"source_kind":kind,"kb_type":kt,"status":st,"conclusion":concl})
cc=collections.Counter(x["conclusion"] for x in unk_rows)
print("9_未归类 逐条结论:",dict(cc))

# ================= L3：对账 + 新增单元显式拒绝 =================
def load(p): return [json.loads(l) for l in open(p,encoding="utf-8") if l.strip()]
R=load(f"{L3}/candidates/rules.jsonl"); SC=load(f"{L3}/candidates/sample_cases.jsonl")
CL=load(f"{L3}/candidates/scoped_clauses.jsonl"); RJ=load(f"{L3}/rejected.jsonl")
def ev(r):
    s=set()
    for e in (r.get("evidence_units") or []):
        if isinstance(e,dict) and e.get("unit_id"): s.add(e["unit_id"])
    for k in ("unit_ids","unit_id"):
        v=r.get(k)
        if isinstance(v,str): s.add(v)
        elif isinstance(v,list): s.update(x for x in v if isinstance(x,str))
    return s
prod=set()
for r in R+SC+CL: prod |= ev(r)
rej={r["unit_id"] for r in RJ if r.get("unit_id")}
ALL={u["unit_id"] for u in units}
newids={u["unit_id"] for u in units if u.get("splitter_version_backfilled_at") is None and u["resource_id"] in {x["resource_id"] for x in R2["fixed"]}}
newids={u["unit_id"] for u in units if u["resource_id"] in {x["resource_id"] for x in R2["fixed"]}}
only_p=ALL&prod-rej; only_r=ALL&rej-prod; both=prod&rej; none=ALL-prod-rej
print(f"\nL3 对账（输入 {len(ALL)}）: 只产出 {len(only_p)} | 只拒绝 {len(only_r)} | 既产出又拒绝 {len(both)} | 两者都无 {len(none)}")
# 新增单元显式拒绝
NEWREJ=[]
for u in units:
    if u["unit_id"] in newids and u["unit_id"] not in prod and u["unit_id"] not in rej:
        NEWREJ.append({"kind":"unit","unit_id":u["unit_id"],"resource_id":u["resource_id"],
          "kb_type":u["kb_type"],"unit_type":u["unit_type"],"form":"none",
          "reason":("§8.4 本批 L2 新增单元：显式拒绝（非静默）。源为 L1 产物的 "
                    +("正文段（paragraph/image_ocr）" if u["unit_type"]!="entry" else "内容角色字段值")
                    +"；其源资源为 URL 正文/新登记子资源，尚未过 L3 的逐条承载判据 → 本批不产出、显式记拒绝，留待蒸馏批。"),
          "rejected_at":RUN,"batch":RUN})
if NEWREJ:
    with open(f"{L3}/rejected.jsonl","a",encoding="utf-8") as fh:
        for r in NEWREJ: fh.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n")
print("L3 新增显式拒绝:",len(NEWREJ))
RJ2=load(f"{L3}/rejected.jsonl"); rej2={r["unit_id"] for r in RJ2 if r.get("unit_id")}
only_p=ALL&prod-rej2; only_r=ALL&rej2-prod; both=prod&rej2; none=ALL-prod-rej2
ident=(len(only_p)+len(only_r)+len(both)+len(none)==len(ALL)) and not (only_p&only_r) and not (only_p&both) and not (only_r&both)
print(f"补后对账: 只产出 {len(only_p)} | 只拒绝 {len(only_r)} | 既产出又拒绝 {len(both)} | 两者都无 {len(none)} | 恒等 {ident} | 两者都无==0 {len(none)==0}")
json.dump({"run_id":RUN,"open_issues":["OI-L1-001","OI-L1-002"],
 "l2":{"gap":377,"meta_closed":41,"refilled":336,"new_units":336,
       "cov_before":[1026,1403],"cov_after":[1362,1403],"meta_detail":R2["meta"]},
 "unknown_dir":unk_rows,
 "l3":{"input":len(ALL),"only_produced":len(only_p),"only_rejected":len(only_r),
       "both":len(both),"neither":len(none),"identity":bool(ident),"new_explicit_rejects":len(NEWREJ),
       "external_recovery":"375 → 375（本批未做）","support_count_1":"447 → 447（本批未标）"},
 "writes":{"l0_manifest":"+1","l1_manifest":"+1","l1_index":"未变","l2_units":"+336","l3_rejected":"+%d"%len(NEWREJ)}},
 open("kb/.work/batch16/final.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
