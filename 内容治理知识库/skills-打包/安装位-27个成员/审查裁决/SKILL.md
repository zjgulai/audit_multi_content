---
name: 审查裁决
description: |
  把多条审查发现汇总成最终裁决：按优先级、版本门与证据要求，产出 PASS / REVIEW / BLOCK / NEEDS_INPUT 并指明责任人。触发词：审查裁决、最终裁决、汇总成最终结论、汇总成一个结论、通过还是打回、按优先级给结论、最终结论和责任人、综合各侧意见、到底能不能发、版本门、证据要求、多条发现汇总、decision engine。何时不用：生成报告或摘要（走 审查报告与记忆）、各专项检查本身（走对应专项 skill）、推送到飞书（走 飞书审查流转）。

  Aggregate multimodal brand review findings into calibrated PASS, REVIEW, BLOCK, or NEEDS_INPUT decisions with priority handling, version gates, evidence requirements, and owner routing.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Review Decision Engine

Use `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/review_engine.py` for deterministic aggregation. The engine expects extracted evidence and risk items; it does not perform OCR, ASR, policy retrieval, or visual recognition.

Decision order:

1. Missing required fields, failed coverage, inaccessible material, or release-hash mismatch → `NEEDS_INPUT`.
2. Confirmed P0 with locatable evidence, or confirmed blocking item with complete evidence → `BLOCK`.
3. Uncertain P0, review item, incomplete evidence, or model disagreement → `REVIEW`.
4. No blocking/review item and complete coverage → `PASS`.
5. Advice-only P3 items never change the main state.

The returned confidence is a heuristic until a gold-set calibration pass is completed. Preserve the trace and do not present it as a probability of legal compliance.

See `~/.dsh/Momcozy知识库/kb/l7/review-engine/contracts/review-contract.json` and `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/review_engine.py`.

## 强制链路里的位置（2026-10-03 加）：**下游，不重复跑层前置**

本 skill 是**裁决 / 报告**环节，不是素材审查入口 —— 所以它**不重复跑 L4–L6 层前置**：
上游（专项 / `kb-review`）给出的 findings **已经带四段溯源**（L4 条款号 ＋ L3 规则与命中片段 ＋ L2 单元 id
＋ L1 抽取件 ＋ **L0 源记录飞书直链与逐字核对**），直接消费即可。

要**发出去**（云文档 ＋「内容治理」多维表格行）就走发布件，别自己拼飞书 API：

```bash
sh kb/kbpy l7/review-engine/core/feishu_publish.py --review-json <引擎json> --apply
```

- 报告**从第 1 行写**（第一行 = 报告标题 H1；写已有文档用 `docs +update --command overwrite`，**禁 `append`**）；
- 表行按 `内容 ID` **upsert**（重复发布不新增行）；去向唯一真源 = `kb/l7/registry/conclusion-destination.yaml`；
- 元数据会自动补（`AUTO-<content_version 前 12 位>` / `未指定` / `v1.0`），**不必问用户**。
