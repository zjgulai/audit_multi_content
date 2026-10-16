#!/usr/bin/env python3
"""Provider-neutral contract helpers for image and video extraction.

The adapter accepts an offline JSON result. It validates the result, preserves
source-level evidence, and only reports coverage as complete when the required
artifacts and status fields agree.
"""

from __future__ import annotations

from typing import Any, Dict, List


VALID_RESULT_STATUSES = {"complete", "partial", "failed"}
VALID_COVERAGE_STATUSES = {"complete", "not_applicable", "incomplete", "failed"}


def extraction_request(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Build a provider-neutral request without selecting a model vendor."""
    return {
        "content_hash": manifest.get("sha256"),
        "source_ref": manifest.get("source_ref"),
        "content_type": manifest.get("content_type"),
        "tasks": {
            "image": ["ocr", "objects", "people", "activities", "scene", "region_evidence"],
            "video": ["asr", "ocr", "shot_boundaries", "adaptive_keyframes", "audio_visual_alignment", "timecode_evidence"],
        }.get(manifest.get("content_type"), []),
        "safety": {"no_identity_inference": True, "no_final_decision": True},
    }


def validate_extraction(
    manifest: Dict[str, Any], extraction: Dict[str, Any]
) -> List[str]:
    """Return contract errors without making a review decision."""
    errors: List[str] = []
    for field in ("provider", "provider_version", "content_hash", "status"):
        if not extraction.get(field):
            errors.append(f"missing:{field}")
    if extraction.get("status") not in VALID_RESULT_STATUSES:
        errors.append("invalid:status")
    if extraction.get("content_hash") != manifest.get("sha256"):
        errors.append("content_hash_mismatch")
    content_type = manifest.get("content_type")
    if content_type == "image" and extraction.get("observations") is None:
        errors.append("missing:observations")
    if content_type == "video":
        if extraction.get("keyframes") is None:
            errors.append("missing:keyframes")
        for field in ("asr_status", "ocr_status", "keyframes_status"):
            if extraction.get(field) not in VALID_COVERAGE_STATUSES:
                errors.append(f"invalid:{field}")
    for field in ("ocr_status", "asr_status", "keyframes_status"):
        if field in extraction and extraction[field] not in VALID_COVERAGE_STATUSES:
            errors.append(f"invalid:{field}")
    return list(dict.fromkeys(errors))


def text_segments(extraction: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return OCR, ASR, and textual visual observations with stable locations."""
    segments: List[Dict[str, Any]] = []
    for kind, field, text_keys in (
        ("ocr", "ocr", ("text",)),
        ("asr", "transcript", ("text",)),
        ("observation", "observations", ("text", "observation", "description", "claim")),
    ):
        values = extraction.get(field) or []
        if isinstance(values, str):
            values = [{"text": values}]
        for index, value in enumerate(values):
            if isinstance(value, str):
                value = {"text": value}
            if not isinstance(value, dict):
                continue
            text = next((value.get(key) for key in text_keys if value.get(key)), "")
            if not str(text).strip():
                continue
            segments.append({
                "kind": kind,
                "index": index,
                "text": str(text),
                "location": value.get("location") or value.get("timecode") or value.get("region"),
            })
    return segments


def apply_extraction(manifest: Dict[str, Any], extraction: Dict[str, Any]) -> Dict[str, Any]:
    """Attach validated extraction metadata and coverage to a source manifest."""
    output = dict(manifest)
    contract_errors = validate_extraction(manifest, extraction)
    output["extraction"] = {
        "provider": extraction.get("provider"),
        "provider_version": extraction.get("provider_version"),
        "content_hash": extraction.get("content_hash"),
        "status": extraction.get("status", "failed"),
        "errors": list(dict.fromkeys(list(extraction.get("errors", [])) + contract_errors)),
        "artifacts": {
            "ocr": extraction.get("ocr", []),
            "transcript": extraction.get("transcript", []),
            "keyframes": extraction.get("keyframes", []),
            "observations": extraction.get("observations", []),
        },
    }
    coverage = dict(output.get("coverage", {}))
    content_type = manifest.get("content_type")
    if "content_hash_mismatch" in contract_errors:
        output["status"] = "failed"
        return output
    if contract_errors or extraction.get("status") != "complete":
        output["status"] = "extraction_incomplete"
    if content_type == "image":
        coverage["image"] = "complete" if extraction.get("observations") is not None and not contract_errors else "incomplete"
        coverage["ocr"] = extraction.get("ocr_status", "incomplete")
        coverage["text"] = "complete" if extraction.get("ocr_status") in {"complete", "not_applicable"} else "incomplete"
    elif content_type == "video":
        coverage["video"] = "complete" if extraction.get("keyframes") is not None and not contract_errors else "incomplete"
        coverage["keyframes"] = extraction.get("keyframes_status", "incomplete")
        coverage["asr"] = extraction.get("asr_status", "incomplete")
        coverage["audio"] = coverage["asr"]
        coverage["ocr"] = extraction.get("ocr_status", "incomplete")
        coverage["text"] = "complete" if coverage["asr"] in {"complete", "not_applicable"} and coverage["ocr"] in {"complete", "not_applicable"} else "incomplete"
    output["coverage"] = coverage
    if not contract_errors and extraction.get("status") == "complete":
        output["status"] = "ready"
    else:
        output["status"] = "extraction_incomplete"
    return output
