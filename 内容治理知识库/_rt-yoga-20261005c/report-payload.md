# 内容审查报告 ·【瑜伽球】广告洞察（rv-20261005-122829）

> **结论：`BLOCK`** —— 由评审链引擎 `with_kb_evidence.py` 产出（退出码 **0**｜置信度 **0.97**｜问题数 **9**）。
> **判定主体：`文案合规审查`**（本会话已用 skill 工具真加载，并以 `--loaded-skill` 申报 —— **agent 自述档，不得当强证据**）。
> 本件是**引擎结论的留痕与逐条归属裁定**，不是新结论；**不得**当作放行依据。

## 〇、先说清四件事，不藏

### 1）本单是同一送审物的第 4 次独立复跑，与前三次逐项一致

| 项 | 本单 | 前三次（其他会话，今日） |
|---|---|---|
| `review_id` | `rv-20261005-122829` | `rv-20261005-115806` ／ `rv-20261005-114430` ／ `rv-20261005-113729` |
| 层前置 BASE | `RT-20261005-YOGA-INSIGHT-R4` | `…-R3` ／ `…-R2` ／ `…`（同族） |
| 会话 | `session-5ed3514a-b2f8-4671-bd0d-618280061ede`（本会话） | 另三个会话 |
| 结论 / 置信度 / 问题数 | `BLOCK` / 0.97 / 9 | 三单同值 |
| 命中条款 | W-1.33 · W-1.26 · W-1.12 · W-1.22 · W-1.35 ＋ 4 条种子候选 | 同 |
| 表行 / 云文档 | `recvx97JtetXJO` ／ docx `E77od6tslo4q07xd6x6cT3osn7f` | `recvx905f4THZm` ／ `recvx8WEHBgeA2` ／ `recvx8VOBkqXju` |

冻结文本与其余三单**内容版本相同**（`content_version = cc5fcd8c…79e500`，飞书侧 `revision_id = 787`，四单一致）；
本单为**独立复算**，未复用任何前会话的结论件。

### 2）`BLOCK` 的唯一引擎依据，是一条**第三方引文**里的正则 token

引擎 `review_engine.decide()` 的 `BLOCK` 在本单只由一条 P0 命中支撑
（`kb/l7/review-engine/core/review_engine.py`：`confirmed_p0` 非空 ⇒ `BLOCK` / 0.97；
本单 `decision_trace.reasons = ["confirmed_p0"]`）。
而那条命中的实际位置是本文档**引用**的 FIT4MOM Instagram 帖文
（`@4951`：`"…it's also a **perfect** way to meet other moms…"`），语义与产品安全承诺无关；
引擎自己也已把它的引据标成**不可逐字回源**（reason 原文：「依据不可逐字回源：该说法为等价说法／正则命中，
源侧无逐字原文」）。

判定主体 `文案合规审查` 的正文有一条明确豁免：
**「Do not block a phrase merely because a token appears in a negation, warning, quote, or comparison.」**

⇒ 两者在本单**真的冲突**。按库内纪律**把冲突摆出来说**，不默默挑一个执行：

| 面 | 本单取值 | 理由 |
|---|---|---|
| **记录状态**（表行 / 报告抬头） | **`BLOCK`**（引擎原值） | **不做静默降级** —— 本库把「降级 / 漏放」列为最高风险方向（`report-output-contract.yaml` GAP-RO-4） |
| **可执行清单**（§七） | 由判定主体裁定 | 被引用第三方文案里的 token **不得**作为改写指令下发（专项正文的 quote 豁免） |

### 3）自命中核查在本单的结论是「**不成立**」

这是**负向结论**，同样按规矩①留痕（见 §三）。

### 4）本单**未拒答**、**未降级**

引擎正常出了三态结论（退出码 0），**没有**以「自命中 / 同源留痕 / 循环论证」为由改判「交人裁」或拒答。

---

## 一、送审物、本次可判边界与冻结输入

