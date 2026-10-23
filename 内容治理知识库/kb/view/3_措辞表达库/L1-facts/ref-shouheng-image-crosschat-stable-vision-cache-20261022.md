---
id: ref-shouheng-image-crosschat-stable-vision-cache-20261022
title: "[参考实现] 守衡同图跨私聊/群聊复用视觉发现，并对画面读数截断有界重试（2026-10-22）"
collection: 3_措辞表达库
tier: L1
topic: 守衡系统 · 图片审查跨会话一致性与视觉读数可靠性
kind: fact
summary: 相同原图私聊模型侧 3 条、群聊模型侧 0 条并导致卡片计数不同。群聊画面读数被 1200 tokens 截断；动态 OCR/画面提示文本参与模型结果缓存键，令相同图像与审查策略无法跨会话复用。现将 sceneRead 默认预算提到 4000、截断时有界翻倍重试；缓存按原图、模型与稳定审查策略标识复用，动态读数不再切分缓存。scene 29/29、cache 14/14、内核 303/303、卡片 350/350；守衡已重启，线上重放仍待用户重发。
owner: 刘华丽
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 为什么相同图片在私聊有视觉发现、群聊却只有知识库建议？
  - 画面层被 finish_reason=length 截断后，如何避免模型侧发现集和卡片计数漂移？
  - 图片模型审查结果缓存应按哪些输入区分，又应忽略哪些会话差异？
  - 同图同模型同审查策略是否应跨私聊和群聊复用结果？
not_proves: 离线测试与重启读数不能证明用户重发同图后的线上回放已通过；不能证明两条不同原图可共用发现；若审查策略或模型版本变化，必须升级缓存策略键；知识库历史记录不能单独作为本图事实或安全结论。
forbidden: 不得把持续截断或模型失败当作零发现；不得将动态 OCR/画面读数差异用于拆分同图同策略缓存；策略变更不升级稳定策略键会复用过期发现；不得把模型侧有效的零发现伪装成失败。
kb_class: []
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图片跨会话结果不一致-视觉截断与缓存键修复-20261022.md
  fingerprint: 026cc87cc0e65767
  captured_at: 2026-10-22
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/scene.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/scene.test.mjs#S3b
  - /Users/lute/project/audit_multi_content/tools/agent/image_review_cache.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/image_review_cache.test.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/agent.mjs
  - /Users/lute/project/audit_multi_content/PMO/shouheng-state/merged-reports/merged-2026-10-22T03_48_08.928Z-1792640888928.json
provenance:
  anchor: PMO/守衡-图片跨会话结果不一致-视觉截断与缓存键修复-20261022.md#事故与可复核证据/#根因/#修复与执行点/#验收与部署
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 仅记录系统运行、代码行为、图片哈希及验收结果；不含个人身份信息。
complements:
  - ref-shouheng-image-model-original-image-multimodal-20261021
  - ref-shouheng-image-video-readings-20261016
---

相同原图（sha256 75b5790174e153acd52bd910c1bdad46ddca7e33165a06d8324d5281cb3bb1a3）在私聊与群聊结果不同：私聊为知识库 4 条 + 模型侧 3 条、合并 4 处；群聊为知识库 4 条、模型侧 0 条、卡片合并 1 处。群聊的 sceneRead 报告 max_tokens=1200 截断；模型侧原图调用成功但本次返回零发现。此前图像缓存把动态 OCR/画面读数拼入 contract 哈希，故群聊读数缺失使缓存键不同，没有复用私聊结果。修复将 sceneRead 默认 maxTokens 调至 4000，截断只重试一次并翻倍；图片模型发现缓存按原图字节、模型与固定图片安全审查策略键，而不按当轮 OCR/画面描述变化。模型、策略变化仍使缓存失效；失败结果仍不缓存。策略内容变化必须更新 image-safety-full-review-v1。scene 29/29、cache 14/14、agent 303/303、cards 350/350；ops 自证全过，重启后 pid=80733 且 wsConnected=true。新线上同图回放尚待用户重发。