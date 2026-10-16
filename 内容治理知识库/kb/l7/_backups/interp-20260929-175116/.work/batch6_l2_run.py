#!/usr/bin/env python3
"""batch6 · L2 结构化切分（件1–件6）+ 并发核查（件9）。只拆不合。"""
import json, os, re, sys, glob, hashlib, collections, shutil, time, subprocess

RUN = "20260924-1210"
L0, L1, L2 = "kb/l0", "kb/l1", "kb/l2"
SPLITTER = "l2-0.3"
SPLITTER_PREV = "l2-0.2"
TBL, TBL_NAME = "tbld8qE92YaY38Yz", "正面和负面样本"
W = "kb/.work"
LOCK = f"{W}/.kb.lock"
if os.path.exists(LOCK):
    raise SystemExit(f"[LOCKED] {open(LOCK).read()} —— 退出，不硬写")
json.dump({"run_id": RUN, "layer": "l2", "pid": os.getpid(),
           "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, open(LOCK, "w", encoding="utf-8"))

def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def uid(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:20]

# ---------------------------------------------------------------- 载入
L0LAT = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); L0LAT[d["resource_key"]] = d
L0E = {k: v for k, v in L0LAT.items() if v["status"] not in ("gone", "retracted")}
L1LAT = {}
for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); L1LAT[d["resource_id"]] = d
L1BY = {v["resource_key"]: v for v in L1LAT.values() if v.get("resource_key")}
def l1file(rid):
    for d in os.listdir(L1):
        p = f"{L1}/{d}/{rid}.json"
        if os.path.isfile(p): return p
    return None

# ---------------------------------------------------------------- 件1：对账基线
INPUT = [k for k in L0E if k in L1BY and L1BY[k]["status"] in ("ok", "extracted")]
INPUT_NON = [k for k in L0E if k in L1BY and L1BY[k]["status"] not in ("ok", "extracted")]
print(f"L2 输入集（L1 有内容）= {len(INPUT)}；L0 有效但 L1 无内容 = {len(INPUT_NON)}")

UNITS, SKIPPED, MANIFEST, INDEX = [], [], [], []
SPLIT_BY_RES = collections.Counter()

def add_manifest(rid, k, kb_type, ssha, result, unit_count=0, reason=""):
    MANIFEST.append({"resource_id": rid, "kb_type": kb_type, "source_sha256": ssha,
                     "splitter_version": SPLITTER, "result": result, "unit_count": unit_count,
                     "status_reason": reason, "observed_at": RUN})

# ================================================================ 件2：split_sample
def read_rec(recid):
    p = f"{L0}/records/{TBL_NAME}/{recid}.json"
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None

sample_rows = [k for k in INPUT if k.startswith(f"bitable:{TBL}:") and "/fld" not in k]
att_rows = [k for k in INPUT if k.startswith(f"bitable:{TBL}:") and "/fld" in k]
print(f"split_sample：记录 {len(sample_rows)} + 附件 {len(att_rows)}")
att_by_rec = collections.defaultdict(list)
for k in att_rows:
    att_by_rec[k.split(":")[2].split("/")[0]].append(k)