| 项 | 值 |
|---|---|
| 送审原话 | 「这个链接内容审核一下」 |
| 送审链接 | `https://my.feishu.cn/wiki/O0unwH2Cfi29ipk50u2cVdACnMc` |
| 文档 | **【瑜伽球】广告洞察** ｜ doc token `EdVPd3Y6PoIzULx08MJcPiVYnuh` ｜ `revision_id = 787` |
| 内容类型 | 广告洞察文档（竞品素材 + AI 拟定文案），**文字为主、跨模态** |
| 送审文本（本单冻结件） | `_rt-yoga-20261005b/yoga-text.txt`，**9,356 字**（去 `figure/source/img/sheet` 资源引用，**不改一字**） |
| `content_version` | `cc5fcd8c206f4988217af4ffe00d53e7976cdced1c2f053aee77f13f3f79e500` |
| `content_id`（引擎 JSON） | `AUTO-cc5fcd8c206f`（已知双 ID：表行 / 云文档用 `AD-20261005-011`，见 `GAP-RO-6`） |
| `review_id` | `rv-20261005-122829` |
| 渠道 / 产品线 / 版本 | 未指定 / 未指定 / v1.0（元数据自动化缺省，人工复核时补） |

**冻结口径（可复算）**：从 lark markdown 正文剥离媒体/结构引用（`<figure>/<source>/<img>/<sheet>` 与剩余 HTML 标签），
保留人类可读文字；脚本 `_rt-yoga-20261005b/extract.py`。已重取一次飞书原文核对：`revision_id` 仍 787、正文逐字节相同。

**文档里有什么**：① 竞品识别（Tridder / Babygo / FIT4MOM / Fridamom / NCT）；② **逐字引用的竞品文案**
（BABYGO、FIT4MOM 四条帖文、Fridamom/Amazon 帖文、NCT 帖文）；③ 中文分析文本；
④ **AI 拟定的 Momcozy Meta 广告脚本与两版广告文案（文案版本 A / B）**；
⑤ 内嵌媒体：**16 个视频 + 约 30 张图片**（竞品素材，均为 `token` 引用）、4 张内嵌电子表格。

**边界（本次不能判什么）**：内嵌 16 个视频与约 30 张图片**本体未到达本机**（仅 `token`，未下载未解码）
⇒ 逐帧画面、婴幼儿安全、隐私、AI 生成披露、第三方 IP **本次一律未判**；
4 张内嵌表格（`sheet-id` `Io65dm` / `DkCXpQ` / `Ak95sP` / `BSJLFn`）**内容未取**，
其中 `BSJLFn` 按正文就是那张「Momcozy 串联场景化 Meta 广告脚本」表 ⇒ **分镜逐条未判**。

---

## 二、两条硬规矩下的处置

| Owner 2026-10-05 规矩 | 本单处置 |
|---|---|
| ① 「自命中」是反面依据，**不是**拒答的理由 | **照办**：本单**没有拒答**，引擎出了三态 `BLOCK`。自命中核查**独立做过并如实报为「不成立」**（§三）。**未**以「自命中 / 同源留痕 / 循环论证」为由降级或拒答；本单也**不存在**可登记的 反例/禁区 findings |
| ② 每一个评审任务都必须落表并回读 | **照办**：写入 `RY2UbCRjXaeeWwscUPScVN5AnQc / tblCXPQVzfFWWCon`，新增行 `recvx97JtetXJO`，独立回读逐字段一致（§十） |

---

## 三、自命中核查 —— 结论：**不成立**（负向结论，随规矩①一并留痕）

规矩①的前提是「**在库里命中已定稿的反例 / 禁区条款**」（`polarity=反例`，或 `semantics` 以「禁区」开头）。
本单**独立查过**（本会话现算，不引用前会话结论），**没有命中**：

