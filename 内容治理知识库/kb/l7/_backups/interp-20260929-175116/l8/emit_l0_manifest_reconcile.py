#!/usr/bin/env python3
"""L0 台账补齐（只追加，绝不改写已有行）—— 对齐飞书侧。

背景（证据见 kb/l8/runs/20260929-1200-l0-align.json）：
  负面样本 108 条记录文件在 kb/l0/records/负面样本/，但 kb/l0/manifest.jsonl 里没有记录级行
  → 下游 l1_extract 用「L0 活跃集 ⊖ L1」算差集，得到 0，于是 108 条永远抽不出来。

本脚本做四件事，全部 append-only（靠 latest-wins 生效）：
  1) 给 108 条新负面样本补记录级行（status=registered）
  2) 给 283 张图片补附件级行（sha256_input=attachment_metadata —— 字节流需下载权限，
     原始口径 file_bytes 待下载后再补一行；本行把「已登记但字节未取」写清楚，不伪装成 file_bytes）
  3) 把 326 条旧负面样本标 gone（记录文件已归档）
  4) 给「知识库分类说明」里被飞书改过的那条补 updated 行

sha256 口径已用既有行反向验证：
  sha256( json.dumps([["field_id",fid,"value",val]...], sort_keys=True, separators=(",",":")) )
  在 recvw35kNoBkHf 上精确复现 manifest 中的 ce546585a9be2a17ca6efc7324e63e6391c1e11e16cafafd7e7b98ed1d392ce2

用法：
  python3 kb/l8/emit_l0_manifest_reconcile.py 20260929-1200          # 预演，只打印
  python3 kb/l8/emit_l0_manifest_reconcile.py 20260929-1200 --apply  # 追加写入
"""
import collections
import hashlib
import json
import os
import sys

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1200"
APPLY = "--apply" in sys.argv
EMITTER = "l8/emit_l0_manifest_reconcile.py"
SCANNER = "0.7"
L0 = "kb/l0"
ARCH_OLD = "kb/l0/_archive/正面和负面样本-superseded-20260929-1045"
NEG_TID = "tbld8qE92YaY38Yz"
ENTRY_BASE = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
EXCL = {"last_modified_time", "last_modified_by"}


def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def rec_hash(fields):
    """与 b2_l0_delta.rec_hash 同口径：按 field_id 排序的 [field_id, value] 对。"""
    items = sorted(((v.get("field_id"), v.get("value")) for v in fields.values() if v.get("field_id")),
                   key=lambda x: x[0])
    return sha(canon([["field_id", k, "value", v] for k, v in items]))


def base_row(**kw):
    row = {"change": None, "depth": 0, "downstream_invalidated": False, "dup_of": None,
           "entry_url": None, "field_id": None, "field_name": None, "kb_type": None,
           "matched_rule": None, "observed_at": RUN, "path": None, "record_id": None,
           "resource_key": None, "revision": None, "sha256": None, "sha256_input": None,
           "sha256_state": None, "source_kind": None, "status": None, "status_reason": "",
           "table_id": None, "table_name": None, "scanner_version": SCANNER, "emitted_by": EMITTER}
    row.update(kw)
    return row


rows = []

# ---------- 1) 108 条新负面样本 ----------
new_dir = f"{L0}/records/负面样本"
new_files = sorted(f for f in os.listdir(new_dir) if f.endswith(".json"))
new_recs = [json.load(open(f"{new_dir}/{f}", encoding="utf-8")) for f in new_files]
for r in new_recs:
    rid, tid = r["record_id"], r["table_id"]
    rows.append(base_row(
        change="l0_feishu_reconcile_register", depth=1, downstream_invalidated=True,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={tid}&record={rid}",
        kb_type="internal_sample", matched_rule="R26", path="[内容治理/入口Base/负面样本]",
        record_id=rid, resource_key=f"bitable:{tid}:{rid}",
        sha256=rec_hash(r["fields"]), sha256_input="record_fields", sha256_state="full",
        source_kind="feishu_bitable_record", status="registered",
        status_reason="l0_feishu_reconcile_20260929-1200：飞书侧整批替换后的 108 条，本次补登记",
        table_id=tid, table_name="负面样本", rule_eligible=True,
        rule_eligible_source="not_material_collection"))
    # ---------- 2) 附件级行（283 张图片） ----------
    for a in (r["fields"].get("图片素材", {}).get("value") or []):
        tok = a.get("file_token")
        if not tok:
            continue
        rows.append(base_row(
            change="l0_feishu_reconcile_register_attachment", depth=2, downstream_invalidated=True,
            entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={tid}&record={rid}",
            field_id=r["fields"]["图片素材"].get("field_id"), field_name="图片素材",
            kb_type="internal_sample", matched_rule="R25",
            path="[内容治理/入口Base/负面样本/图片素材]",
            record_id=rid, resource_key=f"bitable:{tid}:{rid}/{r['fields']['图片素材'].get('field_id')}/{tok}",
            sha256=sha(canon({"file_token": tok, "name": a.get("name"), "size": a.get("size")})),
            sha256_input="attachment_metadata", sha256_state="metadata_only",
            source_kind="feishu_attachment", status="registered",
            status_reason="字节流未取（bot 身份下载附件 403，见 runs/20260929-1155）；"
                          "本次只登记元数据，待取得字节后另补 file_bytes 行",
            table_id=tid, table_name="负面样本"))

