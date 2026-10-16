#!/usr/bin/env python3
"""L0 重新落库：产物写出（库目录 / 记录留痕 / 台账 / 索引 / 候选）。"""
import json, os, re, hashlib, collections, sys

RUN = sys.argv[1]
KB = "kb/l0"
SCANNER = "0.5"
ENTRY_BASE, ENTRY_TBL, ENTRY_TBL_NAME = "GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblMGtPfe8ZUsEdP", "材料收集"

b = json.load(open("kb/.work/built2.json", encoding="utf-8"))
R, E, REC = b["resources"], b["edges"], b["records"]
registry = json.load(open(f"{KB}/registry/kb.json", encoding="utf-8"))
DIR_MAP = registry["dir_map"]                 # 目录名 -> kb_type（人读）
REV = registry["dir_map_reverse"]             # kb_type -> 目录名（机器判断查这张表）
parent_records = [json.loads(l) for l in open("kb/.work/材料收集.ndjson", encoding="utf-8") if l.strip()]
fields_meta = json.load(open(f"kb/.work/fields-{ENTRY_TBL}.json", encoding="utf-8"))["data"]["fields"]
bases = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))
sib_fields = json.load(open("kb/.work/l1.json", encoding="utf-8"))["sibling_tables"]
matched_set = set(b["matched_ids"])
BASE_PREFIX = {"Lk3Qb8y2QaVyZns6gprcVNE9nA0": "广告文案风控库",
               "N2qkb2YxuatqGLsa4U4cFQxgnCe": "外部资料库",
               "SKkkbdZi9aRuMzs7ob0cpSYHnQg": "内容公式与专家修订库"}

def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()

def slug(u):
    s = re.sub(r'^https?://', '', u)
    s = re.sub(r'[^0-9A-Za-z._\-]+', '_', s).strip('_')
    return s[:90]

def filename(e):
    """<source_kind>__<id>.json"""
    k = e["resource_key"]
    sk = e["source_kind"]
    if k.startswith("url:"):
        return f"url__{slug(k[4:])}.json"
    ident = k.split(":", 1)[1].replace(":", "__").replace("/", "_")
    return f"{sk}__{ident}.json"

# ============================================================ 1) 库目录（资源 json 平铺）
for d in DIR_MAP:
    os.makedirs(f"{KB}/{d}", exist_ok=True)

