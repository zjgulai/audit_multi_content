---
name: brand-video-safety-review
description: "Review US-market brand videos using transcript, OCR, shot, keyframe, audio-visual alignment, and timecode evidence for safety, product, endorsement, AI, and platform risks."
---

# Brand Video Safety Review

Return ASR, subtitle text, OCR, shot boundaries, representative frames, and audio/visual alignment through the provider-neutral contract in `../../knowledge-base/multimodal-provider-contract.json`. During the local-first phase, an offline result may be supplied using `../../contracts/offline-extraction-result.json` and passed through `../../core/offline_review.py`. Start with a low-cost full-video scan, then increase sampling around risk words, scene changes, infants, vehicles, sleep, feeding, water, heat, electricity, or product demonstrations.

Every finding needs start/end timecodes, transcript or frame evidence, and the input video hash. Pass transcript, OCR, and textual keyframe observations through `../../core/product_fact_integration.py` when the submission has a SKU, so unapproved product claims become REVIEW and missing evidence becomes NEEDS_INPUT. Treat a missing audio track, unreadable subtitles, incomplete keyframes, or unresolved audio/visual contradiction as a coverage gap. Do not PASS a continuous safety scenario when the extraction cannot establish continuity.

`video-compare-tool` is for compression quality and is not a safety reviewer; use it only when a separate visual-quality comparison is explicitly requested.
