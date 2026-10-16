---
name: 证据源维护
description: |
  维护审查依据的证据源：登记监管指引、平台政策与内部规则的版本、生效日期、辖区与适用范围，产出带版本的证据源清单。触发词：证据源维护、证据来源库、加进证据源、登记进证据源、监管指引、平台政策更新、生效日期、适用范围、归到哪个辖区、证据源清单、法规文件登记、审查依据更新、policy source、source manifest。何时不用：用依据去判断某条内容（走 kb-content-review）、核对宣称真伪（走 产品宣称核验）、判断内容能不能发（走 内容审查总控）。

  Maintain versioned, jurisdiction-aware evidence sources for US-market brand content review, including regulator guidance, platform policies, internal rules, product documents, effective dates, owners, and applicability.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Policy Source Curator

Store policy sources as structured records, not free-form model memory. Each source needs `source_id`, publisher, canonical URL, quoted section or locator, jurisdiction, channel, product scope, effective and review dates, owner, and status.

Only approved, in-scope, non-expired sources may support automatic P0/P1 decisions. A fetched page is not automatically authoritative; preserve the retrieval timestamp and snapshot or hash. Use `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/source_manifest.py` to build the Momcozy source manifest and fetch HTML snapshots from the allowlisted `momcozy.com` domain. The resulting `knowledge-base/source-manifest.json` remains `discovery_only` until product/legal owners approve it.

Do not invent evidence URLs. If a source cannot be retrieved or its scope is unclear, emit an evidence gap and route REVIEW. Keep legal or medical sign-off with the designated owner.

Use the source record shape in `~/.dsh/Momcozy知识库/kb/l7/review-engine/contracts/source-record.json`.

## 强制链路里**不适用**（2026-10-03 加）

本 skill **不是素材审查入口**，所以**不套用**「层前置 → 引擎 → 发飞书」那条链 —— 它维护的是**依据的来源**，不是被判的内容。

- 改了证据源/规则 ⇒ 那是**供给链**动作：走 `kb-pipeline` 重跑 L0–L7，让 L1/L2/L3 跟着重抽重切；
- **不要**在评审链里顺手改证据源，也不要顺手发飞书（那会把「改来源」和「判内容」混成一步，事后分不清）。

> 写清「不适用」是为了**别抢活**：照抄强制链路节会让本 skill 去跑别人的层前置 / 替专项下判，
> 而路由表的让位关系（`kb/l7/registry/routes.yaml`）不允许这样。
