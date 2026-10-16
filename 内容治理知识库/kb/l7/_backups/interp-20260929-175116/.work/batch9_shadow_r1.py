#!/usr/bin/env python3
"""件0.5 影子评估（只算不写）：若把 R1 硬编码改为真求值，23 条「材料收集」记录会新增多少 L2 单元。

口径：完全按 kb/.work/l2_split.py 的四类切分器（split_entry / split_clause /
split_sample / split_attribute）+ has_content() 闸门，逐条真算，不估算。
"""
import json, glob, os, collections

L0, L1 = "kb/l0", "kb/l1"
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
RULES = [r for r in reg["rules"] if r.get("enabled")]

def rule_for(table, hint):
    """与 kb/.work/kb_l0_scan_lib.py::eval_rule 的「记录自带分类值」分支同构。"""
    for t in (hint or []):
        if t == "其它":
            continue
        for r in RULES:
            if (r["match_type"] == "field_value" and r.get("scope_table") == "材料收集"
                    and r.get("match_value") == t):
                return r["kb_type"], r["id"], f"记录字段值:知识库分类={t}"
    for r in RULES:
        if r["match_type"] == "table_name" and r["pattern"] == table:
            return r["kb_type"], r["id"], f"表名:{table}"
    return "unknown", None, "no_rule_matched"

def has_content(o):
    if o.get("segments") or o.get("tables"):
        return True
    for m in (o.get("media_refs") or []):
        if (m.get("ocr_char_count") or 0) > 0 or m.get("visual_description"):
            return True
    return False

def n_units(kb, o):
    """按 l2_split.py 的切分器算该资源会产出几个单元。"""
    segs = [s for s in (o.get("segments") or [])]
    fv = [s for s in segs if s.get("kind") == "field_value"]
    if not has_content(o):
        return 0, "has_content=false"
    if kb == "wording":
        return len([s for s in segs if s.get("kind") in
                    ("field_value","image_ocr","image_visual","paragraph","list_item")]), "split_entry"
    if kb == "external_standard":
        return len(fv), "split_clause(field_value 直出 entry)"
    if kb == "internal_sample":
        return (1 if fv else 0), "split_sample(合并为 1 条)"
    if kb == "product_desc":
        return len(fv), "split_attribute"
    return 0, "unknown(不切)"

# 23 条「材料收集」记录
latest = {}
for ln in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if ln.strip():
        r = json.loads(ln); latest[r["resource_key"]] = r
recs = [v for v in latest.values()
        if v.get("table_name") == "材料收集" and v.get("record_id") and v.get("field_name") is None]
recs.sort(key=lambda r: r["record_id"])
rid_of = lambda k: k.replace(":", "__").replace("/", "_")

def find_l1(rid):
    for d in sorted(os.listdir(L1)):
        p = f"{L1}/{d}/{rid}.json"
        if os.path.isfile(p):
            return p
    return None

rows, tot = [], collections.Counter()
for r in recs:
    rid = rid_of(r["resource_key"])
    art = json.load(open(find_l1(rid), encoding="utf-8"))
    hint = art["segments"] and [s["text"] for s in art["segments"]
                                if s.get("field_name") == "知识库分类"]
    hint = [x for part in (hint or []) for x in str(part).split("、")]
    kt, ridr, src = rule_for("材料收集", hint)
    nu, how = n_units(kt, art)
    tot[kt] += 1
    rows.append({"record_id": r["record_id"], "resource_id": rid,
                 "知识库分类": hint, "old_kb_type": r["kb_type"], "old_rule": r["matched_rule"],
                 "new_kb_type": kt, "new_rule": ridr, "kb_type_source": src,
                 "l1_status": art.get("status"), "l1_segments": len(art.get("segments") or []),
                 "role_content_segments": 0, "would_emit_units": nu, "splitter": how,
                 "current_l2_units": 0})
out = {"run_id": "20260924-1320", "kind": "shadow_only_no_write",
       "records": len(recs), "new_kb_type_dist": dict(tot),
       "expected_new_units_total": sum(x["would_emit_units"] for x in rows), "rows": rows}
json.dump(out, open("kb/.work/batch9/shadow_r1.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("记录数:", len(recs))
for k, v in sorted(tot.items()): print(f"  {k:<18} {v}")
print("若按新 kb_type 真切，预期新增 L2 单元 =", out["expected_new_units_total"])
print()
print(f"{'record_id':<18}{'知识库分类':<22}{'旧':<18}{'新':<18}{'规则':<5}{'L1段':<5}{'将产出':<6}")
for x in rows:
    print(f"{x['record_id']:<18}{'、'.join(x['知识库分类']):<22}{x['old_kb_type']:<18}"
          f"{x['new_kb_type']:<18}{str(x['new_rule']):<5}{x['l1_segments']:<5}{x['would_emit_units']:<6}")
