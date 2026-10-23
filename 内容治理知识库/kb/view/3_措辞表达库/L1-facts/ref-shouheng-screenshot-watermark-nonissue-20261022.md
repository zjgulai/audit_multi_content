---
id: ref-shouheng-screenshot-watermark-nonissue-20261022
title: "[规则] 截图层重复水印不作为图片素材问题或 REVIEW 依据"
collection: 3_措辞表达库
tier: L1
topic: 图片审查/截图层水印
kind: fact
summary: OCR 判据确认重复覆盖式半透明截图或审阅水印时，按采集层标识处理：不计为素材问题、不据此判 REVIEW；遮挡只说明局部识读受限。只有确认属于最终交付创意时才按成品审查。
owner: 刘华丽
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 截图或审阅水印是否应作为图片素材问题？
  - 水印遮挡文字时如何表达审查结论？
  - 何时才应审查水印是否属于最终投放素材？
not_proves: 本规则不证明水印一定来自某个具体软件；不证明被遮挡文字的内容；无法确认水印是否属于最终交付创意时，不得推断消费者会误认。
forbidden: 不得仅凭截图层水印认定隐私泄露、广告主/背书误认或建议删除水印图层；不得据此单独判 REVIEW；遮挡只记为局部识读受限。
kb_class: []
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-截图层水印不应进入素材问题或触发REVIEW-20261022.md
  fingerprint: 04ff747f5843ecfe
  captured_at: 2026-10-22
provenance:
  anchor: PMO/守衡-截图层水印不应进入素材问题或触发REVIEW-20261022.md#规则/#执行点
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 只记录通用图片审查规则，不保留水印文字或个人身份信息。
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/model_side.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/agent.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/model_side_limit.test.mjs
  - /Users/lute/project/audit_multi_content/tools/test_agent.mjs
  - /Users/lute/project/audit_multi_content/内容治理知识库/skills-打包/登记源-中文专项-登记表所指/图片安全审查/SKILL.md
---

当本机 OCR 判据识别出重复覆盖式水印（平铺于不同位置，水印文本已从素材 OCR 中摘除），且原图呈现为半透明截图/审阅叠加层时，应归为截图采集层标识，而非最终素材内容。报告不得将其列为隐私问题、背书/广告主误认或建议删除水印，也不得单独据此判 REVIEW。水印遮住文案时，只说明受遮挡区域的局部识读受限。只有原图证据能确认水印属于最终交付创意内容时，才按成品审查；无法确认时，不推断消费者会误认。