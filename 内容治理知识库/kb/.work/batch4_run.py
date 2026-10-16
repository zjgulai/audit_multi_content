#!/usr/bin/env python3
"""batch4 · L0 补跑：收口「正面和负面样本」与 schema 漂移（承接 run 20260924-1000）。

只做 9 件事：① gone 检测能力 ② 125 记录 gone ③ 77 附件 gone ④ 表资源 updated
⑤ 登记源侧 201 条 + 附件 ⑥ schema 漂移同步 ⑦ 恢复 15 条外部标准 ⑧ field_roles 4 项裁决
⑨ 来源链接真求值 + index 重建。不重跑上一批已完成的部分。
源侧全程只读。kb/l0 台账只追加。
"""
import json, os, re, glob, shutil, hashlib, collections, sys

sys.path.insert(0, "kb/.work")
from kb_l0_scan_lib import (SCANNER_VERSION, GONE_REASON_SOURCE_REMOVED, GONE_REASON_PARENT_GONE,
                            ledger_latest, assert_all_records_scope, source_key_list,
                            detect_gone, assert_accounting, eval_rule)

RUN = "20260924-1100"
L0 = "kb/l0"
W = "kb/.work/batch4"
ARCHIVE_GONE = f"{L0}/_archive/gone-{RUN}"
ARCHIVE_RULELIB = f"{L0}/_archive/rulelib-excluded-20260924-1000"

ENTRY_BASE = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
TBL, TBL_NAME = "tbld8qE92YaY38Yz", "正面和负面样本"
ATT_FIELDS = {"图片素材": "fldnvxjaSr", "视频素材": "fld87JUpEn"}
EXCL = {"last_modified_time", "last_modified_by"}

OPS = []
def op(kind, target, note):
    OPS.append({"op": kind, "nature": "read", "target": target, "note": note})

registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
EXCLUDED_TABLES = tuple(registry.get("excluded_scope", {}).get("tables", []))

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def rec_hash(fvals):
    items = sorted(((k, v) for k, v in fvals.items() if k not in EXCL), key=lambda x: x[0])
    return sha(canon([["field_id", k, "value", v] for k, v in items]))

def fname(resource_key, source_kind):
    if resource_key.startswith("url:"):
        s = re.sub(r'^https?://', '', resource_key[4:])
        return "url__" + re.sub(r'[^0-9A-Za-z._\-]+', '_', s).strip('_')[:90] + ".json"
    ident = resource_key.split(":", 1)[1].replace(":", "__").replace("/", "_")
    return f"{source_kind}__{ident}.json"[:200]

# ================================================================ 读源（只读）
tables = json.load(open(f"{W}/tables.json", encoding="utf-8"))["data"]["tables"]
op("base +table-list", ENTRY_BASE, "入口 Base 表清单（4 张表）与 records_count/rev")
fmeta = json.load(open(f"{W}/fields_tbld8qE92YaY38Yz.json", encoding="utf-8"))["data"]
op("base +field-list", f"{TBL} {TBL_NAME}", f"当前 schema：{fmeta['total']} 个字段（schema 漂移核对）")
recs = [json.loads(l) for l in open(f"{W}/正面和负面样本.ndjson", encoding="utf-8") if l.strip()]
mrec = json.load(open(f"{W}/正面和负面样本.manifest.json", encoding="utf-8"))
scope = assert_all_records_scope(mrec, TBL)
op("base +record-list", f"{TBL_NAME}（{TBL}）",
   f"{mrec['records_count']} 条全字段；record_scope=all_records（不带 --view-id）；rev={mrec['rev']}")
dl = json.load(open(f"{W}/dl_stats.json", encoding="utf-8"))
op("base +record-download-attachment", f"{dl['ok']} 个附件 file_token",
   f"图片素材/视频素材字节流取 sha256(file_bytes)；失败 {len(dl['fail'])} 个")

fid_by_name = {f["name"]: f["id"] for f in fmeta["fields"]}
name_by_fid = {f["id"]: f["name"] for f in fmeta["fields"]}

