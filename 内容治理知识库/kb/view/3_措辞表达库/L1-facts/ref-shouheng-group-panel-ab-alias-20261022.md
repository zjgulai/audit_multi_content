---
id: ref-shouheng-group-panel-ab-alias-20261022
title: "[参考实现] 守衡群聊图片审查将显式面板 A/B 映射用于睡姿核对（2026-10-22）"
collection: 3_措辞表达库
tier: L1
topic: 守衡系统 · 图片审查面板映射与群私聊一致性
kind: fact
summary: 群聊报告已把面板 A（右上）、B（右下）逐项写为仰卧，模型读数也有两处姿势，但旧视觉核对器未把正文映射带入比较，因而误拒完整审查。现在仅接受报告中显式且唯一的 A/B→面板映射；未映射或歧义继续拒绝。专项测试 28/28；群聊原始报告通过修复后的核对器。
owner: 刘华丽
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 同一张图片私聊有结果、群聊却称视觉核对没完成，是否因为面板标签写法不同？
  - 报告正文已明确面板 A（右上）、面板 B（右下），视觉核对器应如何安全处理？
  - 面板字母映射缺失或一对多时是否仍应拒绝？
not_proves: 不能证明图片内容安全或合规；不能替代模型读取原图；不能证明重启后已完成同图在线回放；不能将无映射或歧义的面板字母猜配成具体方位。
forbidden: 不许把面板字母直接当作坐标；只有报告内显式唯一映射才可用于核对；不得以本条代替图片安全审查。
kb_class: []
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/visual_checklist.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/scene.test.mjs#S5i
  - /Users/lute/project/audit_multi_content/PMO/守衡-群聊面板AB标签映射误拒修复-20261022.md
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-群聊面板AB标签映射误拒修复-20261022.md
  fingerprint: d5ae80cf4ab23590
  captured_at: 2026-10-22
provenance:
  anchor: PMO/守衡-群聊面板AB标签映射误拒修复-20261022.md#现象/#根因/#修复
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出个人身份信息；内容为代码位置、系统行为和测试结果。
---

群聊图片报告中的模型读数已有图 1 右上、右下两处婴儿均为仰卧，报告正文也逐项声明「面板 A（右上）」「面板 B（右下）」，但最终核对仍称未逐面板复述。根因是末端视觉核对器没有将正文明确的字母面板映射用于睡姿逐项比较。修复后，只在同一报告中映射明确、图片可确定且目标面板唯一时，面板 A/B 等别名才可匹配对应姿势；缺映射、多图无法绑定或一对多映射仍拒绝。私聊和群聊应共用此确定性核对规则，避免等价面板标注造成差异。执行位置 tools/agent/visual_checklist.mjs::checkVisualChecklist；反向用例 tools/agent/scene.test.mjs 的 S5i，验证唯一映射通过、缺映射和重复映射拒绝。专项自证 28/28；准确群聊报告文本通过。重启部署状态及完整边界见来源 PMO。