#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F7 后置校验：复算 L4 的 C1–C8 判据（重点是 C4「与候选逐字节一致」）。

C4 的原文口径（`l4/registry/l4.json → promotion_rule.criteria.C4_verbatim_with_candidates`）：
    "比对 rule_text/sample_body/clause_text + anchor，逐字节一致；canonical 只加不改"

F7 只往 L3 的规则行**填空字段与加新字段**（owner / effective_from / half_life_days /
valid_until），没有动 rule_text / anchor / article_no 等任何被 C4 比对的内容字段 ——
本脚本就是来证明这一点的。

另附：列出 L3↔L4 的**字段级差异**，确认差异**只**出现在治理元数据上。

用法：python3 kb/.work/fix_f7_verify_c4.py
"""

from __future__ import annotations

import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L3R = os.path.join(KB, "l3", "candidates", "rules.jsonl")
L4 = os.path.join(KB, "l4", "canonical")

# 各形态的「正文对照字段」
BODY_FIELD = {
    "wording_entry": "rule_text",
    "wording_revision_pair": "rule_text",
    "sample_case": "sample_body",
    "scoped_clause": "clause_text",
}
ID_FIELD = {
    "wording_entry": "rule_id",
    "wording_revision_pair": "rule_id",
    "sample_case": "case_id",
    "scoped_clause": "clause_id",
}
# 这三类形态的候选来自另外两个文件，不是 rules.jsonl
CAND_FILE = {
    "wording_entry": "rules.jsonl",
    "wording_revision_pair": "rules.jsonl",
    "sample_case": "sample_cases.jsonl",
    "scoped_clause": "scoped_clauses.jsonl",
}


def load(p):
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def main() -> int:
    cand = {}
    for f in ("rules.jsonl", "sample_cases.jsonl", "scoped_clauses.jsonl"):
        cand[f] = load(os.path.join(KB, "l3", "candidates", f))
    print("候选：", {k: len(v) for k, v in cand.items()})

    total = compared = drift = missing = 0
    drift_examples = []
    field_diff = {}

    for form, body_field in BODY_FIELD.items():
        path = os.path.join(L4, f"{form}.jsonl")
        rows = load(path)
        total += len(rows)
        by_id = {r[ID_FIELD[form]]: r for r in cand[CAND_FILE[form]] if r.get(ID_FIELD[form])}
        for c in rows:
            key = c.get(ID_FIELD[form])
            src = by_id.get(key)
            if src is None:
                missing += 1
                continue
            compared += 1
            # 内容字段逐字节比对
            for f in (body_field, "anchor"):
                if str(c.get(f, "")) != str(src.get(f, "")):
                    drift += 1
                    if len(drift_examples) < 3:
                        drift_examples.append((form, key, f))
            # 字段级差异统计（确认差异只在治理元数据上）
            keys = set(c) | set(src)
            for k in keys:
                if k in ("promoted_at_run", "promoted_from", "promotion_basis", "cite_check"):
                    continue          # L4 自己的晋升记账字段，天然只在 L4
                if c.get(k) != src.get(k):
                    field_diff.setdefault(k, []).append(key)

    print(f"\n── C4 复算：canonical {total} 条 / 比对 {compared} 条 / 源缺失 {missing}")
    print(f"   drift（内容字段不一致）= {drift}")
    if drift_examples:
        for e in drift_examples:
            print("     ", e)

    print("\n── L3↔L4 字段级差异（排除 L4 自己的晋升记账字段）")
    if not field_diff:
        print("     （无）")
    for k, v in sorted(field_diff.items(), key=lambda x: -len(x[1])):
        print(f"     {len(v):5} 条  {k}")

    ok = (drift == 0 and missing == 0)
    print(f"\nC4_verbatim_with_candidates: {'PASS ✅' if ok else 'FAIL ❌'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