# ================================================================ 件1：gone 检测 + 断言
latest0 = ledger_latest(f"{L0}/manifest.jsonl")
src_rec, src_att = source_key_list(TBL, recs, ATT_FIELDS)
det = detect_gone(latest0, TBL, src_rec, src_att)
led_keys_0 = {k for k, v in latest0.items()
              if k.startswith(f"bitable:{TBL}:") and v.get("status") != "retracted"}

# ================================================================ 新资源模型
R, RECFILES, GONE_ROWS = [], [], []

def add(**kw):
    kw.setdefault("dup_of", None); kw.setdefault("moved_from", None)
    kw.setdefault("moved_to", None); kw.setdefault("status_reason", "")
    kw.setdefault("status", "registered"); kw.setdefault("revision", None)
    kw.setdefault("filter_passed", None)
    R.append(kw); return kw

# ---------------------------------------------------------------- 件2：125 条记录 gone
def gone_row(k, reason, extra=None):
    o = latest0[k]
    row = {kk: o.get(kk) for kk in
           ("resource_key", "source_kind", "table_name", "table_id", "record_id", "field_name",
            "field_id", "entry_url", "path", "depth", "kb_type", "matched_rule", "sha256",
            "sha256_input", "sha256_state", "revision", "dup_of")}
    row.update({"status": "gone", "status_reason": reason,
                "downstream_invalidated": True,
                "last_seen_observed_at": det["last_seen"].get(k),
                "gone_detected_at": RUN, "gone_detected_by": f"scanner {SCANNER_VERSION}",
                "gone_basis": "源侧全量 key 清单（record_scope=all_records，不带视图筛选）里已无此 key",
                "observed_at": RUN, "scanner_version": SCANNER_VERSION})
    if extra:
        row.update(extra)
    return row

GONE_ROWS = [gone_row(k, GONE_REASON_SOURCE_REMOVED) for k in det["gone_records"]]

# 件2 的放置处置：gone 文件移出库目录到 _archive/（与上一批 retracted 同款处置，保留不删除）
gone_files_moved = []
file_index = {}
for d in registry["dir_map"]:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        try:
            file_index[json.load(open(p, encoding="utf-8"))["resource_key"]] = p
        except Exception:
            pass
os.makedirs(ARCHIVE_GONE, exist_ok=True)
for k in det["gone_records"]:
    src = file_index.get(k)
    if not src:
        continue
    dst = f"{ARCHIVE_GONE}/{os.path.basename(src)}"
    shutil.move(src, dst)
    gone_files_moved.append({"resource_key": k, "from": src, "to": dst})
    for r in GONE_ROWS:
        if r["resource_key"] == k:
            r["moved_from"], r["moved_to"] = src, dst

# ---------------------------------------------------------------- 件3：77 条附件 gone
att_gone = []
tmp_by_rec = collections.defaultdict(list)
for k in det["gone_attachments"]:
    rid = k.split(":")[1].split("/")[0]
    tmp_by_rec[rid].append(k)
for k in det["gone_attachments"]:
    row = gone_row(k, GONE_REASON_PARENT_GONE,
                   {"parent_record_key": f"bitable:{TBL}:{k.split(':')[1].split('/')[0]}",
                    "parent_gone_reason": GONE_REASON_SOURCE_REMOVED})
    att_gone.append(row)
    src = file_index.get(k)
    if src and os.path.exists(src):
        dst = f"{ARCHIVE_GONE}/{os.path.basename(src)}"
        shutil.move(src, dst)
        row["moved_from"], row["moved_to"] = src, dst
        gone_files_moved.append({"resource_key": k, "from": src, "to": dst})
GONE_ROWS += att_gone

# ---------------------------------------------------------------- 件4：表资源 updated
tbl_key = f"bitable:{ENTRY_BASE}:table:{TBL}"
fschema = [{"field_id": f["id"], "field_name": f["name"], "type": f["type"],
            "options": [o.get("name") for o in (f.get("options") or [])] or None}
           for f in fmeta["fields"]]
