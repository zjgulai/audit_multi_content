#!/usr/bin/env python3
"""L0 补充登记：「正面和负面样本」表 125 条记录 + 77 个图片附件资源。
只追加：不动已有资源文件与台账旧行。kb/l0/ 内写入。
"""
import json, os, re, hashlib, collections, subprocess, sys

RUN = sys.argv[1]
L0 = "kb/l0"
SCANNER = "0.5"
BASE = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
TBL, TBL_NAME = "tbld8qE92YaY38Yz", "正面和负面样本"
EXCLUDED_FIELDS = {"来源"}                      # 唯一排除项
EXCL_HASH = {"last_modified_time", "last_modified_by"}
ATT_FIELD_ID = "fldnvxjaSr"
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))

registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]
fields = json.load(open("kb/.work/l1.json", encoding="utf-8"))["sibling_tables"][TBL_NAME]["fields"]
fid_by_name = {f["field_name"]: f["field_id"] for f in fields}
name_by_fid = {f["field_id"]: f["field_name"] for f in fields}
rows = [json.loads(l) for l in open("kb/.work/正负样本.ndjson", encoding="utf-8") if l.strip()]

def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def rec_hash(fvals):
    items = sorted(((k, v) for k, v in fvals.items() if k not in EXCL_HASH), key=lambda x: x[0])
    return sha(canon([["field_id", k, "value", v] for k, v in items]))

def rid_of(rk):
    return re.sub(r'[^0-9A-Za-z._\-]+', '_', rk.replace(":", "__").replace("/", "_").replace("/", "_"))[:170]

# ---------- 现状（只读）
latest = {}
for line in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        latest[r["resource_key"]] = r
print(f"补登记前：台账 {len(latest)} 条")

ops = [{"op": "base +record-list", "nature": "read", "target": f"bitable:{BASE}:table:{TBL}",
        "note": f"{TBL_NAME} 125 条记录（不按审核状态筛选）"}]
for f in fields:
    ops.append({"op": "base +field-list", "nature": "read", "target": f"bitable:{BASE}:table:{TBL}",
                "note": f"字段 schema：{f['field_name']}"})

new_res, new_recs, att_meta = [], [], []
rec_dir = f"{L0}/records/{TBL_NAME}"
os.makedirs(rec_dir, exist_ok=True)

for r in rows:
    rid = r["record_id"]
    # 记录原值（来源 字段排除）
    kept = {k: v for k, v in r.items() if k != "record_id" and k not in EXCLUDED_FIELDS}
    fvals = {fid_by_name[k]: v for k, v in kept.items() if k in fid_by_name}
    h = rec_hash(fvals)
    rk = f"bitable:{TBL}:{rid}"
    url = f"https://momcozy-in.feishu.cn/base/{BASE}?table={TBL}&record={rid}"
    kt, ridr, kts = "internal_sample", "R9", f"表名:{TBL_NAME}"

    # 记录留痕（来源 不入库）
    rec_out = {
        "record_id": rid, "source_table": TBL_NAME, "table_id": TBL,
        "base_token": BASE, "entry_url": url, "timezone": "Asia/Shanghai", "observed_at": RUN,
        "filter": {"result": "not_filtered", "note": "该表不按审核状态筛选，全部记录登记"},
        "excluded_fields": sorted(EXCLUDED_FIELDS),
        "excluded_reason": "按任务规则：「来源」字段不入库，其余字段全部原值登记",
        "fields": {k: {"field_id": fid_by_name.get(k), "field_type": next((f["type"] for f in fields if f["field_name"] == k), None),
                       "value": v, "raw_verbatim": v} for k, v in kept.items()},
        "field_count_in_source": len(r) - 1, "field_count_stored": len(kept),
        "hash_excludes": sorted(EXCLUDED_FIELDS),
        "raw_record": {k: v for k, v in r.items() if k not in EXCLUDED_FIELDS},
        "note": "字段原值 verbatim；「来源」字段既不落库也不参与 sha256。",
    }
    with open(f"{rec_dir}/{rid}.json", "w", encoding="utf-8") as fh:
        json.dump(rec_out, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    new_recs.append({"resource_key": rk, "record_id": rid, "kb_type": kt})

    new_res.append(dict(resource_key=rk, source_kind="feishu_bitable_record", table_name=TBL_NAME,
        table_id=TBL, record_id=rid, field_name=None, field_id=None, entry_url=url,
        path=f"[内容治理/入口Base/{TBL_NAME}]", depth=1, kb_type=kt, matched_rule=ridr,
        kb_type_source=kts, sha256=h, sha256_input="record_fields", sha256_state="full",
        revision=None, status="registered", status_reason="", filter_passed=None,
        extra={"excluded_fields": sorted(EXCLUDED_FIELDS),
               "note": "补登记：符合「除来源字段外全部提取」规则"}))

    # 附件 → 资源
    for a in (r.get("具体内容（截图/文案/OCR）") or []):
        tok, nm = a.get("file_token"), a.get("name")
        if not tok:
            continue
        dst = f"kb/.work/att/{tok}{os.path.splitext(nm or '')[1] or '.png'}"
        if not os.path.exists(dst):
            subprocess.run(["lark-cli", "base", "+record-download-attachment",
                            "--base-token", BASE, "--table-id", TBL, "--record-id", rid,
                            "--file-token", tok, "--output", dst],
                           capture_output=True, text=True, env=ENV, timeout=180)
            ops.append({"op": "base +record-download-attachment", "nature": "read",
                        "target": f"attachment:{tok}", "note": nm})
        raw = open(dst, "rb").read() if os.path.exists(dst) else b""
        fsha = hashlib.sha256(raw).hexdigest() if raw else None
        ark = f"bitable:{TBL}:{rid}/{ATT_FIELD_ID}/{tok}"
        new_res.append(dict(resource_key=ark, source_kind="feishu_attachment", table_name=TBL_NAME,
            table_id=TBL, record_id=rid, field_name=name_by_fid[ATT_FIELD_ID], field_id=ATT_FIELD_ID,
            entry_url=url, path=f"[内容治理/入口Base/{TBL_NAME}/具体内容（截图/文案/OCR）]", depth=2,
            kb_type="internal_sample", matched_rule="R25",
            kb_type_source="字段名:具体内容（截图/文案/OCR）→ 内部正负样本库",
            sha256=fsha, sha256_input="file_bytes", sha256_state="full" if fsha else "download_failed",
            revision=None, status="registered",
            status_reason="" if fsha else "附件下载失败，未取得字节流",
            filter_passed=None,
            extra={"file_token": tok, "file_name": nm, "size": a.get("size"), "bytes": len(raw),
                   "media_path_hint": f"kb/l1/media/{rid}/{tok}", "note": "图片资源，抽取留待下一步"}))
        att_meta.append({"record_id": rid, "file_token": tok, "name": nm, "sha256": fsha, "bytes": len(raw)})

print(f"新增资源 {len(new_res)}（记录 {len(new_recs)} + 附件 {len(att_meta)}）")

json.dump({"resources": new_res, "records": new_recs, "attachments": att_meta,
           "excluded_fields": sorted(EXCLUDED_FIELDS), "ops": ops},
          open("kb/.work/l0_supplement.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("附件指纹:", sum(1 for a in att_meta if a["sha256"]), "/", len(att_meta))
