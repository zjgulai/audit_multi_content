---
name: brand-review-report-memory
description: "Generate the brand review JSON, concise Feishu-ready summaries, detailed evidence reports, version traceability, and approved human-feedback candidates for knowledge-base updates."
---

# Brand Review Report Memory

Keep the PRD fields stable and add coverage, input manifest, evidence references, decision trace, calibration state, and version gate fields. Use `../../core/report_memory.py` to render portable Markdown and JSON reports before the Feishu adapter maps them to cloud-document links. A risk item is not complete without a location, reason, and evidence reference.

For one or two issues, render each issue inline. For three or more issues, render category counts and a report link while keeping the complete list in the detailed report. Bind every report to `review_id`, content hash, content version, agent version, rule version, and knowledge version.

Human feedback becomes a candidate sample or rule change only after an owner accepts it. Preserve the original model result and the human conclusion together.
