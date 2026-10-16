#!/usr/bin/env python3
"""L0 落库 · 步骤 5 第二层: 枚举关联 Base 的表结构 + 有界记录采样（只读）。"""
import json, os, subprocess, sys

ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
os.makedirs("kb/.work/bases", exist_ok=True)
REC_CAP = 200

BASES = {
    "Lk3Qb8y2QaVyZns6gprcVNE9nA0": {"label": "广告文案风控库", "tables": None},
    "N2qkb2YxuatqGLsa4U4cFQxgnCe": {"label": "外部资料库", "tables": None},
    "SKkkbdZi9aRuMzs7ob0cpSYHnQg": {"label": "内容公式与专家修订库", "tables": None},
}

def run(args, timeout=180):
    try:
        p = subprocess.run(args, capture_output=True, text=True, env=ENV, timeout=timeout)
        return json.loads(p.stdout)
    except Exception as e:
        return {"ok": False, "error": {"type": "parse", "message": str(e)[:200]}}

ops = []
result = {}
for bt, meta in BASES.items():
    tl = run(["lark-cli", "base", "+table-list", "--base-token", bt])
    ops.append({"op": "base +table-list", "nature": "read", "target": f"bitable:{bt}", "note": "枚举关联 Base 的表"})
    tables = tl["data"]["tables"] if tl.get("ok") else []
    entry = {"base_token": bt, "label": meta["label"],
             "base_name": (tl.get("data", {}) or {}).get("name"), "tables": []}
    for t in tables:
        tid, tname = t["id"], t["name"]
        f = run(["lark-cli", "base", "+field-list", "--base-token", bt, "--table-id", tid])
        ops.append({"op": "base +field-list", "nature": "read", "target": f"bitable:{bt}:table:{tid}",
                    "note": f"{tname} 字段 schema"})
        fields = []
        if f.get("ok"):
            for x in f["data"]["fields"]:
                fields.append({"field_id": x["id"], "field_name": x["name"], "type": x["type"],
                               "options": [o.get("name") for o in (x.get("options") or [])] or None,
                               "multiple": x.get("multiple"),
                               "lookup_from": x.get("from"), "lookup_field": x.get("select"),
                               "lookup_where": x.get("where")})
        rc = t.get("records_count") or 0
        recs, truncated = [], False
        if rc > 0:
            rl = run(["lark-cli", "base", "+record-list", "--base-token", bt, "--table-id", tid,
                      "--limit", str(min(REC_CAP, max(rc, 1))), "--format", "ndjson",
                      "--output", f"kb/.work/bases/{tid}.ndjson"])
            ops.append({"op": "base +record-list", "nature": "read",
                        "target": f"bitable:{bt}:table:{tid}",
                        "note": f"{tname} 记录采样，上限 {REC_CAP}"})
            if os.path.exists(f"kb/.work/bases/{tid}.ndjson"):
                for line in open(f"kb/.work/bases/{tid}.ndjson", encoding="utf-8"):
                    if line.strip():
                        recs.append(json.loads(line))
            truncated = len(recs) < rc
        entry["tables"].append({"table_id": tid, "table_name": tname, "records_count": rc,
                                "rev": t.get("rev"), "fields": fields,
                                "records_sampled": len(recs),
                                "records_truncated": truncated,
                                "records": recs})
        print(f"{bt[:12]} | {tname} | fields={len(fields)} | recs={len(recs)}/{rc} truncated={truncated}")
    result[bt] = entry

json.dump(result, open("kb/.work/bases/enum.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ops, open("kb/.work/ops-bases.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("done")