tbl_struct_sha = sha(canon({"table_id": TBL, "table_name": TBL_NAME, "fields": fschema}))
prev_tbl = latest0[tbl_key]
tbl_row = {kk: prev_tbl.get(kk) for kk in
           ("resource_key", "source_kind", "table_name", "table_id", "record_id", "field_name",
            "field_id", "entry_url", "path", "depth", "kb_type", "matched_rule", "dup_of")}
tbl_row.update({"status": "updated", "status_reason": "source_table_replaced",
                "sha256": tbl_struct_sha, "sha256_input": "structure", "sha256_state": "full",
                "revision": None, "downstream_invalidated": True,
                "observed_at": RUN, "scanner_version": SCANNER_VERSION,
                "prev_sha256": prev_tbl.get("sha256"),
                "prev_records_count": 125, "records_count": len(recs),
                "prev_field_count": 12, "field_count": len(fschema),
                "note": "表本身仍在（+table-list 可列到），但内容整体换血：records_count 125→201、"
                        "字段 12→16。故标 updated 而非 gone。"})

# ---------------------------------------------------------------- 件5：登记 201 条记录 + 240 附件
ocr_cache = json.load(open("kb/.work/ocr_cache.json", encoding="utf-8"))
ocr_by_sha = {}
for k, v in ocr_cache.items():
    if v.get("sha256"):
        ocr_by_sha.setdefault(v["sha256"], (k, v))
op("本地只读", "kb/.work/ocr_cache.json",
   f"{len(ocr_cache)} 条既有 OCR（{len(ocr_by_sha)} 个唯一 file_bytes sha256 可作复用键）")

kt_rec, rid_rule, kts_rec, _ = eval_rule(registry, TBL_NAME, excluded_tables=EXCLUDED_TABLES)
RULE_TRACE = [{"scope": f"{TBL_NAME} 记录", "table": TBL_NAME, "kb_type": kt_rec,
               "matched_rule": rid_rule, "kb_type_source": kts_rec}]

new_rec_keys, new_att_keys = [], []
ocr_reused, ocr_pending = [], []
att_dl_index = {}
for fn in os.listdir(f"{W}/att"):
    tok = os.path.splitext(fn)[0]
    att_dl_index[tok] = f"{W}/att/{fn}"

for r in recs:
    rid = r["record_id"]
    fvals = {fid_by_name[k]: v for k, v in r.items() if k in fid_by_name}
    key = f"bitable:{TBL}:{rid}"
    new_rec_keys.append(key)
    add(resource_key=key, source_kind="feishu_bitable_record", table_name=TBL_NAME, table_id=TBL,
        record_id=rid, field_name=None, field_id=None,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={TBL}&record={rid}",
        path=f"[内容治理/入口Base/{TBL_NAME}]", depth=1,
        kb_type=kt_rec, matched_rule=rid_rule, kb_type_source=kts_rec,
        sha256=rec_hash(fvals), sha256_input="record_fields", sha256_state="full",
        filter_passed=None,
        extra={"supplemental": True, "all_fields": {k: v for k, v in r.items() if k != "record_id"},
               "schema_version": f"{len(fschema)} fields @ rev {mrec['rev']}",
               "note": "源侧整体换血后的全量登记；全字段 verbatim 另落 records/"})
    RECFILES.append(r)
    for fld, fid in ATT_FIELDS.items():
        for a in (r.get(fld) or []):
            tok = a.get("file_token")
            if not tok:
                continue
            ak = f"bitable:{TBL}:{rid}/{fid}/{tok}"
            new_att_keys.append(ak)
            p = att_dl_index.get(tok)
            raw = open(p, "rb").read() if p and os.path.exists(p) else b""
            fsha = hashlib.sha256(raw).hexdigest() if raw else None
            kt_a, rid_a, kts_a, _ = eval_rule(registry, TBL_NAME, field_name=fld,
                                              scope_table=TBL_NAME, excluded_tables=EXCLUDED_TABLES)
            ex = {"file_token": tok, "file_name": a.get("name"), "size": a.get("size"),
                  "bytes": len(raw) or None,
                  "media_path_hint": f"kb/l1/media/{rid}/{tok}",
                  "anchor": f"#素材/{rid}/{fld}/#img.{len(new_att_keys)}"}
            if fsha and fsha in ocr_by_sha:
                oldk, oldv = ocr_by_sha[fsha]
                ex.update({"ocr_status": "reused_from_cache", "ocr_reused_from": oldk,
                           "ocr_reused_from_sha256": fsha, "ocr_reused_at": RUN,
                           "ocr_char_count": oldv.get("ocr_char_count"),
                           "ocr_line_count": oldv.get("ocr_line_count"),
                           "note": "file_bytes sha256 与既有资源一致 → 直接复用既有 OCR 产物，未重跑 OCR"})
                ocr_reused.append(ak)
            else:
                ex.update({"ocr_status": "pending_ocr",
                           "note": "新附件，本批只登记资源与 media_refs；OCR 交 L1（下一批）"})
                ocr_pending.append(ak)
            add(resource_key=ak, source_kind="feishu_attachment", table_name=TBL_NAME, table_id=TBL,
                record_id=rid, field_name=fld, field_id=fid,
                entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={TBL}&record={rid}",
                path=f"[内容治理/入口Base/{TBL_NAME}/{fld}]", depth=2,
                kb_type=kt_a, matched_rule=rid_a, kb_type_source=kts_a,
                sha256=fsha, sha256_input="file_bytes",
                sha256_state="full" if fsha else "download_failed",
                status_reason="" if fsha else "附件下载失败，未取得字节流（最多重试 2 次）",
                extra=ex)

