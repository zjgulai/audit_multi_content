#!/usr/bin/env python3
"""Evaluate decisions against a human-adjudicated gold set."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from .review_engine import decide


def _rate(numerator: int, denominator: int):
    return round(numerator / denominator, 4) if denominator else None


def evaluate(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    for record in records:
        actual = record.get("actual_decision")
        if not actual and record.get("payload"):
            actual = decide(record["payload"])["decision"]
        expected = record.get("expected_decision")
        rows.append({"expected": expected, "actual": actual, "p0_should_hit": bool(record.get("p0_should_hit")), "p0_hit": bool(record.get("p0_hit"))})

    total = len(rows)
    correct = sum(row["expected"] == row["actual"] for row in rows)
    predicted_block = [row for row in rows if row["actual"] == "BLOCK"]
    predicted_pass = [row for row in rows if row["actual"] == "PASS"]
    expected_review_or_block = [row for row in rows if row["expected"] in {"REVIEW", "BLOCK"}]
    p0_expected = [row for row in rows if row["p0_should_hit"]]
    return {
        "sample_count": total,
        "three_state_accuracy": _rate(correct, total),
        "block_precision": _rate(sum(row["expected"] == "BLOCK" for row in predicted_block), len(predicted_block)),
        "pass_leakage_rate": _rate(sum(row["expected"] in {"REVIEW", "BLOCK"} for row in predicted_pass), len(predicted_pass)),
        "review_recall": _rate(sum(row["actual"] == "REVIEW" for row in expected_review_or_block), len(expected_review_or_block)),
        "p0_miss_rate": _rate(sum(not row["p0_hit"] for row in p0_expected), len(p0_expected)),
        "denominators": {
            "all": total,
            "predicted_block": len(predicted_block),
            "predicted_pass": len(predicted_pass),
            "expected_review_or_block": len(expected_review_or_block),
            "p0_should_hit": len(p0_expected),
        },
    }