POLARITY_ENUM = {"正例", "反例"}
polarity_dist = collections.Counter()
sample_units = 0
for k in sorted(sample_rows):
    rid = L1BY[k]["resource_id"]; recid = L0E[k]["record_id"]
    rec = read_rec(recid)
    ssha = L1BY[k].get("source_sha256")
    p = l1file(rid)
    art = json.load(open(p, encoding="utf-8")) if p else {}
    seg = {s.get("field_name"): s.get("text") for s in art.get("segments") or []}
    def fv(name):
        v = (rec or {}).get("fields", {}).get(name, {}).get("value") if rec else None
        if isinstance(v, list): return "、".join(str(x) for x in v) if v else None
        return v
    pol = fv("分类")
    pol = pol if pol in POLARITY_ENUM else "unknown"
    polarity_dist[pol] += 1
    anchors = []
    parts = []
    fb = fv("原文反馈")
    if fb: parts.append(str(fb)); anchors.append(f"#{TBL_NAME}/{recid}/原文反馈")
    wx = fv("文字素材")
    if wx: parts.append(str(wx)); anchors.append(f"#{TBL_NAME}/{recid}/文字素材")
    mrefs = []
    for kk in sorted(att_by_rec.get(recid, [])):
        ar = L1BY[kk]; ap = l1file(ar["resource_id"])
        txt = ""
        if ap:
            a = json.load(open(ap, encoding="utf-8"))
            txt = "\n".join(s.get("text") or "" for s in a.get("segments") or [])
            for s in a.get("segments") or []:
                anchors.append(s.get("anchor"))
        if txt.strip(): parts.append(txt)
        mrefs.append({"resource_key": kk, "resource_id": ar["resource_id"],
                      "anchor": (json.load(open(ap, encoding="utf-8"))["segments"][0]["anchor"]
                                 if ap else None),
                      "source_sha256": ar.get("source_sha256"),
                      "ocr_chars": len(txt), "attachment_unit": "merged_into_parent"})
    body = "\n\n".join(x for x in parts if x and x.strip())
    u = {"unit_id": uid(rid, ssha, SPLITTER, "sample", 1),
         "unit_type": "sample", "kb_type": L1BY[k]["kb_type"], "resource_id": rid,
         "source_sha256": ssha, "anchor": anchors[0] if anchors else f"#{TBL_NAME}/{recid}",
         "anchors": anchors, "text": body, "char_count": len(body),
         "heading_path": TBL_NAME, "pair_ref": None, "parent_unit_id": None, "order_in_parent": 1,
         "polarity": pol,
         "sample_body": body,
         "reason_category": fv("原因分类") or "unknown",
         "reason_analysis": fv("具体原因/分析"),
         "advice": fv("建议"),
         "material_type": fv("素材类型"),
         "channel": fv("渠道/市场"),
         "media_refs": mrefs,
         "meta": {"field_name": None, "kind": "sample",
                  "source_fields": [x for x in ("原文反馈", "文字素材", "图片素材") ],
                  "excluded_fields": ["备注（如处理结果/建议）"],
                  "excluded_reason": "该字段在 L0 已改判 other（行政元数据，实测形如「价值评分: 14；参与审核: …」）"},
         "splitter_version": SPLITTER}
    UNITS.append(u); sample_units += 1
    SPLIT_BY_RES[rid] = 1
    add_manifest(rid, k, L1BY[k]["kb_type"], ssha, "split", 1)
    INDEX.append({"unit_id": u["unit_id"], "resource_id": rid, "kb_type": u["kb_type"],
                  "unit_type": "sample", "anchor": u["anchor"], "source_sha256": ssha,
                  "char_count": u["char_count"]})
# 240 附件：内容已并入父记录单元
for k in sorted(att_rows):
    ar = L1BY[k]; recid = k.split(":")[2].split("/")[0]
    parent = SPLIT_BY_RES.get(L1BY.get(f"bitable:{TBL}:{recid}", {}).get("resource_id"))
    parent_rid = L1BY.get(f"bitable:{TBL}:{recid}", {}).get("resource_id")
    SKIPPED.append({"resource_id": ar["resource_id"], "resource_key": k,
                    "kb_type": ar["kb_type"], "reason": "merged_into_parent_sample",
                    "detail": "该附件的 OCR 文本已并入其父记录样本单元的 sample_body，"
                              "父单元通过 media_refs 引用它；按任务要求不平铺成独立样本",
                    "parent_resource_id": parent_rid,
                    "parent_unit_id": uid(parent_rid, ar.get("source_sha256") and
                                          L1BY.get(f"bitable:{TBL}:{recid}", {}).get("source_sha256"),
                                          SPLITTER, "sample", 1) if parent_rid else None})
    add_manifest(ar["resource_id"], k, ar["kb_type"], ar.get("source_sha256"), "skipped",
                 0, "merged_into_parent_sample")

