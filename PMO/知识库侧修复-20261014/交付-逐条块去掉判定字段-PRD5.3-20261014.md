# 交付 — 逐条块去掉「判定」字段（按 PRD §5.3，文案/图片/视频一律）· 2026-10-14

> **Owner 原话**：「按照 prd 5.3 要求，输出的字段是没有『判定：REVIEW』，只有【审查结论：REVIEW】。
> 修改所有的落库规则去掉『判定』这个字段，包括文案/图片/视频，修复后落库，其他不动。」
>
> 三问三答落定的口径：**① 两条路都不再输出任何「判定」行**（含逐条里的 `判定：事实/推断`）
> ｜ **② 授权改守衡仓** ｜ **③ 只重渲染原地覆盖，不重跑审查**。

---

## 一、为什么该删（PRD 逐字，不是我的判断）

`kb/.work/prd.md` 的 §5.3.2 / §5.3.3 模板（第 169–243 行）里，逐条块**只有三个字段**：

```
1.【合规-医疗宣称】视频 00:12 字幕"治疗堵奶"涉嫌医疗宣称。
  原因：母婴内容不得出现治疗、治愈等表述。
  依据：《合规措辞库 v1》第 3.2 条（链接：https://...）
```

三态**只出现在结论行** `【审查结论：REVIEW】共发现 N 处需人工确认。` 这一处。
逐条块里再挂一个「判定」，同一张卡上就出现**两个「判定」**：一个是三态、一个是「事实/推断」，
业务侧分不清哪个是结论 —— 这正是你截图里那处。

★ 顺带纠一个前提：`kb/l5/p0_fastpath.py` 里还有一格叫 **`判定对象（逐字）：…`**，
它说的是「这一单审的是哪段素材」，**不是三态结论**，与本次裁定无关，**没动**。

---

## 二、改了哪些「落库规则」（产出侧，两仓同批）

| # | 文件 | 改法 |
|---|---|---|
| 1 | `kb/l7/review-engine/core/review_engine.py` | `render_summary()` 的逐条渲染删掉 `**判定**：{fact}｜置信度：{conf}` 一行。**取值一个字节没动**：`fact_or_inference` / `confidence` 仍随 `risk_items` 进 JSON 与台账 |
| 2 | `kb/l7/skills/kb-content-review/scripts/review.py` | 回执版式、报告版式各删一行 `判定：…｜置信度：…`（两处） |
| 3 | `kb/l5/p0_fastpath.py` | `_prd_block()`（回执）与 `_doc_block()`（云文档）各删一行；`_item_fields()` 里 `verdict` 那一格**整格去掉**（`grep verdict` 证实**没有任何下游读它**，只被这两个渲染点读） |
| 4 | `kb/l7/review-engine/core/with_kb_evidence.py` | 覆盖缺口说明里那句 `判定：REVIEW（**不是 PASS**）` 删掉。该单结论仍是 REVIEW（抬头 `【审查结论：REVIEW】` 就是它）；`state` / `issue_count` / `severity` / `fails_closed` **一字未改** |
| 5 | **守衡仓** `tools/agent/dual_track.mjs` | ① `renderMergedItem()` 的补充行 `**判定**：${verdict}` 删掉 —— **这一处同时管卡片与报告**（`merged_report.mjs` 的逐条也调它）｜② `renderMerged()` 拒答支路的 `判定：REVIEW` 删掉（那一支抬头本来就是 `【审查结论：NEEDS_INPUT】`，一卡两个三态在互相打架） |
| 6 | 模板与夹具 | `kb/l7/output_template.md`、`kb/l7/selftest_a_block.md`、守衡 `dual_track.mjs` 自证夹具 3 处、`tools/verify_cards.mjs` J11 夹具 |

**守衡已重启**（`launchctl kickstart -k gui/<uid>/com.shouheng.lark`，新 pid 83372 起于 14:11:07，
**晚于** `dual_track.mjs` 最后修改 14:03:39）⇒ 新渲染器已在线上生效。

### ★ 顺带修掉一处**寄生判据**（这个洞是本次才暴露的）

`tools/test_agent.mjs` 与 `tools/verify_cards.mjs` 原先拿
`/^ *\*{0,2}判定\*{0,2}：/gm` **当"条目数"计数器**用 —— 因为逐条块里 `**判定**：` 恰好**每条一次**。
它量的不是「有几条问题」，而是「有几行某个字段」。**字段一删，这些判据会静默数出 0 条**，
红的原因会变成「计数器坏了」而不是「条目少了」—— **红得对不上病**。

