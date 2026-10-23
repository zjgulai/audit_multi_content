---
asks:
  - 为什么同一条 Owner 意见当天会被报两次（同一个问题修复两次仍复现）
  - 卡片上两张同指一份报告的清单链接是怎么来的、真因在哪一层
  - 改卡面文案（例如把链接措辞压短）会把哪些判据悄悄改成假绿
  - 报告里「修改建议」为什么会有 300+ 字，30 字上限该在哪一层落
  - 压缩报告文字时哪些标注不许跟着丢（改法出处标注怎么保住）
  - 怎么证明链接去重的判据不是恒真的（反向对照长什么样）
collection: 3_措辞表达库
corroborated_by:
  - 锁表逐条：kb/l7/registry/owner-fix-locks.yaml::L20（不变量、判据指针、反向对照、实测读数 link_lines 2→1、advice 372→28 字）
  - 契约登记：kb/l7/registry/report-output-contract.yaml::fix_20261019_dup_link_envelope_and_report_advice30（根因、改动文件、gauges）
  - 源码逐行：tools/reply-cards/envelope.mjs 的 REPORT_LINK_LINE_RE / hasReportLinkLine，及 applyReportLink / insertLinkAboveAction 两处改走它；tools/agent/dual_track.mjs 的 ADVICE_MAX 与 sugShort/sugCore/adviceSrcTag
  - 实测反向对照：把信封两处判据改回 .includes('查看完整问题清单与修改建议') ⇒ verify_cards J15a 报「实际出现 2 次」（复现 Owner 那张卡），恢复后 348/0
  - 同口径裁决：kb/l7/registry/prd533-constraints.yaml::conflicts[X1].resolution（30 字裁决，卡面与报告同一把尺）；kb/l7/registry/prd-card-known-drift.yaml::known_conflicts[C2] 状态改为已裁
created_at: 2026-10-19
data_level: L2
evidence_group: coordinate
evidence_level: L2
forbidden: 不许据本条判断某条素材能不能发；不许把「一张卡只有一条链接」当成链接一定点得开（可达性是另一把尺）；不许把「报告建议≤30 字」当成改法变好了——真正要修的是源头产物是否是一句可执行动作，压缩只是硬兜底；不许为了省字数把出处标注删掉（「改法参考库内反例（非库规原文）」是防误导，不是装饰）；不许把判据绑死某一句措辞（那是本轮真因）；不许用 renderMerged 内部那一道 dedupeReportLinkLines 当成主修法——信封层仍在它之后插链接。
half_life_days: 90
id: ref-shouheng-dup-link-and-advice30-20261019
kb_class: []
kind: fact
not_proves: 不能证明任何一条具体内容能不能发——它讲的是守衡卡片/报告的渲染与判据；不能替代 3_措辞表达库 的任何条款（条款号、命中表达、锚点以权威库 kb/l3、kb/l4 为准）；不能证明其他措辞/其他卡片形态也不会有重复链接（判据只认「→（或 ->）＋完整清单或查看完整问题清单与修改建议＋冒号」这一族形状，新措辞仍需补夹具）；不能证明报告的每一条修改建议都已经 ≤30 字（本件修的是渲染与提示词，历史存量报告没有回改）；不能证明 PRD §17 整卡字数已经达标（≥3 档实测仍超，登记在 prd17-limits.yaml::known_conflicts[C1]，与本条无关）；不能证明旧报告的云文档已更新（本件只改产者，不重发历史件）。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为渲染链路与判据说明，不含姓名、联系方式等个人数据；文中「Owner」为角色指称；如后续来源变化需重新判定
provenance:
  anchor: kb/l7/registry/owner-fix-locks.yaml#locks[L20] ＋ kb/l7/registry/report-output-contract.yaml#fix_20261019_dup_link_envelope_and_report_advice30 ＋ kb/l7/registry/prd533-constraints.yaml#conflicts[X1].resolution
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-19
  fingerprint: 93337f9ba0f9789e
  kind: file
  ref: /Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/l7/registry/owner-fix-locks.yaml
