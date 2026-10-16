---
name: brand-policy-source-curator
description: "Maintain versioned, jurisdiction-aware evidence sources for US-market brand content review, including regulator guidance, platform policies, internal rules, product documents, effective dates, owners, and applicability."
---

# Brand Policy Source Curator

Store policy sources as structured records, not free-form model memory. Each source needs `source_id`, publisher, canonical URL, quoted section or locator, jurisdiction, channel, product scope, effective and review dates, owner, and status.

Only approved, in-scope, non-expired sources may support automatic P0/P1 decisions. A fetched page is not automatically authoritative; preserve the retrieval timestamp and snapshot or hash. Use `../../core/source_manifest.py` to build the Momcozy source manifest and fetch HTML snapshots from the allowlisted `momcozy.com` domain. The resulting `knowledge-base/source-manifest.json` remains `discovery_only` until product/legal owners approve it.

Do not invent evidence URLs. If a source cannot be retrieved or its scope is unclear, emit an evidence gap and route REVIEW. Keep legal or medical sign-off with the designated owner.

Use the source record shape in `../../contracts/source-record.json`.
