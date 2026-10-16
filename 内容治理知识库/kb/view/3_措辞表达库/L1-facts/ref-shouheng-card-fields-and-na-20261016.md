---
id: ref-shouheng-card-fields-and-na-20261016
title: "[参考实现] 守衡的卡片字段与「（未填）」（2026-10-16 实测）：字段名认哪个键、哪些格不在清洗清单里、判据为什么全绿而线上照样漏"
collection: 3_措辞表达库
tier: L1
topic: 知识
kind: fact
evidence_level: L2
data_level: L2
sensitivity_level: L2
evidence_group: coordinate
half_life_days: 90
created_at: 2026-10-16
valid_until: 2027-01-14
owner: 刘华丽
kb_class: []
summary: 守衡卡片上「（未填）」与内部读数交替出现的实测与收口（2026-10-16）：真单 ws_outbound.jsonl 第 1266/1270 行，卡面是「（未填）␤读数段」交替 N 组。根因是两处叠在同一个渲染点：① cards.mjs::fieldRow() 读 f.label，而模型 85/85 次全给 f.name（登记表样例却写 {label,value}）⇒ s(undefined) ⇒ NA=（未填）；② 读数全在 fields[].value 里，而 machineAnswerFold 的清洗清单只有五个字符串格、没有 fields ⇒ 清洗一次都没跑到。为什么昨天修两遍还漏：FIX-020/025 的复现件造的是只有三格的卡，而真卡多带一个 fields；修复生效后当晚 20:12/20:19 两张卡（台账 1190/1197）就已复现；且（未填）本身是 10-14 02bda1f 引入的回归（把 undefined 包成了正式占位符）。判据全绿而线上照样漏的原因：J13a3e 的夹具把（未填）当成模型正文写死在 reasoning 里 —— 判据喂的是想象的形状。修法三处：认名收口（LABEL_KEYS/VALUE_KEYS 唯一真源 + fieldPair）、清洗覆盖 fields[]/boundary、判据补真形状 6 条。同一输入新旧对照：（未填）4→0、漏读数 9 类→0、卡面 1490→347 字。附带发现并修了潜伏缺陷：短卡 JSON（<800 字）被当成读数段改写 ⇒ JSON 破掉 ⇒ 整张卡降级成纯文本（线上至今 0 次）。登记 FIX-037/038，提交 f749cfd。
asks:
  - 守衡的卡片上为什么会出现「（未填）」，它是模型写的还是代码渲染的
  - 卡片的一个「字段」里，标签该写成 label 还是 name（登记表与模型实际用的是不是同一个键）
  - 内部读数怎么会被印到卡片正文上（哪些格在清洗清单里、哪些不在）
  - 同一个卡片格式问题，为什么昨天修了两遍、今天又复线了（修复没生效，还是压根没修到这个形状）
  - 判据（verify_cards / prd53_format）为什么改前改后都全绿，而线上照样漏
  - 「（未填）」这个占位符是什么时候开始在台账里出现的（是回归吗）
  - 要改卡面渲染或清洗，得动哪几个文件、先把哪几条判据接上
  - 怎么证明修复真的拦得住（变异自证怎么做、哪几条判据会精确变红）
  - 短卡 JSON（<800 字）为什么会让整张卡降级成纯文本
  - 改了守衡之后怎么知道该不该重启（用哪把尺子判断模块有没有被加载）
not_proves: 不能证明任何一条具体内容能不能发 —— 它讲的是「读数怎么被印到卡面上」，不是审查结论；不能替代 3_措辞表达库 的任何条款（条款号/命中表达/锚点一律以权威库 kb/l3、kb/l4 为准）；不能证明 PRD §5.3.1 要求 PASS 卡正文清空 —— PRD 只规定「一句话结论」，没规定 PASS 卡正文，本条描述的是 2026-10-16 这一版代码的现行口径；不能证明线上已经复现修好 —— PASS＋fields 那个形状在重启后还没在线上再出现过，本轮证据是离线真单复原；不能证明短卡 JSON 那条缺陷已经发过事故 —— 台账里 0 次，它是潜伏缺陷；不能证明这条链在别的部署里也这样。
forbidden: 不许据本条判断某条素材能不能发；不许把「（未填）」当成模型写的内容（它是 cards.mjs 的 NA 占位符，由 fieldRow 渲染）；不许把 registry.mjs 样例里的 {label,value} 当作模型实际会用的键（实测 85/85 是 {name,value}）；不许只改判据不改渲染与清洗（这次复发就是判据喂了想象的形状）；不许据本条声称 PASS＋fields 那个形状已在线上验证通过。
source:
  kind: file
  ref: /Users/lute/Project/audit_multi_content/PMO/守衡-卡片字段与未填-20261016.md
  fingerprint: bfabc743dbc601b9
  captured_at: 2026-10-16