| 查了什么 | 怎么查 | 结果 |
|---|---|---|
| 库内共有多少条「反例 / 禁区」条款 | `kb/l4/canonical/*.jsonl` 按 `polarity=='反例' or semantics.startswith('禁区')` | **181 条**（`form` 全为 `sample_case`） |
| **与 181 条反例的字面重叠** | 规范化（NFKC + 去空白 + 小写）后字符 n-gram 逐条比对，n=14/16/20 | **n=16：0 条；n=20：0 条**。n=14 仅 **1 个**片段 —— `yourmotherhood`（泛用英文营销碎片，非本素材） |
| 最长公共子串 | 逐条对 181 条做「素材 ↔ 条款」最长公共子串 | 最大值 **14 字符**（S-1.3 / S-1.107，即上面那个泛用片段），次高 13；**无一条 ≥16** |
| 反向覆盖 | 素材里 **20 个 ≥18 连续中文字片段** grep 反例/禁区条款全量 | **0 个**出现在其中 |
| 行级 | 素材每一行（≥10 字）是否整行出现在任一 反例/禁区 条款 | **0 行** |
| 引擎侧 | L5 P0 匹配 + 规则层匹配 | 命中的 **5 条 KB 条款全部 `form=entry`、`polarity=None`**（措辞表达层边界规则），**无一条是 `反例` 或 `禁区`** |

⇒ **本单不存在「自命中」**，因此**没有**可登记的 反例/禁区 findings ——
既没有那样的条款号，也没有对应的 `anchor` / `source_sha256` / 逐字摘录可给（规矩①要求的四样**客观不存在**）。
⇒ 本次**未拒答**，也**未**以「自命中」为由降级。

---

## 四、引擎结论（唯一有权产出的那一份）

```
decision = BLOCK    confidence = 0.97    issue_count = 9
evidence_meta.state = BLOCK    findings = 5
decision_trace.reasons = ["confirmed_p0"]      ← decide() 的唯一 BLOCK 分支
layer_preflight.mode = enforced                ← 四层前置已核，非豁免
decision_owner.mode  = declared                ← 判定主体已申报（自述档）
publish.published    = true                    ← 表行 recvx97JtetXJO
```

- L5 P0 确定性匹配：**1 命中**（规则码 **H05**，模式 `\b(safest|perfect|zero[\s-]?risk|risk[\s-]?free)\b`，实际命中 `perfect`）。
- 规则层：命中 **6 条** KB 条款记录（其中 W-1.33 / W-1.26 / W-1.12 / W-1.22 / W-1.35 计为问题；W-1.30 / W-1.40 为边界/安全词记录）。
- 种子规则（`rule_engine.py` 5 条 US 种子）：**4 条 `uncertain` 候选**（均为 `best`），**非结论**。
- 覆盖信号：`covered = true`（命中允许表述/安全词规则）。
- 四层前置：BASE `RT-20261005-YOGA-INSIGHT-R4` ｜ **四道审计红 0 / 退出码 0**
  （L4 `kb-canonical-lookup` → L5 `kb-p0-check` → L6 `kb-recall` → L7 `kb-check`，逐层 RUN `<BASE>-L4…-L7`）。
  L4 / L5 / L6 各带 **1 黄 E5**（落章来自预演台账）⇒ 本单是**机制证据**，非落盘证据（§九）。

---

## 五、九条逐条归属裁定（**本件的主要价值**）

裁定口径 = 判定主体 `文案合规审查` 正文：token 落在**引用 / 否定 / 对照**里**不得**据此拦；
上下文改变语义时标 `uncertain` 并走 `REVIEW`。偏移量以**本单冻结文本**为准（长度 9,356，本会话现算）。

