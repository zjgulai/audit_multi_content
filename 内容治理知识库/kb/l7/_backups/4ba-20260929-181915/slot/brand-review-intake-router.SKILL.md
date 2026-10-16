---
name: brand-review-intake-router
description: "Normalize and validate pre-publication brand content submissions, including text, image, video, URLs, and batch rows, while capturing hashes, versions, SKU, channel, language, and permission status."
---

# Brand Review Intake Router

Create one review manifest per submitted version. Use `../../core/intake_router.py` for public URL, local file, pasted text, and JSON/CSV/TSV batch inputs. Preserve the original source reference and compute a stable content hash when the file or text is available.

Required metadata: `review_id`, `content_id`, `content_version`, `content_type`, `product_line`, `channel`, submitter, source, language, SKU/model scope, and access status.

Use `NEEDS_INPUT` when the material is inaccessible, the release version is unknown, the SKU is missing for a product claim review, or the requested modality extraction failed. Do not silently substitute a thumbnail, preview, or prior version.

Emit `coverage` for text, image, audio, video, OCR, ASR, and keyframes. Values are `complete`, `incomplete`, `failed`, or `not_applicable`. Downstream decision logic treats incomplete or failed required coverage as a gate failure.

See `../../contracts/review-contract.json` for the manifest contract.
