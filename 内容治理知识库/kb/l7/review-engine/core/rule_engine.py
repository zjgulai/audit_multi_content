#!/usr/bin/env python3
"""Small deterministic candidate scanner for the US seed rules.

It deliberately produces review candidates. Product/model conflicts are supplied
by the product claim verifier because a keyword scanner cannot establish them.

★ 真源声明（2026-10-01 加，只加标注、不改判定）：

    本文件扫的是 `knowledge-base/seed-rules.json` 里的 **5 条 US 种子规则**，
    它**不是知识库的规则真源**。规则真源是：

        kb/l3/candidates/rules.jsonl（措辞表达库）→ kb/l4/canonical（发号）

    两者编号体系不同、互无映射（种子 `US-CLAIM-HEALTH-001` ↔ 库内 `W-1.8` 等），
    因此**禁止**把二者当作同一份规则清单来合并或对账。本扫描器只许当
    「专项第 1 源：可定位的候选」，**不得单独支撑 BLOCK/PASS 结论** ——
    结论必须站在带条款号 + anchor + source_sha256 + 逐字摘录的依据侧 findings 上。

    合并/退役这 5 条要改判定结果，属写规则真源，**必须人开闸**，不在代码里自行处理。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).parents[1]

#: 本扫描器输出的候选**不是**权威依据（见模块 docstring 的真源声明）
AUTHORITATIVE = False
AUTHORITY = "seed-rules(非规则真源)"


def _rules() -> List[Dict[str, Any]]:
    data = json.loads((ROOT / "knowledge-base" / "seed-rules.json").read_text(encoding="utf-8"))
    return data["rules"]


def authority() -> Dict[str, Any]:
    """返回本扫描器的权威性声明（供下游把「候选」与「依据」区分开）。

    读 seed-rules.json 的 `authoritative`，缺省按 False —— 缺字段时**默认不权威**，
    这样即使有人把标注删了，也不会悄悄把它升格成依据。
    """
    try:
        data = json.loads((ROOT / "knowledge-base" / "seed-rules.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"authoritative": False, "authority": AUTHORITY, "superseded_by": None}
    return {
        "authoritative": bool(data.get("authoritative", False)),
        "authority": AUTHORITY,
        "superseded_by": data.get("superseded_by"),
    }


def _context_status(text: str, start: int) -> str:
    context = text[max(0, start - 40):start].lower()
    if re.search(r"\b(do not|don't|does not|not|never|avoid|warning|禁止|不要)\b", context):
        return "uncertain"
    return "confirmed"


def scan_text(text: str, *, product_line: str = "", channel: str = "") -> List[Dict[str, Any]]:
    """Return locatable risk candidates; no final decision is made here.

    每条候选都带 `authoritative` / `authority` / `superseded_by` —— 下游据此知道
    这一条**不能**顶替带条款号的库内依据（见模块 docstring 的真源声明）。
    """
    auth = authority()
    findings: List[Dict[str, Any]] = []
    for rule in _rules():
        patterns = rule.get("trigger", {}).get("patterns", [])
        if not patterns:
            continue
        applies = rule.get("applies_to", {})
        if product_line and product_line not in applies.get("product_lines", []) and "all" not in applies.get("product_lines", []):
            continue
        if channel and channel not in applies.get("channels", []) and "all" not in applies.get("channels", []):
            continue
        matches = []
        for pattern in patterns:
            matches.extend(re.finditer(re.escape(pattern), text, flags=re.IGNORECASE))
        selected = []
        for match in sorted(matches, key=lambda m: (m.start(), -(m.end() - m.start()))):
            if any(match.start() < other.end() and match.end() > other.start() for other in selected):
                continue
            selected.append(match)
        for match in selected:
            context_status = _context_status(text, match.start())
            findings.append({
                "risk_id": f"{rule['rule_id']}:{match.start()}",
                "risk_type": rule["title"],
                "priority_tier": rule["priority_tier"],
                "severity": rule["severity"],
                "status": "uncertain",
                "context_status": context_status,
                "action": "review",
                "location": f"text characters {match.start()}-{match.end() - 1}",
                "original_text": match.group(0),
                "reason": "命中美国市场规则候选，需要结合上下文、证据和适用范围人工确认",
                "suggestion": "检查证据、免责声明、渠道政策和产品事实后再决定",
                "evidence_id": f"TEXT:{match.start()}:{match.end()}",
                "rule_id": rule["rule_id"],
                "channel": channel,
                # ★ 非真源标注：这一条是「候选」，不是「依据」
                "authoritative": auth["authoritative"],
                "authority": auth["authority"],
                "superseded_by": auth["superseded_by"],
            })
    return findings


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Scan text for US seed-rule candidates")
    parser.add_argument("text")
    parser.add_argument("--product-line", default="")
    parser.add_argument("--channel", default="")
    args = parser.parse_args()
    print(json.dumps(scan_text(args.text, product_line=args.product_line, channel=args.channel), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
