#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把引擎 9 条 risk_item 的命中词逐个定位到素材原文，并标注归属（Momcozy 自撰 / 第三方引文）。

归属判据（可复核）：素材第 251–289 行 = 本文件里唯一由 Momcozy 撰写的拟发布内容
（"AI分析可应用2" 起的 Meta 广告脚本 + 文案版本 A/B）；其余行 = 竞品研究与第三方引文。
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
text = (ROOT / "_rt-yoga-01-text.txt").read_text(encoding="utf-8")
eng = json.loads((ROOT / "_rt-yoga-01-engine.json").read_text(encoding="utf-8"))
items = eng["decision"]["risk_items"]

# 行号 → 是否为 Momcozy 自撰拟发布段（第 251 行 "AI分析可应用2" 起）
lines = text.split("\n")
offsets, acc = [], 0
for ln in lines:
    offsets.append(acc)
    acc += len(ln) + 1          # "".join(lines) 加了 '\n'


def line_of(pos: int) -> int:
    lo, hi = 0, len(offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if offsets[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def owner_of(line_no: int) -> str:
    """按「命中所在行」判归属：
      ① ≥251 行 = 本文件里唯一由 Momcozy 撰写的**拟发布**内容（Meta 脚本 / 文案版本 A·B）；
      ② 该行以中文为主（CJK 占比 ≥ 20%）= Momcozy 自撰的内部分析/总结（含对竞品的转述）；
      ③ 否则 = 第三方逐字引文（竞品/资讯广告原文）。
    这个口径只看「命中词落在谁的句子里」，可复核、不靠语义推断。
    """
    if line_no >= 251:
        return "Momcozy 自撰·拟发布文案（第251–289行）"
    ln = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else ""
    cjk = sum(1 for ch in ln if "\u4e00" <= ch <= "\u9fff")
    if ln and cjk / max(1, len(ln)) >= 0.20:
        return "Momcozy 自撰·内部分析/总结（转述或引用竞品语境）"
    return "第三方逐字引文（竞品/资讯广告原文）"


TERMS = {
    "r-7baf7ceb47b2e5bc": r"\b(safest|perfect|zero[\s-]?risk|risk[\s-]?free)\b",
    "r-5c056bc02cdd770c": r"乳房胀痛",
    "r-252ba6cf5ee92b00": r"超级",
    "r-3b6c3c82dc667295": r"完美",
    "r-85348bba00a2b5a7": r"hospital",
}

out = []
for it in items:
    rid = it.get("risk_id")
    key = it.get("rule_id") or it.get("risk_id") or ""
    pat = TERMS.get(key)
    if pat is None and it.get("rule_id", "").startswith("US-PLATFORM-ABSOLUTE-001"):
        pat = r"(?i)best"
    occ = []
    if pat:
        for m in re.finditer(pat, text):
            ln = line_of(m.start())
            occ.append({"char": m.start(), "line": ln, "term": m.group(0),
                        "attribution": owner_of(ln),
                        "context": text[max(0, m.start() - 60):m.end() + 60].replace("\n", " ")})
    out.append({
        "risk_id": rid, "rule_code": it.get("rule_code"), "article_no": (it.get("evidence") or {}).get("article_no"),
        "tier": it.get("priority_tier"), "action": it.get("action"),
        "match_pattern": pat, "occurrences": occ,
        "attribution_summary": sorted({o["attribution"] for o in occ}) or ["未定位"],
    })

summary = {
    "schema": "rt-yoga-01-provenance/1",
    "material_lines": len(lines),
    "momcozy_publishable_range": "第 251–289 行（AI分析可应用2 起）",
    "items": out,
    "counts": {
        "items_total": len(out),
        "items_momcozy_publishable": sum(1 for x in out if any(o["line"] >= 251 for o in x["occurrences"])),
        "items_third_party_only": sum(1 for x in out if x["occurrences"] and all(o["line"] < 251 for o in x["occurrences"])),
        "items_unlocated": sum(1 for x in out if not x["occurrences"]),
    },
}
(ROOT / "_rt-yoga-01-provenance.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
for x in out:
    print("%-9s %-6s %-8s %s" % (x["rule_code"], x["tier"], x["action"], " ｜ ".join(x["attribution_summary"])))
    for o in x["occurrences"][:3]:
        print("      @%-6d line %-4d %-8s %s" % (o["char"], o["line"], o["term"], o["context"][:90]))
print(json.dumps(summary["counts"], ensure_ascii=False))