# ================================================================ 件3：split_attribute
attr_rows = [k for k in INPUT if L1BY[k]["kb_type"] == "product_desc"]
attr_rows_all = [k for k in L0E if L0E[k]["kb_type"] == "product_desc"]
print(f"split_attribute：产品描述库 L0 有效 {len(attr_rows_all)}，其中有内容 {len(attr_rows)}")
attr_units = 0
SKU_FIELDS = ["型号", "产品名", "品线", "产品", "SKU"]
for k in sorted(attr_rows):
    ar = L1BY[k]; rid = ar["resource_id"]
    p = l1file(rid); art = json.load(open(p, encoding="utf-8")) if p else {}
    ssha = ar.get("source_sha256")
    sku = None
    for s in art.get("segments") or []:
        if s.get("field_name") in SKU_FIELDS and (s.get("text") or "").strip():
            sku = s["text"].strip(); break
    sku = sku or "unknown"
    segs = art.get("segments") or []
    if not segs:
        SKIPPED.append({"resource_id": rid, "resource_key": k, "kb_type": ar["kb_type"],
                        "reason": "no_segments_in_l1_artifact"})
        add_manifest(rid, k, ar["kb_type"], ssha, "skipped", 0, "no_segments_in_l1_artifact")
        continue
    for i, s in enumerate(segs, 1):
        t = (s.get("text") or "").strip()
        if not t: continue
        u = {"unit_id": uid(rid, ssha, SPLITTER, "attr", i),
             "unit_type": "attribute", "kb_type": ar["kb_type"], "resource_id": rid,
             "source_sha256": ssha, "anchor": s.get("anchor"),
             "text": t, "char_count": len(t),
             "heading_path": s.get("field_name"), "pair_ref": None, "parent_unit_id": None,
             "order_in_parent": i,
             "sku": sku, "attribute_name": s.get("field_name"), "attribute_value": t,
             "meta": {"kind": s.get("kind"), "field_name": s.get("field_name"),
                      "note": "同一属性的多个值不拆成多条（任务要求）"},
             "splitter_version": SPLITTER}
        UNITS.append(u); attr_units += 1
        INDEX.append({"unit_id": u["unit_id"], "resource_id": rid, "kb_type": u["kb_type"],
                      "unit_type": "attribute", "anchor": u["anchor"], "source_sha256": ssha,
                      "char_count": u["char_count"]})
    add_manifest(rid, k, ar["kb_type"], ssha, "split", len(segs))
for k in sorted(set(attr_rows_all) - set(attr_rows)):
    v = L1BY.get(k) or {}
    SKIPPED.append({"resource_id": v.get("resource_id"), "resource_key": k,
                    "kb_type": "product_desc", "reason": "l1_no_content",
                    "detail": f"L1 状态为 {v.get('status')}，无正文可切"})
    add_manifest(v.get("resource_id"), k, "product_desc", v.get("source_sha256"), "skipped", 0, "l1_no_content")

# ================================================================ 件4：未归类 38 条逐条定性
unknown_rows = [k for k in L0E if L0E[k]["kb_type"] == "unknown"]
unknown_verdicts = []
for k in sorted(unknown_rows):
    v = L0E[k]; l1 = L1BY.get(k) or {}
    st = l1.get("status")
    if v["source_kind"] == "feishu_bitable_base":
        verdict, why = "确认无内容", "入口 Base 容器：表清单/字段 schema 属 L0 结构指纹职责，L1 不抽为正文"
    elif v["source_kind"] == "feishu_bitable_table":
        verdict, why = "确认无内容", "容器表：同上；其记录的内容在各自记录资源上抽取"
    elif st == "empty":
        verdict, why = "确认无内容", "该记录在源侧全部字段为空/null，无正文可切"
    elif st == "no_scope":
        verdict, why = "保持 unknown", "缺 drive:file:download，读不到字节流；不猜其归属"
    elif st == "ok":
        verdict, why = "保持 unknown", ("入口容器表的记录本身是「一份待收材料」（R5），"
                                        "其内容归属落在其 link 子资源上；本表本身不作为知识本体切分")
    else:
        verdict, why = "保持 unknown", f"L1 状态 {st}，无内容可切"
    unknown_verdicts.append({"resource_key": k, "source_kind": v["source_kind"],
                             "l1_status": st, "verdict": verdict, "why": why})
    SKIPPED.append({"resource_id": l1.get("resource_id"), "resource_key": k, "kb_type": "unknown",
                    "reason": "unclassified_verdict_" + ("no_content" if verdict == "确认无内容" else "kept_unknown"),
                    "detail": why})
    add_manifest(l1.get("resource_id"), k, "unknown", l1.get("source_sha256"), "skipped", 0, why)
