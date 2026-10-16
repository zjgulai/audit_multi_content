#!/usr/bin/env python3
"""第 3/4/5 项：把增量追加进 L0（资源文件 + 台账 + 边 + index），并更新 registry 采样策略。"""
import json, os, re, hashlib, collections, sys, glob

RUN = sys.argv[1]
L0 = "kb/l0"
SCANNER = "0.5"
BASE_E = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
ENUM = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))
delta = json.load(open("kb/.work/b2_l0_delta.json", encoding="utf-8"))
registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def fname(e):
    return f"{e['source_kind']}__" + re.sub(r'[^0-9A-Za-z._\-]+', '_',
            e["resource_key"].split(":", 1)[1].replace(":", "__").replace("/", "_"))[:150] + ".json"

# ---------- 1) 资源文件（表/记录）
added_files = []
for e in delta["new_res"]:
    d = REV[e["kb_type"]]
    p = f"{L0}/{d}/{fname(e)}"
    if os.path.exists(p):
        print("  跳过已存在:", p); continue
    payload = {"resource_key": e["resource_key"], "source_kind": e["source_kind"],
               "kb_type": e["kb_type"], "matched_rule": e["matched_rule"],
               "kb_type_source": e["kb_type_source"],
               "source": {"table_name": e["table_name"], "table_id": e["table_id"],
                          "record_id": e["record_id"], "field_name": None, "field_id": None},
               "entry_url": e["entry_url"], "path": e["path"], "depth": e["depth"],
               "sha256": e["sha256"], "sha256_input": e["sha256_input"],
               "sha256_state": e["sha256_state"], "revision": None, "dup_of": None, "moved_from": None,
               "status": e["status"], "status_reason": "", "filter_passed": None,
               "observed_at": RUN, "scanner_version": SCANNER, "extra": e.get("extra")}
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2); fh.write("\n")
    added_files.append((p, e))

# ---------- 2) URL 资源（不设上限）+ 边
# 建立 record -> (table_name, table_id, kb_type, base) 映射，用于 URL 归属
rec_meta = {}
for bt, e in ENUM.items():
    for t in e["tables"]:
        for r in t["records"]:
            rec_meta[f"bitable:{bt}:{r['record_id']}"] = {
                "table_name": t["table_name"], "table_id": t["table_id"], "base": bt}
latest = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); latest[r["resource_key"]] = r
for k, v in rec_meta.items():
    if k in latest:
        rec_meta[k]["kb_type"] = latest[k]["kb_type"]
        rec_meta[k]["matched_rule"] = latest[k]["matched_rule"]

url_res, edges = [], []
for u, info in delta["new_urls"]:
    fs = info["first_seen"]
    rk_rec = f"bitable:{fs.get('base_token') or ''}:{fs['record_id']}" if fs.get("base_token") else \
             next((k for k in rec_meta if k.endswith(f":{fs['record_id']}")), None)
    meta = rec_meta.get(rk_rec, {}) if rk_rec else {}
    kt = meta.get("kb_type", "unknown")
    table_name = fs["table"]
    urls = u if len(u) < 300 else u[:300]
    ek = f"url:{u}"
    url_res.append(dict(resource_key=ek, source_kind="url", table_name=table_name,
        table_id=meta.get("table_id"), record_id=fs["record_id"], field_name=fs["field"],
        field_id=None, entry_url=u, path=f"[内容治理/放开截断后补登记/{table_name}/{fs['field']}]",
        depth=2, kb_type=kt, matched_rule=meta.get("matched_rule"),
        kb_type_source=f"继承所属记录的归属（{table_name}）",
        sha256=None, sha256_input="url_text", sha256_state="not_fetched", revision=None,
        status="registered", status_reason="放开数量上限后补登记；本轮未抓取正文（不抽取新内容），正文抓取留待 L1",
        filter_passed=None,
        extra={"ref_count": info["ref_count"], "backfill_reason": "URL 字段取消数量上限",
               "first_seen": fs}))
    edges.append({"from_kind": "feishu_bitable_record", "from_id": f"record:{fs['record_id']}",
                  "to_kind": "url", "to_id": ek, "depth": 2, "field_id": None,
                  "status": "ok", "label": fs["field"]})

for e in url_res:
    d = REV[e["kb_type"]]
    p = f"{L0}/{d}/{fname(e)}"
    if os.path.exists(p):
        print("  跳过已存在:", p); continue
    payload = {"resource_key": e["resource_key"], "source_kind": e["source_kind"],
               "kb_type": e["kb_type"], "matched_rule": e["matched_rule"],
               "kb_type_source": e["kb_type_source"],
               "source": {"table_name": e["table_name"], "table_id": e["table_id"],
                          "record_id": e["record_id"], "field_name": e["field_name"], "field_id": None},
               "entry_url": e["entry_url"], "path": e["path"], "depth": e["depth"],
               "sha256": None, "sha256_input": "url_text", "sha256_state": "not_fetched",
               "revision": None, "dup_of": None, "moved_from": None, "status": "registered",
               "status_reason": e["status_reason"], "filter_passed": None,
               "observed_at": RUN, "scanner_version": SCANNER, "extra": e.get("extra")}
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2); fh.write("\n")
    added_files.append((p, e))

