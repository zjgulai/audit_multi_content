---
id: ref-dsh-kbh04a-kbh05-acceptance-fixture-v2-20261022
title: "[补充验收] DSH KBH-05 新增 BLOCK≥3 固定样例（2026-10-22）"
tier: L1
collection: 3_措辞表达库
topic: DSH 知识库规则 · 固定输出夹具补充验收
kind: fact
summary: KBH-05 固定夹具由三条扩展为 REVIEW 2/3 与 BLOCK 2/4 共四条，增加 PRD §5.3 BLOCK≥3 汇总/报告链接路径；另固定三态输入。KBH-04A 精确 rule_id 索引和活动源文件指纹未改变。
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - PRD §5.3 BLOCK≥3 是否正确走汇总和报告链接路径？
  - 当前 KBH-05 固定夹具有哪些正向样例？
not_proves: 不证明线上飞书链接可达或有效期达到 30 天；不证明规则语义获法务或医学确认。
forbidden: 不得把本地保留域链接描述为线上有效；不得改规则或 skill 工作流。
related:
  - ref-dsh-kbh04a-kbh05-acceptance-20261022
corroborated_by:
  - /Users/lute/project/audit_multi_content/PMO/DSH专项回归追溯矩阵-20261022.md
  - /Users/lute/project/audit_multi_content/PMO/DSH规则逐rule_id样例与测试索引-20261022.json
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/DSH-KBH04A-KBH05验收-20261022.md
  fingerprint: 96cd9819ded53c9b
  captured_at: 2026-10-22
provenance:
  anchor: PMO/DSH-KBH04A-KBH05验收-20261022.md#KBH-05-验收
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 不包含个人身份信息。
---

本条为上一份 DSH KBH-04A/05 验收记录的固定夹具扩展补充。最终夹具含 REVIEW 2 条逐项、REVIEW 3 条汇总、BLOCK 2 条逐项、BLOCK 4 条汇总共四个输出样例；PASS、REVIEW、BLOCK 三态输入各一条。新增 BLOCK 4 条样例实际调用 dual_track 的 renderMerged() 和 merged_report 的 renderMergedReportMd()，断言摘要计数、报告链接门槛、完整报告里的逐条原文证据以及 BLOCK 动作行。命令 node tools/agent/prd53_acceptance.test.mjs 输出“4 个输出样例 + 3 个三态输入 + 证据/唯一计数通过”。此前的三条夹具 entry 保留为历史执行记录；当前最终规格与复现信息见 PMO/DSH-KBH04A-KBH05验收-20261022.md、PMO/DSH专项回归追溯矩阵-20261022.md。