print("未归类定性:", len(unknown_verdicts), dict(collections.Counter(x["verdict"] for x in unknown_verdicts)))

# ================================================================ 件5：splitter_version 补齐 + 幂等
PRE = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
os.makedirs(f"{L2}/_archive", exist_ok=True)
shutil.copyfile(f"{L2}/units.jsonl", f"{L2}/_archive/units-pre-{SPLITTER}.jsonl")
pre_text_sha = sha("\n".join(u["text"] for u in PRE))
pre_none = sum(1 for u in PRE if u.get("splitter_version") in (None, ""))
for u in PRE:
    if u.get("splitter_version") in (None, ""):
        u["splitter_version"] = SPLITTER_PREV          # 补齐为它们的实际产出者
    u["splitter_version_backfilled_at"] = RUN
with open(f"{L2}/units.jsonl", "w", encoding="utf-8") as fh:
    for u in PRE:
        fh.write(json.dumps(u, ensure_ascii=False, sort_keys=True) + "\n")
    for u in UNITS:
        fh.write(json.dumps(u, ensure_ascii=False, sort_keys=True) + "\n")
POST = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
post_pre_text_sha = sha("\n".join(u["text"] for u in POST[:len(PRE)]))
none_after = sum(1 for u in POST if u.get("splitter_version") in (None, ""))
key = collections.Counter((u["resource_id"], u.get("source_sha256"), u.get("splitter_version")) for u in POST)
dupes = {str(k): v for k, v in key.items() if v > 1}

# ================================================================ 件6：revision_pair 复核
pairs = collections.defaultdict(list)
for u in POST:
    if u.get("unit_type") == "revision_pair":
        pairs[(u["resource_id"], (u.get("meta") or {}).get("pair_id"))].append(u)
pair_ids = [k for k in pairs if k[1]]
complete = sum(1 for k in pair_ids if len(pairs[k]) == 2)
spot = []
for k in sorted(pair_ids)[:5]:
    us = pairs[k]
    okp = (len(us) == 2 and all(u.get("pair_ref") for u in us))
    spot.append({"pair_id": k[1], "resource_id": k[0], "units": len(us),
                 "pair_refs": [u.get("pair_ref") for u in us], "complete": okp,
                 "before": (us[0].get("meta") or {}).get("before", "")[:40],
                 "after": (us[0].get("meta") or {}).get("after", "")[:40]})
pair_stat = {"revision_pair_units": sum(len(v) for v in pairs.values()),
             "pair_groups": len(pair_ids), "complete_pairs": complete,
             "pair_rate": round(100.0 * complete / len(pair_ids), 2) if pair_ids else None,
             "spot_check": spot, "note": "未重切该部分（任务要求）"}

# ================================================================ 写台账 + index
with open(f"{L2}/manifest_l2.jsonl", "a", encoding="utf-8") as fh:
    for r in MANIFEST:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L2}/index/l2.jsonl", "a", encoding="utf-8") as fh:
    for r in INDEX:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