# ---------- 3) 边追加到 links/graph.jsonl（append-only）
GP = f"{L0}/links/graph.jsonl"
with open(GP, "a", encoding="utf-8") as fh:
    for e in edges:
        fh.write(json.dumps({"from_kind": e["from_kind"], "from_id": e["from_id"],
                             "to_kind": e["to_kind"], "to_id": e["to_id"], "depth": e["depth"],
                             "field_id": e["field_id"], "status": e["status"],
                             "label": e["label"], "observed_at": RUN},
                            ensure_ascii=False, sort_keys=True) + "\n")
print(f"边追加 {len(edges)} 条")

# ---------- 4) 台账追加
prev = latest
rows, change = [], collections.Counter()
allnew = delta["new_res"] + url_res
for e in allnew:
    key = e["resource_key"]
    old = prev.get(key)
    if old is None:
        st = "registered"; change["new"] += 1
    elif e["sha256"] and old.get("sha256") == e["sha256"]:
        st = "unchanged"; change["unchanged"] += 1
    elif e["sha256"] and old.get("sha256") != e["sha256"]:
        st = "updated"; change["updated"] += 1
    else:
        st = "unchanged"; change["unchanged"] += 1
    rows.append({"resource_key": key, "source_kind": e["source_kind"], "table_name": e["table_name"],
                 "table_id": e["table_id"], "record_id": e["record_id"], "field_name": e["field_name"],
                 "field_id": e["field_id"], "entry_url": e["entry_url"], "path": e["path"],
                 "depth": e["depth"], "kb_type": e["kb_type"], "matched_rule": e["matched_rule"],
                 "sha256": e["sha256"], "sha256_input": e["sha256_input"],
                 "sha256_state": e["sha256_state"], "revision": None, "dup_of": None,
                 "moved_from": None, "status": st, "status_reason": e.get("status_reason") or "",
                 "downstream_invalidated": st in ("registered", "updated", "retracted", "gone"),
                 "observed_at": RUN, "scanner_version": SCANNER})
with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

allm = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); allm[r["resource_key"]] = r

# ---------- 5) index 重建
with open(f"{L0}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(allm):
        r = allm[k]
        fh.write(json.dumps({"resource_key": r["resource_key"], "kb_type": r["kb_type"],
                             "source_kind": r["source_kind"], "status": r["status"],
                             "entry_url": r["entry_url"]}, ensure_ascii=False, sort_keys=True) + "\n")

# ---------- 6) registry 追加采样策略变更 + 源侧已知问题
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
reg.setdefault("sampling_policy", {})
reg["sampling_policy"] = {
    "default_record_limit_per_table": 200,
    "exempt_tables_full_scan": ["专家修订汇总表", "广告文案明细"],
    "url_field_limit": None,
    "changed_at": RUN,
    "reason": "截断丢掉的是核心素材：「专家修订前→后」成对语料、广告文案 27 字段明细、"
              "以及 URL 字段里指向内部标准原文的飞书 wiki 节点。",
    "history": [{"at": "20260923-1117", "policy": "200/表；URL 建边采样 60"},
                {"at": RUN, "policy": "专家修订汇总表/广告文案明细 全量；URL 不设上限；其余表维持 200"}],
}
reg.setdefault("source_issues", []).append({
    "issue_id": "SI-001",
    "title": "视图筛选指向已不存在的字段值",
    "detail": "「正面和负面样本」(tbld8qE92YaY38Yz) 两个视图都按 `备注（如处理结果/建议）` 筛选："
              "vewHHtXyx0 为 `!= \"样例\"`，vewSn5HboA 为 `== \"样例\"`。"
              "实测 125/125 行该字段都不含「样例」（值形如 `价值评分: 14；参与审核: 吴礼芳, 贺美霞`），"
              "故「样例」视图应为空、「表格」视图应显示全部 125 条。",
    "field": "备注（如处理结果/建议）", "table_id": "tbld8qE92YaY38Yz",
    "views": ["vewHHtXyx0", "vewSn5HboA"],
    "action": "只记录，未修改任何视图或筛选条件（硬约束 1）",
    "impact": "该字段被批量覆盖过 → 定时重跑时该字段会产生大量 `updated`，**属预期，不是异常**",
    "operator_hint": "评估变更时请把 `备注（如处理结果/建议）` 的差异排除在异常清单之外",
    "recorded_at": RUN,
})
reg.setdefault("changes", []).append({"run_id": RUN, "change": "append",
    "keys": ["sampling_policy", "source_issues[]"],
    "note": "仅追加新键；既有键未修改"})
with open(f"{L0}/registry/kb.json", "w", encoding="utf-8") as fh:
    json.dump(reg, fh, ensure_ascii=False, indent=2); fh.write("\n")

json.dump({"added_files": len(added_files), "manifest_appended": len(rows),
           "edges_appended": len(edges), "latest_rows": len(allm),
           "change": dict(change), "by_table": delta["by_table"],
           "url_new": len(url_res),
           "manifest_sha_before": delta["manifest_sha_before"],
           "before_lines": delta["before_lines"],
           "before_files": delta["before_files"]},
          open("kb/.work/b2_l0_emit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"资源文件追加 {len(added_files)} | 台账追加 {len(rows)} 行 | 最新台账 {len(allm)}")
print("按库新增:", dict(collections.Counter(e['kb_type'] for e in allnew)))
