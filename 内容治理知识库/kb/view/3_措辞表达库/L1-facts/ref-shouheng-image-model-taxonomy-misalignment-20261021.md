---
id: ref-shouheng-image-model-taxonomy-misalignment-20261021
title: 守衡图片审查：A3 类目误填方向字段时保留模型发现
tier: L1
collection: 3_措辞表达库
kb_class: []
topic: 知识
summary: 模型把合法 A3 所属类别误填到方向类目字段时，不得丢整条发现；应按确定映射保留宽方向、A3 类别和子类，同时拒绝真正未知类目。
owner: 内容治理
kind: fact
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-21
effective_from: 2026-10-21
valid_until: 2027-04-19
asks:
  - 模型类别解析丢弃项是否为合法 A3 类目？
  - 类目错位时能否保留类别、子类和原始输入？
  - 未知自由类目是否仍然被拒绝？
not_proves: 本记录不证明本次新增映射已被线上守衡进程加载；应在后续新图片消息中确认模型 dropped 不再含合法 A3 类目。
derived_from:
  - ref-shouheng-image-model-original-image-multimodal-20261021
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/model_side_limit.test.mjs
  - /Users/lute/project/audit_multi_content/PMO/shouheng-state/merged-reports/merged-2026-10-21T10_03_40.046Z-1792577020046.json
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图片模型类目错位与线上双轨验证-20261021.md
  fingerprint: 98767ce801d059d1
  captured_at: 2026-10-21
provenance:
  anchor: PMO/守衡-图片模型类目错位与线上双轨验证-20261021.md#知识库入库判据
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 仅含代码规则与脱敏后的验收记录
---

线上图片任务中，模型输出的方向类目字段出现了合法 A3 所属类别名称，旧解析器因为这些值不在方向闭集中而丢掉整条发现。A3 类别与方向类目是两条不同轴；若 `category` 字段误放了合法 A3 类名，应使用确定性映射生成最宽方向类目，并保留 A3 类别、合法子类及原始字段值。产品安全映射至消费者安全，商品信息映射至产品描述，北美标签映射至本地化，权利/肖像/隐私/AI 按子类区分隐私与 AI 披露，其他有效 A3 类映射至通用合规方向。对不在方向闭集且不在 A3 闭集的自造类名继续拒收。

执行判据：`tools/agent/model_side_limit.test.mjs` 的第 ⑬ 项验证 3 个合法 A3 错位类均被保留并携带类别、子类，未知自造类被拒；线上留痕检查 `model.dropped`，合法 A3 类名不得再作为丢弃原因。具体代码和线上证据见 source.ref 指向的 PMO 留底。