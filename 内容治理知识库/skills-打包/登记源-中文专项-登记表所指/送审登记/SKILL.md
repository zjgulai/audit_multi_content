---
name: 送审登记
description: |
  送审入口与登记：采集并规范化素材的哈希、SKU、渠道、语言、版本与权限状态，校验提交格式并补齐缺失字段。触发词：送审登记、送审入口、提交送审、素材登记入库、登记入库、采集哈希、SKU 登记、渠道和语言标记、素材格式校验、缺的字段补上、批量送审、规范化登记、权限状态、intake router。何时不用：判断内容能不能发（走 内容审查总控；只看一段文字走 文案合规审查）、审查本身的执行（走各专项）、出报告（走 审查报告与记忆）。

  Normalize and validate pre-publication brand content submissions, including text, image, video, URLs, and batch rows, while capturing hashes, versions, SKU, channel, language, and permission status.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Review Intake Router

Create one review manifest per submitted version. Use `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/intake_router.py` for public URL, local file, pasted text, and JSON/CSV/TSV batch inputs. Preserve the original source reference and compute a stable content hash when the file or text is available.

Required metadata: `review_id`, `content_id`, `content_version`, `content_type`, `product_line`, `channel`, submitter, source, language, SKU/model scope, and access status.

Use `NEEDS_INPUT` when the material is inaccessible, the release version is unknown, the SKU is missing for a product claim review, or the requested modality extraction failed. Do not silently substitute a thumbnail, preview, or prior version.

Emit `coverage` for text, image, audio, video, OCR, ASR, and keyframes. Values are `complete`, `incomplete`, `failed`, or `not_applicable`. Downstream decision logic treats incomplete or failed required coverage as a gate failure.

See `~/.dsh/Momcozy知识库/kb/l7/review-engine/contracts/review-contract.json` for the manifest contract.

## 强制链路里**不适用**（2026-10-03 加）

本 skill **不是素材审查入口**，所以**不套用**「层前置 → 引擎 → 发飞书」那条链 —— 它发生在审查**之前**（采集哈希 / SKU / 渠道 / 版本 / 权限）。

- 它产出的 `content_version` 正是发布件自动生成 `AUTO-<前 12 位>` 的依据 —— **请保持该算法稳定**；
- 它**不跑层前置、不发飞书**；登记完交上游（`kb-review` / 专项）去审。

> 写清「不适用」是为了**别抢活**：照抄强制链路节会让本 skill 去跑别人的层前置 / 替专项下判，
> 而路由表的让位关系（`kb/l7/registry/routes.yaml`）不允许这样。
