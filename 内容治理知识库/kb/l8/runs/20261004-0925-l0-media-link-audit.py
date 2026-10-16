#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L0 媒体/链接覆盖只读审计（kb-l0-feishu 阶段 5/8 的只读核验）

输入：本轮 align 快照 kb/l8/_stage/feishu-align/<RUN>/<table>.ndjson
      kb/l0/manifest.jsonl（台账）、kb/l0/attachments/（磁盘）
输出：/tmp/<RUN>-l0-media-link-audit.json（再由外层 /bin/cp 落 kb/l8/runs/）

只读：不写 L0、不写台账、不调飞书写接口。
"""
import json, os, re, sys, glob, collections

RUN = sys.argv[1]
KB = "kb"
SNAP = f"{KB}/l8/_stage/feishu-align/{RUN}"
OUT = f"/tmp/{RUN}-l0-media-link-audit.json"

IMG_INLINE_RE = re.compile(r"img_v3_[A-Za-z0-9_\-]{6,}")
URL_RE = re.compile(r"https?://[^\s\)\(\[\]\{\}\"'，。；、）】》]+")
FEISHU_HOST_RE = re.compile(r"^https?://[^/]*feishu\.(cn|com)", re.I)


def walk_strings(obj):
    """产出 (path, string) —— path 形如 字段名 或 字段名[i].name"""
    if isinstance(obj, str):
        yield "", obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            for p, s in walk_strings(v):
                yield (f"{k}.{p}" if p else str(k)), s
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            for p, s in walk_strings(v):
                yield (f"[{i}].{p}" if p else f"[{i}]"), s


def is_attach_item(v):
    return isinstance(v, dict) and "file_token" in v


# ---------- 1. 台账 ----------
rows = [json.loads(l) for l in open(f"{KB}/l0/manifest.jsonl", encoding="utf-8") if l.strip()]
latest = {}
token_status = collections.defaultdict(collections.Counter)
ledger_tokens = set()
url_keys = set()
ledger_obj_tokens = collections.Counter()
for r in rows:
    rk = r.get("resource_key") or ""
    latest[rk] = r
    kind = rk.split(":", 1)[0]
    if kind == "bitable" and r.get("source_kind") == "feishu_attachment":
        parts = rk.split("/")
        tok = parts[-1] if parts else ""
        ledger_tokens.add(tok)
        token_status[tok][r.get("status")] += 1
    if kind == "url":
        url_keys.add(rk[len("url:"):])
    # 对象类 token（wiki / slides / sheets / docx / file）
    for pref in ("wiki:", "slides:", "sheets:", "docx:", "file:", "bitable:"):
        if rk.startswith(pref):
            ledger_obj_tokens[rk.split(":", 1)[1].split("/")[0]] += 1

# ---------- 2. 快照 ----------
per_table = {}
attach_all = collections.defaultdict(list)   # token -> [ctx]
attach_field_counter = collections.Counter()
video_items = 0
inline_tokens = collections.Counter()
inline_records = collections.defaultdict(set)
all_urls = collections.Counter()
url_ctx = collections.defaultdict(set)
records_total = 0

for path in sorted(glob.glob(f"{SNAP}/*.ndjson")):
    table_id = os.path.basename(path)[:-len(".ndjson")]
    n = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        n += 1
        rid = d.get("record_id")
        for k, v in d.items():
            if k == "record_id":
                continue
            if isinstance(v, list) and v and all(is_attach_item(x) for x in v):
                for it in v:
                    tok = it.get("file_token")
                    name = it.get("name") or ""
                    attach_field_counter[f"{table_id}|{k}"] += 1
                    attach_all[tok].append({
                        "table_id": table_id, "record_id": rid, "field": k,
                        "file_token": tok, "name": name, "size": it.get("size"),
                        "ext": os.path.splitext(name)[1].lower(),
                    })
                    if k == "视频素材" or os.path.splitext(name)[1].lower() in (
                            ".mp4", ".mov", ".avi", ".m4v", ".webm"):
                        video_items += 1
            for p, s in walk_strings(v):
                for m in IMG_INLINE_RE.findall(s):
                    inline_tokens[m] += 1
                    inline_records[m].add((table_id, rid))
                for m in URL_RE.findall(s):
                    u = m.rstrip(".,);]")
                    all_urls[u] += 1
                    url_ctx[u].add((table_id, rid, k))
    per_table[table_id] = {"records": n, "attach_items": 0}
    records_total += n

for ctxs in attach_all.values():
    for c in ctxs:
        per_table[c["table_id"]]["attach_items"] += 1

# ---------- 3. 附件覆盖 ----------
disk_files = {}
for root, dirs, files in os.walk(f"{KB}/l0/attachments"):
    for f in files:
        if f == "_MANIFEST.json":
            continue
        tok = os.path.splitext(f)[0]
        disk_files[tok] = os.path.join(root, f)

attach_total = sum(len(v) for v in attach_all.values())
att_missing_ledger, att_missing_disk, att_gone = [], [], []
for tok, ctxs in attach_all.items():
    if tok not in ledger_tokens:
        att_missing_ledger.append({"token": tok, "ctx": ctxs[:3], "n_ref": len(ctxs)})
    if tok not in disk_files:
        att_missing_disk.append({"token": tok, "ctx": ctxs[:3], "n_ref": len(ctxs)})
    st = token_status.get(tok)
    if st and (st.get("gone") or st.get("retracted")):
        att_gone.append({"token": tok, "status": dict(st), "ctx": ctxs[:1]})

# ---------- 4. 内嵌图 ----------
inline_by_record = collections.Counter()
for tok, recs in inline_records.items():
    for r in recs:
        inline_by_record[r[1]] += 1
inline_in_ledger = sorted(t for t in inline_tokens if t in ledger_tokens)
inline_on_disk = sorted(t for t in inline_tokens if t in disk_files)

# ---------- 5. 链接 ----------
def norm(u):
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.split("#")[0].rstrip("/")
    return u.lower()

ledger_url_norm = {norm(u) for u in url_keys}
ledger_token_set = set(ledger_obj_tokens)
feishu_urls, ext_urls = [], []
for u in all_urls:
    (feishu_urls if FEISHU_HOST_RE.match(u) else ext_urls).append(u)

feishu_tokens = {}
for u in feishu_urls:
    m = re.search(r"/(wiki|docx|docs|sheets|slides|base|file)/([A-Za-z0-9]+)", u)
    if m:
        feishu_tokens[u] = m.group(2)
    else:
        m2 = re.search(r"/([A-Za-z0-9]{20,})", u)
        feishu_tokens[u] = m2.group(1) if m2 else None

url_missing = [u for u in all_urls if norm(u) not in ledger_url_norm]
url_missing_ext = [u for u in url_missing if not FEISHU_HOST_RE.match(u)]
url_missing_feishu = [u for u in url_missing if FEISHU_HOST_RE.match(u)]
feishu_token_unresolved = [u for u in url_missing_feishu
                           if not any(t and t in ledger_token_set for t in [feishu_tokens.get(u)])]

result = {
    "run": RUN,
    "snapshot": SNAP,
    "tables": per_table,
    "records_total": records_total,
    "attach": {
        "items_total": attach_total,
        "unique_tokens": len(attach_all),
        "by_table_field": dict(attach_field_counter),
        "registered_in_ledger": attach_total - len(att_missing_ledger),
        "missing_in_ledger_count": len(att_missing_ledger),
        "missing_in_ledger": att_missing_ledger[:50],
        "on_disk_tokens": sum(1 for t in attach_all if t in disk_files),
        "missing_on_disk_count": len(att_missing_disk),
        "missing_on_disk": att_missing_disk[:50],
        "disk_status_gone": att_gone[:20],
        "disk_files_total": len(disk_files),
    },
    "video": {"items_total": video_items},
    "inline_img": {
        "unique_tokens": len(inline_tokens),
        "occurrences": sum(inline_tokens.values()),
        "records": len(inline_by_record),
        "in_ledger": len(inline_in_ledger),
        "on_disk": len(inline_on_disk),
        "sample": list(inline_tokens)[:5],
    },
    "links": {
        "unique_urls": len(all_urls),
        "feishu_domain": len(feishu_urls),
        "external": len(ext_urls),
        "missing_total": len(url_missing),
        "missing_external": len(url_missing_ext),
        "missing_feishu": len(url_missing_feishu),
        "missing_external_list": url_missing_ext,
        "missing_feishu_unresolved_by_node_token": feishu_token_unresolved,
        "missing_feishu_list": url_missing_feishu,
    },
    "ledger": {
        "rows": len(rows),
        "attachment_unique_keys": len(ledger_tokens),
        "url_keys": len(url_keys),
    },
}
os.makedirs("/tmp", exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print(json.dumps({
    "attach_items": result["attach"]["items_total"],
    "attach_unique": result["attach"]["unique_tokens"],
    "attach_missing_ledger": result["attach"]["missing_in_ledger_count"],
    "attach_missing_disk": result["attach"]["missing_on_disk_count"],
    "video_items": video_items,
    "inline_tokens": result["inline_img"]["unique_tokens"],
    "inline_records": result["inline_img"]["records"],
    "inline_in_ledger": result["inline_img"]["in_ledger"],
    "urls": result["links"]["unique_urls"],
    "url_missing": result["links"]["missing_total"],
    "url_missing_ext": result["links"]["missing_external"],
    "url_missing_feishu": result["links"]["missing_feishu"],
    "out": OUT,
}, ensure_ascii=False, indent=1))