summary: 同一条 Owner 意见当天被报两次，两次都是「修在了错的层/错的介质」。① 链接：上一轮在 dual_track.renderMerged 里加 dedupeReportLinkLines()，判据（test_agent Z59）也直接调那个函数——测的是函数、不是人看到的那张卡；而第二条链接是信封层 reply-cards/envelope.mjs 的 applyReportLink / insertLinkAboveAction 在渲染之后插进去的，那道去重看不见它。真因更朴素：那两处「块里已经有了吗」判断绑死旧字面量 .includes('查看完整问题清单与修改建议')，而当天为 PRD §17 字数把卡面措辞改成「→ 完整清单：」⇒ 认不出 ⇒ 再补一条（还是长措辞）⇒ 一张卡上下两条同指一份报告。修法：判据认形状不认措辞（REPORT_LINK_LINE_RE / hasReportLinkLine，两种措辞都认），补链接时用短措辞；dedupeReportLinkLines 降为最后兜底。② 建议：上一轮只压卡面 sugCard，报告仍用 sugFull，而 Owner 看的是报告 ⇒ 报告分支 sugShort = _clip(sugCore, ADVICE_MAX=30)，并把源头 advice.mjs / model_side.mjs 提示词一并要求 ≤30 字。另有一条连带：出处标注（改法参考库内反例（非库规原文））不许随压缩被砍掉，挪到标题行末尾，且只在真参考过时才印。反向对照：把信封两处判据改回旧字面量 ⇒ J15a 精确变红（实测「实际出现 2 次」，就是 Owner 那张卡）；恢复后 verify_cards 348/0。
tier: L1
title: "[参考实现] 一张卡只许一条清单链接 ＋ 报告「修改建议」≤30 字（2026-10-19 二次报修）：为什么上一轮修了没生效，以及判据该盯哪一层"
topic: 知识
valid_until: 2027-01-17
---

## 一句话

**同一条意见被报两次，原因是两次都修在了错的层/错的介质上。** 判据要盯「人真正看到的那个介质、那一层」，不是盯同名的邻居函数。

## 一、现象（Owner 2026-10-19，第二次报同两条）

```
1.卡片上的清单链接有两个，去掉上面的，保留下面的
  → 完整清单：https://momcozy-in.feishu.cn/docx/TCr8…
  → 查看完整问题清单与修改建议：https://momcozy-in.feishu.cn/docx/TCr8…

2.审查报告中，修改建议你写了200多字，修改建议 ≤30 字
```

两条同指一份报告；建议那一格实测 **372 字**。

## 二、真因（两条都不是上一轮以为的那个）

### ① 链接：重复是**信封层**插的，`renderMerged` 里的去重看不见它

上一轮的做法是：在 `tools/agent/dual_track.mjs::renderMerged` 里加一道
`dedupeReportLinkLines(blockText)`，并让 `test_agent` 的 Z59 **直接调这个函数**做判据。
于是「测过了」——但测的是**函数**，不是**人看到的那张卡**。

真正插第二条的是 `tools/reply-cards/envelope.mjs`：

- `applyReportLink(kind, data, reportLink)` —— 整卡找一遍，已有就不补；
- `insertLinkAboveAction(text, url)` —— 在 §5.3 块的动作行之上插一条。

两处的「块里已经有了吗」判断写的是**旧字面量**：

```js
if (src.includes('查看完整问题清单与修改建议')) return { text: src, action: 'already' };
if (JSON.stringify(data).includes('查看完整问题清单与修改建议')) { ... }
```

而同日为了 PRD §17 的整卡字数（≥3 档 ≤100 字），卡面措辞已从
`→ 查看完整问题清单与修改建议：`（16 字）压成 `→ 完整清单：`（7 字）。
⇒ 块里明明是 `→ 完整清单：…`，两处判断都返回 false ⇒ 走到 `in-block`
⇒ **在动作行之上再插一条**（还用回更长的旧措辞）⇒ 上下两条。

`dedupeReportLinkLines()` 早在 `renderMerged` 内部就跑完了，信封这一条是**它之后**加进去的。

### ② 建议：上一轮只压了卡面，Owner 看的是报告

| 介质 | 变量 | 上一轮 |
|---|---|---|
| 卡面 `head` | `sugCard = _clip(sugLine, 30, …)` | 已压 |
| 报告 `layout === 'report'` | `sugShort = sugFull`（全写） | **没压** |

## 三、修法

### 链接：认形状，不认措辞

```js
// envelope.mjs
export const REPORT_LINK_LINE_RE = /(?:→|->)\s*(?:完整清单|查看完整问题清单与修改建议)\s*[：:]/;
export const hasReportLinkLine = (v) => REPORT_LINK_LINE_RE.test(String(v ?? ''));
```

- `insertLinkAboveAction` / `applyReportLink` 两处都改走它；
- 自己补链接时用**短措辞** `→ 完整清单：`（与 `renderMerged` 的 `reportNote` 同一句，
  也不再白吃 §17 的 9 个字）；