| # | 条款号 | 层 | 命中 token | 在文档里的**实际位置**（本单偏移） | 归属 | 能否作为改写指令 |
|---|---|---|---|---|---|---|
| 1 | **W-1.33** | P0·block | 正则 `\b(safest\|perfect\|zero[\s-]?risk\|risk[\s-]?free)\b` | `@4951` FIT4MOM **引用帖文**：「it's also a **perfect** way to meet other moms」 | **第三方引用**，且与产品安全**无关** | **不能** —— 且引擎自标引据不可逐字回源 |
| 2 | **W-1.26** | P1·review | `乳房胀痛` | `@5923` **描述 Fridamom 素材**的生理细节（分析文本） | **第三方引用 / 描述** | 不能（且 W-1.26 自述「需人工判定」） |
| 3 | **W-1.12** | P1·review | `超级` | `@8781` **本文件自有文案 A**：「产后身体敏感，需要**超级**柔软的支撑？」 | **本文件自有** | **超条款范围** —— W-1.12 边界是**吸力夸大**（`super strong/超强/极致/…`），此处指柔软度 |
| 4 | **W-1.22** | P1·review | `完美` ×6 | `@1748 / @2147 / @2545 / @5848 / @6441` 分析文本；`@8704` **自有文案的否定式**「我们**没有**完美无缺的模特」 | 分析文本 + **否定式** | 不能（否定式豁免） |
| 5 | **W-1.35** | P1·review | `hospital` | `@6679 / @6747` Fridamom/Amazon **引用帖文**：「at the **hospital** … hospital bag」 | **第三方引用** | 不能 |
| 6–9 | （无） | P1·uncertain | `best` ×4 | `@332` BABYGO 引用「**Best** birthing ball on the market!」／`@1533` NCT 引用「**best** practice」／`@5032` FIT4MOM 引用「our **best**」／`@6902` Amazon 引用「**best**sellers」 | **全部第三方引用** | 不能 —— 且 W-1.22 / W-1.33 明写 **`best`/`#1`/`No.1` 排名最高级按 2026-09-09 口径已放开，不再判险** |

**结论**：9 条里 **8 条落在第三方引用 / 分析文本 / 否定式**上，第 9 条（`超级`）**超出其条款声明的适用范围**。
⇒ 引擎的 `BLOCK` **不能读成「本文件自有文案已确认违规」**；其唯一 P0 依据是一条**引文内的正则 token**。

---

## 六、依据侧四段溯源（谁能核到哪一层）

| 条款号 | L4 `anchor` | L3 规则码 / rule_id | L1/L0 `source_sha256` | L0 逐字核对 |
|---|---|---|---|---|
| W-1.33 | `#广告文案明细/recvuJYdOb1B8v/命中片段` | H05 ／ `r-7baf7ceb47b2e5bc` | `e7aabf7478753887ea85470fa114b4d0b22d74d21cb901b3a02e7672dff4f4c5` | `recvuJYdOb1B8v`｜**不一致 ❌**：摘录是**正则**，L0 字段值只有 `H05:perfect pump` |
| W-1.26 | `#品线内容边界规则库/recvuMNZc45BSy/边界内容` | U04 ／ `r-5c056bc02cdd770c` | `8d94242a1fdbe4dbb16481ef4ad72aeda3d555a6e47a53d1e8cddc62c254f367` | `recvuMNZc45BSy`｜逐字命中 ✅（`…, 乳房胀痛, 乳房疼痛`） |
| W-1.12 | `#品线内容边界规则库/recvuJP1LVe2xP/边界内容` | M02 ／ `r-252ba6cf5ee92b00` | `a240aa6a49af138054084674abb583e90b40090afc5fefc550aecb5b9537dc05` | `recvuJP1LVe2xP`｜逐字命中 ✅（`…, 超级`） |
| W-1.22 | `#品线内容边界规则库/recvuJP1dDumuM/边界内容` | H05 ／ `r-3b6c3c82dc667295` | `1c61c44b09ff77d121546f5ec15f74eba03afda2b77c1c77eb70b1e7525337fb` | `recvuJP1dDumuM`｜逐字命中 ✅（`…, 完美, …`） |
| W-1.35 | `#广告文案明细/recvuJYdObBgjg/命中片段` | U03 ／ `r-85348bba00a2b5a7` | `1ca01a6690922a697e9d428439674863df67709688a6b32fe846705603f5e011` | `recvuJYdObBgjg`｜逐字命中 ✅（`… / U03:hospital`） |
| —（6–9） | — | 种子规则（`rule_engine.py`） | — | **无 KB 依据**（`uncertain` 候选，非结论） |

- **sha 措辞红线**：上表 sha 一律是「**与 L0 记录值比对一致**」，**不是重算** ——
  L0 的 sha 输入是 `record_fields` 字段 blob，本地 L0 件**不含**该 blob；要真核对只能点下面的 L0 直链。
