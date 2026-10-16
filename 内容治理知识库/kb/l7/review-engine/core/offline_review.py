#!/usr/bin/env python3
"""Run the local review engine from a payload and offline extraction JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from .media_adapter import apply_extraction, text_segments
    from .product_fact_integration import apply_product_fact_gates
    from .review_engine import decide
    from .rule_engine import scan_text
except ImportError:  # direct script execution
    from media_adapter import apply_extraction, text_segments
    from product_fact_integration import apply_product_fact_gates
    from review_engine import decide
    from rule_engine import scan_text


def _annotate_finding(finding: dict, segment: dict) -> dict:
    output = dict(finding)
    match = re.search(r"(\d+)-(\d+)$", str(finding.get("location", "")))
    suffix = f"{match.group(1)}-{match.group(2)}" if match else "unknown"
    source_location = segment.get("location") or f"{segment['kind']} segment {segment['index']}"
    output["location"] = f"{source_location} ({segment['kind']}[{segment['index']}]) {finding.get('location', '')}"
    output["evidence_id"] = f"OFFLINE:{segment['kind']}:{segment['index']}:{suffix}"
    output["extraction_source"] = {"kind": segment["kind"], "index": segment["index"], "location": source_location}
    return output


def run(payload: dict, extraction: dict) -> dict:
    """Attach offline evidence, scan OCR/ASR text, and invoke the decision engine."""
    output = dict(payload)
    base_manifest = dict(output.get("input_manifest") or {})
    base_manifest.setdefault("content_type", output.get("content_type"))
    base_manifest.setdefault("content_id", output.get("content_id"))
    base_manifest.setdefault("content_version", output.get("content_version"))
    manifest = apply_extraction(base_manifest, extraction)
    output["input_manifest"] = manifest
    output["coverage"] = manifest.get("coverage", output.get("coverage", {}))
    output["extraction"] = manifest.get("extraction", {})
    findings = []
    segments = text_segments(extraction)
    for segment in segments:
        findings.extend(
            _annotate_finding(item, segment)
            for item in scan_text(
                segment["text"],
                product_line=output.get("product_line", ""),
                channel=output.get("channel", ""),
            )
        )
    gate_findings, gate_results = apply_product_fact_gates(output, segments)
    output["product_fact_gate"] = gate_results
    output["risk_items"] = list(output.get("risk_items", [])) + findings + gate_findings
    return decide(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local review from offline OCR/ASR/keyframe JSON")
    parser.add_argument("payload", type=Path, help="Review payload JSON")
    parser.add_argument("extraction", type=Path, help="Offline extraction result JSON")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = run(
        json.loads(args.payload.read_text(encoding="utf-8")),
        json.loads(args.extraction.read_text(encoding="utf-8")),
    )
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
