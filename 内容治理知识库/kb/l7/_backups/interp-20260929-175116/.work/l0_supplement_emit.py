#!/usr/bin/env python3
"""L0 补充登记：追加资源文件 + 追加台账行 + 追加 registry 规则 + 重建 index。
严格只追加：已存在的资源文件不触碰，台账用 append 模式。
"""
import json, os, re, hashlib, collections, sys, glob, shutil
from datetime import datetime

RUN = sys.argv[1]
L0, L1 = "kb/l0", "kb/l1"
SCANNER = "0.5"
BASE = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
TBL, TBL_NAME = "tbld8qE92YaY38Yz", "正面和负面样本"
START = datetime.now().timestamp()

sup = json.load(open("kb/.work/l0_supplement.json", encoding="utf-8"))
registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]

# ---------- 0) 记录本次启动前的已有产物指纹（用于自检「已有产物未被修改」）
before_manifest = []
for line in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        before_manifest.append(line.rstrip("\n"))
before_mh = hashlib.sha256("\n".join(before_manifest).encode()).hexdigest()
before_files = {}
for d in DIR_MAP:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        st = os.stat(p)
        before_files[p] = (st.st_mtime, st.st_size)
print(f"基线：台账 {len(before_manifest)} 行 sha256={before_mh[:16]}；已有资源文件 {len(before_files)} 个")

# ---------- 1) 追加 registry 规则（只追加新规则）
new_rules = [
    {"id": "R25", "match_type": "field_name", "scope_table": TBL_NAME,
     "pattern": "具体内容（截图/文案/OCR）", "kb_type": "internal_sample",
     "note": "「正面和负面样本」表的素材附件字段，图片/视频资源归内部正负样本库（补登记）"},
    {"id": "R26", "match_type": "table_name", "scope_table": TBL_NAME, "pattern": TBL_NAME,
     "kb_type": "internal_sample",
     "note": "「正面和负面样本」为独立入口表：不按审核状态筛选，除「来源」字段外全部登记（补登记）"},
]
existing_ids = {r["id"] for r in registry["rules"]}
added_rules = [r for r in new_rules if r["id"] not in existing_ids]
if added_rules:
    registry["rules"].extend(added_rules)
    reg2 = dict(registry)
    reg2["supplemental_registrations"] = registry.get("supplemental_registrations", []) + [{
        "run_id": RUN,
        "what": "补登记入口表「正面和负面样本」（独立入口，不按审核状态筛选）及其图片附件",
        "rules_added": [r["id"] for r in added_rules],
        "excluded_fields": sup["excluded_fields"],
        "note": "既有规则与既有字段未改动，仅追加。",
    }]
    with open(f"{L0}/registry/kb.json", "w", encoding="utf-8") as fh:
        json.dump(reg2, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
print(f"registry 追加规则：{[r['id'] for r in added_rules]}")

# ---------- 2) 追加资源文件
written = []
for e in sup["resources"]:
    d = REV[e["kb_type"]]
    fn = f"{e['source_kind']}__" + re.sub(r'[^0-9A-Za-z._\-]+', '_',
             e["resource_key"].split(":", 1)[1].replace(":", "__").replace("/", "_"))[:150] + ".json"
    p = f"{L0}/{d}/{fn}"
    if os.path.exists(p):
        print("  跳过已存在（不覆盖）:", p)
        continue
    payload = {
        "resource_key": e["resource_key"], "source_kind": e["source_kind"], "kb_type": e["kb_type"],
        "matched_rule": e["matched_rule"], "kb_type_source": e["kb_type_source"],
        "source": {"table_name": e["table_name"], "table_id": e["table_id"], "record_id": e["record_id"],
                   "field_name": e["field_name"], "field_id": e["field_id"]},
        "entry_url": e["entry_url"], "path": e["path"], "depth": e["depth"],
        "sha256": e["sha256"], "sha256_input": e["sha256_input"], "sha256_state": e["sha256_state"],
        "revision": e["revision"], "dup_of": None, "moved_from": None,
        "status": e["status"], "status_reason": e["status_reason"],
        "filter_passed": e["filter_passed"], "observed_at": RUN, "scanner_version": SCANNER,
        "extra": e.get("extra"),
    }
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    written.append((p, e["resource_key"]))

# ---------- 3) 台账追加（append-only，不重写）
prev = {}
for line in before_manifest:
    r = json.loads(line)
    prev[r["resource_key"]] = r
rows, change = [], collections.Counter()
for e in sup["resources"]:
    key = e["resource_key"]
    old = prev.get(key)
    if old is None:
        status = "registered"; change["new"] += 1
    elif e["sha256"] and old.get("sha256") == e["sha256"]:
        status = "unchanged"; change["unchanged"] += 1
    elif e["sha256"] and old.get("sha256") != e["sha256"]:
        status = "updated"; change["updated"] += 1
    else:
        status = "unchanged"; change["unchanged"] += 1
    rows.append({"resource_key": key, "source_kind": e["source_kind"], "table_name": e["table_name"],
                 "table_id": e["table_id"], "record_id": e["record_id"], "field_name": e["field_name"],
                 "field_id": e["field_id"], "entry_url": e["entry_url"], "path": e["path"],
                 "depth": e["depth"], "kb_type": e["kb_type"], "matched_rule": e["matched_rule"],
                 "sha256": e["sha256"], "sha256_input": e["sha256_input"],
                 "sha256_state": e["sha256_state"], "revision": e["revision"], "dup_of": None,
                 "moved_from": None, "status": status, "status_reason": e["status_reason"] or "",
                 "downstream_invalidated": status in ("registered", "updated", "retracted", "gone"),
                 "observed_at": RUN, "scanner_version": SCANNER})
with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

latest = {}
for line in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        latest[r["resource_key"]] = r

# ---------- 4) index 重建（由台账投影）
with open(f"{L0}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(latest):
        r = latest[k]
        fh.write(json.dumps({"resource_key": r["resource_key"], "kb_type": r["kb_type"],
                             "source_kind": r["source_kind"], "status": r["status"],
                             "entry_url": r["entry_url"]}, ensure_ascii=False, sort_keys=True) + "\n")

json.dump({"run_id": RUN, "start_ts": START, "before_manifest_rows": len(before_manifest),
           "before_manifest_sha256": before_mh, "before_files": {k: list(v) for k, v in before_files.items()},
           "written": written, "latest_rows": len(latest), "change": dict(change),
           "rules_added": [r["id"] for r in added_rules]},
          open("kb/.work/l0_supplement_emit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"资源文件追加 {len(written)} | 台账追加 {len(rows)} 行 | 最新台账 {len(latest)} | 变更 {dict(change)}")