- L0 直链（飞书侧原始记录，`kb/l0` 的 `entry_url`）：
  - W-1.33：`https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdOb1B8v`
  - W-1.26：`https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblD1MiUK1v5fdjD&record=recvuMNZc45BSy`
  - W-1.12：`https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblD1MiUK1v5fdjD&record=recvuJP1LVe2xP`
  - W-1.22：`https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblD1MiUK1v5fdjD&record=recvuJP1dDumuM`
  - W-1.35：`https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdObBgjg`

---

## 七、对本文件**自有文案**的可执行清单（判定主体裁定）

真正会被复用到投放的是「AI分析可应用2」的**文案版本 A / B** 与那张脚本表。按现有证据：

| # | 自有文案原文（逐字） | 命中的条款 | 处置 |
|---|---|---|---|
| A-1 | 「半夜**漏奶**和**疼痛**，让你心力交瘁？**搞定！**」 | **W-1.26**（疼痛/堵奶场景化名词表述：**需人工判定**是痛点场景描述还是功效承诺；**与 goodbye/no more/relieve 等消除性表述连用应升级 H01/H07**）。「搞定！」即消除性表述 | **REVIEW → 交人裁**：由业务 / 医学顾问判「痛点场景」还是「功效承诺」；若为后者，按 W-1.17 / W-1.35 的处理口径改写 |
| A-2 | 「别让**产后焦虑**消耗你！」 | **知识库查不到**（`产后焦虑` 在 `kb/l4/canonical` 0 命中） | **不得**由常识补 —— 标 REVIEW，请医学顾问判是否构成健康状态宣称 |
| A-3 | 「产后身体敏感，需要**超级**柔软的支撑？」 | W-1.12（边界 = **吸力**夸大） | **超范围**，不作为指令；但如渠道另有绝对化口径，交渠道复核 |
| B-1 | 「让你在清晨**多睡一小时**的免提神器。」 | **知识库查不到**（效果类具体数值，无对应条款） | 标 REVIEW：具体数值型效果声称需给测试来源与口径，否则删除或改为非量化表述 |
| B-2 | 「Motherhood's better with a plan (and a comfy bra).」 | — | 未命中，**未命中 ≠ 合规** |

⇒ **自有文案侧没有任何一条能支撑 `BLOCK` 级动作**：A-1 的条款（W-1.26）**自述「需人工判定」**，A-2 / B-1 查不到条款。
⇒ 但自有文案侧也**拿不到 `PASS`**：文案面向美区 Meta，**渠道未指定、产品线 / SKU 未指定**，且 A-1 / A-2 / B-1 三项待人工判。

---

## 八、覆盖缺口（如实列）

1. **16 个视频 + 约 30 张图片未取本体**（仅 `token`）⇒ 视频 / 图片专项**一项未跑**（画面安全、婴幼儿、隐私、AI 披露、第三方 IP）。
2. **4 张内嵌表格未取**（含 `BSJLFn` = 拟定的 Meta 脚本表）⇒ 分镜脚本未审。
3. **渠道未指定** ⇒ 渠道特有条款未叠加（现状按通用口径）。
4. **产品线 / SKU 未指定** ⇒ 未与 SKU 事实库比对，A-1 / A-2 / B-1 的宣称**无事实层核对**。

---

## 九、边界与如实声明

- **本单未落盘，是机制证据**：四层前置以**预演档**跑（全程无 `--apply`），L4 / L5 / L6 各带 1 黄 **E5**；
  四道审计**红 0**、退出码 0 ⇒ 只能读成「逐层调用机制通了」，**不能**读成「这些层真落盘过」。
- 判定主体 `文案合规审查` 的加载是 **agent 自述档**（`--loaded-skill` 申报），**不得当强证据**。
- 全程**未写库**（未加 `--apply`），未改 `kb/l0…l7` 任何数据；飞书写入只发生在**登记表行 + 云文档**（§十），
  那是**填写动作**，不是 KB 写库。
