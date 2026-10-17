---
asks:
  - 报告的执行段为什么要按结论分两支（BLOCK 与 REVIEW 各怎么写）
  - PRD 里 REVIEW 与 BLOCK 的收尾句逐字是什么、哪个带 @
  - BLOCK 单为什么一个 @ 也不该出现
  - 总览表的承办列与「@谁去修」有什么区别
  - 这一段改动的判据是哪些（Z48 / Z48g）、反向对照怎么钉的
  - 卡片为什么不用改（它一直是对的）
collection: 3_措辞表达库
corroborated_by:
  - /Users/lute/Project/audit_multi_content/PMO/守衡-执行段按结论分支-打回vs派单-20261017.md（PRD 原文摘录与两支写法）
  - /Users/lute/Project/audit_multi_content/tools/agent/merged_report.mjs（must 分支：打回 vs 派单）
  - /Users/lute/Project/audit_multi_content/tools/agent/dual_track.mjs（orderActionLine：BLOCK 请修改后重新提交。／REVIEW 建议转 @… 复核。）
  - /Users/lute/Project/audit_multi_content/tools/test_agent.mjs（Z48g，含反向对照与「两支标题必须不同」）
created_at: 2026-10-17
data_level: L2
evidence_group: rule
evidence_level: L2
forbidden: 不许把 BLOCK 单写成「转 @人复核」（PRD 是打回，不是转人）；不许把 REVIEW 单写成「请修改后重新提交」（那会取消了人工复核那一跳）；不许因为本节就把总览表的承办列理解成派单通知（它不带 @）；不许改卡片的收尾句式（它由 orderActionLine 产出，本来就对）。
half_life_days: 180
id: ref-shouheng-report-exec-branch-20261017
kb_class: []
kind: fact
not_proves: 不能证明「@ 到了具体的人」—— 角色句柄未配置时 @ 只是角色位，不会真正推送；不能证明 BLOCK 报告不需要责任人（承办列仍在，属责任范围声明）；不能证明两种结论之外（PASS / NEEDS_INPUT）也有报告（PASS 不出报告，NEEDS_INPUT 不走这条渲染）；不能替代 PRD 原文（条款以 docx PXfBdjTwFokEQixtmTscqm7knNh 为准）。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为 PRD 口径与判据；提及的是角色而非具体人
provenance:
  anchor: PMO/守衡-执行段按结论分支-打回vs派单-20261017.md#一、PRD 原文（查过，不是转述）
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-17
  fingerprint: af0f395ad84c23b4
  kind: file
  ref: /Users/lute/Project/audit_multi_content/PMO/守衡-执行段按结论分支-打回vs派单-20261017.md
summary: Owner 指出：按照 PRD，命中 BLOCK 时审查报告**不会 @xx @xxx 去修复，而是直接打回建议修复**；只有 REVIEW 才会 @xx 分派。而报告的执行段（第三段）**不分结论、一律逐角色 @ 派单**，字面上就是 REVIEW 的模版 —— 于是一份 BLOCK 报告一边写「请修改后重新提交」，一边把六条问题分给四个人「跟进」。查 PRD（wiki NB55wAq8liEOdKkquL2cgtPEnmg → docx PXfBdjTwFokEQixtmTscqm7knNh）逐字确认：REVIEW（§5.3.2/§5.3.3）每处收尾都是「建议转 @法务 @医学顾问 复核。」（带 @）；BLOCK（§5.3.4）每处收尾都是「请修改后重新提交。」（不带 @）—— Owner 的读法就是 PRD 的写法。改法：merged_report 的执行段按 must 分支 —— BLOCK ⇒ 标题「打回，修改后重新提交」、正文写「这一单打回，不派单、不转人复核，请按每条的修改建议改完再重新提交一次」、**不出现任何 @**、不出现「跟进问题（第 N 条）」、收尾仍是 PRD 那句；REVIEW ⇒ 标题「按问题分派」、逐角色「@…：跟进问题（第 N 条）」、收尾「建议转 @… 复核。」。总览表的承办列保留（那是责任范围，不是派单通知）。判据：Z48 的执行段断言改成 BLOCK 分支（一个 @ 都不许有），新增 Z48g 钉 REVIEW 分支与反向对照（同一批条目换成 BLOCK 必须无 @；两支标题必须不同）。读数 test_agent 269/0、dual_track 自证 126/0、verify_cards 347/0；那份 BLOCK 样张重投到 rev 19，回读 8 项全绿。边界：卡片没动（它的收尾一直由 orderActionLine 算，本来就是 PRD 口径），错的只有报告那一节。
tier: L1
title: "[规则] 报告的执行段按结论分两支（2026-10-17）：BLOCK 打回不 @ 人／REVIEW 才 @ 人派单 —— PRD §5.3.2/§5.3.3 带 @、§5.3.4 不带"
topic: 知识
valid_until: 2027-04-15
---

# 报告的「执行」那一节必须按结论分两支

## 一、Owner 的原话与 PRD 原文

Owner：「按照 prd，命中 block，审查报告**不会 @xx @xxx 去修复，直接打回建议修复**；
命中 review 的，审查报告才会 @xx @xx 去修复。目前审查报告的执行 3 适合 review 模版，
若结论是 block 要按照 prd 优化。」

查 PRD（wiki NB55wAq8liEOdKkquL2cgtPEnmg → docx PXfBdjTwFokEQixtmTscqm7knNh 逐字）：

- REVIEW（§5.3.2 / §5.3.3）每处收尾都是「**建议转 @法务 @医学顾问 复核。**」—— 带 @；
- BLOCK（§5.3.4）每处收尾都是「**请修改后重新提交。**」—— 不带 @。

⇒ Owner 的读法就是 PRD 的写法。而报告里那一节**不分结论、一律逐角色 @xx 派单**，
字面上是 REVIEW 的模版：一份 BLOCK 报告一边写「请修改后重新提交」，一边把六条问题分摊给四个人「跟进」。

## 二、改成两支

BLOCK ⇒ 打回：标题「执行（打回，修改后重新提交）」；正文写「这一单打回，不派单、不转人复核，
请按上面每一条的修改建议改完再重新提交一次」；**不出现任何 @**、不出现「跟进问题（第 N 条）」；
收尾仍是 PRD 那句「请修改后重新提交。」。

REVIEW ⇒ 派单：标题「执行（按问题分派）」；逐角色「@…：跟进问题（第 1、2 条）」；
收尾「建议转 @… 复核。」。

总览表的「承办」列保留：它回答「这是谁的责任范围」，与「@ 谁去修」是两件事（它不带 @）。

## 三、判据

第 48 组新增 Z48g，并把 Z48 的执行段断言改成 BLOCK 分支：BLOCK 夹具下标题必须是「打回」、
**一个 @ 都不许有**、不许有「跟进问题（第」、必须有「按修改建议改完再提交」、收尾是那句 PRD 原文；
REVIEW 夹具下必须有逐角色 @ 派单与「建议转 @… 复核。」、且**不许**出现 BLOCK 的收尾。
反向对照：同一批条目换成 BLOCK 必须一个 @ 都没有；两支标题必须不同（同名即等于没分支）。
读数：test_agent 269/0、dual_track 自证 126/0、verify_cards 347/0。

## 四、边界

卡片没动：卡片的收尾本来由 orderActionLine 算（BLOCK ⇒ 请修改后重新提交。），一直是 PRD 口径 ——
错的只有**报告**那一节。PASS 单不出报告；NEEDS_INPUT 不走这条渲染。
若 Owner 认为 BLOCK 单连「承办」列也不该有，那只是一行改动。
