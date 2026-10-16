---
name: brand-content-review-agent
description: |
  Orchestrate local pre-publication review of US-market brand text, image, and video assets for breast pumps, baby monitors, bottle washers, and feeding products. Use when a submission needs versioned PASS, REVIEW, BLOCK, or NEEDS_INPUT decisions, evidence, and human routing.
  【中文入口 · 一批素材的发布前审查全流程】当用户要**一批**素材（文字 + 图片 + 视频混在一起）
  走**发布前审查全流程**、并要一个**统一结论**时使用：
  「送审 / 送审一批素材 / 走一遍发布前审查 / 审查全流程 / 这批素材一起审 /
   给个统一结论 / 这批素材最后到底能不能上 / 文字图片视频一起过一遍发布前审查 /
   统一出个结论并告诉该找谁 / 串起来从收素材到出结论」。
  触发词：送审、送审一批、发布前审查、发布前审查全流程、审查全流程、这批素材一起审、
  统一结论、一起过一遍、pre-publication review、submission review、
  brand-content-review-agent。
  不适用（**已能识别专项就别抢活**，交给对应成员）：
    · 单条文字 / 广告用语 / listing、PDP 文案 → brand-text-compliance-review；
    · 单张图片 / 主图 / 图上文字 → brand-image-safety-review；
    · 单条视频 / 短视频 / 画面时间码 → brand-video-safety-review（视频安全审查）；
    · 产品宣称真伪 / SKU 事实 / 认证范围 → brand-product-claim-verifier；
    · AI 生成披露 / 肖像商标授权 / 儿童出镜隐私 → brand-ai-provenance-rights-review；
    · 美国本地化 / 计量单位 / 文化歧义 → brand-us-locale-cultural-review；
    · 只要某条判定或某条结论的**依据** → kb-content-review；
    · 专项归属不明 / 单条内容该不该拦，且用户没要全流程 → kb-review；
    · 只要送审登记（哈希 / SKU / 渠道采集）→ brand-review-intake-router；
    · 只要最终裁决、不要全流程 → brand-review-decision-engine；
    · 只要报告 / 群发摘要 / 存档 → brand-review-report-memory；
    · 结果同步到飞书群与多维表格 → brand-feishu-review-adapter；
    · 评测审查流程本身的准确率 / 漏放 → brand-review-evaluation。
---

# Brand Content Review Agent

Use this skill as the workflow entry point **for a batch submission that needs the full
pre-publication flow and one consolidated decision**. Keep the review core independent from
Feishu, model vendors, and storage providers.

## 何时由本 skill 接（中文口径）

- 用户送来**一批**素材（≥2 类模态，或明确说"一起审"），要**一个**统一结论；
- 用户要**全流程**：收素材 → 登记 → 专项 → 事实闸门 → 裁决 → 报告 → 分派；
- 用户要**版本留痕**与**责任人分派**。

**只接到此为止**：单条内容、已能识别专项的，按 description 的"不适用"交给对应成员。
本 skill 是**编排者**，不是审查员——专项判定一律下沉给专项成员，否则它们的触发出测会归零。

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
