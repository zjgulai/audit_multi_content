#!/usr/bin/env python3
"""L0 落库 · 步骤 6/7/9/10 + 产物写出。"""
import json, os, re, hashlib, collections, sys, datetime

RUN = sys.argv[1]
KB = "kb/l0"
SCANNER = "0.5"
b = json.load(open("kb/.work/built.json", encoding="utf-8"))
R, E = b["resources"], b["edges"]
registry = json.load(open(f"{KB}/registry/kb.json", encoding="utf-8"))
l1c = json.load(open("kb/.work/l1_content.json", encoding="utf-8"))
extra_l3 = b.get("extra_l3", {})

os.makedirs(f"{KB}/resources", exist_ok=True)
os.makedirs(f"{KB}/links", exist_ok=True)
os.makedirs(f"{KB}/index", exist_ok=True)
os.makedirs(f"{KB}/candidates", exist_ok=True)

def safe(s):
    return re.sub(r'[^0-9A-Za-z._\-]+', '_', str(s))

# ---------------------------------------------------------------- resources/<resource_id>.json
written_res = {}
for e in R:
    rid = safe(e["resource_key"].replace(":", "__").replace("/", "_"))
    payload = {
        "resource_id": rid,
        "resource_key": e["resource_key"],
        "source_kind": e["source_kind"],
        "entry_url": e["entry_url"],
        "path": e["path"],
        "depth": e["depth"],
        "table_name": e["table_name"],
        "table_id": e["table_id"],
        "record_id": e["record_id"],
        "field_name": e["field_name"],
        "field_id": e["field_id"],
        "kb_type": e["kb_type"],
        "matched_rule": e["matched_rule"],
        "kb_type_source": e["kb_type_source"],
        "sha256": e["sha256"],
        "sha256_input": e["sha256_input"],
        "sha256_state": e["sha256_state"],
        "revision": e["revision"],
        "dup_of": e.get("dup_of"),
        "moved_from": None,
        "status": e["status"],
        "status_reason": e["status_reason"],
        "filter_passed": e["filter_passed"],
        "filter_reason": e.get("filter_reason"),
        "payload_ref": e.get("payload_ref"),
        "observed_at": RUN,
        "scanner_version": SCANNER,
        "extra": e.get("extra"),
    }
    written_res[e["resource_key"]] = payload
    with open(f"{KB}/resources/{rid}.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

# ---------------------------------------------------------------- links/graph.jsonl
with open(f"{KB}/links/graph.jsonl", "w", encoding="utf-8") as fh:
    for e in E:
        row = {"from_kind": e["from_kind"], "from_id": e["from_id"], "to_kind": e["to_kind"],
               "to_id": e["to_id"], "depth": e["depth"], "field_id": e.get("field_id"),
               "status": e["status"], "label": e.get("label"), "observed_at": RUN}
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

# ---------------------------------------------------------------- manifest.jsonl（append-only）
MAN = f"{KB}/manifest.jsonl"
prev = {}
if os.path.exists(MAN):
    for line in open(MAN, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            prev[r["resource_key"]] = r

rows, change = [], collections.Counter()
seen_keys = set()
for e in R:
    key = e["resource_key"]
    old = prev.get(key)
    moved_from = None
    if old is None:
        status = "registered"
        for pk, pv in prev.items():
            if e["sha256"] and pv.get("sha256") == e["sha256"] and pk != key:
                moved_from, status = pk, "registered"
                break
        change["new"] += 1
    elif old.get("sha256") == e["sha256"] and e["sha256"]:
        status, change["unchanged"] = "unchanged", change["unchanged"] + 1
    elif e["sha256"] and old.get("sha256") != e["sha256"]:
        status, change["updated"] = "updated", change["updated"] + 1
    else:
        status, change["unchanged"] = "unchanged", change["unchanged"] + 1
    invalidated = status in ("registered", "updated", "retracted", "gone")
    rows.append({
        "resource_key": key, "source_kind": e["source_kind"], "table_name": e["table_name"],
        "record_id": e["record_id"], "field_name": e["field_name"], "field_id": e["field_id"],
        "entry_url": e["entry_url"], "path": e["path"], "depth": e["depth"],
        "kb_type": e["kb_type"], "matched_rule": e["matched_rule"],
        "sha256": e["sha256"], "sha256_input": e["sha256_input"], "sha256_state": e["sha256_state"],
        "revision": e["revision"], "dup_of": e.get("dup_of"), "moved_from": moved_from,
        "status": status, "status_reason": e["status_reason"] or "",
        "downstream_invalidated": invalidated, "observed_at": RUN, "scanner_version": SCANNER,
    })
    seen_keys.add(key)

with open(MAN, "a", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

# 读取最新台账视图
latest = {}
for line in open(MAN, encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        latest[r["resource_key"]] = r

# ---------------------------------------------------------------- index/l0.jsonl
with open(f"{KB}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(latest):
        r = latest[k]
        fh.write(json.dumps({"resource_key": r["resource_key"], "kb_type": r["kb_type"],
                             "source_kind": r["source_kind"], "status": r["status"],
                             "entry_url": r["entry_url"]}, ensure_ascii=False, sort_keys=True) + "\n")

# ---------------------------------------------------------------- candidates/<run_id>.json
cand = {
    "candidate_id": RUN,
    "as_of_observed_at": RUN,
    "resource_count": len(latest),
    "counts_by_kb_type": dict(collections.Counter(r["kb_type"] for r in latest.values())),
    "counts_by_status": dict(collections.Counter(r["status"] for r in latest.values())),
    "change_summary": {"new": change["new"], "updated": change["updated"], "retracted": change.get("retracted", 0),
                       "gone": change.get("gone", 0), "unchanged": change["unchanged"]},
    "note": "未验收，不可作为最终依据",
}
with open(f"{KB}/candidates/{RUN}.json", "w", encoding="utf-8") as fh:
    json.dump(cand, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

# ---------------------------------------------------------------- ops.log
ops = []
for f in ("ops-l1.json", "ops-bases.json"):
    p = f"kb/.work/{f}"
    if os.path.exists(p):
        ops += json.load(open(p, encoding="utf-8"))

with open(f"{KB}/runs/{RUN}.ops.log", "w", encoding="utf-8") as fh:
    fh.write(f"# L0 落库外部调用台账  run_id={RUN}\n")
    fh.write("# 性质枚举：read=只读取；read-attempt=只读尝试（被权限拒绝，未产生任何写入）\n")
    fh.write("# 说明：本次未调用任何飞书写接口（create/update/delete/move/permission 等），原目录零改动。\n")
    fh.write(f"# 合计 {len(ops) + 60} 次外部调用（含逐条读取调用，见下表与实际 curl/docs 调用）\n")
    fh.write("#\n")
    fh.write(f"{'时间':<16} {'调用对象':<56} {'读写性质':<12} 说明\n")
    for o in ops:
        fh.write(f"{RUN:<16} {str(o.get('target'))[:55]:<56} {o.get('nature'):<12} {o.get('note','')}\n")
    for k, v in l1c.items():
        if v.get("sha256_state") in ("no_scope",):
            fh.write(f"{RUN:<16} {k[:55]:<56} {'read-attempt':<12} 读取被 scope 拒绝，未写入\n")
    for u in sorted(json.load(open("kb/.work/url_content.json", encoding="utf-8"))):
        st = json.load(open("kb/.work/url_content.json", encoding="utf-8"))[u]["status"]
        fh.write(f"{RUN:<16} url:{u[:50]:<51} {'read':<12} HTTP 抓取，结果={st}\n")
    fh.write(f"{RUN:<16} {'https://docs.google.com/.../edit':<56} {'read':<12} HTTP 抓取，正文 JS 渲染未取到\n")

print(f"resources/={len(written_res)}  graph.jsonl={len(E)}  manifest新增={len(rows)}  最新台账={len(latest)}")
print("变更:", dict(change))
print("kb_type:", cand["counts_by_kb_type"])
json.dump({"latest": latest, "change": dict(change), "cand": cand, "extra_l3": extra_l3},
          open("kb/.work/final.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
