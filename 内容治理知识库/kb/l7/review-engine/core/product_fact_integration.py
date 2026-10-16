#!/usr/bin/env python3
"""Attach SKU product-fact gate findings to text and extracted media evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    from .product_fact_queue import product_fact_gate
except ImportError:  # direct script execution
    from product_fact_queue import product_fact_gate


ROOT = Path(__file__).parents[1]
QUEUE_PATH = ROOT / "knowledge-base" / "product-fact-approval-queue.json"


def _load_queue() -> Dict[str, Any]:
    if not QUEUE_PATH.is_file():
        return {"entries": []}
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def _normalise(text: str) -> str:
    return " ".join(str(text).lower().split())


def apply_product_fact_gates(
    payload: Dict[str, Any],
    segments: Iterable[Dict[str, Any]],
    queue: Dict[str, Any] | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return risk findings and gate results for claims visible in text segments."""
    sku = payload.get("sku")
    if not sku:
        return [], []
    queue = queue or _load_queue()
    entries = [entry for entry in queue.get("entries", []) if entry.get("sku") == sku]
    findings: List[Dict[str, Any]] = []
    gates: List[Dict[str, Any]] = []
    seen = set()
    for segment_index, segment in enumerate(segments):
        text = str(segment.get("text", ""))
        normalised_text = _normalise(text)
        for entry in entries:
            phrase = _normalise(entry.get("fact", ""))
            if not phrase or phrase not in normalised_text:
                continue
            key = (entry.get("fact_id"), segment_index)
            if key in seen:
                continue
            seen.add(key)
            gate = product_fact_gate(queue, sku, entry.get("fact", ""))
            gate = dict(gate)
            gate.update({"fact_id": entry.get("fact_id"), "sku": sku, "claim": entry.get("fact", ""), "segment_index": segment_index})
            gates.append(gate)
            if gate.get("decision") == "CONTINUE":
                continue
            location = segment.get("location") or f"segment {segment_index}"
            findings.append({
                "risk_id": f"FACT-GATE:{entry.get('fact_id')}:{segment_index}",
                "risk_type": "产品事实审批",
                "priority_tier": "P1",
                "severity": "high",
                "status": "uncertain",
                "action": "review",
                "location": location,
                "original_text": text,
                "reason": gate.get("reason", "产品事实尚未完成审批"),
                "suggestion": "确认 SKU、证据快照和允许使用的 claim wording 后重新提交",
                "evidence_id": f"FACT-GATE:{entry.get('fact_id')}:{segment_index}",
                "gate_decision": gate.get("decision"),
                "next_owners": gate.get("owners", []),
            })
    return findings, gates
