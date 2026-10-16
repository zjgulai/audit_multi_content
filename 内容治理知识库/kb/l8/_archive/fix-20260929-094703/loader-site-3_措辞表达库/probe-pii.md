---
id: probe-pii
title: 闸门探针
collection: 3_措辞表达库
tier: L2
topic: 测试
summary: 验证框架闸门
owner: 刘华丽
kind: judgment
evidence_level: L2
data_level: L2
half_life_days: 200
created_at: 2026-09-17
valid_until: 2027-09-17
asks:
  - 闸门会不会拦
not_proves: 不能证明闸门有效
source:
  kind: file
  ref: /tmp/x
  fingerprint: abc12345
  captured_at: 2026-09-17
provenance:
  anchor: 探针
  confidence: 确定
verification:
  independent_sources: 2
  predictive: 2
  non_obvious: 2
  score: 1
  verdict: keep
sensitivity_level: L2
pii:
  detected: true
  masked: false
  strategy: ""
---

本条目记录的是闸门探针的实测结论。校验器需要检查元字段完整性、子库登记情况、层级与路径是否一致。
内容质量门控会从长度、信息密度、重复率、语言质量四个维度分别打分，总分低于阈值即拒绝入库。
三重验证要求独立佐证、预测力与非常识三条判据同时满足，缺任何一条都要降级或者直接淘汰掉。
数据分级与个人隐私检测属于安全红线，凡是检出敏感信息又没有脱敏的内容一律不得进入知识库。
冲突处置分为数值冲突、时态更迭与观点分歧三类，其中观点分歧只呈现不裁决，交给人工来定夺。
删除动作有四道前置闸门，快照路径、显式目标、逐字确认与回滚负责人缺一不可，少一道就不许执行。
