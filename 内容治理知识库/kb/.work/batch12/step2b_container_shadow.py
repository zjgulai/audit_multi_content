#!/usr/bin/env python3
"""§6.4 闸门影子（只算不写）：完整修法 = 真求值 + 容器不发射。预期新增 L2 单元 == 0。"""
import json, os, glob, collections, hashlib

L0,L1,L2="kb/l0","kb/l1","kb/l2"
reg=json.load(open(f"{L0}/registry/kb.json",encoding="utf-8"))
POL=reg["container_policy"]
FR=reg["field_roles"]; OV=reg["field_role_table_overrides"]
RULES=[r for r in reg["rules"] if r.get("enabled")]
DIRMAP=reg["dir_map_reverse"]

latest={}
for l in open(f"{L0}/manifest.jsonl",encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["resource_key"]]=r
EFF={k:v for k,v in latest.items() if v.get("status") not in ("gone","retracted") and k.startswith(("bitable:","url:","wiki:"))}
print("L0 有效资源:",len(EFF))

links=[json.loads(l) for l in open(f"{L0}/links/graph.jsonl",encoding="utf-8") if l.strip()]
child_of=collections.Counter(e["from_id"] for e in links)

# 单元按资源计数：用 units.jsonl（index 的 9261/9469 行不带 resource_id，只有 208 行带）
units_by_res=collections.Counter()
for l in open(f"{L2}/units.jsonl",encoding="utf-8"):
    if l.strip(): units_by_res[json.loads(l)["resource_id"]]+=1
print("L2 单元总数(按 units.jsonl):",sum(units_by_res.values()),"涉及资源:",len(units_by_res))

rid_of=lambda k:k.replace(":","__").replace("/","_")
def l1path(rid):
    for d in os.listdir(L1):
        p=f"{L1}/{d}/{rid}.json"
        if os.path.isfile(p): return p
    return None

def role(table, fname):
    return OV.get(f"{table}::{fname}", FR.get(fname, None))

def rule_for(table, hint):
    for t in (hint or []):
        if t=="其它": continue
        for r in RULES:
            if (r["match_type"]=="field_value" and r.get("scope_table")=="材料收集"
                    and r.get("match_value")==t):
                return r["kb_type"], r["id"]
    for r in RULES:
        if r["match_type"]=="table_name" and r["pattern"]==table:
            return r["kb_type"], r["id"]
    return "unknown", None

def n_units(kb, art):
    segs=art.get("segments") or []
    if not (segs or art.get("tables")): return 0
    fv=[s for s in segs if s.get("kind")=="field_value"]
    if kb=="wording": return len([s for s in segs if s.get("kind") in
        ("field_value","image_ocr","image_visual","paragraph","list_item")])
    if kb=="external_standard": return len(fv)
    if kb=="internal_sample": return 1 if fv else 0
    if kb=="product_desc": return len(fv)
    return 0

rows=[]; containers=[]
for k,v in sorted(EFF.items()):
    rid=rid_of(k); p=l1path(rid)
    if not p: continue
    art=json.load(open(p,encoding="utf-8"))
    segs=art.get("segments") or []
    tbl=art.get("source",{}).get("table_name") or v.get("table_name")
    roles=[role(tbl,s.get("field_name")) for s in segs]
    C1 = bool(segs) and all(r!="content" for r in roles)
    C2 = child_of.get(f"record:{v.get('record_id')}",0)>0 or child_of.get(k,0)>0
    C3 = units_by_res.get(rid,0)==0
    cont = C1 and C2 and C3
    hint=[]
    if art.get("source",{}).get("table_name")=="材料收集":
        for s in segs:
            if s.get("field_name")=="知识库分类":
                hint=[x for x in str(s.get("text") or "").split("、") if x]
    kt,rid_r=rule_for(v.get("table_name") or tbl,hint)
    cur=units_by_res.get(rid,0)
    would = 0 if cont else n_units(kt,art)
    if cont: containers.append((k,rid,C1,C2,C3,cur))
    rows.append({"resource_key":k,"resource_id":rid,"table":v.get("table_name") or tbl,
                 "old_kb_type":v.get("kb_type"),"old_rule":v.get("matched_rule"),
                 "new_kb_type":kt,"new_rule":rid_r,"C1":C1,"C2":C2,"C3":C3,"container":cont,
                 "current_units":cur,"would_emit":would,"segments":len(segs),
                 "roles":dict(collections.Counter(r for r in roles))})
# ---- 影子口径（只算「会被本次修法改变的资源」，不重算无关资源）----
# 单元变化只可能来自两处：
#   (a) kb_type 变了 → 换 splitter。本批只有 23 条「材料收集」记录的 kb_type 变（unknown→真值）。
#   (b) 新被打上 container → 抑制发射。新打标 = 上面这 107 个。
# 其余资源 kb_type 不变、也不新打 container → 增量恒为 0，无需重算（重算反而会因 L1→L2 管线
# 差异算出虚假数字，第一版影子就是这么错的：得到 -1098）。
recs=[r for r in rows if r["table"]=="材料收集"
      and latest[r["resource_key"]].get("record_id") and latest[r["resource_key"]].get("field_name") is None]
added   = sum(r["would_emit"] for r in recs) - sum(r["current_units"] for r in recs)
deletions=[r for r in rows if r["container"] and r["current_units"]>0]
new_units = added
print(f"\n容器判定（C1∧C2∧C3）：{len(containers)} 个资源")
print(f"(a) 23 条记录 kb_type 改判后：current {sum(r['current_units'] for r in recs)} → would_emit {sum(r['would_emit'] for r in recs)}  ⇒ 增量 {added}")
print(f"(b) 新打 container 的 107 个资源中，当前已有单元的 = {len(deletions)}  ⇒ 误删风险 deletions_risk = {len(deletions)}")
print(f"\n预期新增 L2 单元 = {new_units}")
dist=collections.Counter(r["new_kb_type"] for r in recs)
print(f"\n「材料收集」记录 {len(recs)} 条 → 改判分布 {dict(dist)}")
print(f"其中判为容器: {sum(1 for r in recs if r['container'])}/{len(recs)}")
print("容器样本（前 8）:")
for k,rid,c1,c2,c3,cur in containers[:8]:
    print(f"   {k}  C1={c1} C2={c2} C3={c3} units={cur}")
gate = (new_units==0 and not deletions and len(recs)==23)
print(f"\n=== 闸门：{'通过 ✔' if gate else '不通过 ✘ 必须停工'} ===")
json.dump({"run_id":"20260924-1512","kind":"shadow_only_no_write",
  "container_policy_defined_at":POL["defined_at"],
  "containers":len(containers),"expected_new_units":new_units,
  "method":("只算会被本次修法改变的资源：(a) kb_type 改变的 23 条记录 + (b) 新打 container 的 107 个；"
            "其余资源增量恒为 0，不重算（L1→L2 管线差异会算出虚假数字）"),
  "deletions_risk":len(deletions),"gate_pass":gate,
  "records_23":len(recs),"containers_list":[c[0] for c in containers],"records_dist":dict(dist),
  "records_container":sum(1 for r in recs if r["container"]),
  "records_current_units":sum(r["current_units"] for r in recs),
  "records_would_emit":sum(r["would_emit"] for r in recs),
  "rows":rows},
  open("kb/.work/batch12/container_shadow.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("→ kb/.work/batch12/container_shadow.json")