⇒ 新增 `dual_track.countRenderedItems()`（数逐条块**行首编号**，与排版无关），**8 处计数点全部改用它**。

---

## 三、判据：每一处删除都配了**反向对照**

只写「删掉了」不叫修好 —— 没有失败信号，谁把它加回来都不会红。所以同批补了：

| 文件 | 新增判据 |
|---|---|
| `kb/.work/l7_integrity.py` | ① `夹具里不再有 判定 行` ② `BLOCK 逐条块无 判定 行`（查**引擎真产出**，非夹具） |
| `kb/l5/p0_fastpath.py` | 自证 ④ 加一条：逐条块里一旦再冒出 `^\s+\*\*判定\*\*：` ⇒ **精确变红** |
| 守衡 `tools/test_agent.mjs` | W9 加**打在生产者的**反向对照：真调 `renderMerged` 渲染一次，断言无该行 |

★ 两条既有判据同步**收窄**（不是放宽）：`l7_integrity` 的 `逐条分流(1-2)` 补充行白名单
只认 `锚点`/`source_sha256`；`逐条块含引用三要素`→`两要素` —— 它原先把
`判定：…置信度：` 当成引用契约的一部分，而那**不是**引用契约要的东西（要的是 锚点 + source_sha256）。

### ★ 一处坦诚的自我更正

W9 那条反向对照**第一版是错的**：我写成「查搬进卡片的那段正文」，结果**当场红**。
红得对：那段正文是**链的老输出原样搬过来的**，里头本来就带 `判定：`（夹具故意留的，
验的是「旧格式仍搬得动」），而**搬运动作不许改字**。
⇒ 要钉「新格式没有它」，必须**真渲染一次**。查搬运结果 = 禁止搬运保真，是拿错的尺子量对的东西。
已改成调 `renderMergedItem`。

---

## 四、落库产物：原地覆盖（**没有重跑任何一条审查**）

### 4.1 飞书云文档 —— 78 份、删 314 处

先量后改：按采集表 80 行的「报告链接」取到 **78 个不同 doc token**，逐份 fetch 后
**78/78 都带** `判定：` 字段（共 **324 处**）。

改法 = **机械化删段，不是重渲染**：

```
lark-cli docs +update --as bot --profile dsh-kb --doc <token> \
  --command str_replace --pattern "<b>判定</b>：REVIEW" --content ""
```

★ 为什么必须用**最窄**的模式：我第一版把两侧的 `<br/>` 一起删（想顺手不留双换行），
**实测会吃掉下一个字段的 `<br/>`** ⇒ `建议` 跟 `依据` 粘到同一行。
机械删段的铁律：**只删要删的那几个字，别碰邻居**。

每份改前原文存 `PMO/shouheng-state/_fix-doctors-20261014/<token>.before.xml`，
改后存 `.after.xml`，逐份读数存 `report.json`（**可回滚、可对账**）。

**复核（改完逐份真读回来，不是看日志）**：

| 检查项 | 结果 |
|---|---|
| 云文档残留 `判定：` | **0 / 78** |
| 逐条条数 = 删前（逐份比对） | **78 / 78 一致** |
| 超链接数 = 删前（逐份比对） | **78 / 78 一致**（合计 175 个） |
| 结论行 `【审查结论：` 仍在 | **78 / 78** |

### 4.2 本机留底 —— 276 份、删 1262 行

`PMO/shouheng-state/merged-reports/` 里 280 份留底，**276 份**含该行（共 1262 行）。
同一把尺子机械删行，改前全部备份到 `_fix-doctors-20261014/merged-reports-before/`，
逐份 sha256 存 `merged-reports-report.json`。

复核：残留 **0 / 280**；含 `【审查结论` 的 **280/280**；含 `**原因**`/`**依据**` 的 **271 份**
（另 9 份本来就没有逐条块，是拒答单/汇总单）。

★ `.md` 走的是「先写 `.swtmp` 临时件 + 改名」的通道，**没有用 python 直写 `.md`**
（直写会让宿主侧多读 4096 字节）；`kb/l8/envelope_census.py` 跑完 **结论：OK**。

### 4.3 表行 —— **一个字都不需要改**（先量过，不是推测）

我按「**行首的 `判定：` 字段**」逐格扫了两张表（`--as bot` 直读）：

| 表 | 行数 | 含行首 `判定：` 字段的行 |
|---|---|---|
| 采集表 `tblavfbMDMeRsulo` | 80 | **0** |
| 结论表 `tblCXPQVzfFWWCon` | 200 | **0** |

