---
id: ref-dsh-kb-rule-hardening-audit-20261022
title: "[审计方法] DSH 知识库规则元数据与 P0 链路只读审计（2026-10-22）"
collection: 3_措辞表达库
tier: L1
topic: DSH 知识库 · 规则审计与可追溯性
kind: fact
summary: 只读审计 L3/L5 P0 规则代码一致性、PRD §6.5 元数据、fastpath 来源指纹和仓库快照漂移；2026-10-22 实测 P0 代码 19/19 一致、639 个唯一规则 ID 均有至少一项 §6.5 元数据缺口，活动库 3 个受审文件均与仓库快照不同。缺项必须由责任方据源补齐，禁止按推断批量填值；审计器不接入单审热路径，不改 skill 路由和 L0-L7 顺序。
owner: 刘华丽
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 如何审计 DSH 内容审核规则的 P0 代码一致性与 PRD 元数据完整性？
  - 规则元数据缺失时，是否可以按相邻规则或经验批量补全？
  - 只读知识库审计如何避免影响现有 skill 自动化工作流？
not_proves: 不能证明 639 个元数据缺项的具体值；不能证明活动知识库与仓库快照应当完全一致；不能替代业务或法务裁定；不能证明运行时规则已被修改或部署。
forbidden: 不得按推断补入产品线、渠道、风险等级、来源、版本或责任人；不得把 2026-10-22 的计数当作永久事实；不得把只读审计器接入单条审核热路径；不得改变 PRD/skill 工作流、拒答闸门或 L0-L7 顺序。
corroborated_by:
  - /Users/lute/project/audit_multi_content/docs/superpowers/specs/2026-10-22-dsh-kb-rule-hardening.md
  - /Users/lute/project/audit_multi_content/docs/superpowers/plans/2026-10-22-dsh-kb-rule-hardening.md
  - /Users/lute/project/audit_multi_content/tools/verify_dsh_kb_rules.py
  - /Users/lute/project/audit_multi_content/tools/test_verify_dsh_kb_rules.py
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/DSH知识库规则加固-首批审计器验收-20261022.md
  fingerprint: 1104249dcef61108
  captured_at: 2026-10-22
provenance:
  anchor: PMO/DSH知识库规则加固-首批审计器验收-20261022.md#首批审计发现/#工作流兼容与边界
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 内容只含系统审计读数、文件路径和流程边界；无个人联系信息。
---

本条记录一项可复用的 DSH 知识库规则审计方法与 2026-10-22 实测结果。审计器动态读取运行时知识库根路径，只读检查 L3 与 L5 的 P0 规则代码是否一致、PRD §6.5 所需元数据是否齐全、fastpath 规则是否可追溯到 L3、来源 SHA-256 是否有效，并报告活动库与仓库快照的文件指纹差异。

当日读数：L3 规则 1,020 行、外部标准 129 行、639 个唯一规则 ID、63 个唯一 P0 规则 ID；L3/L5 的 P0 代码集合 19/19 一致。639 个唯一规则 ID 均存在至少一项 PRD §6.5 元数据缺项；缺项维度计数见来源 PMO 留底。活动库的 rules.jsonl、external_standard.jsonl、p0_patterns.jsonl 三个受审文件均与仓库快照不同。审计器按设计报告 FAIL，不猜测元数据、不自动同步或覆盖活动库。

边界：只读审计器独立运行，不进入单条审核热路径；不改入向路由、skill handoff、L0-L7 顺序、三态结论、P0 停止规则或发布闸门。所有元数据补齐都必须由来源文件、业务/法务责任人和对应 PRD 条款逐项确认，再单独走知识库正式入库、读回和回归验收。