#!/usr/bin/env python3
"""§1.1 裁决①：第2件（excluded_scope 记录级例外）+ 第3件（留痕行 + 15 条 provenance）。
L0 白名单三处：registry.excluded_scope / 台账追加 1 行 / 15 条资源记录的 provenance。"""
import json,os,re,hashlib,time,collections
L0,L1="kb/l0","kb/l1"; RUN="20260924-1700"
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def atomic(p,t):
    x=p+".tmp"; open(x,"w",encoding="utf-8").write(t); open(x,encoding="utf-8").read(); os.replace(x,p)
rows=[json.loads(l) for l in open(f"{L0}/manifest.jsonl",encoding="utf-8") if l.strip()]
lat={}
for r in rows: lat[r["resource_key"]]=r
T=[r for r in lat.values() if r.get("matched_rule")=="R15" and r["status"]=="restored"]
T.sort(key=lambda x:x["resource_key"])
assert len(T)==15, len(T)
print("15 条:",len(T))
before_rows=sum(1 for l in open(f"{L0}/manifest.jsonl",encoding="utf-8") if l.strip())

# ---------- 第2件：excluded_scope 加记录级例外 ----------
REG=f"{L0}/registry/kb.json"; reg=json.load(open(REG,encoding="utf-8"))
prev=json.dumps(reg["excluded_scope"],ensure_ascii=False)
reg["excluded_scope_prev"]=json.loads(prev)
reg["excluded_scope"]={
 "tables":["规则库"],
 "policy":"整体不纳入：不登记资源、不进库目录、不进 index；既有存量登记为 retracted",
 "reason":"用户口径：「全部」不包含规则库，连存量一起清",
 "by_rule_state":"R6–R10 已 enabled=false，规则库记录不会再兜底进 unknown",
 "since":"20260924-1000",
 "archived_to":"kb/l0/_archive/rulelib-excluded-20260924-1000",
 "archived_resource_count":16,
 "record_level_exceptions":[
   {"rule":"R15","matched_rule":"R15","pattern":"来源链接","field_id":"fld1VehxHe",
    "kb_type":"external_standard","resource_count":15,
    "semantics":("规则库**表本体与其 50 条记录**继续整表排除；**但 R15 抽出的「来源链接」字段值（15 个唯一 URL）"
                 "正式纳入**。它们是六平台（FTC / FDA / Amazon / Google / Meta / TikTok）合规原文的 URL 锚点，"
                 "不是那 50 条记录本身（那 50 条都带 规则ID=EXT-*），也不含未确认内容。")},
   {"rule":"R16","matched_rule":"R16","pattern":"来源文档","field_id":None,
    "kb_type":"external_standard","resource_count":0,
    "semantics":"R16（来源文档）同样自本例外生效；实测当前 0 条资源，登记为**已授权但无实例**，避免下次又被整表排除误伤。"}
 ],
 "record_level_exception_basis":{"decision":"owner 2026-09-24 裁决（方案 A：15 条正式纳入）",
   "recorded_at":RUN,"note":"本例外只覆盖 R15/R16 抽出的字段值；规则库的表资源与记录仍未登记。"},
 "since_exception":RUN,
}
atomic(REG, json.dumps(reg,ensure_ascii=False,indent=1)+"\n")
print("第2件：excluded_scope 已加 record_level_exceptions")

# ---------- 第3件-1：台账追加 1 行 ----------
prov="excluded_table_source_link"
audit={"change":"restore_provenance_ratified","resource_key":f"audit:restore-provenance:{RUN}",
 "source_kind":None,"status":"audit_note","depth":0,"table_name":None,"table_id":None,"record_id":None,
 "field_name":None,"field_id":None,"entry_url":None,"path":None,"kb_type":"external_standard",
 "matched_rule":"R15","sha256":None,"sha256_input":None,"sha256_state":None,"revision":None,
 "dup_of":None,"moved_from":None,"downstream_invalidated":False,"observed_at":RUN,"scanner_version":"0.7",
 "status_reason":("15 条「来源链接」URL 于 run 20260924-1100 被 restored（retracted→restored），"
   "但该批的 changes 自述只写「新增 gone 检测能力与 schema 漂移同步；台账既有行未改」，**未记录这次生命周期变更**；"
   "owner 2026-09-24 裁决正式纳入。溯源 = 表 tblXsrMVkDNZ3oW8（规则库）的「来源链接」字段，规则 R15。"
   "本行只做留痕，不回填历史。"),
 "audit":{"defect":"lifecycle_change_unrecorded_in_changes",
  "resources":15,"restored_at_run":"20260924-1100","restored_decision":"user_decision_20260924",
  "ratified_at_run":RUN,"ratified_by":"owner 2026-09-24 裁决（方案 A）",
  "provenance_field":prov,"provenance_landed_in":["kb/l0/1_外部标准库/*.json ×15",
    "kb/l1/manifest_l1.jsonl ×15 行","kb/l1/<库目录>/*.json ×15 个"],
  "changes_self_description_was":"本批新增 gone 检测能力与 schema 漂移同步；台账既有行未改。",
  "changes_self_description_problem":("该自述**漏记**了本批把 15 条 status 由 retracted 改成 restored 这件事；"
    "changes.keys 也未列任何相关键。（严格说「台账既有行未改」在 append-only 意义上成立 —— 它是**追加** restored 新行，"
    "没有改写旧行；但「本批只做了 A 和 B」这个语义自述与事实不符。）"),
  "authorization_trace_survives_only_in":"run 20260924-1100 的 restored 行（第 2 新行）；"
    "run 20260924-1240 的 add_field_rule_eligible 重新发射时**丢掉了** restored_decision/provenance_note 等血缘字段，"
    "故只读「最新行」的消费者看不到授权依据 —— 本批的 provenance 落盘即为此补位。",
  "recovered_row_policy":"不回填历史行；只在资源记录与 L1 侧写入 provenance，并追加本行说明"}}