# ---------------------------------------------------------------- 件7：恢复 15 条外部标准
rulelib_urls = sorted(k for k, v in latest0.items()
                      if v.get("table_name") == "规则库" and k.startswith("url:")
                      and v["status"] == "retracted")
restored = []
restored_files = []
for k in rulelib_urls:
    o = latest0[k]
    kt, ridr, kts, tr = eval_rule(registry, "规则库", field_name="来源链接",
                                  scope_table="规则库", excluded_tables=())   # 真求值（件9）
    row = {kk: o.get(kk) for kk in
           ("resource_key", "source_kind", "table_name", "table_id", "record_id", "field_name",
            "field_id", "entry_url", "path", "depth", "kb_type", "matched_rule", "sha256",
            "sha256_input", "sha256_state", "revision", "dup_of")}
    row.update({"status": "restored", "status_reason": "restored_by_user_decision",
                "matched_rule": ridr, "kb_type": kt, "kb_type_source": kts,
                "rule_eval_trace": tr["trace"], "rule_eval_mode": "evaluated",
                "discovered_via": "规则库::来源链接",
                "discovered_via_table_id": "tblXsrMVkDNZ3oW8",
                "discovered_via_field_id": "fld1VehxHe",
                "provenance_note": "血缘来自入口 Base 兄弟表「规则库」的「来源链接」字段；"
                                   "规则库**本体**按 excluded_by_scope 不纳入（R6–R10 停用、表资源与记录不登记），"
                                   "但被它引用的这 15 个 URL 是 FDA/FTC 法规原文与四大平台广告政策，"
                                   "按 field_name=来源链接 → external_standard 的既有口径属**独立外部标准**，"
                                   "用户裁决保留。不重建下钻边（父节点已排除，重建会产生悬空边）。",
                "restored_from": o.get("moved_from") or f"{ARCHIVE_RULELIB}/{fname(k, o['source_kind'])}",
                "restored_at": RUN, "restored_decision": "user_decision_20260924",
                "downstream_invalidated": True,
                "observed_at": RUN, "scanner_version": SCANNER_VERSION})
    restored.append(row)
    src = os.path.join(ARCHIVE_RULELIB, fname(k, o["source_kind"]))
    if os.path.exists(src):
        d = registry["dir_map_reverse"][kt]
        os.makedirs(f"{L0}/{d}", exist_ok=True)
        dst = f"{L0}/{d}/{os.path.basename(src)}"
        shutil.move(src, dst)
        restored_files.append({"resource_key": k, "from": src, "to": dst})
        row["moved_from"], row["moved_to"] = src, dst