corroborated_by:
  - 源码逐行：tools/reply-cards/cards.mjs 的 fieldRow 读 f.label、s()/NA 落占位符；tools/reply-cards/envelope.mjs 的 machineAnswerFold 清洗清单是五个字符串格
  - 真单台账：PMO/logs/ws_outbound.jsonl 第 1266/1270 行（当次）与第 1190/1197 行（修复生效后当晚复现）；（未填）按天统计 10-13 及以前 = 0，10-14/15/16 = 6/7/4
  - 模型实际形状：PMO/shouheng-state/sessions/dm_ou_batch_runner.json 里模型给的 fields 键组合 85/85 全是 (name,value)
  - 判据与变异：node tools/verify_cards.mjs 343/0；变异三条（fieldRow 退回 s(f.label) / 关掉 fields 清洗 / 拆护栏三）各自精确变红，还原后 sha256 逐字一致
  - 加载态：PMO/shouheng-state/daemon-run.json 的 startedAt（pid 64874，11:11:17）晚于两个模块 mtime（11:09:36）⇒ 已加载
provenance:
  anchor: PMO/守衡-卡片字段与未填-20261016.md#一/#二/#三/#四/#五/#六/#七
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为实现说明、命令与台账行号，不含姓名、联系方式等个人数据；文中「Owner」为角色指称；如后续来源变化需重新判定
---

# 守衡的卡片字段与「（未填）」（2026-10-16 实测）

> 与另几条参考实现的分工：readings r2 讲**读数是什么形状、多慢**；readings-ownership 讲**读数是谁产的、谁看得到**；
> reading-identity 讲**读数是不是本单的**；question-cell 讲**「送审问题」那一格怎么组装**；
> 本件讲**读数怎么被印到卡面上的** —— 渲染端认哪个键、哪些格根本不在清洗清单里。

---

## 〇、起因（Owner 原话）

> 「守衡输出的 pass 结论，按照 prd 一句话结论，现在格式不对，**这个问题昨天修复了，今天又复线了**，查下什么原因」

真单：`PMO/logs/ws_outbound.jsonl` **第 1266 行**（10:50:06，`…wellness-1-…`）与
**第 1270 行**（10:54:45）。台账第 1270 行逐字（1,416 字）：

```
【审查结论：PASS】未发现已知底线风险，可转交 @sign-off 责任人（未配置） 进行 sign-off。
Cleaning & On-the-Go Bundle 图：链侧 REVIEW/0；合并稿为空
（未填）
链的口径：凡属画面层的判定，只能依据送审时那份「画面读数」。…
（未填）
链侧三态 = `REVIEW ｜ 0 ｜ 置信度 None`（带依据侧 `NEEDS_INPUT`）；而表内结论读数 = PASS。…
（未填）
`未命中 ≠ 合规`；本次 `REVIEW` 是覆盖缺口…
（未填）
链侧：「飞书那一步：没有做」 —— `published=false`…
```

形状 = **「（未填）␤读数段」交替 N 组**（N = `fields` 的格数）。当天 4 张结论卡（01:34 / 02:35 / 02:50 / 02:54）
**全是 PASS、全是这个形状**。

## 一、根因：两处缺陷叠在**同一个渲染点**上

各自都对，合起来才出问题：

**① `（未填）` 不是模型写的** —— 它是 `tools/reply-cards/cards.mjs::fieldRow()` **渲染**出来的：

```js
fields.map((f) => ({ content: `**${s(f.label)}**\n${s(f.value)}` }))
```

- 登记表 `registry.mjs` 的样例写的是 **`{label, value}`**；
- 而**模型 85/85 次全给 `{name, value}`**（批跑会话全量数的，`label` 一次都没出现过）；
- `f.label` = `undefined` ⇒ `flat1(undefined)` 返回 `''` ⇒ `s()` 落 `NA = （未填）`；
- 而 **`s(f.value)` 是原样照印**，一个字都不洗。

