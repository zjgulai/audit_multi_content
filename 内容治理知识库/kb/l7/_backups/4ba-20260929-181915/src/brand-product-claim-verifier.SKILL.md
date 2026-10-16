---
name: brand-product-claim-verifier
description: "Extract and verify product claims in US-market brand content against SKU-level product facts, approved wording, tests, certifications, and model/version scope."
---

# Brand Product Claim Verifier

Extract both explicit and reasonably implied claims from copy, OCR, subtitles, voice, and visual demonstrations. Normalize each claim to a type such as feature, performance, safety, health, comparison, certification, ranking, or endorsement.

Compare claims against the approved facts for the submitted SKU and version. The staging queue is `../../knowledge-base/product-fact-approval-queue.json`; the active library is `../../knowledge-base/product-fact-library.json`. The confirmed approval matrix is `../../knowledge-base/product-fact-approval-policy.json`. Use `product_fact_gate` in `../../core/product_fact_queue.py` before treating a product claim as supported. Discovery facts remain unavailable to automatic PASS until all required owner approvals and approved wording are recorded. Distinguish:

Persist role decisions with `../../core/product_fact_approval.py`. It appends an idempotent event, updates the queue, and rebuilds the active library from approved entries only.

- `supported`: exact model and evidence match;
- `mismatch`: claim conflicts with the model, region, or approved wording;
- `insufficient_evidence`: claim may be true but the required proof is absent;
- `out_of_scope`: no applicable fact is available.

`mismatch` with reliable evidence can be BLOCK; `insufficient_evidence` and `out_of_scope` default to REVIEW. Never treat a generic product page as proof for a different model.