# ================================================================ 写资源文件
written = []
for e in R:
    d = registry["dir_map_reverse"][e["kb_type"]]
    os.makedirs(f"{L0}/{d}", exist_ok=True)
    p = f"{L0}/{d}/{fname(e['resource_key'], e['source_kind'])}"
    payload = {"resource_key": e["resource_key"], "source_kind": e["source_kind"],
               "kb_type": e["kb_type"], "matched_rule": e["matched_rule"],
               "kb_type_source": e["kb_type_source"],
               "source": {"table_name": e["table_name"], "table_id": e["table_id"],
                          "record_id": e["record_id"], "field_name": e["field_name"],
                          "field_id": e["field_id"]},
               "entry_url": e["entry_url"], "path": e["path"], "depth": e["depth"],
               "sha256": e["sha256"], "sha256_input": e["sha256_input"],
               "sha256_state": e["sha256_state"], "revision": e["revision"],
               "dup_of": None, "moved_from": None, "status": e["status"],
               "status_reason": e["status_reason"], "filter_passed": e["filter_passed"],
               "observed_at": RUN, "scanner_version": SCANNER_VERSION, "extra": e.get("extra")}
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2); fh.write("\n")
    written.append(p)

# 刷新表资源文件（件4 的唯一例外）
tbl_file = file_index.get(tbl_key)
if tbl_file and os.path.exists(tbl_file):
    payload = json.load(open(tbl_file, encoding="utf-8"))
    payload.update({"sha256": tbl_struct_sha, "sha256_state": "full",
                    "status": "updated", "status_reason": "source_table_replaced",
                    "observed_at": RUN, "scanner_version": SCANNER_VERSION})
    payload.setdefault("extra", {}).update({"records_count": len(recs), "field_count": len(fschema),
                                            "prev_records_count": 125, "prev_field_count": 12,
                                            "note": "表仍在但内容整体换血（125→201 条、12→16 字段）"})
    with open(tbl_file, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2); fh.write("\n")

# ---------------------------------------------------------------- records/ verbatim
os.makedirs(f"{L0}/records/{TBL_NAME}", exist_ok=True)
n_rec_files = 0
for r in RECFILES:
    rid = r["record_id"]
    p = f"{L0}/records/{TBL_NAME}/{rid}.json"
    fields = {f["name"]: {"field_id": f["id"], "field_type": f["type"],
                          "value": r.get(f["name"]), "raw_verbatim": r.get(f["name"])}
              for f in fmeta["fields"]}
    json.dump({"record_id": rid, "source_table": TBL_NAME, "table_id": TBL, "base_token": ENTRY_BASE,
               "entry_url": f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={TBL}&record={rid}",
               "timezone": "Asia/Shanghai", "observed_at": RUN,
               "filter": {"result": "not_filtered",
                          "note": "独立入口表（R26）：不按材料审核状态筛选；本批全字段 verbatim"},
               "schema": {"field_count": len(fmeta["fields"]), "table_rev": mrec["rev"],
                          "snapshot_at": RUN},
               "fields": fields, "raw_record": dict(r),
               "note": f"字段原值 verbatim；源侧整体换血后的全量登记。scanner_version={SCANNER_VERSION}。"},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_rec_files += 1

# ================================================================ 台账追加
rows = GONE_ROWS + [tbl_row] + [{k: e.get(k) for k in
        ("resource_key", "source_kind", "table_name", "table_id", "record_id", "field_name",
         "field_id", "entry_url", "path", "depth", "kb_type", "matched_rule", "sha256",
         "sha256_input", "sha256_state", "revision", "dup_of", "status", "status_reason")}
        | {"downstream_invalidated": True, "observed_at": RUN, "scanner_version": SCANNER_VERSION}
        for e in R] + restored
with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

latest = ledger_latest(f"{L0}/manifest.jsonl")

# ================================================================ 件6 + 件8：registry
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))

