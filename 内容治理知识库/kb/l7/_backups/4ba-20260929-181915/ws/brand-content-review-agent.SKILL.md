---
name: brand-content-review-agent
description: "Orchestrate local pre-publication review of US-market brand text, image, and video assets for breast pumps, baby monitors, bottle washers, and feeding products. Use when a submission needs versioned PASS, REVIEW, BLOCK, or NEEDS_INPUT decisions, evidence, and human routing."
---

# Brand Content Review Agent

Use this skill as the workflow entry point. Keep the review core independent from Feishu, model vendors, and storage providers.

## Workflow

1. Validate the review payload against `../../contracts/review-contract.json`.
2. Preserve the input file hash, content version, product line, channel, SKU, and source permissions.
3. Run the relevant modality adapters. They must emit locatable evidence and risk items; they must not decide the final state. For an offline OCR/ASR/keyframe result, use `../../core/offline_review.py` with `../../contracts/offline-extraction-result.json`.
4. Run the product-fact gate on claims found in any text, OCR, ASR, or visual extraction before running `brand-review-decision-engine` through `../../core/review_engine.py`.
   For a text-only smoke test, use `../../core/review_text.py` to combine the seed scanner and the decision engine.
5. Generate the concise summary and detailed evidence report with `brand-review-report-memory`.
6. Route PASS to sign-off, REVIEW to the relevant specialist, BLOCK back to the submitter, and NEEDS_INPUT back for missing material or metadata.
7. Store the decision with agent, rule, knowledge, model, input hash, and release hash versions.

## Hard gates

- Never emit PASS when required modality extraction, SKU scope, evidence, permissions, or release-version matching is incomplete.
- Treat P0 keyword hits as candidates until context and evidence are resolved.
- P3 wording suggestions never change the main decision.
- Human conclusions are feedback candidates until an owner approves a rule or sample update.

Read `../../contracts/review-contract.json` for the shared payload and `../../PLAN.md` for the workflow boundaries.
