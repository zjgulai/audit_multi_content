---
id: ref-dsh-kbh04a-kbh05-acceptance-20261022
title: "[验收] DSH KBH-04A 逐规则正例索引与 KBH-05 PRD 输出夹具（2026-10-22）"
tier: L1
collection: 3_措辞表达库
topic: DSH 知识库规则 · 自动化验收与追溯
kind: fact
summary: 活动库 639 个唯一 rule_id 中，19 个 P0 规则有 169/169 条逐字来源正例按精确 rule_id 命中；其余 620 个未映射项保持 UNMEASURED。新增 PRD §5.3 固定输出夹具验证三态、计数、证据链接、报告门槛与回执；不改规则与 skill 工作流。
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 活动库逐 rule_id 正例索引和每条规则的当前测试状态是什么？
  - PRD §5.3 的三态、报告阈值、唯一计数和证据链接有哪些固定验收样例？
  - 哪些规则边界和线上链接仍未测或需要专业确认？
not_proves: 不证明规则法律或医学含义正确，不把 620 个未映射规则和共享负例算作覆盖，不证明 example.invalid 测试链接线上可达或有效期不少于 30 天。
forbidden: 不得按 rule_code 猜 rule_id；不得把 UNMEASURED 说成通过；不得把自动化样例命中解释为 Owner、法务或医学裁定；不得改变审核 skill 工作流。
related:
  - ref-dsh-regression-trace-matrix-20261022
corroborated_by:
  - /Users/lute/project/audit_multi_content/PMO/DSH专项回归追溯矩阵-20261022.md
  - /Users/lute/project/audit_multi_content/PMO/DSH规则逐rule_id样例与测试索引-20261022.json
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/DSH-KBH04A-KBH05验收-20261022.md
  fingerprint: 2563a9572e9d8198
  captured_at: 2026-10-22
provenance:
  anchor: PMO/DSH-KBH04A-KBH05验收-20261022.md#KBH-04A-读数/#KBH-05-验收
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 不包含个人身份信息；记录规则计数与验收状态。
---

本条记录 2026-10-22 DSH 规则整改自动化验收。KBH-04A 使用活动库真实输入和只读 P0 引擎，以 rule_id 为唯一连接键：639 个唯一规则 ID 中 19 个直接映射到 P0 模式，169/169 条逐字来源/规则边界样例均由相同 rule_id 命中；620 个未映射规则保持 UNMEASURED，未将规则码级共享反例冒充逐规则覆盖。逐条路径、源锚点、样例、测试 ID 和源文件 SHA-256 见 PMO/DSH规则逐rule_id样例与测试索引-20261022.json。KBH-05 固定样例运行真实 mergedState、mergeFindings、renderMerged 和报告渲染器，验证 PASS/REVIEW/BLOCK、2 条逐项输出、3 条摘要与报告门槛、原文证据链接、同位置重复项只计一次、不同面板不合并及动作回执；跨层媒材身份、报告字段和回执顺序连接到 tools/test_agent.mjs 现有测试。此次只新增显式本地审计与验收入口，没有更改 L0–L7 规则/判断、路由、技能、评审链、发送闸门或守衡运行态。否定边界、场景映射、外链可达性仍是待测或待确认。完整判据、复现命令和存量失败见 PMO/DSH-KBH04A-KBH05验收-20261022.md 与 PMO/DSH专项回归追溯矩阵-20261022.md。