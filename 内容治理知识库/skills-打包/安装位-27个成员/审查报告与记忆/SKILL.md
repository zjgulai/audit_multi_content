---
name: 审查报告与记忆
description: |
  生成审查报告与留痕：带证据链与版本追溯的完整报告、可直接群发的精简摘要、审查记录存档，并把人工反馈整理成候选条目。触发词：审查报告与记忆、审查报告、证据报告、详细证据报告、带证据链的审查结论、版本追溯、群发摘要、可以直接贴到群里的摘要、能直接发飞书的摘要、审查记录存档、过程和结论整理成报告、整理成报告、人工反馈整理、候选条目、report memory。何时不用：做最终裁决（走 审查裁决）、把结果推到飞书（走 飞书审查流转）、判断内容本身能不能发（走 内容审查总控）。

  Generate the brand review JSON, concise Feishu-ready summaries, detailed evidence reports, version traceability, and approved human-feedback candidates for knowledge-base updates.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Review Report Memory

Keep the PRD fields stable and add coverage, input manifest, evidence references, decision trace, calibration state, and version gate fields. Use `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/report_memory.py` to render portable Markdown and JSON reports before the Feishu adapter maps them to cloud-document links. A risk item is not complete without a location, reason, and evidence reference.

For one or two issues, render each issue inline. For three or more issues, render category counts and a report link while keeping the complete list in the detailed report. Bind every report to `review_id`, content hash, content version, agent version, rule version, and knowledge version.

Human feedback becomes a candidate sample or rule change only after an owner accepts it. Preserve the original model result and the human conclusion together.

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
