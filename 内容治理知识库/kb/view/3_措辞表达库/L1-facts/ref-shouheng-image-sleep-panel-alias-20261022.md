---
id: ref-shouheng-image-sleep-panel-alias-20261022
title: "[参考实现] 守衡图片睡姿核对器接受顶部/底部面板别名，同时拒绝歧义匹配（2026-10-22）"
collection: 3_措辞表达库
tier: L1
topic: 守衡系统 · 图片审查视觉核对与面板同义判据
summary: 图片模型读数是右上/右下，skill 核对逐面板写成顶部/底部，旧校验器因坐标字符串不完全相同而错误拒绝完整审查。现在仅在对应方位唯一时接受顶部/上方/上部或底部/下方/下部别名；多面板或跨图片存在歧义时仍要求明确坐标。图片专项自证 27/27、守衡内核 301/301。
owner: 刘华丽
kind: fact
evidence_level: L2
data_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 为什么图片报告已写顶部/底部两个面板的睡姿，视觉核对器仍称没有逐面板复述
  - 右上/右下与顶部/底部何时可视为同一面板位置
  - 怎么防止顶部/底部别名将多个相同方位面板错误匹配
  - 这次图片睡姿面板误拒绝的修复代码、反向用例和验收结果是什么
not_proves: 不能证明图片内容本身安全或合规；不能替代视觉模型对原图的分析；不能证明只加载 skill 就代表完整执行；不能证明任意自定义方位词都可互换；不能把存在歧义的顶部/底部简称当成具体面板证据。
kb_class: []
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图片睡姿面板别名误报-20261022.md
  fingerprint: df0419cda6764bba
  captured_at: 2026-10-22
corroborated_by:
  - PMO/logs/ws_outbound.jsonl#2026-10-22T02:15:28Z：线上拒绝文案将本次原因明确报为“未逐面板复述姿势”
  - tools/agent/scene.test.mjs#S5h：顶部/底部别名通过、两个上方面板只写“顶部”时拒绝
  - tools/test_agent.mjs#N4d：视觉核对闸门接线和睡姿复述行为级断言
pii:
  detected: false
  masked: false
  strategy: 未检出个人身份信息；内容为代码位置、系统行为和测试结果。
provenance:
  anchor: PMO/守衡-图片睡姿面板别名误报-20261022.md#现象与根因/#修复与判据/#验收与部署
  confidence: 确定
sensitivity_level: L2
forbidden: 不许据本条判断图片是否合规或安全；不许在同图多个上方面板/下方面板时用一个“顶部/底部”短语代替逐面板核对；不许将本条当成图片审查 skill 已执行的证明。
complements:
  - ref-shouheng-image-video-readings-20261016
---

# 守衡图片睡姿面板别名误报修复（2026-10-22）

## 现象与根因

图片模型读数记录了图 1 右上、右下两处婴儿均为仰卧；图片审查报告也逐面板写出了「面板 A（顶部）＝仰卧」「面板 B（底部）＝仰卧」。但完整流程闸门仍以「视觉核对项未逐面板复述姿势」拒绝三态结论。

根因在 `tools/agent/visual_checklist.mjs::checkVisualChecklist()`：旧判据要求面板读数的坐标字符串（如「右上」「右下」）原样出现在核对文案中。它没有识别同一面板的方位别名「顶部」「底部」，所以将已有的逐面板核对误判为遗漏。模型侧视觉读取和图片审查 skill 的阶段执行不是这次拒绝的原因；误拒发生在最后的规则校验。

## 修复与判据

- 将「顶部／上方／上部／上面板／上半部分」映射到唯一的上方面板；将「底部／下方／下部／下面板／下半部分」映射到唯一的下方面板。
- 只有同一图片中对应方位唯一时才接受方位简称；同一图片有多个上方面板/下方面板时必须写清具体面板。跨图片出现相同方位时，简称还必须带图片编号。
- 新增正反例：本次「右上/右下」读数由「顶部/底部」复述时通过；两个上方面板只写「顶部」时继续拒绝，防止别名规则放宽成猜配。

执行点：`tools/agent/visual_checklist.mjs` 面板级睡姿匹配；测试位于 `tools/agent/scene.test.mjs` 的 S5h。

## 验收与部署

- `node tools/agent/scene.test.mjs`：27/27。
- `node tools/test_agent.mjs`：301/301。

## 知识库入库状态

本条经安装的 `dsh-kb` 正式 `ingest()` API 入库，并通过同一 API `read()` 回读。当前 Codex 工具目录未暴露 `kb_ingest` MCP 工具，因此按用户明确要求入库，调用本机正式插件 API，以 `human: true` / `actor: 刘华丽` 通过知识库既有人工入库闸门；不是手写条目文件或账本。入库读回和账本读数见下方验收记录。
