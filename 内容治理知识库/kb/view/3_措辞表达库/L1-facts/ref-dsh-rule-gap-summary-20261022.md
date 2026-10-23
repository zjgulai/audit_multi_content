---
id: ref-dsh-rule-gap-summary-20261022
title: "[审计摘要] DSH 规则缺口与活动库/仓库快照差异（2026-10-22）"
collection: 3_措辞表达库
tier: L1
topic: DSH 知识库 · 规则治理只读报告
kind: fact
summary: 可读版报告汇总 639 个唯一规则 ID 的 §6.5 元数据缺项，并给出 L3/L5 活动库与仓库快照按 ID 的内容差异。P0 代码集合 19/19 一致；63 个 P0 ID 均存在元数据缺项。九个 PRD 场景保持 UNMEASURED，因为没有批准的映射与黄金样本分母。
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 如何解释本次活动规则库元数据缺口与快照差异？
  - 为什么 PRD 九场景都应报告为 UNMEASURED？
  - P0 规则码对齐能证明哪些范围，不能证明哪些范围？
not_proves: 不证明活动库或仓库快照哪一侧权威；不证明各场景已经完整覆盖；不提供任何缺失规则属性的推断值；读数只适用于本次快照。
forbidden: 不得按 modality 填 content_type；不得把 P0 code parity 当成规则语义覆盖证明；不得依据名称相似判定场景覆盖；不得直接覆盖或同步规则文件。
complements:
  - ref-dsh-rule-gap-report-activity-snapshot-20261022
corroborated_by:
  - /Users/lute/project/audit_multi_content/PMO/DSH规则缺口清单-活动库快照对比-20261022-验收.md
  - /Users/lute/project/audit_multi_content/PMO/DSH规则缺口清单-活动库快照对比-20261022.json
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/DSH规则缺口清单-活动库快照对比-20261022.md
  fingerprint: 6df96e860f8d7303
  captured_at: 2026-10-22
provenance:
  anchor: PMO/DSH规则缺口清单-活动库快照对比-20261022.md#结论/#当前限制与后续动作
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 无个人身份信息；包含规则计数、文件差异和流程边界。
---

本条为 2026-10-22 DSH 规则审计结果的可读摘要；完整逐规则缺口、hash 行级差异和运行环境路径见所链接 JSON。活动知识库与仓库快照分别读取，不自动同步。

639/639 唯一 rule_id 缺少至少一项 PRD §6.5 元数据；63 个 P0 规则 ID 均在缺口清单。content_type 显式适用范围值为 0/639；旧 modality 字段不能替代。PRD §7.2 九个场景均为 UNMEASURED，直到 Owner 批准规则到场景映射并给出应审规则和黄金样本分母。

P0 规则码 L3/L5 19/19 一致。行级快照差异为：L3 rules 活动 1,020 行/510 ID，快照 1,018 行/509 ID，活动仅多 1 ID；external_standard 有 6 个共同 ID 内容不同；p0_patterns 有 2 个活动独有 ID、17 个共同 ID 内容不同。差异只用于排查，不足以裁定哪侧权威。该摘要只有一个证据来源，证据级别是 L1 线索，不能作为权威规则源。