# ---------- 3) 326 条旧负面样本 → gone ----------
if os.path.isdir(ARCH_OLD):
    old_files = sorted(f for f in os.listdir(ARCH_OLD) if f.endswith(".json") and not f.startswith("_"))
    for f in old_files:
        r = json.load(open(f"{ARCH_OLD}/{f}", encoding="utf-8"))
        rid, tid = r["record_id"], r["table_id"]
        rows.append(base_row(
            change="l0_feishu_reconcile_gone", depth=1, downstream_invalidated=True,
            entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={tid}&record={rid}",
            kb_type="internal_sample", matched_rule="R26", path="[内容治理/入口Base/负面样本]",
            record_id=rid, resource_key=f"bitable:{tid}:{rid}",
            sha256=rec_hash(r["fields"]), sha256_input="record_fields", sha256_state="full",
            source_kind="feishu_bitable_record", status="gone",
            status_reason="飞书侧整批替换（原 record_id 在飞书返回 Record not found）；"
                          f"本地留档 {ARCH_OLD}",
            table_id=tid, table_name="负面样本"))

# ---------- 4) 知识库分类说明：被飞书改过的那条 ----------
chg_dir = f"{L0}/records/知识库分类说明"
chg = []
for f in sorted(os.listdir(chg_dir)):
    if not f.endswith(".json"):
        continue
    r = json.load(open(f"{chg_dir}/{f}", encoding="utf-8"))
    if r["record_id"] == "recvvfWFhMpe9l":
        chg.append(r)
for r in chg:
    rid, tid = r["record_id"], r["table_id"]
    rows.append(base_row(
        change="l0_feishu_reconcile_update", depth=1, downstream_invalidated=True,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={tid}&record={rid}",
        kb_type=r.get("kb_type") or "unknown", matched_rule="R26",
        path="[内容治理/入口Base/知识库分类说明]", record_id=rid, resource_key=f"bitable:{tid}:{rid}",
        sha256=rec_hash(r["fields"]), sha256_input="record_fields", sha256_state="full",
        source_kind="feishu_bitable_record", status="updated",
        status_reason="飞书侧改库名：内部正面与负面样本库 → 内部负面样本库（要包含什么 去掉正面）；"
                      "L0 记录文件需同步刷新",
        table_id=tid, table_name=r.get("source_table")))

# ---------- 预演 ----------
by_status = collections.Counter(r["status"] for r in rows)
by_kind = collections.Counter(r["source_kind"] for r in rows)
print(f"[预演] 将追加 {len(rows)} 行（append-only）")
print("   status:", dict(by_status))
print("   source_kind:", dict(by_kind))
print("   sha256_input:", dict(collections.Counter(r["sha256_input"] for r in rows)))
for r in rows[:2] + rows[108:110] + rows[110:112]:
    print("   ·", json.dumps(r, ensure_ascii=False)[:190])

if not APPLY:
    print("\n未写入（加 --apply 才追加）")
    sys.exit(0)

before = sum(1 for _ in open(f"{L0}/manifest.jsonl", encoding="utf-8"))
with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
after = sum(1 for _ in open(f"{L0}/manifest.jsonl", encoding="utf-8"))
print(f"\n[写入] manifest 行数 {before} → {after}（+{after-before}）")
json.dump({"run": RUN, "emitter": EMITTER, "appended": len(rows), "by_status": dict(by_status),
           "by_source_kind": dict(by_kind), "rows_before": before, "rows_after": after,
           "sha256_convention_proof": "recvw35kNoBkHf → ce546585a9be2a17ca6efc7324e63e6391c1e11e16cafafd7e7b98ed1d392ce2"},
          open(f"kb/l8/runs/{RUN}-l0-manifest-emit.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"[写入] 运行记录 kb/l8/runs/{RUN}-l0-manifest-emit.json")
