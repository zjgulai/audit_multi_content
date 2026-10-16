---
name: brand-review-decision-engine
description: "Aggregate multimodal brand review findings into calibrated PASS, REVIEW, BLOCK, or NEEDS_INPUT decisions with priority handling, version gates, evidence requirements, and owner routing."
---

# Brand Review Decision Engine

Use `../../core/review_engine.py` for deterministic aggregation. The engine expects extracted evidence and risk items; it does not perform OCR, ASR, policy retrieval, or visual recognition.

Decision order:

1. Missing required fields, failed coverage, inaccessible material, or release-hash mismatch → `NEEDS_INPUT`.
2. Confirmed P0 with locatable evidence, or confirmed blocking item with complete evidence → `BLOCK`.
3. Uncertain P0, review item, incomplete evidence, or model disagreement → `REVIEW`.
4. No blocking/review item and complete coverage → `PASS`.
5. Advice-only P3 items never change the main state.

The returned confidence is a heuristic until a gold-set calibration pass is completed. Preserve the trace and do not present it as a probability of legal compliance.

See `../../contracts/review-contract.json` and `../../core/review_engine.py`.
