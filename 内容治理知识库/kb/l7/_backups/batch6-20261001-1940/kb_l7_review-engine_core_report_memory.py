#!/usr/bin/env python3
"""Render review results into portable Markdown and JSON report files."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict


def render_markdown(result: Dict[str, Any]) -> str:
    groups = defaultdict(list)
    for item in result.get("risk_items", []):
        groups[item.get("risk_type") or item.get("category") or "未分类"].append(item)
    lines = [
        f"# 内容审核报告 {result.get('review_id', '')}",
        "",
        f"- 内容 ID：{result.get('content_id', '')}",
        f"- 内容版本：{result.get('content_version', '')}",
        f"- 结论：{result.get('decision', '')}",
        f"- 置信度（未校准启发式）：{result.get('confidence', '')}",
        f"- Agent 版本：{result.get('agent_version', '')}",
        f"- 规则版本：{result.get('rule_version', '')}",
        f"- 知识库版本：{result.get('knowledge_version', '')}",
        "",
        "## 问题清单",
        "",
    ]
    if not groups:
        lines.append("未发现风险项。")
    for category, items in groups.items():
        lines.append(f"### {category}")
        lines.append("")
        for index, item in enumerate(items, start=1):
            lines.extend([
                f"{index}. **{item.get('risk_id', '')}**（{item.get('priority_tier', '')} / {item.get('severity', '')}）",
                f"   - 位置：{item.get('location', '未定位')}",
                f"   - 原文/观察：{item.get('original_text') or item.get('observation') or '未提供'}",
                f"   - 原因：{item.get('reason', '')}",
                f"   - 建议：{item.get('suggestion', '')}",
                f"   - 证据：{item.get('evidence_url') or item.get('evidence_id') or '缺失'}",
                "",
            ])
    lines.extend([
        "## 决策轨迹",
        "",
        f"- 下一步：{result.get('next_action', '')}",
        f"- 责任角色：{', '.join(result.get('next_owners') or [])}",
        f"- SLA：{json.dumps(result.get('sla', {}), ensure_ascii=False)}",
        f"- 版本门禁：{json.dumps(result.get('version_gate', {}), ensure_ascii=False)}",
        f"- 覆盖状态：{json.dumps(result.get('coverage', {}), ensure_ascii=False)}",
    ])
    return "\n".join(lines) + "\n"


def write_report(result: Dict[str, Any], output_dir: str | Path) -> Dict[str, str]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    review_id = result.get("review_id", "review")
    json_path = directory / f"{review_id}.json"
    markdown_path = directory / f"{review_id}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}
