---
id: ref-dsh-rule-gap-report-activity-snapshot-20261022
title: "[审计读数] DSH 活动规则字段缺口与仓库快照行级差异（2026-10-22）"
collection: 3_措辞表达库
tier: L1
topic: DSH 知识库 · 规则元数据与快照差异
kind: fact
summary: 只读报告发现 639 个唯一规则 ID 均有至少一项 PRD §6.5 字段缺项，63 个 P0 ID 全部在缺口中；规则内容类型显式字段为 0/639，旧 modality 值不能替代。活动库与仓库快照行级差异已按 ID 统计，差异不判定权威端；PRD 九个场景均保持 UNMEASURED，等待批准映射与样本分母。
owner: 刘华丽
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 规则元数据缺口的分层和计数如何读？
  - 旧 modality 字段能否代替 PRD content_type？
  - 活动知识库与仓库快照有差异时能否直接同步？
  - 缺少场景映射和黄金样本时，覆盖状态应如何记录？
not_proves: 不能给缺失元数据推断值；不能证明活动库或仓库快照哪一侧权威；不能证明任何场景已覆盖或未覆盖；不能把当日行数和 ID 计数当作长期事实。
forbidden: 不得按 modality 推断 content_type；不得按 taxonomy 名称相似度推断九场景覆盖；不得直接覆盖或同步 L3/L5；不得把 19/19 P0 规则码一致解释成规则正文和语义覆盖充分。
complements:
  - ref-dsh-kb-rule-hardening-audit-20261022
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/report_dsh_kb_rule_gaps.py
  - /Users/lute/project/audit_multi_content/tools/test_report_dsh_kb_rule_gaps.py
  - /Users/lute/project/audit_multi_content/PMO/DSH规则缺口清单-活动库快照对比-20261022.json
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/DSH规则缺口清单-活动库快照对比-20261022-验收.md
  fingerprint: e6e8bd1bb5805362
  captured_at: 2026-10-22
provenance:
  anchor: PMO/DSH规则缺口清单-活动库快照对比-20261022-验收.md#当前读数/#验收
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 不含个人身份信息；记录规则 ID、计数、路径和审计边界。
---

本条记录 2026-10-22 对 DSH 活动规则库和仓库快照进行只读盘点的可复用方法及现场读数。机器报告按唯一 rule_id 统计 PRD §6.5 元数据缺项，按 rule_id/pattern_id 对规范化 JSON 行计算 SHA-256 多重集差异，并依据 PRD §5.2、§7.2 列出内容类型与九个场景。

当日缺口：639 个唯一规则 ID 均至少缺一个 §6.5 字段，其中 P0 63、P1 243、P2 214、P3 119；content_type 显式值 0/639。旧 modality 字段 516 条为 text、123 条缺失，但不能代替适用内容类型。九个场景均为 UNMEASURED，因为没有经批准的分类映射和应审/黄金样本分母。

行级快照比较：L3 rules 活动库 1,020 行/510 ID、仓库 1,018 行/509 ID，活动侧仅有 1 个额外 ID；external_standard 两边各 129 行，有 6 个 ID 内容不同；p0_patterns 活动侧 19 行、仓库侧 17 行，2 个 ID 仅活动侧存在，17 个共同 ID 内容不同。P0 规则码集合 L3/L5 19/19 一致。所有数据只用于定位；报告不裁定哪侧权威，不改写规则或模式。