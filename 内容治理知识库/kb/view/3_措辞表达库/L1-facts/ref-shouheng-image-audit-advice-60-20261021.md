---
id: ref-shouheng-image-audit-advice-60-20261021
title: 守衡图片审查：完整技能闸门、KB 建议展示与 60 字上限
tier: L1
collection: 3_措辞表达库
kb_class: []
topic: 知识
summary: 图片审查须由完整技能回执与视觉核对驱动；具体 KB 建议要经过清理、聚合和正确元数据对齐后进入卡片及报告；建议字数运行上限统一为 60。
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
  - 图片审查流程未完成时是否可以发布三态结论？
  - 多条同位置知识库规则的具体修改建议如何展示？
  - 守衡图片审查建议字数上限由哪个登记表统一执行？
  - 过滤条目后如何保证知识库依据仍绑定原问题？
not_proves: 不能证明当前守衡线上进程已重启或通过同一图片的在线重放；不能把相似历史审核意见单独升级为禁止、打回或法律结论；上游 PRD 原文仍是 30 字，60 字是守衡运行覆盖值。
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/dual_track.mjs
  - /Users/lute/project/audit_multi_content/tools/test_agent.mjs
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图片审查建议展示与60字上限修复-20261021.md
  fingerprint: c4870a5029e67dc1
  captured_at: 2026-10-21
provenance:
  anchor: PMO/守衡-图片审查建议展示与60字上限修复-20261021.md#定位
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 正文仅含审查代码、规则与自证结果，不含自然人信息
---

# 守衡图片审查建议展示与 60 字上限修复

日期：2026-10-21

## 定位

最近一条图片审核回复暴露了三个相连的展示缺陷：

1. 依据缺失的模型条目会被卡片层过滤，但合并报告仍接收过滤前的条目，导致卡片、条数和报告不一致。
2. 渲染元数据按筛选后的序号生成，记录层按原始序号读取，KB 依据与建议可能错挂到相邻问题。
3. 同一位置拆出的多条 KB 规则没有稳妥聚合；即使合并后有具体建议，也可能被免责声明和建议上限挤掉。

图片审查完整流程的 fail-closed 闸门已在此前落入守衡内核：图片技能回执、视觉核对清单或完整审查步骤不齐时，不发布三态结论。本轮复核并用图像流程反例验证了这一行为。

## 修改

- 修改建议上限统一从约束登记表读取为 60；模型提示、建议生成与压缩、卡片、报告、合规检查共用 `ADVICE_MAX`。上游 PRD 原文仍保留为 30 字，并以 `runtime_override` 记录 Owner 于 2026-10-21 明确调整为 60，避免把上游版本误报为已更新。
- 建议格清理“源记录未提供建议”“仅供历史参考”等非动作说明；具体 KB 建议在建议生成缺失时回退显示。多条同位置 KB 规则聚合时保留完整具体建议，避免生成的一句建议覆盖掉规则清单。
- 卡片与报告统一使用过滤后的 `displayItems`；每个渲染项保留原始来源索引，逐条记录依该索引关联元数据。
- 素材中的逐字引用作为素材锚点展示；模型条目没有外部来源或素材锚点时，结构化来源明确记为 `none`。

## 判据与验收

新增回归样本覆盖“源记录未给建议”的免责声明和 KB 中的具体改法：具体改法必须出现在卡片与报告建议格、免责声明不出现、建议不超过当前 60 字上限。另有用例覆盖多条 KB 规则合并、过滤后元数据不串项、素材原文锚点和图片流程缺项时拒绝给结论。

本轮验收读数：

- `node tools/agent/prd533.mjs --selftest`：全部通过；边界样本 61 字超限。
- `python3 '/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/l8/prd533_check.py' --selftest`：全部通过，知识库侧读到 50/50/60。
- `node tools/agent/advice.test.mjs`：7/7。
- `node --test tools/agent/merged_record.test.mjs`：10/10。
- `node tools/agent/dual_track.mjs --selftest`：合并自证 143/143；抽取自证 55/55。
- `node tools/verify_cards.mjs`：349/349；`node tools/agent/image_intent_gate.mjs`：12/12；`node tools/agent/model_side_limit.test.mjs`：9/9。
- `node tools/test_agent.mjs`：301/301。包含图片审查不完整时 fail-closed 的反向对照。
- `python3 tools/verify_skill.py --workflow-check --controls`：图片审查工作流契约与反向对照通过。
- `python3 tools/verify_agents_budget.py` 与 `git diff --check`：通过。

## 尚未闭环的外部动作

代码与判据已写入工作区，但本环境没有权威 `kb_ingest` 工具/CLI 或知识库写入接口；因此没有伪造入库记录。执行 `python3 tools/verify_ingest_coverage.py --strict` 后，须在可调用权威 `kb_ingest` 的环境将本留底件及判据入库，再回读确认覆盖。守衡线上进程也尚未重启，因此本次代码变更尚未通过线上图片重放验证。
