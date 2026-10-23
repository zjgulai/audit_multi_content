---
id: ref-shouheng-screenshot-watermark-filter-enforced-20261022
title: "[规则执行] 截图层水印发现从模型问题集中剔除，报告说明局部识读限制"
collection: 3_措辞表达库
tier: L1
topic: 图片审查/截图层水印
kind: fact
summary: 图片 OCR 判据确认重复覆盖式截图层水印后，模型侧提示与确定性过滤共同保证它不计为素材问题、不单独触发 REVIEW；报告附录说明若遮挡只影响局部识读。无截图层判据时不过滤成品水印发现。
owner: 刘华丽
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 截图层水印应如何影响图片审核结论？
  - 模型仍报告截图水印时如何阻止它抬高 REVIEW？
  - 如何避免过滤真正属于成品的水印问题？
not_proves: 不证明 OCR 水印判据能判定所有水印来源；不证明被遮挡文字内容；不证明用户同图线上回放已通过。
forbidden: 有截图层 OCR 判据时，水印相关发现不得进入问题集；没有该判据时，不得自动过滤可能属于成品的水印；不得据截图水印推断消费者误认。
supersedes: ref-shouheng-screenshot-watermark-nonissue-20261022
kb_class: []
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-截图层水印不应进入素材问题或触发REVIEW-20261022.md
  fingerprint: a76f383a37f12ecd
  captured_at: 2026-10-22
provenance:
  anchor: PMO/守衡-截图层水印不应进入素材问题或触发REVIEW-20261022.md#规则/#执行点/#验收
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 仅记录通用图片审查规则与代码执行点，不记录截图中的个人标识。
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/model_side.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/agent.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/model_side_limit.test.mjs
  - /Users/lute/project/audit_multi_content/tools/test_agent.mjs
  - /Users/lute/project/audit_multi_content/内容治理知识库/skills-打包/登记源-中文专项-登记表所指/图片安全审查/SKILL.md
  - /Users/lute/project/audit_multi_content/PMO/守衡-截图层水印不应进入素材问题或触发REVIEW-20261022.md
---

执行规则：本机 OCR 判据以重复平铺/多位置覆盖的水印形态识别截图层审阅标识后，将该判读交给图像模型，并在模型侧结果解析处做确定性兜底：只要这类水印仍出现在模型发现字段中，就从最终问题集剔除，避免据此生成 REVIEW。报告附录显示“截图层水印不计为素材问题，不据此判 REVIEW；若遮住文字，只说明局部识读受限”。若没有 OCR 截图层判据，则不触发过滤，保留对可能属于最终创意内容的成品水印审查。模型提示同时禁止推断广告主/背书误认和要求删除截图水印。