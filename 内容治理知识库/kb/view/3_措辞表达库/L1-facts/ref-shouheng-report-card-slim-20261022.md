---
asks:
  - 报告里为什么不再有「图片安全审查 skill 全流程结果」这一节，删了之后图片审查还完整吗
  - 卡片的「视觉分析与 OCR」去哪了，视觉分析还要不要做、缺项会怎样
  - 知识库命中那条为什么不再写「相似历史审核意见/匹配分」，新的问题描述是哪来的
  - 「婴幼儿跟成人同床，并且睡在柔软的枕头上」这句话是怎么从条款原文抽出来的，会不会改事实
  - 依据文档链接现在是什么格式，为什么同类条款只留一条链接
  - 同一张图命中四条同记录条款时，依据格里为什么只出现一个表格名
  - 报告和卡片的改动要重启守衡才生效吗，怎么证
  - 这一轮改动的自证读数是哪些，失败项是哪一条、为什么与本轮无关
collection: 3_措辞表达库
corroborated_by:
  - 源码逐行：tools/agent/merged_report.mjs 的 renderMergedReportMd（skill 全流程节已删）与 shouldPublishMergedReport（回到 ≥3）；tools/reply-cards/envelope.mjs 的 toCardOrText（imageAnalysis 块已撤）；tools/agent/dual_track.mjs 的 compactBasisLine / neutralHistoryFacts / _kbFromEngineJson
  - 真单回放：PMO/shouheng-state/merged-reports/merged-2026-10-22T02_49_11.413Z-1792637351433.md（改前：skill 全流程节 + 记录级历史意见当依据）与 node test/_diag/report_after_20261022.mjs（改后：中性问题描述 + 一条链接）
  - 自证读数：node tools/test_agent.mjs 303/0；node tools/verify_cards.mjs 350/0；node tools/agent/dual_track.mjs --selftest 154/0；node tools/agent/merged_report.test.mjs 13/0
  - 反向对照：把同一份 skill 正文喂给 renderMergedReportMd ⇒ 六个阶段特征串命中 0；给 imageAnalysis 也不落卡；两条不同 URL 的条款各留各的链接
created_at: 2026-10-22
data_level: L2
evidence_group: coordinate
evidence_level: L2
forbidden: 不许据本条判断某条素材能不能发；不许把「报告不展示 skill 全流程」读成「skill 不用完整执行」；不许把中性问题描述当成条款原文（它是按风险事实重写的，原话仍在条款里，可点依据核对）；不许把「表格名+一条链接」当成可以合并不同 URL 的许可（不同记录是不同回源入口）；不许把历史意见条目从问题清单里摘掉（Owner 选的是改说法）；不许据本条声称线上卡片已经改好（未重启）。
half_life_days: 90
id: ref-shouheng-report-card-slim-20261022
kb_class: []
kind: fact
not_proves: 不能证明任何一条具体内容能不能发——它讲的是报告/卡片的展示口径与取数，不是审查结论；不能替代 3_措辞表达库 的任何条款（条款号、命中表达、锚点以权威库 kb/l3、kb/l4 为准）；不能证明视觉分析可以不做——视觉分析与 skill 全流程仍是出结论的前置（visual_checklist 缺项压 NEEDS_INPUT），本条只说明它不上卡面；不能证明中性问题描述能把所有条款原文都抽成事实（抽不出时如实写「条款所列情形需人工确认」，且不改变条款本身的判定）；不能证明线上已经生效——本轮没有重启守衡（restart 闸门 --check 显示 6 个 import 模块待加载）；不能证明外部标准那条依据也需要压成「文档名+链接」（Owner 的例子是库内表格，外部标准格式本轮未动）。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为报告/卡片展示口径与判据说明，不含姓名、联系方式等个人数据；文中「Owner」为角色指称
provenance:
  anchor: PMO/守衡-报告与卡片精简-20261022.md#二、改法
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-22
  fingerprint: a199edc9e74e6432
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-报告与卡片精简-20261022.md
summary: 守衡报告与卡片的四项展示口径收口（Owner 2026-10-22 逐字定）。① 报告撤掉「图片安全审查 skill 全流程结果」整节（10:49 真单里它比结论正文长 3 倍），发布闸回到 PRD §5.3.4 的 ≥3，不再因「完整图片审查」强行出报告；② 卡片撤掉「视觉分析与 OCR」，imageAnalysis 整条接线（agent→ws_daemon→envelope 入参）一并删掉，不留没人读的入参；③ 知识库负面样本规则（N-0x）命中改说法：问题描述=中性事实（去掉载体/版面前缀、括注与建议句，爸爸/妈妈/家长→成人、宝宝/孩子→婴幼儿），原因=事实+条款类别+需人工确认是否适用本单画面，两格都不出现「历史/相似/匹配分/记录级」；④ 依据格收成 PRD §5.3.3 句式《表格名》第 A、B、C 条（链接：[点开核对](url)），表格名一次、条款号一串、链接一条，不同 URL 绝不合并。skill 仍须完整执行（visual_checklist 两道闸门不动，缺项压 NEEDS_INPUT）；历史意见条目仍计入问题数（改的是说法，不是摘条）；外部标准那条依据格式未动。
tier: L1
title: "[参考实现] 报告与卡片精简（2026-10-22 Owner 四条）：撤 skill 全流程节 / 撤卡面视觉分析与 OCR / 知识库命中改说法 / 依据格收成「表格名+条款号+一条链接」"
topic: 知识
valid_until: 2027-01-20
---

