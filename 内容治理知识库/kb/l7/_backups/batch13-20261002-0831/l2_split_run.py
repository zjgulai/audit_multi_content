#!/usr/bin/env python3
"""§7 L2 逐条判定 + 补切（口径 E；splitter_version=l2-0.3）。既有单元一字不动。"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import json,os,re,hashlib,collections,sys,time
L0,L1,L2="kb/l0","kb/l1","kb/l2"
_AV=list(sys.argv[1:])
def _take(flag):
    """摘取 `--flag v` / `--flag=v` 的值并从 argv 里删掉（不影响位置参数 RUN）。"""
    for i,a in enumerate(_AV):
        if a==flag and i+1<len(_AV):
            v=_AV[i+1]; del _AV[i:i+2]; return v
        if a.startswith(flag+"="):
            v=a.split("=",1)[1]; del _AV[i]; return v
    return None
# ── 落章档（2026-10-01 加）：--skill <id> = 本层**真正执行**的 skill id ──────────
# 真源 = `kb/l7/registry/layers.yaml` 本层 `skill:` 字段，**由调用者读表后传入**；
#   本脚本**不硬编码任何 skill id** —— 同一事实写两处，第二处必然过期（本库已因此返工三次）。
# 落章必须由**执行本层的进程**（就是本脚本）写，编排器不得代写：代写即 registry_echo，
#   该字段结构上不可能为假、不能当证据（判据见 kb/l7/scripts/skill_invocation_audit.py
#   的 E1/E2 与「落章契约」节）。
SKILL=_take("--skill")
# 干跑档（2026-09-29 补）：不带 --apply 只预演，**权威库**（units/index/manifest_l2）一字不写。
# 背景：本脚本原先运行即写盘 —— 一次意外的对照运行就真实改写了 units.jsonl，
#       详见 kb/l2/runs/20260929-1754-l2-unscheduled-run.json
APPLY="--apply" in _AV
# run_id 默认值改为当前时间戳（原为硬编码 "20260929-1300"，会让无参数运行冒充历史 run、provenance 无法归因）
RUN=_AV[0] if _AV and not _AV[0].startswith("--") else time.strftime("%Y%m%d-%H%M")
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
# 口径修正（2026-09-30）：缺口 = 该资源**没有当前正文的单元**。
# 原先是 `r not in U`（有没有**任何**单元行），而 units.jsonl 是 append-only、旧单元行不删，
# 于是「单元已被取代」的资源永远进不了补切名单 —— 正文被重抽、旧单元已退役的资源，
# 会在这里被当成「已覆盖」而永久漏切（本批 3 本大书正文从 20 万字补到 200 万字就是这情况）。
# 退役机制一上线，这个口径就是静默漏切的源头，故与 kb/l8/l2_staleness_audit.py 取齐。
_cur_sha=collections.defaultdict(set)
for u in units: _cur_sha[u["resource_id"]].add(u.get("source_sha256"))
gap=[r for r in E if ART[r].get("source_sha256") not in _cur_sha.get(r,set())]
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
# ── 台账 + 落章（2026-10-01 重构）────────────────────────────────────────────
# 病灶：预演路径原先在写台账**之前** sys.exit(0)（旧 :115），于是「本层引擎被跑过」在磁盘上
#   一点痕迹都没有 —— skill_invocation_audit.py 的 E2（逐层无落章）对预演恒红，
#   「--via-skill 逐层调用」这条链拿不出证据。
# 改法：预演也写**一条自己承认是预演的**台账，文件名带 `-dryrun` 后缀、记录内 dry_run=true /
#   applied=false，与真落盘台账（`<RUN>.json`）**文件名可分、字段可分**，不会被误读成执行证据。
#   权威库（units / index / manifest_l2）在预演下**仍然一字不写**。
# 落章字段 `skill`（顶层）= 调用者从 layers.yaml 读出的本层 skill id，只在本脚本被 --skill
#   显式告知时才写 —— 不猜、不默认、不从别处抄。
REC={"run_id":RUN,"gap":len(gap),"meta_closed":len(meta),"refilled":len(fixed),
 "new_units":len(NEW),"meta":meta,"fixed":fixed,
 "cov_before":{"with_segments":len(E),"with_units":len(E)-len(gap)},
 "cov_after":{"with_segments":len(E),"with_units":len(E)-len(meta)},
 "dry_run":not APPLY,"applied":bool(APPLY)}
if SKILL:
    REC["skill"]=SKILL
    REC["skill_source"]="--skill 参数（调用者读 layers.yaml 本层 skill: 后传入；本脚本不硬编码）"
def _write_rec(path):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    json.dump(REC,open(path,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    return path
if not APPLY:
    _byres=collections.defaultdict(int)
    for u in NEW: _byres[u["resource_id"]]+=1
    print(f"[dry-run] 权威库未落盘。将追加：units.jsonl +{len(NEW)} 行 / index/l2.jsonl +{len(NEW)} 行 / "
          f"manifest_l2.jsonl +{len(_byres)} 行")
    _p=_write_rec(f"kb/l2/runs/{RUN}-dryrun.json")
    print(f"[dry-run] 预演台账 → {_p}"
          + (f"（顶层 skill={SKILL}）" if SKILL else "（**未传 --skill，无落章**）")
          + f"；它只证明「本层引擎被跑过」，**不是落盘证据**（落盘台账是 kb/l2/runs/{RUN}.json，dry_run=false）")
    print("[dry-run] 要真落盘：加 --apply（本轮未加）")
    sys.exit(0)
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
_p=_write_rec(f"kb/l2/runs/{RUN}.json")
print(f"[apply] 落盘台账 → {_p}"
      + (f"（顶层 skill={SKILL}）" if SKILL else "（**未传 --skill，无落章**）"))
print("覆盖率:",len(E)-len(gap),"/",len(E),"→",len(E)-len(meta),"/",len(E))
