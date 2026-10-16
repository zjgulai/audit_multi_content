#!/usr/bin/env python3
"""Resolve the confirmed role-level SLA target for a review result."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).parents[1]


def _policy() -> Dict[str, Any]:
    return json.loads((ROOT / "knowledge-base" / "sla-policy.json").read_text(encoding="utf-8"))


def resolve_sla(decision: str, risk_items: list[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    items = risk_items or []
    priorities = {item.get("priority_tier") for item in items}
    priority = "P0" if "P0" in priorities else "P1" if "P1" in priorities else "P2" if "P2" in priorities else "any"
    for target in _policy()["targets"]:
        if target["state"] == decision and target["priority"] in {priority, "any"}:
            return {"priority": priority, "target": target["target"], "escalate_to": target["escalate_to"], "timezone": _policy()["timezone"], "clock_rules": _policy()["clock_rules"]}
    return {"priority": priority, "target": "manual", "escalate_to": ["项目统筹"], "timezone": _policy()["timezone"]}
