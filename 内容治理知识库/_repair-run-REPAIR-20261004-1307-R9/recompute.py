#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 9 轮 kb-repair：②③ 两项复算（只读，不采信 workflow-check-known-drift.yaml 的任何自述）。

复算四件事：
  (1) L3 算术：现行行数 / 整文件 sha / 两条前缀哈希，与两条基线对照。
  (2) ③ 来源审计：扫 kb/l{3,4,5,6,7}/runs/*.json 的 artifacts[]，查 20 项 mismatch 的现 sha 有无 run 记录出处。
  (3) 20 项 mismatch 的存在性实测：逐个 os.path.exists（区分「改了」与「没了」）。
  (4) l7.json 逐字段比对：与 pre-edit 备份对照。
写盘：无（只打印；调用方用 bash 重定向落 JSON）。
"""
import glob
import hashlib
import json
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WS)
out = {}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ── (1) L3 算术 ────────────────────────────────────────────────
p3 = "kb/l3/candidates/rules.jsonl"
raw = open(p3, "rb").read()
lines = raw.split(b"\n")
if lines and lines[-1] == b"":
    lines.pop()
whole = hashlib.sha256(raw).hexdigest()
pre1018 = hashlib.sha256(b"".join(x + b"\n" for x in lines[:1018])).hexdigest()
pre1527 = hashlib.sha256(b"".join(x + b"\n" for x in lines[:1527])).hexdigest()
l6rec = json.load(open("kb/.work/l6_integrity.json", encoding="utf-8"))
l6sha = l6rec["checks"]["frozen_layers"]["l3_candidates"]["sha256"]
l6lines = l6rec["checks"]["frozen_layers"]["l3_candidates"].get("lines")
l4rec = json.load(open("kb/l4/runs/20260923-1445.json", encoding="utf-8"))
l4sha = next(a["sha256"] for a in l4rec["artifacts"] if a["path"].endswith("candidates/rules.jsonl"))
l3reg = json.load(open("kb/l3/registry/l3.json", encoding="utf-8"))
reg_sha = (((l3reg.get("appended_fields") or {}).get("old_lines_untouched") or {}).get("sha256"))
out["leg2_arithmetic"] = {
    "live_lines": len(lines), "live_whole_sha256": whole,
    "live_mtime": __import__("time").strftime("%Y-%m-%d %H:%M:%S", __import__("time").localtime(os.path.getmtime(p3))),
    "prefix_1018_sha256": pre1018, "prefix_1527_sha256": pre1527,
    "prefix1018_equals_whole": pre1018 == whole, "prefix1527_equals_whole": pre1527 == whole,
    "baseline_L6": {"sha256": l6sha, "lines": l6lines, "checked_at": l6rec.get("checked_at")},
    "baseline_L4": {"sha256": l4sha, "source": "kb/l4/runs/20260923-1445.json"},
    "criteria_base1018_matches_L6": pre1018 == l6sha,
    "criteria_whole1527_matches_L4": pre1527 == l4sha,
    "live_sha_in_l3_registry": reg_sha == whole,
    "l3_registry_appended_fields_sha256": reg_sha,
    "structurally_impossible": (len(lines) <= 1527) and (len(lines) <= (l6lines or 10 ** 9)),
}

# ── (2)(3) ③ 段：20 项 mismatch 的来源审计 + 存在性 ──────────────
wf = json.load(open("kb/l8/workflow_check_CHK-20261004-1250-CLOSE.json", encoding="utf-8"))
leg3 = next(l for l in wf["legs"] if l["leg"].startswith("③"))
mismatch = leg3["detail"]["mismatch"]
base_paths = set()
for rp in ("kb/l4/runs/20260923-1445.json", "kb/l5/runs/20260923-1430.json",
           "kb/l6/runs/20260923-1440.json", "kb/l7/runs/20260923-1500.json"):
    if os.path.exists(rp):
        for a in json.load(open(rp, encoding="utf-8")).get("artifacts", []):
            base_paths.add(a["path"])

prov = {p: [] for p in mismatch}
n_runs = 0
for rp in glob.glob("kb/l*/runs/*.json") + glob.glob("kb/l*/*/runs/*.json"):
    if os.path.basename(os.path.dirname(os.path.dirname(rp))) == "l8":
        continue
    try:
        rec = json.load(open(rp, encoding="utf-8"))
    except Exception:
        continue
    n_runs += 1
    rid = rec.get("run_id") or os.path.basename(rp)
    arts = rec.get("artifacts")
    for a in (arts if isinstance(arts, list) else []):
        if not isinstance(a, dict):
            continue
        ap = a.get("path")
        if ap in prov and a.get("sha256"):
            prov[ap].append({"run": rid, "record": rp, "sha256": a["sha256"]})

audit = {}
for p in mismatch:
    exists = os.path.exists(p)
    cur = sha(p) if exists else None
    hits = [h for h in prov[p] if h["sha256"] == cur]
    audit[p] = {"exists": exists, "live_sha256": cur,
                "run_records_declaring_live_sha": len(hits),
                "latest_declaring_run": (hits[-1]["run"] if hits else None),
                "sample_records": [h["record"] for h in hits[:3]]}
out["leg3_audit"] = {
    "checked": leg3["detail"]["checked"], "mismatch_count": len(mismatch),
    "run_records_scanned": n_runs,
    "with_provenance": sum(1 for v in audit.values() if v["run_records_declaring_live_sha"]),
    "without_provenance": [p for p, v in audit.items() if not v["run_records_declaring_live_sha"]],
    "missing_files": [p for p, v in audit.items() if not v["exists"]],
    "per_item": audit,
    "baseline_is_20260923_fixed": sorted(base_paths)[:3],
}

# ── (4) l7.json 逐字段比对 ─────────────────────────────────────
pre = "kb/l7/_backups/batch18b-20261002-1201/l7.json.pre-edit"
if os.path.exists(pre):
    a = json.load(open("kb/l7/registry/l7.json", encoding="utf-8"))
    b = json.load(open(pre, encoding="utf-8"))
    diffs = []

    def walk(x, y, path=""):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in set(x) | set(y):
                walk(x.get(k), y.get(k), f"{path}.{k}")
        elif x != y:
            diffs.append({"field": path, "now": (str(x)[:120] if not isinstance(x, (dict, list)) else type(x).__name__),
                          "pre_edit": (str(y)[:120] if not isinstance(y, (dict, list)) else type(y).__name__)})
    walk(a, b)
    out["leg3_l7_json_diff"] = {
        "live_sha256": sha("kb/l7/registry/l7.json"), "pre_edit_sha256": sha(pre),
        "declared_run_id": a.get("run_id"), "diff_count": len(diffs), "diffs": diffs,
    }

print(json.dumps(out, ensure_ascii=False, indent=1))
