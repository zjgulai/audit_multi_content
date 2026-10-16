---
asks:
  - 审查报告为什么会拿「@守衡」当素材正文
  - 调用方式（@ 提一嘴）与素材内容怎么区分
  - 为什么有媒材时那一节的标签要写「不是素材本身」
  - 纯图单在置信度台账里是不是撞成了同一个键
  - 这条修复的判据在哪、是不是接线级的
  - 那份已发出的报告能不能改
collection: 3_措辞表达库
corroborated_by:
  - 报告原件逐字（飞书 docx NKmbdpRrbooHFAxSNb2cIdlsnGe，bot 身份直读）
  - 代码定位：tools/agent/model_side.mjs::readingsForModelSide（【素材正文】= inbound.text）与 review_gate.mjs::chainInput（无媒材那一支才用 inbound.text）
  - 判据：test_agent 第 18c 组 R1–R3 接线级（真跑 runSubmissionGate 抓 readings）；留底件 sha256[:16] bc9b0bc650bc3f78
created_at: 2026-10-16
data_level: L2
evidence_group: coordinate
evidence_level: L2
forbidden: 不许据本条判断某条素材能不能发；不许把这一条理解成「人写的话都不用看」—— 对方的提问仍是上下文，只是**不是素材本身**；不许据本条声称那份已发出的报告已修正（没动它）；不许拿它当「纯文案单也不含 mention」的依据（那一支还没改）。
half_life_days: 90
id: ref-shouheng-invocation-is-not-material-20261016
kb_class: []
kind: fact
not_proves: 不能证明任何一条具体内容能不能发；不能替代 3_措辞表达库 的任何条款；不能证明那份已发出的报告已被更正（它还在飞书上，没动）；不能证明纯文案单的素材文本已经干净（chainInput 无媒材那一支仍用 inbound.text，未改）；不能证明改完之后模型再也不会提到调用方式（它仍可能从别处推断，只是输入里不再有那个词）。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为报告引用与实现说明，提及的「李倩怡」仅作为事发场景的指称、不涉联系方式等个人数据；「Owner」为角色指称；如后续来源变化需重新判定
provenance:
  anchor: PMO/守衡-调用方式不是素材-20261016.md#一/#二/#三/#四/#五/#六
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-16
  fingerprint: bc9b0bc650bc3f78
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-调用方式不是素材-20261016.md
summary: 审查报告把「@守衡」当成素材正文的根因与修法（2026-10-16）：model_side.mjs 把 inbound.text（消息原文，含 mention）贴上【素材正文】标签喂给模型侧，于是报告里出现「正文只带了中文账号名 @守衡…建议换成官方英文 handle」——Owner 指出那是调用方式、不是待审素材。修法两点：改用剥掉 @ 的 userText；有媒材时那一节标签自报「不是素材本身」（纯文案单照旧【素材正文】，剥完为空就一节不印）。同一根因第二处：置信度台账键 sha256(inbound.text) ⇒ 所有纯图单撞成同一个键，改成 input.text。判据 test_agent 第 18c 组 R1–R3（接线级，真跑 runSubmissionGate 抓 readings）。
tier: L1
title: "[参考实现] 「@守衡」不是素材（2026-10-16）：模型侧曾把消息原文含 mention 贴上【素材正文】标签，报告因此判「中文 handle」；同一根因还污染了台账键"
topic: 知识
valid_until: 2027-01-14
---

# 「@守衡」不是素材（2026-10-16）

> 留底件：`PMO/守衡-调用方式不是素材-20261016.md`（4,673 字节，sha256 前 16 位 `bc9b0bc650bc3f78`）。
> 现场：报告 docx `NKmbdpRrbooHFAxSNb2cIdlsnGe`（李倩怡那条图单）第 1 条。

---

## 一、Owner 的问题

原话：「这是李倩怡群里 @守衡 的审查报告，有一点是 **"但正文只带了中文账号名 @守衡"** 为什么会提到这句？
这是我们做飞书的提问，面对美国市场，是提供的素材能不能进美国市场，**不是指我调用守衡的方式**」。

报告第 1 条逐字：「1.【本地化】素材正文（发布账号名）与图 1 主文字（品牌名 momcozY）——
无库内依据·建议转人工｜原因：…**正文只带了中文账号名 @守衡**…**建议把正文里的 @守衡 换成品牌官方
英文 handle**（例如 @momcozy），或直接删掉该水印…」
⇒ **把「怎么叫我们」当成了「素材写了什么」**，还据此给了一条改法建议。

## 二、根因（一行）

`tools/agent/model_side.mjs::readingsForModelSide` 里：
`const body = inbound.text; parts.push('【素材正文】\n' + body)` ——
而 `inbound.text` 是**消息原文（mention 就在里面）**，却被贴上了 **【素材正文】** 这个标签。
那是模型侧唯一的输入 ⇒ 模型照着标签判，才产出「素材正文（发布账号名）」。
**链那一侧没这个问题**：`chainInput` 只在「没有媒材」时才把 `inbound.text` 当素材。

## 三、修法（两点缺一不可）

① 取**剥掉 @ 之后**的 `userText`（`handleMessage` 早就算好，上午刚用在落表那一格）；
② **标签说实话**：有媒材时它是「对方这条消息里写的字（**这不是素材本身**…素材是下面的读数）」；
纯文案单照旧 `【素材正文】`；**剥完为空就一节都不印**。提示词第 4 条的定位规则同步补了这个标签。

## 四、同一根因的第二处

置信度台账的键也拿消息原文算：`materialSha8 = sha256(inbound.text)[:8]` ⇒
**所有纯图单撞成同一个键**（纯图单的 `inbound.text` 就是「@守衡」），而那一格的意义正是
「与这一单是哪条素材一一对应」。改成 `input.text`（链那侧的素材文本）。
它**只**影响台账键 —— 行上的 `内容 ID` 是另一处独立计算。

## 五、判据（接线级）

`test_agent` 第 18c 组 `R1–R3`：真跑 `runSubmissionGate`、抓递给模型侧的 readings ——
`R1` 只 @ 一下（无正文）⇒ 读数里没有 `@守衡`、也没有【素材正文】那一节，图上字照旧在；
`R2` 有提问＋图 ⇒ 留话不留 mention、那节**自报「不是素材本身」**；
`R3` 反向对照：纯文案单**照旧是【素材正文】**。

## 六、没做的

① 那份**已发出的报告改不了**（投递件）—— 本条只保证下一次不再这么判；
要不要补更正说明是 Owner 的决定，**没动它**。
② **纯文案单的素材文本仍含 mention**（`chainInput` 无媒材那一支）；实测真实行里看不到 `@守衡`，
故没动 —— 动它会让 `内容 ID` 跟着变（去重语义），要单独定。
③ 当天另有会话在同一仓库改 `dual_track.mjs`/`review_publish.mjs`，`test_agent` 的 `Z45` 红是它进行中的活。
