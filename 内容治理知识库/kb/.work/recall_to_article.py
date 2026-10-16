#!/usr/bin/env python3
"""只读：把 L6 召回结果（unit_id）回落成 L2 正文 + L4 条款号。

用法（cwd = 内容治理/）：
    kb/kbpy .work/recall_to_article.py <recall.json> [<recall.json> ...]
输出：stdout 的 JSON（一份合并报告）。
不写库、不改索引。
"""
import json, os, re, sys

KB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
L2 = os.path.join(KB, "l2", "units.jsonl")
L4 = os.path.join(KB, "l4", "canonical")


def load_recalls(paths):
    """返回 [(query, mode, [ {unit_id, rank, score, excerpt, anchor, sha, kb_type, sources} ])]"""
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            o = json.load(f)
        rows = []
        for r in o.get("results", []):
            rows.append({
                "rank": r.get("rank"),
                "score": r.get("score"),
                "unit_id": r.get("unit_id"),
                "anchor": r.get("anchor"),
                "source_sha256": r.get("source_sha256"),
                "kb_type": r.get("kb_type"),
                "table": r.get("table"),
                "lang": r.get("lang"),
                "excerpt": r.get("text_excerpt"),
                "segment_index": r.get("segment_index"),
                "segment_count": r.get("segment_count"),
                "sources": r.get("sources"),
            })
        out.append({"file": os.path.basename(p), "query": o.get("query"),
                    "mode": o.get("mode"), "lists_used": o.get("lists_used"), "rows": rows})
    return out


def l2_lookup():
    idx = {}
    with open(L2, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            idx[o.get("unit_id")] = {
                "text": o.get("text"),
                "anchor": o.get("anchor"),
                "kb_type": o.get("kb_type"),
                "char_count": o.get("char_count"),
                "resource_id": o.get("resource_id"),
                "parent_unit_id": o.get("parent_unit_id"),
                "rule_eligible": o.get("rule_eligible"),
                "unit_type": o.get("unit_type"),
            }
    return idx


L4_FILES = ["sample_case.jsonl", "wording_revision_pair.jsonl", "wording_entry.jsonl", "scoped_clause.jsonl"]
TEXT_FIELDS = ["clause_text", "sample_body", "rule_text", "forbidden_expression"]


def l4_lookup():
    by_unit = {}
    for fn in L4_FILES:
        p = os.path.join(L4, fn)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                uids = set()
                if o.get("unit_id"):
                    uids.add(o["unit_id"])
                for u in o.get("unit_ids") or []:
                    uids.add(u)
                for e in o.get("evidence_units") or []:
                    if isinstance(e, dict) and e.get("unit_id"):
                        uids.add(e["unit_id"])
                body = ""
                for tf in TEXT_FIELDS:
                    if o.get(tf):
                        body = o[tf]
                        break
                rec = {
                    "article_no": o.get("article_no"),
                    "form": o.get("form"),
                    "status": o.get("status"),
                    "kb_type": o.get("kb_type"),
                    "anchor": o.get("anchor"),
                    "source_sha256": o.get("source_sha256"),
                    "text": body,
                    "reason": o.get("reason") or o.get("reason_analysis") or o.get("p_level_basis"),
                    "suggested_replacement": o.get("suggested_replacement"),
                    "rule_code": o.get("rule_code"),
                    "p_level": o.get("p_level"),
                    "risk_level": o.get("risk_level"),
                }
                for u in uids:
                    by_unit.setdefault(u, []).append(rec)
    # 去重（同一 (article_no, anchor) 在多文件里重复登记）
    for u, recs in by_unit.items():
        seen, uniq = set(), []
        for r in recs:
            k = (r["article_no"], r["anchor"])
            if k in seen:
                continue
            seen.add(k)
            uniq.append(r)
        by_unit[u] = uniq
    return by_unit


def main():
    paths = sys.argv[1:]
    if not paths:
        print("usage: kbpy .work/recall_to_article.py <recall.json> ...", file=sys.stderr)
        return 2
    recalls = load_recalls(paths)
    l2 = l2_lookup()
    l4 = l4_lookup()

    report = {"recalls": [], "l4_hit_units": 0, "l2_hit_units": 0}
    for rec in recalls:
        rows = []
        for r in rec["rows"]:
            uid = r["unit_id"]
            m2 = l2.get(uid)
            m4 = l4.get(uid, [])
            if m2:
                report["l2_hit_units"] += 1
            if m4:
                report["l4_hit_units"] += 1
            rows.append({
                **r,
                "l2": m2,
                "l4": m4,
                "full_text": (m2 or {}).get("text"),
            })
        report["recalls"].append({**rec, "rows": rows})
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
