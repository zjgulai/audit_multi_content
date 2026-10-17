---
asks:
  - 报告里那一行「链接：点开」是哪来的、它跳转到哪里、为什么不是我加的素材链接
  - 报告里的链接可以从哪里来（哪两种合法来源）
  - 为什么不能从素材正文里挖 URL 出来当链接
  - 引用原文时 markdown 链接与裸 URL 该怎么处理（降链接、包行内代码）
  - 为什么除「依据文档链接」外其他格子都要降链接、而那一格必须保持可点
  - 为什么只改审查对象那一格不够（还有哪些格子会印同一段原文）
  - 链接送审（gate.kind = link）时链接应该怎么出现、反向对照怎么钉的
  - 已经入库的旧条目里有一条作废规则，该怎么处理（不改原文件 + supersedes）
collection: 3_措辞表达库
corroborated_by:
  - /Users/lute/Project/audit_multi_content/PMO/守衡-报告第二十三轮-链接只来自两处-20261017.md（追查链、rev 13→15 两版验收）
  - /Users/lute/Project/audit_multi_content/tools/agent/merged_report.mjs（materialBlock 只认显式 links；文案降链接与裸 URL 包行内代码）
  - /Users/lute/Project/audit_multi_content/tools/agent/dual_track.mjs（demoteLinks；报告分支五格降链接，依据那一格不降）
  - /Users/lute/Project/audit_multi_content/tools/test_agent.mjs（Z49e，五条含反向对照）
created_at: 2026-10-17
data_level: L2
evidence_group: coordinate
evidence_level: L2
forbidden: 不许把「报告里没有链接」当成「没有素材」（可能只是没上传成功，要照实说链接未生成）；不许因为要去链接就把「依据文档链接」里的飞书直链也降掉（那是回源唯一入口）；不许把外部依据链接（FTC / Amazon 这类）当陌生域名一起清掉；不许用本条推翻「链接送审时要给可点链接」—— 反向对照钉着它。
half_life_days: 90
id: ref-shouheng-report-link-sources-20261017
kb_class: []
kind: fact
not_proves: 不能证明所有「看起来像链接的东西」都已清干净（只盖住了 markdown 链接语法与裸 URL 两种形状）；不能证明 production.it 是恶意站点 —— 只证它是一台与本次审查无关的活站点（实测 HTTP 200）；不能证明外部依据链接（FTC／Amazon）一定合规，它只说明那是模型侧引用的公开依据；不能证明业务侧已验收报告可读性；不能替代 3_措辞表达库 的任何条款。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为链接来源口径与判据；出现的域名 production.it 是公开域名，不涉个人数据
provenance:
  anchor: PMO/守衡-报告第二十三轮-链接只来自两处-20261017.md#一、直接回答
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-17
  fingerprint: ef7c7b09a6f02e98
  kind: file
  ref: /Users/lute/Project/audit_multi_content/PMO/守衡-报告第二十三轮-链接只来自两处-20261017.md
