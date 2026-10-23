---
id: ref-dsh-regression-trace-matrix-20261022
title: "[审计矩阵] DSH 专项回归证据与待测项（2026-10-22）"
collection: 3_措辞表达库
tier: L1
topic: DSH 知识库 · 回归追溯与验收
kind: fact
summary: 盘点 P0 正例计数、共享边界反例、L7 既有测试及 PRD 九场景未测状态；不把局部测试外推为全规则覆盖。
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 哪些 P0 规则码已有逐字正例测试？
  - 现有 matcher 反例能证明哪些边界，哪些仍未测？
  - 为什么 PRD §7.2 九个场景必须保持 UNMEASURED？
not_proves: 不证明法律正确性、各规则适用范围或 P1-P3 场景覆盖完整；不把共享反例解释成逐 rule_id 覆盖。
forbidden: 不得按规则码猜 rule_id 映射；不得补造反例或预期 verdict；不得将 UNMEASURED 汇总成已覆盖。
corroborated_by:
  - /Users/lute/project/audit_multi_content/PMO/DSH专项回归追溯矩阵-20261022.md
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/DSH专项回归追溯矩阵-20261022.md
  fingerprint: 5312706808011a4b
  captured_at: 2026-10-22
provenance:
  anchor: PMO/DSH专项回归追溯矩阵-20261022.md#验收口径/#PRD-7.2-场景域
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 无个人身份信息；包含规则计数和测试追溯状态。
---

本矩阵盘点 2026-10-22 活动 P0 回归正例、共享边界反例、L7 既有测试和 PRD §7.2 九场景状态。19 个 P0 规则码有 175/175 个逐字源正例命中；否定/引用/全角/中英文反例目前是共享覆盖，不能外推为每个 rule_id 全覆盖。PRD 九场景均保持 UNMEASURED，直到有批准映射和样本分母。矩阵区分 TESTED、PARTIAL、UNMEASURED，不补规则值，不裁决法务语义。