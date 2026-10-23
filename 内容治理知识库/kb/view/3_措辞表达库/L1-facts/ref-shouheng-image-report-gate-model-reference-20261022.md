---
id: ref-shouheng-image-report-gate-model-reference-20261022
title: 守衡图片报告门必须使用已解析的模型侧结果（2026-10-22）
tier: L1
collection: 3_措辞表达库
kb_class: []
topic: 知识
summary: 图片报告门必须读取本轮已解析的模型侧结果；不能在 dual 尚未赋值时访问 dual?.model，否则会误拒已完成的模型视觉审查并丢失报告/卡片视觉分析。
owner: 内容治理
kind: fact
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
effective_from: 2026-10-22
valid_until: 2027-04-20
asks:
  - 为什么图片模型侧已成功返回，报告仍没有视觉分析与 OCR？
  - 图片报告门是否读取了当前作用域中已解析的模型侧结果？
  - 如何通过行为测试证明模型视觉读数进入合并报告与最终卡片？
  - 部署后还需要什么线上证据才能确认用户可见结果？
not_proves: 离线自证和新进程在线不证明用户端新图片卡片已显示视觉分析；需重发原图确认报告与卡片展示，并核对模型请求确实携带本轮原图。
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/agent.mjs
  - /Users/lute/project/audit_multi_content/tools/test_agent.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/merged_report.test.mjs
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图片视觉分析报告门误拒绝修复-20261022.md
  fingerprint: e1b05d55b84c283e
  captured_at: 2026-10-22
provenance:
  anchor: PMO/守衡-图片视觉分析报告门误拒绝修复-20261022.md#修复与回归判据
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 正文仅含代码链路、判据和验收读数，不含个人数据
---

图片审查报告门必须使用本轮图片模型侧已经解析完成的结果。`runSubmissionGate()` 的报告构建发生在双轨合并对象 `dual` 赋值之前；此处读取 `dual?.model` 会恒得到空值，令 `imageEvidenceFailure()` 将已运行的模型侧误判为未完成。随后完整图片审查内容不进入合并报告，返回卡片也没有 `imageAnalysis`。应将当前作用域中已解析的 `model` 传给报告门。

执行判据：在 `runSubmissionGate()` 行为测试中给定完整 skill 阶段、通过的引擎图片闸、模型侧 `ok: true` 及原图 OCR/视觉场景读数；必须同时断言合并报告包含“图片安全审查 skill 全流程结果”、卡片字段含 OCR 与“视觉模型读数”。反向验证模型侧失败和引擎图片闸拒绝仍阻断结论。静态变量存在性测试不足以替代此行为判据。

部署闭环还须读取重启后 PID、心跳和 `wsConnected=true`；线上展示结论只有在重发原图后检查到卡片与报告确实展示视觉分析，并确认本轮原图进入多模态请求时才能成立。OCR 和视觉描述只是辅助输入，不可替代原图。