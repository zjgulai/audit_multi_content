---
name: brand-text-compliance-review
description: "Review US-market captions, listings, PDP copy, social copy, OCR text, subtitles, and voice transcripts for advertising, safety, product-claim, endorsement, and wording risks."
---

# Brand Text Compliance Review

Extract claims before editing language. Use `../../core/rule_engine.py` for deterministic candidate scanning, then check medical or health implications, safety promises, absolute or ranking language, unsupported numbers, testimonials and endorsements, required disclosures, product/model accuracy, and channel-specific restrictions.

Every finding must include the original text, exact location, risk type, priority tier, reason, evidence reference, and suggested action. Use `copy-editor` only for P3 clarity and wording suggestions; it must not override legal, medical, safety, or product-fact findings.

When context changes the meaning of a flagged phrase, mark it `uncertain` and route REVIEW. Do not block a phrase merely because a token appears in a negation, warning, quote, or comparison.
