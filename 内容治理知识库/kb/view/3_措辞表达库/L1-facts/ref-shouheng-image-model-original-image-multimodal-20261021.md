---
id: ref-shouheng-image-model-original-image-multimodal-20261021
title: 守衡图片审查：模型侧必须接收原图并呈现视觉语义发现
tier: L1
collection: 3_措辞表达库
kb_class: []
topic: 知识
summary: 图片审核必须把本轮原图作为多模态输入交给模型，OCR 与视觉描述仅作辅助；模型侧失败时阻断单边结论，纯视觉语义判断可无外部依据但需具体画面锚点。
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
  - 模型侧是否实际收到本轮原图像素？
  - 纯视觉语义结论是否包含可核对的画面锚点？
  - 模型侧失败时是否阻断只含知识库结论的正常回复？
not_proves: 离线自证通过不证明线上守衡进程已加载新代码；需重启后用新图片核对模型请求、成功状态及双侧结果展示。
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/model_side_limit.test.mjs
  - /Users/lute/project/audit_multi_content/tools/test_agent.mjs
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图片模型侧原图多模态审查修复-20261021.md
  fingerprint: 09506af8995767c2
  captured_at: 2026-10-21
provenance:
  anchor: PMO/守衡-图片模型侧原图多模态审查修复-20261021.md#可执行判据
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 正文仅含代码链路、规则和验收读数，不含个人数据
---

图片审查的模型侧必须收到本轮原图的图像内容，模型才能直接进行视觉识别与场景语义理解。OCR 文本和视觉描述只能帮助模型理解，不能代替原图输入。模型侧还必须有成功状态；若原图未传、模型未运行或模型输出失败，系统不得只展示知识库结论作为完整图片审查结果。模型可以基于画面本身提出视觉或语义发现，不要求每条观察都有外部资料依据，但必须指出具体可核对的画面锚点。涉及法律、平台政策、行业标准或专家安全判断时仍需相应外部依据。

执行判据：① wire-level 自证中请求图像解码后逐字节等于输入原图；② 图片审查失败闸门证明模型侧失败会阻断正常结论；③ 在线回放确认本轮原图作为模型图片输入、模型成功运行，最终报告保留知识库发现和模型视觉/语义发现。上述任一项缺失，审查均未闭环。详情及代码位置见 PMO 留底。