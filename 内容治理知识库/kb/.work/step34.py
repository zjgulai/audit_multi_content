#!/usr/bin/env python3
"""L0 落库 · 步骤 3/4/5(第一层): 冻结筛选快照、字段原值落库、抽取 link 字段。"""
import json, os, re, hashlib, sys, datetime

KB = "kb/l0"
RUN = sys.argv[1]
TZ = "Asia/Shanghai"
ENTRY = {"space": "momcozy-in.feishu.cn", "base_token": "GnRZbIuXraCzf0sGr2UcmZ62nfc",
         "table_id": "tblMGtPfe8ZUsEdP", "view_id": "vewHCQJrgo", "table_name": "材料收集"}
SRC_KIND = "feishu_bitable_record"

LINK_RE = re.compile(r'\[(?P<text>.*?)\]\((?P<url>https?://[^\)\s]+)\)', re.S)
BARE_RE = re.compile(r'(?<!\()(?P<url>https?://[^\s\)\]]+)')

def norm_text(s):
    """normalization: utf-8 / LF / 去行尾空格 / 折叠空行"""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def sha(txt):
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()

def canon(obj):
    """sort_keys 确定性序列化"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def extract_links(raw):
    """返回 [(text, url)]，保持出现顺序"""
    if not raw:
        return []
    out = [(m.group("text"), m.group("url")) for m in LINK_RE.finditer(raw)]
    if not out:
        out = [("", m.group("url")) for m in BARE_RE.finditer(raw)]
    return out

def url_kind(u):
    """按 URL 路径形态做轻量判断（仅作 routing 提示，最终以 +inspect 为准）"""
    m = re.search(r'feishu\.cn/(wiki|base|sheets|slides|file|docx|docs|drive/folder|record)/', u)
    if not m:
        return "url"
    seg = m.group(1)
    return {"wiki": "wiki", "base": "base", "sheets": "sheets", "slides": "slides",
            "file": "file", "docx": "docx", "docs": "docs", "drive/folder": "folder",
            "record": "record"}.get(seg, "url")

def _formula_expr(f):
    """公式/查找字段的表达式（原样取自 schema，不自行解释）"""
    t = f.get("type")
    if t == "formula":
        return f.get("expression") or f.get("formula") or (f.get("property") or {}).get("expression")
    if t == "lookup":
        return {"lookup_from_table": f.get("from"), "lookup_field": f.get("select"),
                "where": f.get("where"), "aggregate": f.get("aggregate")}
    return None

def _formula_deps(f):
    """依赖字段 id 列表：把表达式/where 里引用的字段名解析成 field_id"""
    names = set()
    if f.get("type") == "formula":
        expr = f.get("expression") or f.get("formula") or ""
        names |= set(re.findall(r'\{([^}]+)\}', expr or ""))
        names |= set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', expr or ""))
    if f.get("type") == "lookup":
        for cond in ((f.get("where") or {}).get("conditions") or []):
            for part in cond:
                if isinstance(part, dict) and part.get("type") == "field_ref":
                    names.add(part.get("field"))
        if f.get("select"):
            names.add(f["select"])
    deps = []
    for n in sorted(names):
        if n in meta_by_name:
            deps.append({"field_name": n, "field_id": meta_by_name[n]["id"]})
    return deps

# ---------- 读取原始记录 ----------
raw_rows = [json.loads(l) for l in open("kb/.work/材料收集.ndjson", encoding="utf-8") if l.strip()]
fields_meta = json.load(open("kb/.work/fields-tblMGtPfe8ZUsEdP.json", encoding="utf-8"))["data"]["fields"]
fname_by_id = {f["id"]: f["name"] for f in fields_meta}
meta_by_name = {f["name"]: f for f in fields_meta}

STATUS_FIELD = "材料审核状态"
APPROVED = "通过"

matched, excluded = [], []
for r in raw_rows:
    rid = r["record_id"]
    st = r.get(STATUS_FIELD)
    vals = st if isinstance(st, list) else ([] if st in (None, "") else [st])
    if not vals:
        excluded.append((rid, "no_status"))
    elif APPROVED in vals:
        matched.append(rid)
    else:
        excluded.append((rid, "status_not_passed"))

os.makedirs(f"{KB}/records/{ENTRY['table_name']}", exist_ok=True)

# ---------- 字段原值落库 ----------
FORMULA_TYPES = {"formula", "lookup"}
for r in raw_rows:
    rid = r["record_id"]
    rid_fields, formula_fields, link_fields, att_fields = {}, {}, [], []
    for f in fields_meta:
        nm, fid, ftype = f["name"], f["id"], f["type"]
        val = r.get(nm)
        role = _role = None
        if ftype in FORMULA_TYPES:
            dep = _formula_deps(f)
            formula_fields[nm] = {
                "field_id": fid, "field_type": ftype,
                "expression": _formula_expr(f),
                "depends_on_fields": dep,
                "value_snapshot": val,
                "snapshot_note": "公式/查找引用字段不存值，仅存本次求值快照",
            }
            rid_fields[nm] = {"field_id": fid, "field_type": ftype, "value": None,
                              "stored_as": "formula_snapshot", "raw_verbatim": val}
        else:
            rid_fields[nm] = {"field_id": fid, "field_type": ftype, "value": val,
                              "raw_verbatim": val}
    rec = {
        "record_id": rid,
        "table_id": ENTRY["table_id"],
        "table_name": ENTRY["table_name"],
        "base_token": ENTRY["base_token"],
        "entry_url": f"https://{ENTRY['space']}/base/{ENTRY['base_token']}?table={ENTRY['table_id']}&view={ENTRY['view_id']}&record={rid}",
        "source_kind": SRC_KIND,
        "timezone": "Asia/Shanghai",
        "observed_at": RUN,
        "filter": {"field": STATUS_FIELD, "expected": APPROVED,
                   "result": "matched" if rid in matched else "excluded",
                   "reason": "" if rid in matched else dict(excluded).get(rid)},
        "fields": rid_fields,
        "formula_and_lookup_fields": formula_fields,
        "raw_record": r,
        "note": "字段原值 verbatim 保留；日期保留原始时间戳与时区；单选/多选同时保留选项 id（见 raw_record）。",
    }
    with open(f"{KB}/records/{ENTRY['table_name']}/{rid}.json", "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

# ---------- 抽取 link 字段 ----------
link_items = []
for r in raw_rows:
    if r["record_id"] not in matched:
        continue
    raw = r.get("材料链接") or ""
    for text, url in extract_links(raw):
        link_items.append({
            "record_id": r["record_id"], "field_name": "材料链接", "field_id": "fldr4c8nnT",
            "anchor_text": text, "url": url, "url_kind": url_kind(url),
            "kb_type_hint": r.get("知识库分类") or [],
        })

snapshot = {
    "run_id": RUN,
    "entry": {"url": f"https://{ENTRY['space']}/base/{ENTRY['base_token']}?table={ENTRY['table_id']}&view={ENTRY['view_id']}",
              "base_token": ENTRY["base_token"], "table_id": ENTRY["table_id"],
              "table_name": ENTRY["table_name"], "view_id": ENTRY["view_id"]},
    "filter_condition": {"field": STATUS_FIELD, "operator": "==", "value": APPROVED,
                         "raw_option_set": ["待审核", "通过", "暂不采用", ""],
                         "checked_at": RUN, "timezone": TZ},
    "snapshot_time": RUN,
    "snapshot_time_tz": TZ,
    "records_total_in_table": len(raw_rows),
    "matched_count": len(matched),
    "excluded_count": len(excluded),
    "matched_record_ids": matched,
    "excluded_records": [{"record_id": i, "reason": c} for i, c in excluded],
    "excluded_reason_legend": {
        "no_status": "材料审核状态为空，不满足筛选条件，先不处理",
        "status_not_passed": "材料审核状态不为「通过」，不满足筛选条件，先不处理",
    },
    "drill_down": {"max_depth": 2, "rule_extraction_depth": 2},
    "link_items_extracted": link_items,
}
with open(f"{KB}/runs/{RUN}.json", "w", encoding="utf-8") as fh:
    json.dump(snapshot, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

with open("kb/.work/links-l1.json", "w", encoding="utf-8") as fh:
    json.dump(link_items, fh, ensure_ascii=False, indent=2)

print(f"matched={len(matched)} excluded={len(excluded)} links_l1={len(link_items)}")