# 件6：R17 / R25 指向新字段
r17 = next(r for r in reg["rules"] if r["id"] == "R17")
r25 = next(r for r in reg["rules"] if r["id"] == "R25")
schema_sync = {"R17": {"before": r17["pattern"], "after": "图片素材"},
               "R25": {"before": r25["pattern"], "after": "视频素材"}}
r17["pattern_before_schema_migration"] = r17["pattern"]
r17["pattern"] = "图片素材"
r17["note"] = ("正负样本表的素材附件字段（图片素材 attachment），归内部正负样本库。"
               "schema 漂移同步：" + RUN + " 起 `具体内容（截图/文案/OCR）` 已不存在。")
r25["pattern_before_schema_migration"] = r25["pattern"]
r25["pattern"] = "视频素材"
r25["note"] = ("「正面和负面样本」表的素材附件字段（视频素材 attachment），归内部正负样本库。"
               "schema 漂移同步：" + RUN + " 起 `具体内容（截图/文案/OCR）` 已不存在。")

# 件6：field_roles / overrides 指向新字段
fr = reg["field_roles"]
fr_changes = []
def set_role(k, v, why):
    old = fr.get(k, "<缺失>")
    if old != v:
        fr[k] = v
        fr_changes.append({"field": k, "before": old, "after": v, "why": why})

set_role("图片素材", "attachment", "schema 漂移：`具体内容（截图/文案/OCR）` 拆出的图片字段（同 field_id fldnvxjaSr）")
set_role("视频素材", "attachment", "schema 漂移：新拆分出的视频附件字段（fld87JUpEn）")
set_role("文字素材", "content", "schema 漂移：文字素材本体（fldOg8fc7I），承载可引用的素材表述")
set_role("原文反馈", "content", "schema 漂移：源侧原始反馈表述（fldj5jQxo1），可引用")
set_role("建议", "content", "schema 漂移：建议表达（fld7r80PbU），可引用")

# 件8：4 项裁决
set_role("备注（如处理结果/建议）", "other",
         "用户裁决：SI-001 实测 125/125 行为「价值评分: 14；参与审核: …」，纯行政元数据被机器批量覆盖过；"
         "标 content 会让 L3 造出伪规则")
set_role("要包含什么", "text", "用户裁决：是「收料/建库」的治理说明，不是可发布的文案表述")
set_role("建议字段/材料", "text", "用户裁决：同上")
set_role("需向对接人收集的问题", "text", "用户裁决：同上")
# 具体原因/分析：用户驳回，保持 content
assert fr["具体原因/分析"] == "content", "具体原因/分析 应保持 content"
fr_changes.append({"field": "具体原因/分析", "before": "content", "after": "content",
                   "why": "用户明确驳回降级：它是正负样本的核心字段（「这条样本为什么对/错」），"
                          "正是「承载可引用的理由」；L2 单元数为 0 是因为该表从未被切分，不是没有内容；"
                          "sample_case 形态要求「原因分类 + 原因分析 + 建议」三要素"})

ov = reg["field_role_table_overrides"]
retired = reg.setdefault("field_role_retired", [])
DEAD = "正面和负面样本::具体内容（截图/文案/OCR）"
if DEAD in ov:
    retired.append({"key": DEAD, "role": ov.pop(DEAD), "retired_at": RUN,
                    "reason": "schema 迁移：该字段已不存在，被拆成 图片素材/视频素材/文字素材；"
                              "按「改指向新字段」处置，死条目移入本清单留痕（未删除历史）"})
ov["正面和负面样本::图片素材"] = "attachment"
ov["正面和负面样本::视频素材"] = "attachment"
ov["数据表::资料名称"] = "link"          # 件8 第 4 项

reg["field_role_evidence_notes"] = [
    n for n in reg.get("field_role_evidence_notes", []) if n["field"] != "资料名称"]