# 报告与卡片精简（2026-10-22）

## 一、Owner 四条（逐字）

1. 「报告不展示 图片安全审查 skill 全流程结果」
2. 「输出的卡片不展示『视觉分析与 OCR』」
3. 「命中知识库侧的**不应该出现历史审核意见作为依据**」→ 确认结果：
   「**命中知识库规则的，只写问题描述，不写历史两个字，改说法**」；
   问题描述来源再确认：**B（改写成中性事实，不搬条款原文里的细节）**。
4. 「依据文档链接中，就一条链接怎么写这么多字？跟 prd 一致，**表格名称+飞书链接**就好」

## 二、改法

| # | 落点 | 改法 |
|---|---|---|
| 1 | `tools/agent/merged_report.mjs` | 删掉「## 图片安全审查 skill 全流程结果」整节；`shouldPublishMergedReport` 去掉 `imageSkillReview` 分支——门槛回到 PRD §5.3.4 的 ≥3 |
| 2 | `tools/reply-cards/envelope.mjs` · `tools/ws_daemon.mjs` · `tools/agent/agent.mjs` | 卡面不再注入「视觉分析与 OCR」；`imageAnalysis` 整条接线撤掉（入参、`meta`、`imageAnalysisDisplay`） |
| 3 | `tools/agent/dual_track.mjs::_kbFromEngineJson` | N-0x 命中：问题描述=中性事实（`neutralHistoryFacts`）；原因=事实+条款类别+需人工确认是否适用本单画面。两格都不出现「历史/相似/匹配分/记录级」 |
| 4 | `tools/agent/dual_track.mjs::compactBasisLine` | 依据格收成 `《表格名》第 A、B 条（链接：[点开核对](url)）`；同一记录表格名一次、链接一条；不同 URL 不合并；外部标准原样放过 |
| 5 | `tools/agent/dual_track.mjs::renderMergedItem` | 卡面依据 `《表格名》第 N-1.307 等 4 条｜原始出处：url` |

## 三、判据（都带反向对照）

- **⑦d**：同一 URL 四条款 ⇒ 表格名一次、链接一条；两条不同 URL ⇒ 各留各的；外部标准原样。
- **⑦e**：`主标题醒目柔和，画面是宝宝跟爸爸同床…` ⇒ `婴幼儿跟成人同床，并且睡在柔软的枕头上`；
  纯建议句 ⇒ 空串；接线级：`kbFindingsOf` 出来的条目 `description` 非空、`reason` 无「历史/相似/匹配分」。
- **T5–T9**：一整份 skill 正文喂进去，六阶段特征串命中 0；`shouldPublishMergedReport` 回到 ≥3。
- **Z20b**：给 `imageAnalysis` 也不许落卡；`replyTo` 签名里不许再有它。

## 四、边界

- skill 仍须完整执行：`visual_checklist.mjs` 两道闸门不动，缺项 ⇒ NEEDS_INPUT。
- 历史意见条目仍计入问题数、仍算 REVIEW（改说法，不摘条）。
- 「历史」二字仍出现在**表格名称**里（飞书表真名），这是第 4 条「表格名称+飞书链接」的一部分。
- 外部标准那条依据格式未动。

## 五、读数

`test_agent 303/0`｜`verify_cards 350/0`｜`dual_track --selftest 154/0`（抽取 55/0）｜
`merged_report.test 13/0`｜`advice.test 7/0`。

⚠️ `merged_record.test.mjs` 有 1 条**先于本轮**的红（⑩）：同一工作区另一路把 `sugCore` 的优先顺序
改成了 `adv` 先于 `sugKb`，而夹具期望库侧建议生效。本轮未触碰那一行。

## 六、部署

未重启守衡。`bash tools/restart_shouheng.sh --check`：PID 6425（10:54:53 启动），
待加载 6 个 import 模块（`agent.mjs` / `dual_track.mjs` / `merged_report.mjs` / `prd533.mjs` /
`reply-cards/envelope.mjs` / `ws_daemon.mjs`）。重启后验：群里发一张图，看卡片与报告两处的形状。