**② 读数全在 `fields[].value` 里，而清洗清单里没有 `fields`** ——
`tools/reply-cards/envelope.mjs::machineAnswerFold()` 逐格清洗的是
`['title','verdict','reasoning','wrong','verdict_text']` 五个**字符串格**，`fields`／`boundary` 都不在里面
⇒ 清洗**一次都没跑到**。

> ★ 一句话：**「字段名格印占位符、字段值格原样印读数」** —— 交替就是 N 个 `fields` 各印两行。

## 二、为什么「昨天修了、今天又复线」——三层，都不是「修复失效」

1. **从来没修到这个形状。** FIX-020（10-15 15:11）与 FIX-025（10-15 17:45）的复现件
   `tools/.probe_pass_card_20261015.mjs` 造的是**只有 `title/verdict/reasoning` 三格**的卡；
   而**真卡多带一个 `fields`** —— 那一格恰好落在两次修复的缝里。**「修好了」验的是另一个形状。**
2. **昨晚就已复现，只是没人看见。** FIX-025 落库 17:45、守衡 19:58 重启（pid 98334）；
   而台账**第 1190 行（20:12:47）与第 1197 行（20:19:36）**两张 PASS 卡照样有「（未填）」与读数
   —— **在修复生效之后约 2 小时**。不是「今天又坏」，是「昨天就没全好」。
3. **`（未填）` 本身是 2026-10-14 引入的回归。** `fieldRow` 从 2026-09-21 建起来就一直读 `f.label`；
   10-14 那次（`02bda1f`）把它包进 `s()`，于是原本印出来的 `undefined`
   变成了**看起来像正式占位符的 `（未填）`**。台账按天统计正好对上：
   `（未填）` 在 **10-13 及以前 = 0**，10-14 / 10-15 / 10-16 = **6 / 7 / 4**。

**与 FIX-022 是同一个病、同一个文件、第三处执行点**：那次修了 `flat1` 的标签分支、
`carryCardText` 也合了口径 —— 但 **`fieldRow` 自己另写了一份认键逻辑**，没被合进去。

## 三、判据为什么全绿（这才是能复发的原因）

`verify_cards` **337/0**、`prd53_format` **19/0** —— 改前改后都绿，而线上正漏着。

`verify_cards` 的 J13a3e 夹具是 `{title, verdict, reasoning}` **三格**，
而且它把 `（未填）` **当成模型正文里的一行**写死在 `reasoning` 字符串里 ——
**而真单里的 `（未填）` 是 `fieldRow` 渲染出来的，模型根本没写过这四个字。**
⇒ **判据喂的是「写判据的人以为的形状」，事故正好落在它没喂的那一类上**（FIX-023 那条纪律的第三次复发）。

## 四、修法（三处，缺一件都还会漏）

| # | 改哪 | 改什么 |
|---|---|---|
| ① | `cards.mjs::fieldRow` | **认名收口**：新增 `LABEL_KEYS`（`label/name/title/key`）与 `VALUE_KEYS`（`value/note/content/text`）**唯一真源** ＋ `fieldPair()`；`flat1` 的标签分支也改读同一张表。**认不出标签就只印值、不印 `（未填）`** —— `（未填）` 只留给「**值**真的缺了」那一档 |
| ② | `envelope.mjs::machineAnswerFold` | 补 `boundary` 进字符串格清单；新增 **`fields[]` 整组清洗** —— 逐格 `stripInternalNotes(…, {machine,cardField})` ＋ `hasSubstance()`（**与 FIX-020 同一把尺子，不新造**）：洗后**还有实质内容**就留（模型写的话一句不丢），**整格是读数**就整格不留；原文 `foldInto` 进折叠区（「搬是搬，砍是砍」） |
| ③ | `verify_cards.mjs` | 新增 **J13a3f / f2 / f3 / f4 / f5 / f6** 六条，夹具**逐字取自真单**（`dm_ou_batch_runner.json` 里模型那一轮的卡，`fields` 键名与四格内容一字未改）；其中 f3 / f4 是**源码级接线**判据（行为级判据挡不住「把 `fieldRow` 改回去」） |

改完的卡：抬头结论行 ＋ 模型那句原话 ＋ 证据折叠区。

## 五、实证（同一输入的新旧对照）

把旧代码整套装回去、喂**同一张真卡**：

