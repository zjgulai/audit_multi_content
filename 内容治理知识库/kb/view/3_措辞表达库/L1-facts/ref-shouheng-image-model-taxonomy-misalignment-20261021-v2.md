---
id: ref-shouheng-image-model-taxonomy-misalignment-20261021-v2
title: 守衡图片审查：A3 类目错位保留模型发现（补丁已加载）
tier: L1
collection: 3_措辞表达库
kb_class: []
topic: 知识
summary: 模型把合法 A3 所属类别误填到方向类目字段时保留发现；补丁已重启加载，WebSocket 在线，等待用户新图片验证。
owner: 内容治理
kind: fact
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-21
effective_from: 2026-10-21
valid_until: 2027-04-19
supersedes: ref-shouheng-image-model-taxonomy-misalignment-20261021
asks:
  - 合法 A3 类目误填方向字段时是否保留？
  - 线上新图片的 model.dropped 是否不再包含合法 A3 类目？
  - 原图是否仍作为模型图片输入且 KB 具体建议可见？
not_proves: 新图片尚未在类目映射补丁加载后重放；目前已证明之前的线上模型侧成功、KB 有 4 条，且新代码自证通过。
derived_from:
  - ref-shouheng-image-model-original-image-multimodal-20261021
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/model_side_limit.test.mjs
  - /Users/lute/project/audit_multi_content/PMO/shouheng-state/merged-reports/merged-2026-10-21T10_03_40.046Z-1792577020046.json
  - /Users/lute/project/audit_multi_content/PMO/logs/restart-ledger.jsonl
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图片模型类目错位与线上双轨验证-20261021.md
  fingerprint: 58713cda5fa1680b
  captured_at: 2026-10-21
provenance:
  anchor: PMO/守衡-图片模型类目错位与线上双轨验证-20261021.md#2026-10-21-后续类目补丁已加载
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 仅含代码规则与脱敏后的验收记录
---

模型把合法 A3 所属类别误填到方向 `category` 字段时，解析器按确定映射保留整条模型发现，并记录 A3 类别、有效子类和原始字段；不在方向或 A3 闭集中的未知类目仍拒收。修复代码位于 `tools/agent/model_side.mjs::routeCategoryFromTaxonomy()` 与 `parseFindings()`，第 ⑬ 项回归验证三条合法错位类保留、一条未知类拒绝。

图片线上回放（新进程 PID 43763）确认模型侧成功、知识库侧有 4 条，并生成双轨 REVIEW。随后类目映射补丁完成离线自证并于 2026-10-21 通过重启闸门加载到 PID 59470；WebSocket 在线。运维自证 84/85，唯一红项是既有 C1 绕闸脚本，非本修复。在线新图重放尚待用户验证，因此不能把类目修复宣称为已完成在线验收。