- `dedupeReportLinkLines()` 保留为**最后一道兜底**，不是主修法。

两个坑写在代码注释里，免得下一个人踩回去：

- **不许写 `^` 行首锚**：`applyReportLink` 那条是拿 `JSON.stringify(data)` 判的，
  换行被转义成字面量 `\n`，行首锚永远不命中；
- **两种措辞都要认**：库侧（`kb/l5/p0_fastpath.py` 等）产出的仍是长的那条。

### 建议：卡面与报告同一把尺

- `ADVICE_MAX = 30`（由 `CARD_ADVICE_MAX` 改名 —— 它已经不只管卡面了）；
- 报告分支：`sugShort = _clip(sugCore, ADVICE_MAX, false)`；
- 量的是**改法本体** `sugCore`，不是带出处标注的 `sugLine`。否则那半句
  「（库内无可参考建议 —— 改法是按素材给出的…）」会被截进 30 字里，
  **Owner 2026-10-19 点名去掉的两句又回到报告**（Z23 当场抓到）。
- **源头**一并收口：`advice.mjs` 的 SYSTEM 规则 0 与 `model_side.mjs` 提示词 4b
  都要求「≤30 字的一句可执行动作」。渲染层只是**硬兜底** —— 源头写 300 字，
  截出来的是半句诊断，不是动作。

### 连带：出处标注不许被压缩砍掉

它防的是「把模型写的改法读成库规原文」（Owner 2026-10-09 的口径）。压到 30 字之后它一定被截，
砍掉就是拿压缩换掉防误导 ⇒ 挪到**标题行末尾**（元信息那一格，与来源标记并列）：

```
**F-01 ｜ 合规与受监管宣称·绝对化用语 ｜ 未分级**  —— **有库内条款依据** · 改法参考库内反例（非库规原文）
```

**只在真参考过时（`adviceReferencedKb === true`）才印**；没参考时一个字都不印。
判据：**标注必须与事实一致** —— 参考了才说参考了，没参考绝不许说参考了。

## 四、判据与反向对照

| 判据 | 钉什么 |
|---|---|
| `verify_cards` **J15a** | 块里已有**短措辞** ⇒ 全卡恰好 1 条（今天的真形状） |
| `verify_cards` **J15a2** | 块里已有**长措辞** ⇒ 也恰好 1 条（两种措辞都要绿） |
| `verify_cards` **J15b** | 块里没有 ⇒ 必须补进来 1 条（不许丢链接） |
| `test_agent` **Z49f** | 报告「修改建议」≤30 字；整段长建议不许出现；不许挂「完整改法见…」 |
| `test_agent` **Z59** | 卡面与报告同一把尺（原断言是「报告 >60 字」，已按后令翻转） |
| `test_agent` **Z23 / Z26** | 出处标注仍在、且与事实一致；报告建议 ≤30 |

**反向对照（真造一遍）**：把信封两处判据改回
`.includes('查看完整问题清单与修改建议')` ⇒

```
❌ J15a 块里已有短措辞链接（→ 完整清单：）⇒ 全卡只许出现一次
     实际出现 2 次
```

恢复后 `verify_cards` **348/0**。这一条就是 Owner 那张卡的样子。

## 五、被自己的判据抓到的三处自身错误

1. **判据绑死措辞**：J15a 的夹具原来写的是长措辞，所以线上换了措辞它照样绿 ——
   判据喂的是想象的形状（与 `J13a3e` 的「（未填）」同一个错法）。
2. **Z23 抓到标注泄漏**：报告格压 30 字时把出处标注一起截进去了，等于把
   Owner 点名去掉的两句话又印回报告。
3. **Z55 夹具脆**：卡面的「原因/依据/建议」三格现在都压过了，往这三格塞长度**不会**
   让整条变长（实测 basisLine 加 48 字，读数一个字没动）⇒ 必须用**没有上限的 `location`**
   撑长度，否则「合计 >200 但每条不超」这个形状根本构造不出来。

## 六、边界

- 本件讲的是**渲染与判据**，不判任何素材能不能发。
- 历史存量报告**没有回改**：本件只改产者。
- §17 整卡字数 ≥3 档**仍然超**（`kb/l7/registry/prd17-limits.yaml::known_conflicts[C1]`），与本条无关。
- 「一张卡只有一条链接」不等于「链接一定点得开」—— 可达性是另一把尺。