- 第五、七节的归属裁定是**判定主体（人侧口径）的判断**，不是引擎产出；引擎产出的是**未加归属的 token 命中**。
- 本件结论 `BLOCK`，**不是** PASS / REVIEW；`BLOCK` 的**唯一**引擎依据是引文内一条正则 token（§〇.2）。
- **本单复现并沿用已登记的引擎缺口 `GAP-QUOTE-1` / `GAP-SELFHIT-1`**：
  `decide()` 的 `confirmed_p0` 不区分「命中落在品牌自有文案」还是「落在文档引用的第三方文案」，
  且不因 `unmet_citation` 降级 ⇒ 对「研究 / 洞察类文档」会产出**引文误报型 BLOCK**；
  同时评审引擎对「已定稿反例/禁区」**没有消费者**。
  **只登记，不修**（未获判定为缺陷前不动 `decide()`）。
- **重复落表观察（如实报）**：同一送审物今日已由另三个会话各写一行（`AD-20261005-004` ×2、`AD-20261005-007`），
  本单按 `conclusion-destination.yaml`「每次审查新增一行」口径再写一行 `AD-20261005-011`。
  该表内因此存在 **4 行同内容、2 种内容 ID 形态**（`AUTO-…` 引擎侧 / `AD-…` 发布侧），
  属已登记的 `GAP-RO-6`（业务编号规则未定），**不是本单新引入**。

---

## 十、飞书落表（Owner 规矩②）与独立回读

去向：`RY2UbCRjXaeeWwscUPScVN5AnQc` / `tblCXPQVzfFWWCon`（与 `kb/l7/registry/conclusion-destination.yaml` 登记一致）。

| 字段 | 值 |
|---|---|
| 内容 ID | `AD-20261005-011` |
| 产品线 / 渠道 / 内容类型 / 送审版本 | 未指定 / 未指定 / 广告洞察文档（竞品素材+AI拟定文案） / v1.0 |
| Agent 结论 / 置信度 / 问题数量 | `BLOCK` / 0.97 / 9 |
| 问题分类汇总 | 绝对化与安全承诺-虚假安全承诺 2；功效宣称-疼痛功效承诺 1；绝对化与安全承诺-绝对化性能表述 1；背书与资质-医疗场景宣称 1；Absolute or ranking claim requires context and proof 4 |
| 报告链接 | https://momcozy-in.feishu.cn/docx/E77od6tslo4q07xd6x6cT3osn7f |
| 状态 | `BLOCK` |
| 送审问题 | 这个链接内容审核一下 |
| record_id | `recvx97JtetXJO`（**新增一行，非 upsert 覆盖**） |
| 写入时间 | `2026-10-05T12:28:36+08:00` |
| 身份 | `--profile dsh-kb --as bot` |
| 独立回读 | ✅ `base +record-get` 逐字段核过（内容 ID / 结论 / 置信度 / 问题数量 / 内容类型 / 渠道 / 产品线 / 版本 / 报告链接 / 状态 / 送审问题 均对上）；`_rt-yoga-20261005c/readback.json` |
| 人工复核人 / 复核结论 / sign-off 人 / 发布时间 | **留空**（人工字段，等复核填写） |

### 两条硬规矩回执

| 规矩 | 回执 |
|---|---|
| ① 「自命中」是反面依据，不是拒答理由 | **不适用（自命中不成立）**：独立核查见 §三；本单**未拒答**（引擎出 `BLOCK`，退出码 0），**未降级**。 |
| ② 每个评审任务必须落表并回读 | **已照办**：新增行 `recvx97JtetXJO`，`base +record-get` 逐字段回读一致。 |

---

> 结论由引擎 `with_kb_evidence.py` 产出；条款号 / `anchor` / `sha256` / L0 直链均取自引擎输出与 `kb/l0`、`kb/l4` 落盘件，**未手写**。
> 第五、七节的归属裁定由判定主体 `文案合规审查` 给出，已与引擎原值并列留痕；两处冲突已按库规显式摆出（§〇.2）。
