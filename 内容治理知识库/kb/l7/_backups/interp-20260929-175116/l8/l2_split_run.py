#!/usr/bin/env python3
"""§7 L2 逐条判定 + 补切（口径 E；splitter_version=l2-0.3）。既有单元一字不动。"""
import json,os,re,hashlib,collections,sys
L0,L1,L2="kb/l0","kb/l1","kb/l2"
RUN=sys.argv[1] if len(sys.argv)>1 else "20260929-1300"
SPLIT="l2-0.3"
def sha(t): return hashlib.sha256(t.encode()).hexdigest()
def uid(*p): return hashlib.sha1("|".join(str(x) for x in p).encode()).hexdigest()[:20]
reg=json.load(open(f"{L0}/registry/kb.json",encoding="utf-8")); OV,FR=reg["field_role_table_overrides"],reg["field_roles"]
l1=[json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl",encoding="utf-8") if l.strip()]
lat={}
for r in l1: lat[r["resource_id"]]=r
units=[json.loads(l) for l in open(f"{L2}/units.jsonl",encoding="utf-8") if l.strip()]
U={u["resource_id"] for u in units}
ART={}
for d in os.listdir(L1):
    dp=f"{L1}/{d}"
    if not (os.path.isdir(dp) and d[0].isdigit()): continue
    for f in os.listdir(dp):
        if f.endswith(".json"):
            try: ART[f[:-5]]=json.load(open(f"{dp}/{f}",encoding="utf-8"))
            except Exception: pass
E=[rid for rid,o in ART.items() if o.get("segments") and lat.get(rid,{}).get("status") not in ("invalidated","retracted")]
gap=[r for r in E if r not in U]
# ---- 判定：段是否为「内容」----
def is_content(s):
    if s.get("kind")!="field_value": return True          # paragraph/image_ocr/heading/list_item = 内容
    tbl=None; r=OV.get(f"{tbl}::{s.get('field_name')}", FR.get(s.get("field_name")))
    return r=="content"
def split_units(o):
    """按 l2_split.py 的切分器语义：content 段 → 单元。"""
    kb=o["kb_type"]; segs=[s for s in (o.get("segments") or []) if is_content(s)]
    if not segs: return []
    out=[]
    if kb=="internal_sample":
        parts=[f"[{s['kind']}] {s['text']}" if s["kind"] in ("image_ocr","image_visual")
               else f"{s.get('field_name')}: {s['text']}" if s["kind"]=="field_value" else s["text"] for s in segs]
        txt="\n".join(p for p in parts if p)
        if txt: out.append(("sample",txt,segs[0]["anchor"],o.get("source",{}).get("table_name")))
    else:
        for s in segs:
            ut="entry" if s["kind"]=="field_value" else "clause"
            out.append((ut,s["text"],s["anchor"],s.get("field_name")))
    return out
meta=[]; fixed=[]; NEW=[]
for rid in gap:
    o=ART[rid]; kt=o["kb_type"]; ssha=o.get("source_sha256"); l0=lat.get(rid,{})
    got=split_units(o)
    if not got:
        meta.append({"resource_id":rid,"kb_type":kt,"segments":len(o["segments"]),
                     "reason":"全部段的字段角色 role != 'content' → 按口径不切，闭合",
                     "kinds":dict(collections.Counter(s["kind"] for s in o["segments"]))})
        continue
    for i,(ut,txt,anc,hp) in enumerate(got,1):
        NEW.append({"unit_id":uid(SPLIT,rid,ssha or "",ut,anc,"",i),"resource_id":rid,"kb_type":kt,
          "source_sha256":ssha,"text":txt,"char_count":len(txt or ""),"anchor":anc,
          "unit_type":ut,"heading_path":hp,"order_in_parent":i,"parent_unit_id":None,"pair_ref":None,
          "meta":{"kind":"field_value" if ut=="entry" else "paragraph","field_name":hp},
          "splitter_version":SPLIT,"splitter_version_backfilled_at":None,"rule_eligible":l0.get("rule_eligible",True),
          "rule_eligible_run":l0.get("rule_eligible_run",RUN),
          "rule_eligible_source":l0.get("rule_eligible_source","not_material_collection")})
    fixed.append({"resource_id":rid,"kb_type":kt,"units":len(got),
                  "reason":"该有单元却没切 → 补切（既有 splitter 语义，l2-0.3）"})
print(f"待判 {len(gap)} → 元数据闭合 {len(meta)} / 补切 {len(fixed)}（新增单元 {len(NEW)}）")
# 既有 units.jsonl 的 schema 按 unit_type 不同（entry/clause 17 键；sample 多 8 键；attribute 多 4 键）。
# 逐类型对齐：同类既有单元的键并集 = 该类新增单元应有的键集。
BYT=collections.defaultdict(set)
for u in units: BYT[u.get("unit_type")] |= set(u)
print("既有 unit_type → 键数:",{k:len(v) for k,v in BYT.items()})
for u in NEW:
    want=BYT.get(u["unit_type"])
    assert want, f"新类型 {u['unit_type']} 在既有单元里没有先例"
    NEW[NEW.index(u)]={k:u.get(k) for k in want}
if NEW:
    with open(f"{L2}/units.jsonl","a",encoding="utf-8") as fh:
        for u in NEW: fh.write(json.dumps(u,ensure_ascii=False,sort_keys=True)+"\n")
    with open(f"{L2}/index/l2.jsonl","a",encoding="utf-8") as fh:
        for u in NEW: fh.write(json.dumps({"anchor":u["anchor"],"char_count":u["char_count"],
            "kb_type":u["kb_type"],"source_sha256":u["source_sha256"],"unit_id":u["unit_id"]},
            ensure_ascii=False,sort_keys=True)+"\n")
    byres=collections.defaultdict(int)
    for u in NEW: byres[u["resource_id"]]+=1
    with open(f"{L2}/manifest_l2.jsonl","a",encoding="utf-8") as fh:
        for rid,n in byres.items():
            o=ART[rid]
            fh.write(json.dumps({"kb_type":o["kb_type"],"observed_at":RUN,"resource_id":rid,
              "result":"split","source_sha256":o.get("source_sha256"),"splitter_version":SPLIT,
              "unit_count":n},ensure_ascii=False,sort_keys=True)+"\n")
print("units.jsonl 行数:",sum(1 for l in open(f"{L2}/units.jsonl",encoding="utf-8") if l.strip()))
json.dump({"run_id":RUN,"gap":len(gap),"meta_closed":len(meta),"refilled":len(fixed),
 "new_units":len(NEW),"meta":meta,"fixed":fixed,
 "cov_before":{"with_segments":len(E),"with_units":len(E)-len(gap)},
 "cov_after":{"with_segments":len(E),"with_units":len(E)-len(meta)}},
 open(f"kb/l2/runs/{RUN}.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("覆盖率:",len(E)-len(gap),"/",len(E),"→",len(E)-len(meta),"/",len(E))