with open(f"{L0}/manifest.jsonl","a",encoding="utf-8") as fh:
    fh.write(json.dumps(audit,ensure_ascii=False,sort_keys=True)+"\n")
after_rows=sum(1 for l in open(f"{L0}/manifest.jsonl",encoding="utf-8") if l.strip())
print(f"第3件-1：台账 {before_rows} → {after_rows}（+{after_rows-before_rows}）")

# ---------- 第3件-2：15 条 L0 资源记录写 provenance ----------
REV=json.load(open(REG,encoding="utf-8"))["dir_map_reverse"]
def rid_of(k): return re.sub(r'[^0-9A-Za-z._\-]+','_',k.replace(":","__").replace("/","_"))[:170]
# 文件名解析：扫描库目录按「去 scheme 后的尾部」匹配（历史命名不统一：有的留 https____，有的不留）
import glob
allf={}
for d in os.listdir(L0):
    dp=f"{L0}/{d}"
    if not (os.path.isdir(dp) and d[0].isdigit()): continue
    for f in os.listdir(dp): allf[f]=f"{dp}/{f}"
def findfile(rk):
    u=rk.split(":",1)[1]; host=u.split("://",1)[-1]
    san=host.replace("/","_").rstrip("_")
    for exact in (f"url__{host.replace('/','_')}.json", f"url__{host.rstrip('/').replace('/','_')}.json"):
        if exact in allf: return allf[exact]
    # 历史命名有截断：取「最长且 san 以其为前缀」的候选，唯一才认
    cands=[(len(k)-9,v) for k,v in allf.items() if k.startswith("url__") and san.startswith(k[5:-5])]
    cands.sort(reverse=True)
    assert len(cands)==1, (rk,[c[1] for c in cands])
    return cands[0][1]
l0files=[]
for r in T:
    p=findfile(r["resource_key"])
    obj=json.load(open(p,encoding="utf-8"))
    obj["provenance"]=prov
    obj["provenance_basis"]={"decision":"owner 2026-09-24 裁决（方案 A）","ratified_at_run":RUN,
        "source":{"base":"GnRZbIuXraCzf0sGr2UcmZ62nfc","table":"tblXsrMVkDNZ3oW8（规则库）",
                  "field":"来源链接","rule":"R15"},
        "why":"六平台合规原文 URL 锚点，非那 50 条记录本身；规则库表本体与记录仍整表排除"}
    atomic(p, json.dumps(obj,ensure_ascii=False,indent=1)+"\n")
    l0files.append(p)
print("第3件-2：L0 资源记录写入 provenance:",len(l0files),"个")

# ---------- 第3件-3：L1 侧 15 条台账行 + 产物 ----------
l1=[json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl",encoding="utf-8") if l.strip()]
rids={rid_of(r["resource_key"]) for r in T}
n_man=0;n_art=0;l1man=[]
for r in l1:
    if r["resource_id"] in rids and not r.get("provenance"):
        r=dict(r); r["provenance"]=prov; n_man+=1
    l1man.append(r)
atomic(f"{L1}/manifest_l1.jsonl","".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in l1man))
arts=[]
l1f={}
for d in os.listdir(L1):
    dp=f"{L1}/{d}"
    if os.path.isdir(dp):
        for f in os.listdir(dp): l1f[f[:-5]]=f"{dp}/{f}"
for r in T:
    rid=rid_of(r["resource_key"]); p=l1f.get(rid)
    if not p: continue
    o=json.load(open(p,encoding="utf-8")); o["provenance"]=prov
    o["provenance_basis"]={"decision":"owner 2026-09-24 裁决（方案 A）","ratified_at_run":RUN}
    atomic(p,json.dumps(o,ensure_ascii=False,indent=1)+"\n"); n_art+=1; arts.append(p)
print(f"第3件-3：L1 台账行 {n_man} 条 + L1 产物 {n_art} 个 写入 provenance")

json.dump({"run_id":RUN,"verdict1":{"item1":{"restore_authorized":True,
  "decision":"user_decision_20260924（run 20260924-1100 报告 §5 件7 有完整记录）",
  "changes_self_description_inconsistent":True,
  "note":"changes 自述漏记 15 条 retracted→restored；append-only 意义上「既有行未改」成立（是追加新行）"},
  "item2":{"field":"excluded_scope.record_level_exceptions","rules":["R15","R16"],"count":15},
  "item3":{"ledger_rows_before":before_rows,"ledger_rows_after":after_rows,
           "provenance":prov,"l0_files":l0files,"l1_manifest_rows":n_man,"l1_artifacts":arts}}},
  open("kb/.work/batch15/verdict1.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