⇒ 落表那一列本来就是 `evidenceBlock` 的 `【逐条依据（落库留痕）】`（只有 类别/位置/原因 → 依据），
**从来没有过这一格**。所以「修复后落库」这一步落的是**云文档**，表行无需改、也**没动**。

（旁证：`grep 判定` 在这两张表里各有 60 / 86 行"命中"，但逐条看全是
「覆盖**判据**不成立」「未能得出结论」这类**词内巧合**，不是字段。）

---

## 五、闸门与自证（全量复跑）

| 闸门 | 结果 |
|---|---|
| 引擎 pytest（`kb/l7/review-engine/tests/`） | **101 passed** |
| `kb/l5/p0_fastpath.py --selftest` | **通过 39 / 失败 0**（含新增反向对照） |
| `kb/.work/l7_integrity.py` | `template_conformance` **PASS** ｜ `template_from_engine` **PASS** |
| `kb/l8/workflow_smoke.py` | **exit 0 —— 契约齐**（S1/S2/S3/S4/S5/S7 全绿） |
| 守衡 `dual_track --selftest` | **93/0** ＋ 抽取自证 **37/0** |
| 守衡 `verify_cards.mjs` | **通过 304 · 不通过 0** |
| 守衡 `test_agent.mjs` | 通过 218–220 / 失败 1–3 —— 见下 |

### 未通过的三条：**逐条定性，都不是本次改动引起的**

| 失败项 | 定性 | 依据 |
|---|---|---|
| `真实群里用户消息解析出姓名` | **环境/数据**，与本次无关 | 真打飞书群取 20 条历史；实测 `listMembers` 正常返回三人（刘华丽/李倩怡/周健），是**历史消息里某条发送者不在当前成员表** ⇒ 解析出空串。改动前就红 |
| `search_workspace 找得到那个 token` / `0 命中必须带分母` | **测试自身的前提被环境撑破** | 报错逐字：「到 **5000 个文件上限**就停了，还有没走到的地方…已扫 5000 个、跳过 1298 个」⇒ 该测试要求「整仓检索不被截断」，而**仓已超过它的上限**。与 `判定` 字段无关（它只是次数在不同运行间**时红时绿**） |

★ 我**没有**为了让它们变绿去改这两个测试 —— 那是拿错的尺子量对的东西。

---

## 六、边界（哪些**没**动，以及为什么）

- **没有**重跑任何一条审查、**没有**新增/删除任何表行、**没有**改任何结论（三态、问题数、置信度全程未变）。
- **没有**改飞书侧源（入口 Base / 文案风控库 / 外部资料库 / 内容公式库 / PRD）—— 只写了我们自己产出的云文档。
- **没有**回改已经发出去的**历史群消息**（那是留痕，不是产物；改了等于篡改记录）。
- 守衡 `review_publish.mjs::conclusionOf` 的认读清单里**保留** `判定：X` —— 那是**读旧回答的兼容**
  （历史卡片 / 重放 / 老补发队列），删了会让存量数据抽不出结论。已登记进 `report-output-contract.yaml`。
- `fact_or_inference` / `confidence` 这类**数据**仍在 JSON/台账里（只改了**版式**，没删数据）。

## 七、回滚路径

```bash
# 云文档：逐份拿改前原文重放
node tools/_fix_remove_verdict_20261014.mjs --tokens <token文件> --apply   # 脚本在同目录留了 .before.xml
# 本机留底：直接拷回
cp PMO/shouheng-state/_fix-doctors-20261014/merged-reports-before/*.md PMO/shouheng-state/merged-reports/
# 代码：两仓各自回退本次 6 个文件的改动（kb 侧 4 个 .py/.md + 守衡侧 2 个 .mjs + 2 个测试件）
```

## 八、复现命令

```bash
# 1) kb 侧
cd <内容治理工作区>
python3 -m pytest kb/l7/review-engine/tests/ -q
python3 kb/l5/p0_fastpath.py --selftest
python3 kb/.work/l7_integrity.py
python3 kb/l8/workflow_smoke.py

# 2) 守衡侧
cd /Users/lute/Project/audit_multi_content
node tools/agent/dual_track.mjs --selftest
node tools/verify_cards.mjs
node tools/test_agent.mjs

# 3) 落库产物复核（真读回来）
node tools/_fix_remove_verdict_20261014.mjs --tokens <token文件>     # 不带 --apply = 只量不改
```