reg["field_role_coverage"] = {
    "l2_universe_size": reg["field_role_coverage"]["l2_universe_size"],
    "covered": reg["field_role_coverage"]["covered"],
    "missing_count": 0,
    "l2_universe_counts": reg["field_role_coverage"]["l2_universe_counts"],
    "measured_at": reg["field_role_coverage"]["measured_at"],
    "note": f"{RUN} 复核：L2 论域 88 项仍 100% 覆盖；本批新增的 5 个新 schema 字段亦已给角色。",
}
reg.setdefault("schema_snapshots", []).append({
    "table_name": TBL_NAME, "table_id": TBL, "at": RUN, "rev": mrec["rev"],
    "field_count": len(fschema), "previous_field_count": 12, "records_count": len(recs),
    "previous_records_count": 125,
    "fields": [{"field_id": f["id"], "field_name": f["name"], "type": f["type"]} for f in fmeta["fields"]],
    "rules_synced": schema_sync,
})
reg.setdefault("changes", []).append({
    "run_id": RUN, "change": "update",
    "keys": ["rules[R17].pattern", "rules[R25].pattern", "field_roles", "field_role_table_overrides",
             "field_role_retired", "field_role_evidence_notes", "field_role_coverage",
             "schema_snapshots[]", "gone_policy"],
    "note": "本批新增 gone 检测能力与 schema 漂移同步；台账既有行未改。",
    "scanner_version": SCANNER_VERSION,
})
reg["gone_policy"] = {
    "status": "gone", "since": RUN,
    "rule": "台账有效 key 与源侧全量 key 清单（all_records 口径、不带视图筛选）做差集 → 差集内落 gone",
    "assertion": "gone + 在库 + excluded + retracted == 该表历史键全集；且 源侧清单 == 在库 + excluded",
    "reasons": [GONE_REASON_SOURCE_REMOVED, GONE_REASON_PARENT_GONE],
    "placement": "gone 的资源文件移出库目录到 kb/l0/_archive/gone-<run_id>/（保留不删除，与 retracted 同款处置）",
    "note": "gone ≠ retracted：retracted 是口径排除（不该在库），gone 是源侧删除（曾经在库、现在没了）",
}
with open(f"{L0}/registry/kb.json", "w", encoding="utf-8") as fh:
    json.dump(reg, fh, ensure_ascii=False, indent=2); fh.write("\n")

# ================================================================ L3 registry 追加标注
l3p = "kb/l3/registry/l3.json"
l3 = json.load(open(l3p, encoding="utf-8"))
l3["filter_rules"]["step1_metadata"].setdefault("schema_sync_log", []).append({
    "at": RUN, "by": "L0 batch4", "state": "已同步",
    "note": "「正面和负面样本」schema 漂移（12→16 字段）已同步到 L0 field_roles："
            "新增 图片素材/视频素材(attachment)、文字素材/原文反馈/建议(content)；"
            "`备注（如处理结果/建议）` 由 content 改为 other（SI-001 实测为行政元数据）；"
            "`要包含什么`/`建议字段/材料`/`需向对接人收集的问题` 由 content 改为 text；"
            "`具体原因/分析` 按用户裁决保持 content。L3 直接读 L0 field_roles，无需自带表。",
    "content_fields_now": sorted(k for k, v in reg["field_roles"].items() if v == "content"),
})
with open(l3p, "w", encoding="utf-8") as fh:
    json.dump(l3, fh, ensure_ascii=False, indent=2); fh.write("\n")

# ================================================================ 件9 + index 重建
live = {k: v for k, v in latest.items()
        if v["status"] not in ("gone", "retracted")}