summary: Owner 一句「你送的文案，为什么给『链接：点开』？这链接跳转是哪里？」问出一个我自己造的缺陷：报告里那一行不是素材链接，是我从文案正文里挖出来的 URL —— 那段原文是 increasing milk [production.It](http://production.it/) supports…，粘贴时编辑器把 .It 当成意大利域名后缀自动做了链接，production.it 是与本次审查毫无关系的 .it 公开站点（实测 HTTP 200）。更难看的是同一份报告第 5 条问题描述原文就是「这里粘着一个 markdown 链接残留」，一边判它是缺陷、一边给它可点入口。修法两条：① 链接只来自两处 —— 我们上传的媒材，或这一单本身是链接送审（gate.kind = link 时由调用方显式传 links，只认 http(s)）；普通文案里粘着的 URL 一个都不挖，第二十二轮那条「裸 URL 单列一格」作废。② 引用原文不等于替原文做入口 —— 文案里的 markdown 链接降成纯文字，引用里的裸 URL 包成行内代码（否则飞书自动变超链接），覆盖除「依据文档链接」外的所有格子（维度、位置、问题描述、原因、修改建议、总览表每一格）；依据那一格保持可点，因为它是我们自己的飞书直链与模型侧引用的公开依据（FTC、Amazon Ads）。验收时又发现只改审查对象不够：第 5 条问题描述逐字引用了那段 markdown，回读仍有一个指向 production.it 的超链接 ⇒ 清扫必须覆盖所有引用原文的格子。判据 Z49e 五条含反向对照（真·链接送审必须给可点链接），拆掉修法即精确变红；test_agent 267/0、dual_track 自证 126/0、verify_cards 347/0。重渲染到 rev 15：文档内只剩 4 个超链接（2 条 L0 记录直链与 2 条 FTC/Amazon 依据），无陌生域名链接。本条订正同日 ref-shouheng-report-business-surface-20261017 的第③条。
supersedes: ref-shouheng-report-business-surface-20261017
tier: L1
title: "[反例] 报告里的「链接：点开」跳到了别人的域名（2026-10-17）：那条链接是我从文案正文里挖出来的 —— 现在链接只来自两处，引用原文不替原文做入口"
topic: 知识
valid_until: 2027-01-15
---

# 报告里的链接只能来自两处（订正同日第③条）

## 一、被规则制造出来的缺陷

Owner 一句问住：「你送的文案，为什么给『链接：点开』？这链接跳转是哪里？」

答案是：那一行**不是素材链接**，是我从文案正文里挖出来的一个 URL ——
`[production.It](http://production.it/)`。它本来只是粘贴时被编辑器自动加的 markdown 链接
（正文原话是 `increasing milk production.It supports`，`.It` 被当成意大利域名后缀），
`production.it` 是**.it 下的一台活着的公开站点**（实测 HTTP 200），与 Momcozy、与这条素材毫无关系。
更难看的是：同一份报告第 5 条问题的问题描述，原文就是「这里粘着一个 markdown 链接残留」——
**一边判它是缺陷，一边给它做了可点入口**。

## 二、现在的规矩

### ⓐ 链接只来自两处，绝不从正文里挖

1. 我们上传的媒材（media_link 上传到飞书云空间、设组织内可阅读并回读确认）；
2. 这一单本身是链接送审（gate.kind === 'link'）—— 此时 URL 就是送审对象，由调用方显式传 links。
   只认 http(s)；javascript:、ftp: 之类一律忽略。

普通文案里粘着的 URL 一个都不挖。第二十二轮那条「裸 URL 在文案里出现时单列一格」**作废**。

### ⓑ 引用原文不等于替原文做入口

- 文案里的 markdown 链接语法降成纯文字：`[production.It](http://production.it/)` 变成 `production.It`；
- 引用里的裸 URL 包成行内代码（反引号包住），因为飞书会把裸 URL 自动变超链接；
- 覆盖**除「依据文档链接」外的所有格子**：维度、位置、问题描述、原因、修改建议，以及问题总览表每一格。

「依据文档链接」保持可点：那是我们自己的飞书直链（回源用）与模型侧引用的公开依据
（实测这份报告里有 FTC 的 Health Products Compliance Guidance 与 Amazon Ads 的 Claims and substantiation），
它们是真证据，能点开是优点。

## 三、验收时又改了一版（值得记住）

先把「审查对象」那一行改完、回了 rev 13，回读仍发现文档里**有一个指向 production.it 的超链接**
—— 来源是第 5 条问题描述逐字引用了那段 markdown。
⇒ 清扫必须覆盖**所有引用原文的格子**，只改审查对象是不够的。
教训与同日另一轮同形：**判据要问「还有哪些格子会印这段字」，不能只问「我刚改的那一格对不对」**。

## 四、判据

新增 Z49e，五条（含反向对照）：文案里的 md 链接必须降成文字但文字要留下；
非链接送审不许出现「链接」行；裸 URL 必须包成行内代码；**真·链接送审必须给可点链接**（反向对照）；
links 传非 http(s) 一律忽略且正文 URL 也不许变成链接。拆掉修法即精确变红。
读数：test_agent 267/0、dual_track 自证 126/0、verify_cards 347/0。

## 五、重渲染与边界

同一份报告重投到 rev 15：文档内只剩 4 个超链接（2 条我们的 L0 记录直链 ＋ 2 条模型侧引用的
公开依据 FTC／Amazon Ads），没有任何指向陌生域名的链接。
边界：这不是「素材里有链接」的通用解 —— 对方真发来落地页要审时，链接会正常出现在报告里
（反向对照钉着）；外部依据链接仍然可点，要收掉得另定口径。
第二十二轮那份留底件里作废的那句**原文件没改**（改了会让已入库条目的 source.fingerprint 全部对不上）——
作废声明写在第二十三轮的留底件里，知识库侧走「新建 + supersedes」。
