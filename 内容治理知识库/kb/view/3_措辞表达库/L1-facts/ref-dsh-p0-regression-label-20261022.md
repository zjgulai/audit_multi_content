---
id: ref-dsh-p0-regression-label-20261022
title: "[验收] P0 回归自证动态模式计数修正（2026-10-22）"
collection: 3_措辞表达库
tier: L1
topic: DSH 知识库 · 回归自证与审计
kind: fact
summary: P0 回归自证文案改为报告实际模式数；仓库快照和活动库分别为 17 与 19，脚本 8/8 通过。修正标签与测试，不改规则或审核工作流。
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 为什么 P0 自证的固定模式数量标签会过期？
  - 如何保证 P0 自证报告的分母与规则数据一致？
not_proves: 不裁定活动库与仓库快照的权威关系，不证明规则语义覆盖已齐全。
forbidden: 不得将模式数写死；不得据此同步规则数据或改变审核口径。
corroborated_by:
  - /Users/lute/project/audit_multi_content/PMO/DSH-P0回归自证动态计数修正-20261022.md
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/DSH-P0回归自证动态计数修正-20261022.md
  fingerprint: 61e89a0b3e9961ee
  captured_at: 2026-10-22
provenance:
  anchor: PMO/DSH-P0回归自证动态计数修正-20261022.md#发现与处理/#验收
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 不含个人身份信息；记录测试与规则计数。
---

2026-10-22 修正 P0 回归自证中的历史硬编码模式数。仓库快照自证报告 17 条模式/162 个用例，活动库自证报告 19 条模式/175 个用例，各自均 8/8 通过。新增测试运行两份脚本并核对显示数与对应模式文件行数。此修改只修正文案的运行时计数来源，不改变规则、审核入口或 skill 工作流。详见 PMO/DSH-P0回归自证动态计数修正-20261022.md。首次入库正文不足 200 字被 E026 拒绝并回滚，随后补充说明重试。