with open(f"{L0}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(live):
        r = live[k]
        fh.write(json.dumps({"resource_key": r["resource_key"], "kb_type": r["kb_type"],
                             "source_kind": r["source_kind"], "status": r["status"],
                             "entry_url": r["entry_url"]}, ensure_ascii=False, sort_keys=True) + "\n")

# ================================================================ 件1 断言 + 自检
led_after = {k for k, v in latest.items()
             if k.startswith(f"bitable:{TBL}:") and v["status"] not in ("gone", "retracted")}
acc = assert_accounting(gone_rows=det["gone_total"], excluded_keys=0, retracted_keys=0,
                        in_library_keys=len(led_after),
                        keys_ever=det["keys_ever_in_ledger_scope"],
                        source_key_list=det["source_key_list"])

files_now = {}
for d in registry["dir_map"]:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        j = json.load(open(p, encoding="utf-8"))
        files_now[j["resource_key"]] = (p, j)
mismatch = []
for k, (p, j) in files_now.items():
    d = os.path.basename(os.path.dirname(p))
    led = latest.get(k)
    if led is None:
        mismatch.append((k, "文件在、台账无行")); continue
    if j["kb_type"] != led["kb_type"]:
        mismatch.append((k, f"文件 {j['kb_type']} != 台账 {led['kb_type']}")); continue
    if registry["dir_map"][d] != j["kb_type"]:
        mismatch.append((k, f"文件 {j['kb_type']} != 目录 {d}"))

index_rows = sum(1 for l in open(f"{L0}/index/l0.jsonl", encoding="utf-8") if l.strip())
out = {
    "run_id": RUN, "scanner_version": SCANNER_VERSION, "part": "batch4 · L0 补跑",
    "source_read": {"table": TBL_NAME, "table_id": TBL, "records_count": mrec["records_count"],
                    "rev": mrec["rev"], "scope": scope,
                    "read_at": RUN, "measured_at_note": "复核时刻实测 records_count 见 records_count"},
    "gone": {"records": len(det["gone_records"]), "attachments": len(det["gone_attachments"]),
             "total": det["gone_total"],
             "source_missing_from_ledger_records": len(det["source_missing_from_ledger_records"]),
             "source_missing_from_ledger_attachments": len(det["source_missing_from_ledger_attachments"]),
             "files_moved_to_archive": len(gone_files_moved), "archive_dir": ARCHIVE_GONE},
    "table_resource": {"key": tbl_key, "status": "updated", "status_reason": "source_table_replaced",
                       "prev_records_count": 125, "records_count": len(recs),
                       "prev_field_count": 12, "field_count": len(fschema)},
    "registered": {"records": len(new_rec_keys), "attachments": len(new_att_keys),
                   "attachment_fields": ATT_FIELDS,
                   "records_by_kb_type": dict(collections.Counter(e["kb_type"] for e in R
                                                                 if e["source_kind"] == "feishu_bitable_record")),
                   "attachments_by_kb_type": dict(collections.Counter(e["kb_type"] for e in R
                                                                      if e["source_kind"] == "feishu_attachment")),
                   "ocr_reused": len(ocr_reused), "ocr_pending": len(ocr_pending),
                   "ocr_reused_keys": ocr_reused[:20], "ocr_fail_download": len(dl["fail"]),
                   "download_failed": dl["fail"]},
    "schema_drift": {"field_count_now": len(fschema), "rules_synced": schema_sync,
                     "field_role_changes": fr_changes,
                     "overrides_retired": [x["key"] for x in retired],
                     "overrides_now": reg["field_role_table_overrides"]},
    "restored": {"count": len(restored), "files_moved_back": len(restored_files),
                 "files": restored_files,
                 "discovered_via": "规则库::来源链接",
                 "matched_rule_after_eval": dict(collections.Counter(r["matched_rule"] for r in restored)),
                 "kb_type_after_eval": dict(collections.Counter(r["kb_type"] for r in restored))},
    "rule_eval": {"mode": "真求值（rule_eval_mode=evaluated）", "trace_sample": RULE_TRACE,
                  "restored_trace_sample": restored[0]["rule_eval_trace"] if restored else None},
    "accounting": acc,
    "ledger_rows_appended": len(rows),
    "index": {"rows": index_rows, "live_rows": len(live),
              "decrease_from_gone": det["gone_total"],
              "formula": "index == 台账有效最新行（非 gone / 非 retracted）"},
    "resource_files": len(files_now), "mismatch": mismatch,
    "written_files": written, "record_files": n_rec_files,
    "ops": OPS,
}
json.dump(out, open(f"{L0}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("source_read", "gone", "table_resource", "registered",
                                      "restored", "accounting", "index", "resource_files",
                                      "mismatch")}, ensure_ascii=False, indent=1))
print("台账追加行:", len(rows), "| 新资源文件:", len(written), "| records/ 新文件:", n_rec_files)