written = {}
dupe_names = collections.defaultdict(list)
for e in R:
    d = REV[e["kb_type"]]
    fn = filename(e)
    dupe_names[(d, fn)].append(e["resource_key"])
    payload = {
        "resource_key": e["resource_key"],
        "source_kind": e["source_kind"],
        "kb_type": e["kb_type"],
        "matched_rule": e["matched_rule"],
        "kb_type_source": e["kb_type_source"],
        "source": {"table_name": e["table_name"], "table_id": e["table_id"],
                   "record_id": e["record_id"], "field_name": e["field_name"],
                   "field_id": e["field_id"]},
        "entry_url": e["entry_url"],
        "path": e["path"],
        "depth": e["depth"],
        "sha256": e["sha256"],
        "sha256_input": e["sha256_input"],
        "sha256_state": e["sha256_state"],
        "revision": e["revision"],
        "dup_of": e["dup_of"],
        "moved_from": e["moved_from"],
        "status": e["status"],
        "status_reason": e["status_reason"],
        "filter_passed": e["filter_passed"],
        "observed_at": RUN,
        "scanner_version": SCANNER,
        "extra": e.get("extra"),
    }
    with open(f"{KB}/{d}/{fn}", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    written[e["resource_key"]] = (d, fn)

collisions = {k: v for k, v in dupe_names.items() if len(v) > 1}

# ============================================================ 2) 记录留痕 records/<源表名>/
FORMULA_TYPES = {"formula", "lookup"}
def formula_block(f, val):
    return {"field_id": f["id"], "field_type": f["type"],
            "expression": (f.get("expression") or f.get("formula") or
                           ({"lookup_from_table": f.get("from"), "lookup_field": f.get("select"),
                             "where": f.get("where"), "aggregate": f.get("aggregate")}
                            if f["type"] == "lookup" else None)),
            "depends_on_fields": sorted(
                ({"field_name": n, "field_id": next((x["id"] for x in fields_meta if x["name"] == n), None)}
                 for n in _deps(f)), key=lambda x: str(x["field_name"])),
            "value_snapshot": val,
            "snapshot_note": "公式/查找引用字段不存值，只存表达式 + 依赖字段 + 本次求值快照"}

def _deps(f):
    names = set()
    if f["type"] == "lookup":
        for c in ((f.get("where") or {}).get("conditions") or []):
            for p in c:
                if isinstance(p, dict) and p.get("type") == "field_ref":
                    names.add(p.get("field"))
        if f.get("select"):
            names.add(f["select"])
    return names

rec_dir = f"{KB}/records/{ENTRY_TBL_NAME}"
os.makedirs(rec_dir, exist_ok=True)
n_rec_files = 0
for r in parent_records:
    rid = r["record_id"]
    if rid not in matched_set:
        continue          # 被排除的记录：不落 records/，只在 runs/<run_id>.json 留痕
    fields_blk, formula_blk = {}, {}
    for f in fields_meta:
        nm, val = f["name"], r.get(f["name"])
        if f["type"] in FORMULA_TYPES:
            formula_blk[nm] = formula_block(f, val)
            fields_blk[nm] = {"field_id": f["id"], "field_type": f["type"], "value": None,
                              "stored_as": "formula_snapshot", "raw_verbatim": val}
        else:
            fields_blk[nm] = {"field_id": f["id"], "field_type": f["type"], "value": val,
                              "raw_verbatim": val}
    rec = {"record_id": rid, "source_table": ENTRY_TBL_NAME, "table_id": ENTRY_TBL,
           "base_token": ENTRY_BASE,
           "entry_url": f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}&record={rid}",
           "timezone": "Asia/Shanghai", "observed_at": RUN,
           "filter": {"field": "材料审核状态", "expected": "通过", "result": "matched"},
           "fields": fields_blk, "formula_and_lookup_fields": formula_blk, "raw_record": r,
           "note": "字段原值 verbatim；日期保留原始时间戳与时区；单选/多选保留读接口返回的原值（选项 id 源接口不返回，不补造）。"}
    with open(f"{rec_dir}/{rid}.json", "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    n_rec_files += 1

# 关联 Base 记录留痕
for bt, bd in bases.items():
    for tb in bd["tables"]:
        if not tb["records"]:
            continue
        tdir = f"{KB}/records/{BASE_PREFIX.get(bt, bt)}__{tb['table_name']}"
        os.makedirs(tdir, exist_ok=True)
        for rec in tb["records"]:
            rid = rec["record_id"]
            fields_blk = {f["field_name"]: {"field_id": f["field_id"], "field_type": f["type"],
                                            "value": rec.get(f["field_name"]),
                                            "raw_verbatim": rec.get(f["field_name"])}
                          for f in tb["fields"]}
            out = {"record_id": rid, "source_table": tb["table_name"], "table_id": tb["table_id"],
                   "base_token": bt, "source_base_label": bd["label"],
                   "entry_url": f"https://momcozy-in.feishu.cn/base/{bt}?table={tb['table_id']}&record={rid}",
                   "timezone": "Asia/Shanghai", "observed_at": RUN,
                   "filter": {"result": "not_in_entry_table_scope",
                              "note": "非筛选入口表，随结构下钻登记，未做状态筛选"},
                   "fields": fields_blk, "raw_record": rec,
                   "note": "字段原值 verbatim；下钻第二层记录。"}
            with open(f"{tdir}/{rid}.json", "w", encoding="utf-8") as fh:
                json.dump(out, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            n_rec_files += 1

# 分类说明表记录留痕
cat_dir = f"{KB}/records/知识库分类说明"
os.makedirs(cat_dir, exist_ok=True)
for rec in [json.loads(l) for l in open("kb/.work/分类说明.ndjson", encoding="utf-8") if l.strip()]:
    rid = rec["record_id"]
    fields_blk = {f["field_name"]: {"field_id": f["field_id"], "field_type": f["type"],
                                    "value": rec.get(f["field_name"]),
                                    "raw_verbatim": rec.get(f["field_name"])}
                  for f in sib_fields["知识库分类说明"]["fields"]}
    out = {"record_id": rid, "source_table": "知识库分类说明",
           "table_id": "tblZP8jG4tiUL98C", "base_token": ENTRY_BASE,
           "entry_url": f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table=tblZP8jG4tiUL98C&record={rid}",
           "timezone": "Asia/Shanghai", "observed_at": RUN,
           "filter": {"result": "not_in_entry_table_scope",
                      "note": "入口 Base 同级表，随结构下钻登记，未做状态筛选"},
           "fields": fields_blk, "raw_record": rec, "note": "字段原值 verbatim。"}
    with open(f"{cat_dir}/{rid}.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    n_rec_files += 1

# ============================================================ 3) 边表
with open(f"{KB}/links/graph.jsonl", "w", encoding="utf-8") as fh:
    for e in E:
        fh.write(json.dumps({"from_kind": e["from_kind"], "from_id": e["from_id"],
                             "to_kind": e["to_kind"], "to_id": e["to_id"], "depth": e["depth"],
                             "field_id": e.get("field_id"), "status": e["status"],
                             "label": e.get("label"), "observed_at": RUN},
                            ensure_ascii=False, sort_keys=True) + "\n")

# ============================================================ 4) 台账 manifest.jsonl
MAN = f"{KB}/manifest.jsonl"
prev = {}
if os.path.exists(MAN):
    for line in open(MAN, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            prev[r["resource_key"]] = r
rows, change = [], collections.Counter()
for e in R:
    key, old = e["resource_key"], prev.get(e["resource_key"])
    moved_from = None
    if old is None:
        status = "registered"
        for pk, pv in prev.items():
            if e["sha256"] and pv.get("sha256") == e["sha256"] and pk != key:
                moved_from = pk
                break
        change["new"] += 1
    elif e["sha256"] and old.get("sha256") == e["sha256"]:
        status, change["unchanged"] = "unchanged", change["unchanged"] + 1
    elif e["sha256"] and old.get("sha256") != e["sha256"]:
        status, change["updated"] = "updated", change["updated"] + 1
    else:
        status, change["unchanged"] = "unchanged", change["unchanged"] + 1
    rows.append({"resource_key": key, "source_kind": e["source_kind"], "table_name": e["table_name"],
                 "table_id": e["table_id"], "record_id": e["record_id"], "field_name": e["field_name"],
                 "field_id": e["field_id"], "entry_url": e["entry_url"], "path": e["path"],
                 "depth": e["depth"], "kb_type": e["kb_type"], "matched_rule": e["matched_rule"],
                 "sha256": e["sha256"], "sha256_input": e["sha256_input"],
                 "sha256_state": e["sha256_state"], "revision": e["revision"], "dup_of": e["dup_of"],
                 "moved_from": moved_from, "status": status, "status_reason": e["status_reason"] or "",
                 "downstream_invalidated": status in ("registered", "updated", "retracted", "gone"),
                 "observed_at": RUN, "scanner_version": SCANNER})
with open(MAN, "a", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
latest = {}
for line in open(MAN, encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        latest[r["resource_key"]] = r

# ============================================================ 5) 索引（台账投影）
with open(f"{KB}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(latest):
        r = latest[k]
        fh.write(json.dumps({"resource_key": r["resource_key"], "kb_type": r["kb_type"],
                             "source_kind": r["source_kind"], "status": r["status"],
                             "entry_url": r["entry_url"]}, ensure_ascii=False, sort_keys=True) + "\n")

# ============================================================ 6) 候选切片
cand = {"candidate_id": RUN, "as_of_observed_at": RUN, "resource_count": len(latest),
        "counts_by_kb_type": dict(collections.Counter(r["kb_type"] for r in latest.values())),
        "counts_by_status": dict(collections.Counter(r["status"] for r in latest.values())),
        "change_summary": {"new": change.get("new", 0), "updated": change.get("updated", 0),
                           "retracted": change.get("retracted", 0), "gone": change.get("gone", 0),
                           "unchanged": change.get("unchanged", 0)},
        "excluded_records": len(b["excluded"]),
        "note": "未验收，不可作为最终依据；不含版本号"}
with open(f"{KB}/candidates/{RUN}.json", "w", encoding="utf-8") as fh:
    json.dump(cand, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

json.dump({"latest": latest, "written": {k: list(v) for k, v in written.items()},
           "collisions": {str(k): v for k, v in collisions.items()},
           "change": dict(change), "cand": cand, "n_rec_files": n_rec_files},
          open("kb/.work/emit2_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"资源文件 {len(written)} | 记录文件 {n_rec_files} | 台账新增 {len(rows)} 行 | 最新台账 {len(latest)}")
print("文件名冲突:", collisions or "无")
print("变更:", dict(change))
print("库分布:", cand["counts_by_kb_type"])