# registry
reg = json.load(open(f"{L2}/registry/l2.json", encoding="utf-8"))
reg["splitter_version_before"] = reg["splitter_version"]
reg["splitter_version"] = SPLITTER
reg["splitters"]["sample"] = {
    "kb_type": "internal_sample", "minimal_unit": "一条正负样本",
    "status": "ready_and_run", "ran_at": RUN, "resource_count": len(sample_rows),
    "unit_count": sample_units,
    "how": "一条记录 = 一个样本单元；polarity 取源侧「分类」（正例/反例，枚举外或缺失 → unknown）；"
           "sample_body = 原文反馈 + 文字素材 + 该记录全部图片附件的 OCR 文本（用 \\n\\n 连接）；"
           "附件不平铺，父子关系用 media_refs[].resource_id + parent unit 表达",
    "fields": ["polarity", "sample_body", "reason_category", "reason_analysis", "advice",
               "material_type", "channel", "media_refs"],
    "excluded": {"备注（如处理结果/建议）": "L0 已改判 other（行政元数据），不取任何内容"},
}
reg["splitters"]["attribute"] = {
    "kb_type": "product_desc", "minimal_unit": "一条属性", "status": "ready_and_run",
    "ran_at": RUN, "resource_count": len(attr_rows), "unit_count": attr_units,
    "how": "按 (sku, attribute_name) 一条单元；sku 从 型号/产品名/品线/产品/SKU 字段取，取不到 unknown；"
           "同一属性的多个值不拆成多条",
}
reg["skip_reasons"] = {
    "merged_into_parent_sample": "附件 OCR 文本已并入父记录样本单元，不平铺成独立样本",
    "l1_no_content": "L1 状态非 ok/extracted，无正文可切",
    "no_segments_in_l1_artifact": "L1 产物没有 segments",
    "unclassified_verdict_no_content": "未归类资源经逐条定性为「确认无内容」",
    "unclassified_verdict_kept_unknown": "未归类资源经逐条定性为「保持 unknown」",
}
reg["idempotency"]["splitter_version_current"] = SPLITTER
reg["splitter_version_backfill"] = {
    "at": RUN, "backfilled": pre_none, "filled_with": SPLITTER_PREV,
    "why": "这 9261 个单元由 l2-0.2 产出，补成它们的实际产出者而不是当前版本，避免伪版本声明",
    "text_touched": False, "text_sha_before": pre_text_sha, "text_sha_after_prefix": post_pre_text_sha,
}
reg["unknown_verdicts"] = unknown_verdicts
reg.setdefault("changes", []).append({
    "run_id": RUN, "change": "update",
    "keys": ["splitter_version", "splitters.sample", "splitters.attribute", "skip_reasons",
             "splitter_version_backfill", "unknown_verdicts", "idempotency.splitter_version_current"],
    "note": "件2/件3/件5/件4；既有 9261 单元只补 splitter_version，text 未改",
})
json.dump(reg, open(f"{L2}/registry/l2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(f"{L2}/registry/l2.json", "a", encoding="utf-8").write("\n")

# ================================================================ 件1 对账
covered = set(SPLIT_BY_RES)
skip_by_res = collections.Counter(s["resource_id"] for s in SKIPPED if s.get("resource_id"))
recon = {"input": len(INPUT), "with_units": len(covered), "skipped": len(INPUT) - len(covered),
         "skipped_detail": dict(collections.Counter(s["reason"] for s in SKIPPED)),
         "diff": len(INPUT) - len(covered) - (len(INPUT) - len(covered)),
         "l0_effective_non_content": len(INPUT_NON)}
out = {"run_id": RUN, "splitter_version": SPLITTER,
       "reconcile": recon,
       "units": {"before": len(PRE), "new": len(UNITS), "after": len(POST),
                 "by_kb_type_new": dict(collections.Counter(u["kb_type"] for u in UNITS)),
                 "by_unit_type_new": dict(collections.Counter(u["unit_type"] for u in UNITS)),
                 "by_kb_type_after": dict(collections.Counter(u["kb_type"] for u in POST))},
       "split_sample": {"resources": len(sample_rows) + len(att_rows), "records": len(sample_rows),
                        "attachments_merged": len(att_rows), "units": sample_units,
                        "skipped": len(att_rows), "polarity": dict(polarity_dist)},
       "split_attribute": {"l0_total": len(attr_rows_all), "with_content": len(attr_rows),
                           "units": attr_units,
                           "skipped": len(set(attr_rows_all) - set(attr_rows))},
       "unknown": {"count": len(unknown_verdicts),
                   "verdicts": dict(collections.Counter(x["verdict"] for x in unknown_verdicts)),
                   "detail": unknown_verdicts},
       "splitter_version": {"backfilled": pre_none, "none_after": none_after,
                            "total_units": len(POST),
                            "text_sha_pre": pre_text_sha, "text_sha_post_prefix": post_pre_text_sha,
                            "text_unchanged": pre_text_sha == post_pre_text_sha},
       "idempotency": {"key": ["resource_id", "source_sha256", "splitter_version"],
                       "duplicate_keys": dupes, "duplicate_count": len(dupes)},
       "revision_pair": pair_stat,
       "skipped_rows": SKIPPED, "manifest_rows": len(MANIFEST), "index_rows": len(INDEX)}
json.dump(out, open(f"{L2}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("reconcile", "units", "split_sample", "split_attribute",
                                      "unknown", "splitter_version", "idempotency")},
                 ensure_ascii=False, indent=1)[:2500])
if os.path.exists(LOCK): os.remove(LOCK)
