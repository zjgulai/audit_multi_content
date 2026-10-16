---
name: brand-feishu-review-adapter
description: "Adapt the local brand review contract to Feishu group mentions, files, multidimensional tables, cloud documents, status updates, and owner routing without coupling Feishu into the review core."
---

# Brand Feishu Review Adapter

Treat Feishu as a transport and workflow adapter. Convert incoming messages, attachments, URLs, and batch rows into the local review contract; convert engine results into a concise message, a detailed report link, and a table update.

Preserve `review_id`, input hash, content version, and source URL across every write. Use idempotency on `review_id + content_version`; a repeated webhook must not create a second review. Do not place full sensitive media in messages or table cells when a restricted report link is available.

Required adapter capabilities:

- group mention intake;
- file/link permission check;
- multi-dimensional table read/write;
- cloud document report creation or link registration;
- owner mentions for REVIEW and sign-off;
- status update for resubmission and human conclusion.

If no Feishu connector or credentials are available, expose the same interface through JSON files or webhooks. Use `../../core/feishu_adapter.py` for the local fallback: it writes a chat message, report link, role-placeholder mentions, and multidimensional-table patch with idempotency on `review_id + content_version`. The core engine must remain runnable without Feishu.
