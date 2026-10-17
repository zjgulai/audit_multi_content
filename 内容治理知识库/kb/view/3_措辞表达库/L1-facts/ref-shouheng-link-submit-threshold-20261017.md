---
asks:
  - 一条文字送审的正文里出现 URL，算不算链接送审、怎么判
  - 报告里为什么会给文字类素材加一行「链接：点开」（该在哪个入口修）
  - 为什么报告是「忠实执行判词」而错的不是报告
  - linkOnly 的阈值取多少、依据是什么、误判面在哪
  - 判成文字送审之后链接会不会丢（该读还会读吗）
  - 这条与第 23 轮「链接只来自两处」的关系（同一个口子吗）
  - 判据是哪些（Z50／Z50b）、反向对照怎么钉的
collection: 3_措辞表达库
corroborated_by:
  - /Users/lute/Project/audit_multi_content/PMO/守衡-文字送审被误判成链接送审-20261017.md（真单日志判词与修复回读）
  - /Users/lute/Project/audit_multi_content/tools/agent/review_gate.mjs（linkOnly 与 isSubmission ② 的收窄）
  - /Users/lute/Project/audit_multi_content/tools/agent/agent.mjs（报告的 material.links 也走 linkOnly）
  - /Users/lute/Project/audit_multi_content/tools/test_agent.mjs（Z50 四半与 Z50b）
created_at: 2026-10-17
data_level: L2
evidence_group: rule
evidence_level: L2
forbidden: 不许拿本条判断某段文案能不能发；不许把 40 字当成 PRD 规定（它是启发式）；不许因为本条就不过「正文里带的链接」（links 仍然回给调用方，该读还会读）；不许把「报告加了链接行」当成报告层的 bug 去改报告版式（本条修的是入口判词）。
half_life_days: 180
id: ref-shouheng-link-submit-threshold-20261017
kb_class: []
kind: fact
not_proves: 不能证明 40 字阈值覆盖所有情形（正文长、但真要审的是链接的单子会被判文字送审）；不能证明闸门其他分支（media / text / meta-ask）也一定对；不能证明 PRD 定义过「怎样算链接送审」（PRD 没写，这是本仓启发式）；不能替代 3_措辞表达库 的任何条款。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为判定口径与判据读数
provenance:
  anchor: PMO/守衡-文字送审被误判成链接送审-20261017.md#一、先回答「有没有落库」
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-17
  fingerprint: 810476c80388fdcf
  kind: file
  ref: /Users/lute/Project/audit_multi_content/PMO/守衡-文字送审被误判成链接送审-20261017.md
summary: "Owner 拿着报告问「为什么文字类的还加个错误的链接」——报告里写着「送审内容：文案 926 字｜链接 1 条 / 链接：点开」。第 23 轮定的规矩是「链接只来自两处（我们上传的媒材，或这一单本身就是链接送审）」，第二处接的是 gate.kind === 'link'，而这一单的闸门判词恰是「link —— 贴了链接（1 条）—— 要读的就在链接里」：闸门的老判据「正文里有 URL ⇒ kind=link」把一段 900 字广告文案里粘贴残留的 http://production.it/ 当成「要读的东西」。⇒ 报告没错，它忠实执行了判词；错的是判词。修法（入口，一个地方）：review_gate 新增 linkOnly(text) = {links, body(去掉链接后的正文), isLinkOnly: links 非空且 body ≤ 40 字}，isSubmission 的链接分支改为只认 isLinkOnly，报告的 material.links 也用同一判据；判成纯文字不等于丢掉链接（links 仍回给调用方，该读还是会读）。阈值 40 字是启发式不是 PRD 条款（正常「贴个链接让我看」那句话 8~10 字都在里面，真文案远超它）。判据 Z50①短正文仍判 link、②长文案必须判 text（本轮回填的真单）、③判文字后 links 不许丢、④反向对照；Z50b 钉报告侧同口径。读数 test_agent 271/0、dual_track 自证 126/0、verify_cards 347/0。那份真报告 docx/GSJtdC9wSoI3KExVgf9c8Oz2ndb 已修到 rev 7：链接 1 条消失、文档内无 production.it 链接、执行段仍是打回且无 @。"
tier: L1
title: "[规则] 「链接送审」要加一条判据（2026-10-17）：贴的链接必须就是素材 —— 否则一条文字送审会因为正文里的粘贴残留被印上「链接：点开」"
topic: 知识
valid_until: 2027-04-15
---

# 「链接送审」的判据：贴的链接必须就是素材

## 一、这条是从哪个口子进来的

Owner 拿着报告问：「你刚修复的问题没有落库吗？**为什么文字类的还加个错误的链接？**」
（报告里那一段：送审内容 文案 926 字｜链接 1 条 ／ 链接：点开）

第 23 轮定的规矩是「链接只来自两处：我们上传的媒材，**或这一单本身就是链接送审**」。
第二处当时接的是 `gate.kind === 'link'`。而这一单的闸门判词是：

```
🧭 送审闸门：link —— 贴了链接（1 条）—— 要读的就在链接里｜起链
```

闸门的老判据是「正文里有 URL ⇒ kind = link」。那段 900 字广告文案里粘着
`http://production.it/`（粘贴时编辑器把 `production.It` 当意大利域名后缀自动加的链接），
于是闸门认为「要读的就在链接里」⇒ 报告忠实执行那个判词，把它列成「链接 1 条 / 链接：点开」。

⇒ **报告没错，错的是判词。** 一条文字送审的正文里出现 URL，不等于这一单的素材是那个 URL。

## 二、判据

在闸门里加一个可单独调用的判定（一个入口，两处都用它）：

```
LINK_ONLY_MAX_BODY = 40 字
linkOnly(text) = { links, body: 去掉链接后的正文, isLinkOnly: links 非空 且 body ≤ 40 字 }
```

- `isSubmission` 的「② 链接」那一支改用 `isLinkOnly`；
- 报告的 `material.links` 也用它：**只有 linkOnly 为真时才把 URL 列成链接**；
- 判成纯文字**不等于丢掉链接**：links 照样回给调用方（链接仍在正文里，该读还是会读）。

阈值取 40 字：正常「贴个链接让我看」那句话都在里面（「审一下这个落地页」8 字、
「这条视频的落地页能发吗」10 字），而任何一段真文案都远超它。

## 三、判据与读数

Z50①短正文带链接仍判 link（不误伤正常链接送审）；Z50②长文案带链接必须判 text（本轮回填的真单）；
Z50③判成文字后 links 不许丢；Z50④反向对照（那段正文本来就超阈值）；Z50b 报告侧同口径
（文字送审一个链接行都不许有，真链接送审必须有链接行）。读数 test_agent 271/0、
dual_track 自证 126/0、verify_cards 347/0。

## 四、边界

40 字是**启发式，不是 PRD 条款** —— PRD 没定义「怎样才算链接送审」。这条阈值只解决
「长文案里粘着链接」这一类；若将来出现「正文很长、但真要审的就是那个链接」的单子，
它会被判成文字送审，那时人说一句「读这个链接」即可。
`kind` 会影响落表的「类型」那一格（图片/视频 / 链接 / 文字），这一单今后记「文字」，这是对的。
这条修的是**入口**（判词），报告侧那三条规矩（链接只来自两处、引用不替原文做入口、全写不截断）一个字没动。
