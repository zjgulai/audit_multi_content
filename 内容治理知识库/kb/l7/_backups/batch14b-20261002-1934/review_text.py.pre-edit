#!/usr/bin/env python3
"""Run the seed text scanner followed by the deterministic decision engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .product_fact_integration import apply_product_fact_gates
    from .rule_engine import scan_text
    from .review_engine import decide
except ImportError:  # direct script execution
    from product_fact_integration import apply_product_fact_gates
    from rule_engine import scan_text
    from review_engine import decide


def run(payload: dict, text: str) -> dict:
    payload = dict(payload)
    gate_findings, gate_results = apply_product_fact_gates(payload, [{"text": text, "location": "text"}])
    payload["product_fact_gate"] = gate_results
    payload["risk_items"] = list(payload.get("risk_items", [])) + scan_text(
        text,
        product_line=payload.get("product_line", ""),
        channel=payload.get("channel", ""),
    ) + gate_findings
    return decide(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local text review pipeline")
    parser.add_argument("payload", type=Path)
    parser.add_argument("text")
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    print(json.dumps(run(payload, args.text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
