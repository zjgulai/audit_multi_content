#!/usr/bin/env python3
"""四段溯源组装（RT-20261005-YOGA-02）：
① 条款号(L4) ② 规则与命中片段(L3) ③ anchor/source_sha256(L2/L1) ④ L0 逐字字段值 + entry_url。
数据全部来自 kb/l0 records 与引擎输出；不做任何重算 sha 的声称。
"""
import json, pathlib, re, glob

here = pathlib.Path(__file__).resolve().parent
root = here.parent
eng = json.load(open(here / "engine.stdout.json", encoding="utf-8"))
risks = eng["decision"]["risk_items"]

# L0 索引：record_id -> (path, entry_url, fields)
idx = {}
for p in glob.glob(str(root / "kb/l0/records/*/*.json")):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    rid = d.get("record_id")
    if rid:
        idx[rid] = (p, d.get("entry_url"), d.get("fields", {}))

rows = []
for i, r in enumerate(risks, 1):
    ev = r.get("evidence", {}) or {}
    anchor = ev.get("anchor") or ""
    m = re.search(r"#([^/]+)/([^/]+)/([^/]+)", anchor)
    table = m.group(1) if m else None
    rid = m.group(2) if m else None
    l0 = idx.get(rid)
    verbatim_field = m.group(3) if m else None
    l0_value = None
    if l0 and verbatim_field:
        fv = (l0[2] or {}).get(verbatim_field)
        if isinstance(fv, dict):
            l0_value = fv.get("value")
        else:
            l0_value = fv
    rows.append({
        "n": i,
        "priority_tier": r.get("priority_tier"),
        "severity": r.get("severity"),
        "action": r.get("action"),
        "category": r.get("risk_type"),
        # ① 条款号 (L4)
        "l4_article_no": ev.get("article_no") or r.get("article_no"),
        "l4_form": "entry",
        # ② 规则与命中片段 (L3)
        "l3_rule_code": r.get("rule_code"),
        "l3_rule_id": r.get("rule_id"),
        "matched_fragment": r.get("original_text"),
        # ③ anchor + source_sha256 (L2/L1)
        "anchor": anchor,
        "source_sha256": ev.get("source_sha256"),
        # ④ L0
        "l0_table": table,
        "l0_record_id": rid,
        "l0_entry_url": l0[1] if l0 else None,
        "l0_verbatim_field": verbatim_field,
        "l0_verbatim_value": l0_value,
        "l0_local_file": l0[0].replace(str(root) + "/", "") if l0 else None,
        "library": ev.get("library"),
        "evidence_complete": r.get("evidence_complete"),
        "reason": (r.get("reason") or "")[:300],
    })

out = {
    "material_sha256": __import__("hashlib").sha256(
        (root / "_rt-yoga-02-text.txt").read_bytes()).hexdigest(),
    "review_id": eng["decision"]["review_id"],
    "content_id": eng["decision"]["content_id"],
    "findings": rows,
    "sha_wording_rule": "只能写「与 L0 记录值比对一致」，不许写「重算通过」——"
                        "L0 的 sha 输入是 record_fields blob，本地 L0 件不含该 blob。",
}
print(json.dumps(out, ensure_ascii=False, indent=2)[:6000])
(here / "provenance.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
