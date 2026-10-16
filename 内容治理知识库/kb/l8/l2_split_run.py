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
# 与 L6 的尺寸护栏同值（kb/.work/l6_scope_lib.py::MAX_UNIT_CHARS）—— 切分侧与索引侧必须同一个数
MAX_UNIT_CHARS=8000
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
# ★ 2026-10-08（Owner 批准）：缺口判据**补上切分器版本**。
#   病灶：原先只看「正文 sha 有没有对应单元」⇒ **改了切分器语义也推不动重切** ——
#   实测：把 internal_sample 改成「拼接过长则按段回退」后，干跑照样报 +0，
#   因为那 8 个产物的 sha 没变、旧语义的单元还在。
#   而本 skill 登记的**幂等键本来就是三元组** `(resource_id, source_sha256, splitter_version)`
#   —— 这里把第三个分量补上，让「切分器升级」成为**可推动**的事件。
#   注意：**不会重复切**。旧行留在库，重切后 `l2_align_current.py` 按
#   「本条文本出自旧 sha 的正文」之外的路径把它退役（判据见该脚本）；且新单元 unit_id 含 vers。
#   ⚠️ 我第一版把 `SPLIT not in _cur_vers` 直接并进 gap —— 结果待重切 **822 个**资源。
#      查因：库内 splitter_version 是 `l2-0.2`（9374 个）/ `l2-0.3`（3725 个）两代并存，
#      「版本一升就全场重切」是**把 822 份正文拖下水**换 8 个修复，范围失控。**已退回。**
#   ⇒ 改成**有判据的定向重切**：只重切「现有单元**违反今天的切分不变量**」的资源 ——
#      具体就是 `internal_sample` 那条：旧语义拼出的 sample **超尺寸上限**（本轮要修的那 8 个）。
#      判据可复算、可解释、且随不变量自动收敛（修完就不再命中）。
_oversize_sample=set()
# ★ 2026-10-08（Owner 批准「两条都修」）：**同一不变量的 clause 版**。
#   病灶：`external_standard` 的语义是「逐段 → clause 单元」，而 `split_units()` 的 else 分支
#   **没有尺寸护栏** ⇒ 生产方若把整篇写成 1 个段（飞书链接类实测 13 份、最长 188,828 字），
#   就会切出 1 个巨 clause 单元 ⇒ 被 L6 的 `oversize_gt_8000` 整份挡在索引外 ⇒ 守衡检索不到。
#   实测这 13 条 = 1,754,363 字从来就没进过 L6。
#   ⇒ 改法与 sample 那条**同原理**：判据是「现有单元违反今天的切分不变量」，
#     且**窄**——只看该资源**最后一行**（units.jsonl append-only，末行即当前信念）。
#   ⚠️ 不扩到「任一单元超尺寸」：那样命中 116 个资源（实测），其中 101 个是旧切分器
#     `l2-0.2` 的遗留与 `internal_sample` 拼接超尺寸，属**另一批**，未获批准不动。
_oversize_clause=set()
_units_by_res=collections.defaultdict(list)
for u in units: _units_by_res[u["resource_id"]].append(u)
for _r,_us in _units_by_res.items():
    if not _us: continue
    # 取该资源**最后一行**（units.jsonl 是 append-only ⇒ 行序即时间序，最后一行是当前信念）
    _last=_us[-1]
    if _last.get("unit_type")=="sample" and len(_last.get("text") or "")>MAX_UNIT_CHARS:
        _oversize_sample.add(_r)
    elif _last.get("unit_type")=="clause" and len(_last.get("text") or "")>MAX_UNIT_CHARS:
        _oversize_clause.add(_r)
gap=[r for r in E if (ART[r].get("source_sha256") not in _cur_sha.get(r,set())
                      or r in _oversize_sample or r in _oversize_clause)]
_resplit_oversize=[r for r in gap if ART[r].get("source_sha256") in _cur_sha.get(r,set())]
if _resplit_oversize:
    print(f"  ⚠️ 定向重切：{len(_resplit_oversize)} 个资源（现有单元**超尺寸**，按新语义应回退成按段切）"
          f"｜其中超尺寸 sample {len(_oversize_sample)} / 超尺寸 clause {len(_oversize_clause)}")
# ---- 判定：段是否为「内容」----
def is_content(s):
    if s.get("kind")!="field_value": return True          # paragraph/image_ocr/heading/list_item = 内容
    tbl=None; r=OV.get(f"{tbl}::{s.get('field_name')}", FR.get(s.get("field_name")))
    return r=="content"
def _split_oversize_text(text, target=MAX_UNIT_CHARS):
    """把超尺寸段按行切成若干块，**逐字拼回等于原文**（`"".join` 可还原）。

    单行本身就超 target 时再按字符切（块尾不带 `\\n`，行边界块尾带 `\\n`）。
    返回值每块**已含自己的行尾分隔符**，所以调用方 `"".join(块)` 与原文逐字相同。
    """
    lines = text.split("\n")
    out, cur = [], []
    for i, line in enumerate(lines):
        if len(line) > target:
            if cur:
                out.append("\n".join(cur) + "\n")
                cur = []
            n = (len(line) + target - 1) // target
            for k in range(n):
                piece = line[k * target:(k + 1) * target]
                if k == n - 1 and i < len(lines) - 1:
                    piece += "\n"
                out.append(piece)
            continue
        if cur and sum(len(x) for x in cur) + len(line) + len(cur) > target:
            out.append("\n".join(cur) + "\n")
            cur = []
        cur.append(line)
    if cur:
        out.append("\n".join(cur))
    return out