| | （未填） | 漏出的读数 | 卡面字数 |
|---|---|---|---|
| 修复前 | **4** | **9 类** | 1490 |
| 修复后 | **0** | **0 类** | 347 |

**变异自证三条，逐条精确变红**（真造一遍、还原后 sha256 逐字一致）：

1. `fieldRow` 退回 `s(f.label)` ⇒ **J13a3f ＋ J13a3f2 ＋ J13a3f3** 变红；
2. 关掉 `machineAnswerFold` 的 `fields` 那一跳 ⇒ **J13a3f** 变红（读数露出）；
3. 拆掉护栏三（JSON 保护）⇒ **J13a3f6** 变红。

判据终态：`verify_cards` **343/0**（原 337/0）｜`prd53_format` 19/0｜`test_agent` 237/0｜
`verify_fixed` 11/0｜`python3 kb/l8/workflow_smoke.py` **exit 0（S1–S8 契约齐）**。

## 六、附带发现的第二个缺陷（同一个症状类，潜伏）

写 ③ 的夹具时撞出来的：同一份卡 JSON，`extractCardBlock(raw)` 直接调**成功**，
而走 `toCardOrText(raw, …)` 却 `mode=text`「**对象括号没配平**」。

根因：`toCardOrText` 里 `stripInternalNotes(reply, {machine})` 跑在 `extractCardBlock` **之前**
（那是有意的：模型若把查证笔记抄进块里，晚一步就摘不到），而 `machineReadingSentences` 的
护栏一只认「**本行**以 `[[card:` 开头」—— 而块标记与 JSON **不在同一行**
⇒ **JSON 那一行没有任何护栏**，只剩「段长 > 800 就不动」那条**侥幸**挡着。
一份 **769 字**的短卡 JSON 于是被 `split('；')` 摘掉读数句 ⇒ JSON 破掉 ⇒ **整张卡降级成纯文本**发出。

**⚠️ 线上至今 0 次**（`ws_outbound.jsonl` 里「没能把回答组织成卡片」= 0）——
真卡的 JSON 都超过 800 字、被那条侥幸挡住了。**这是潜伏缺陷，不是已发事故。**
修法＝**护栏三**：整段是合法 JSON 对象就不许改写；判据 `J13a3f6`。

## 七、还欠着的

- **PASS ＋ `fields` 那个形状在线上还没再出现过**：重启后 10 条出站里 4 张结论卡都是 REVIEW/BLOCK
  （走逐条块那条路，本来就没这个毛病）。本轮证据是**离线真单复原**，不是线上复现。
- **PASS 卡正文该不该整段清空，没有裁定**：PRD §5.3.1 只说「一句话结论」，没规定 PASS 卡正文。
  现在模型写了实质内容时会保留那段（本例 347 字里就是模型自己标的「两种互不相容的说法…请你核」）。
  按「模型写的话一句不丢」该留；要改成「PASS 卡一律只留结论行」，那是**新决策**，得补一条判据守着。

## 八、出处（都能自己跑一遍）

- 守衡侧：`tools/reply-cards/cards.mjs`（`LABEL_KEYS` / `VALUE_KEYS` / `fieldPair` / `fieldRow` / `flat1`）、
  `tools/reply-cards/envelope.mjs`（`machineAnswerFold` / `stripInternalNotes` / `machineReadingSentences` 的护栏三）、
  `tools/verify_cards.mjs`（J13a3f 家族）。
- 真单与读数：`PMO/logs/ws_outbound.jsonl` 第 1266 / 1270 / 1190 / 1197 行；
  `PMO/shouheng-state/sessions/dm_ou_batch_runner.json`；`PMO/shouheng-state/daemon-run.json`；`PMO/logs/restart-ledger.jsonl`。
- 登记：`PMO/已修问题.jsonl` 的 **FIX-037 / FIX-038** 与 `PMO/已修问题索引.md`；提交 **`f749cfd`**。
- 加载态：守衡 pid **64874** 启动于 **11:11:17**，而 `cards.mjs` / `envelope.mjs` 的 mtime 是 **11:09:36**
  ⇒ **早于启动 = 已加载**（那次重启由另一会话发起，顺带带上本修复）。
- ⚠️ 写盘纪律：本留底件走 **node / `/bin/cp` 通道**——用 python 直写 `.md` 会落 4096 字节信封，
  宿主侧读成 binary（本件第一次就是这么写的，已按 `GUIDE.md` §八 修回）。