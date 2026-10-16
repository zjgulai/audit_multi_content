---
name: brand-image-safety-review
description: "Review US-market brand images for OCR text, product and scene accuracy, infant and child safety, privacy, AI provenance, endorsement, and other locatable content risks."
---

# Brand Image Safety Review

Use the provider-neutral contract in `../../knowledge-base/multimodal-provider-contract.json` for OCR, object, person, activity, and scene observations. A vendor adapter may use `vision-analysis` or another provider, but it must return the material hash, provider version, coverage status, and region evidence. Add domain rules for car seats, sleep, feeding, washing, bathing, household power, infant handling, privacy, and AI-generated or composited scenes.

Record bounding-box or region descriptions and the image hash for each finding. Pass OCR and textual visual observations through `../../core/product_fact_integration.py` when the submission has a SKU, so unapproved product claims become REVIEW and missing evidence becomes NEEDS_INPUT. Separate observation from interpretation: “infant is on an adult bed” is evidence; the safety classification and applicable rule are a subsequent finding.

If the image is too small, occluded, or ambiguous to establish a safety fact, emit REVIEW or NEEDS_INPUT rather than PASS. Do not judge aesthetics, typography, or color unless they create a safety, claim, or platform-policy issue.