def split_units(o):
    """按 l2_split.py 的切分器语义：content 段 → 单元。"""
    kb=o["kb_type"]; segs=[s for s in (o.get("segments") or []) if is_content(s)]
    # ★ 2026-10-08 补：视频关键帧 OCR 段也进切分。
    #   背景：视频画面文字由 `kb/l8/extract_video_keyframes.py` 抽出来，
    #   落在产物的 **独立字段** `video_ocr_segments`（每条带 `anchor=#t.MM:SS-MM:SS`，口径见
    #   `kb/l1/registry/l1.json` 的 `anchor_spec.video`）—— 单独放是为了**不把视频文本混进正文段**，
    #   但 L2 原先只读 `segments` ⇒ 视频文本**进不了库、检索不到**。这里把它一并纳入。
    for _v in (o.get("video_ocr_segments") or []):
        for _s in (_v.get("segments") or []):
            if isinstance(_s, dict) and (_s.get("text") or "").strip():
                segs.append({"kind": _s.get("kind") or "video_ocr", "text": _s["text"],
                             "anchor": _s.get("anchor") or "#t.video"})
    if not segs: return []
    out=[]
    if kb=="internal_sample":
        parts=[f"[{s['kind']}] {s['text']}" if s["kind"] in ("image_ocr","image_visual")
               else f"{s.get('field_name')}: {s['text']}" if s["kind"]=="field_value" else s["text"] for s in segs]
        txt="\n".join(p for p in parts if p)
        # ★ 2026-10-08（Owner 批准）：拼接结果**超尺寸护栏上限**时，**按段回退**。
        #   病灶：internal_sample 的语义是「整份资源聚成 1 个 sample 单元」，而体量大的资源
        #   （wiki 多段文档，实测最长 35,019 字）拼出来**天然超 8,000 字** ⇒ 被 L6 的尺寸护栏
        #   整份挡在索引外 —— **不是 SCOPE 白名单挡的**，实测这 8 个产物从来就没进过 L6。
        #   修法：仍保留「聚成 sample」语义（拼得下就还是 1 条），**只在拼不下时**按段回退，
        #   每段用**它自己的 anchor**（溯源反而更细）。**不动护栏阈值**（Amazon 帮助页那种
        #   页面脚本仍被挡：它们是 16k+ 的单段，回退也还是超限）。**不动 revision_pair**。
        if txt and len(txt) > MAX_UNIT_CHARS:
            for s in segs:
                one=(f"[{s['kind']}] {s['text']}" if s["kind"] in ("image_ocr","image_visual")
                     else f"{s.get('field_name')}: {s['text']}" if s["kind"]=="field_value" else s["text"])
                if one.strip():
                    out.append(("sample", one, s.get("anchor") or segs[0]["anchor"],
                                o.get("source",{}).get("table_name")))
        elif txt:
            out.append(("sample", txt, segs[0]["anchor"], o.get("source",{}).get("table_name")))
    else:
        for s in segs:
            ut="entry" if s["kind"]=="field_value" else "clause"
            _t=s["text"] or ""
            if len(_t) > MAX_UNIT_CHARS:
                # ★ 2026-10-08（Owner 批准）：**尺寸护栏做成「切」而不是「丢」**。
                #   病灶：本分支原先对段长**没有任何判据** ⇒ 生产方一旦把整篇写成 1 个段，
                #   这里就吐出 1 个巨 clause 单元 ⇒ 被 L6 的 `oversize_gt_8000` 静默挡在索引外
                #   （实测 13 份飞书链接、1,754,363 字从来没进过 L6）。
                #   修法：超尺寸段**按行切成 ≤ MAX_UNIT_CHARS 的块**，锚点加 `/p<n>` 序号
                #   （同一行被按字符切开时也不会撞锚点）。这是**兜底**——L1 侧已按
                #   `anchor_spec` 的 `#l.a-b` 重新分块（见 kb/l8/rechunk_l1_segments.py），
                #   此处保证「以后再有生产方写出巨段」也不会静默隐形。
                #   **不动护栏阈值**，**不动 internal_sample 的聚合语义**。
                _base=s.get("anchor") or "#正文"
                _n=0
                for _piece in _split_oversize_text(_t):
                    _n+=1
                    out.append((ut, _piece, f"{_base}/p{_n}", s.get("field_name")))
            else:
                out.append((ut,_t,s["anchor"],s.get("field_name")))
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
# ── 批次21 · 第1块：落章写 `pipeline_run_id`（编排归属）──────────────────────
# 为什么不改判据而是写这个字段：落章契约（skill_invocation_audit.py:56-61）**早就支持**
# `pipeline_run_id == <编排RUN>` 这一支，`stamp_of()` 也早就实现读它（`:186`），
# 只是**从来没人写**（实测全库 0 命中）⇒ E2 在编排 RUN 名下恒查不到落章。
# ★ 注入位置必须在 `_write_rec` **之外**：上一版注在 `os.makedirs(...)` 与
#   `json.dump(...)` 之间，把函数体劈成两半 ⇒ `return path` 掉到模块层 ⇒
#   `SyntaxError: 'return' outside function`（**副本实测抓到**，真库未受影响）。
try:
    import sys as _sm_sys, os as _sm_os
    _sm_sys.path.insert(0, _sm_os.path.join(_sm_os.path.dirname(_sm_os.path.dirname(
        _sm_os.path.dirname(_sm_os.path.abspath(__file__)))), "kb", "l7", "scripts"))
    from stamp_meta import stamp_fields as _stamp_fields
    REC.update(_stamp_fields())
except Exception as _sm_e:
    print("[warn] pipeline_run_id 未写入：%r" % (_sm_e,))
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
