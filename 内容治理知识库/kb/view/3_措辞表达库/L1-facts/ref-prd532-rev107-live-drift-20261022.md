---
asks:
  - PRD §5.3.2 现在（2026-10-22）到底有几行、每行写什么、SUGGEST 在哪一格
  - rev107 与 rev101 的逐字差是什么（列头、行数、PASS/REVIEW/BLOCK 定义）
  - 为什么 prd532_check 在远端已经漂到 rev107 时仍然报 PASS、退出码 0
  - 这轮把真源、判据、闸门各改成了什么（A1b/A2d/A9b 与 --live）
  - 远端漂移现在由谁在跑、跑不到时算什么（未测 ≠ 通过 ≠ 红）
  - SUGGEST 究竟是不是 decision 的取值、四个统计桶怎么算
  - 怎么用真历史数据做反向对照（指向 rev101 快照会红哪几条）
  - 还有哪些没落（四桶统计、回归集期望态、结论行前缀、守衡跨仓）
  - PRD 自身还剩哪条内部冲突（三态/四态混用，S2）
collection: 3_措辞表达库
corroborated_by:
  - 飞书 sheet xcdTpv rev107（快照 _prd-20261022/sheet-xcdTpv-rev107.json，2026-10-22 16:40 直拉远端 A1:D4）
  - 飞书 docx PXfBdjTwFokEQixtmTscqm7knNh raw_content（快照 _prd-20261022/prd-raw_content-20261022.txt：§5.3.2「SUGGEST 规则」、§5.3.4「PASS + SUGGEST」样张、§17 空节）
  - kb/l7/registry/prd532-states.yaml ＋ kb/l8/prd532_check.py（rev107 真源、A1b/A2d/A9b/--live 与 25/0 自证）
created_at: 2026-10-22
data_level: L2
evidence_group: rule
evidence_level: L2
forbidden:
  - 不许把「四态」读成 decision 四值（rev107：三个主状态 ＋ 一个标签 ＋ 四个统计桶）
  - 不许把 SUGGEST 写回 states（它连一行都不是，只在 PASS 的附属信息格里）
  - 不许用本条替代 PRD 原文（sheet xcdTpv rev107 / docx PXfBdjTwFokEQixtmTscqm7knNh）
  - 不许声称 prd532_check 快照模式的绿等于「跟今天的 PRD 一致」（要 --live 才算）
  - 不许把「拉不到远端」写成通过（那是未测）
half_life_days: 180
id: ref-prd532-rev107-live-drift-20261022
kb_class: []
kind: fact
not_proves: 不能证明 rev107 是定稿 —— 它只是 2026-10-22 16:40 那一刻的远端读数，下一次改版要靠 prd532_live 去发现；不能证明四桶分布已能算出来（bitable_stats.py:107 仍是 TRI_STATE，SUGGEST 样本 0 条）；不能证明守衡侧已按新口径同步（本轮只读那个工作区，prd53.mjs 仍含 SUGGEST ⇒ 只报跨仓待同步、不判红）；不能证明 PRD 已改齐（§6.3「汇总四态结论」、§11.1「整体四态准确率」与 §10.1 三值/§11.2 三态一致数仍并存，改动权不在我方）；不能替代 PRD 原文（docx PXfBdjTwFokEQixtmTscqm7knNh / sheet xcdTpv rev107）；不能证明需求方已验收「三值＋标签」这个读法 —— 它证明的是 PRD 原文现在这么写、且两侧代码与判据按它落地。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为 PRD 口径、sheet 与 docx 的 token、代码路径与实测读数；未引用人名，sign-off 责任人一律写成占位
provenance:
  anchor: 交付-PRD532-rev107远端漂移与判据-20261022.md#二、rev 107 与 rev 101 的差（逐字）
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-22
  fingerprint: 1b75a4bca8bd7a94
  kind: file
  ref: /Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/交付-PRD532-rev107远端漂移与判据-20261022.md
summary: 2026-10-22 16:40 直接拉远端：PRD §5.3.2 内嵌表 sheet xcdTpv 已是 rev107 —— 表头改「主状态/定义/附属信息/动作」，只剩 PASS/REVIEW/BLOCK 三行，SUGGEST 不再占行、只作 PASS 的「附属信息」；正文新增「SUGGEST 规则」两行。库侧真源与判据当时仍停在 rev101，而 prd532_check 报「PASS 六处一致」退出码 0 —— 因为 A2c 比的是两个本地文件（真源 revision vs 当天快照），一起陈旧就互相印证。本轮把真源升 rev107、判据改成「主状态=三行 + SUGGEST 不许进 states + 附属信息列逐字 + PASS 附属信息必须含 SUGGEST」、新增 --live 远端比对并挂进 ci/run_gates.py 的 prd532_live（真触发者＝每日 14:00 的 com.kb.gates）。读数：快照模式 PASS、--live PASS(source=live)、--selftest 25/0、run_gates 2/2、owner_locks 45/45；反向对照用真历史数据（指向 rev101 快照）红 10 条。引擎/渲染/落表一行未改。
supersedes: ref-prd532-suggest-as-pass-label-20261019
tier: L1
title: PRD §5.3.2 rev107（2026-10-22 实测）：SUGGEST 从「一行」降成 PASS 的一格 —— 真源升版、远端漂移闸、以及旧判据为什么恒绿
topic: 知识
valid_until: 2027-04-20
---

## 一、这条讲什么

2026-10-22 核对「知识库对 PASS / PASS+SUGGEST / BLOCK / REVIEW 怎么定义、跟 PRD 一致吗」时，
照旧先读真源，再**直接拉了一次远端**。远端与库里的字面不一致：

- 库（真源 `prd532-states.yaml`）：**rev 101**，表是「状态 / 定义 / 系统流转动作」**四行**，SUGGEST 占一行；
- 远端（sheet `xcdTpv`）：**rev 107**，表是「**主状态** / 定义 / **附属信息** / **动作**」**三行**，
  SUGGEST **不占行**，只出现在 PASS 的「附属信息」格：`可附带 SUGGEST（如措辞优化建议）`。

口径本身没变（三值 ＋ 一个标签 ＋ 四个统计桶），**变的是它写在哪**：从「一行」降成「一格」。

## 二、逐字读数（2026-10-22 16:40 +0800）

| 行 | 主状态 | 定义 | 附属信息 | 动作 |
|---|---|---|---|---|
| PASS | 未发现已知底线风险，或仅有无伤大雅的错别字。 | 可附带 SUGGEST（如措辞优化建议） | 转 sign-off / brief 提交方；SUGGEST 提示内容方参考 |
| REVIEW | 存在边界模糊、需专业判断的问题（如医疗暗示、复杂场景安全）。 | 可附带具体风险点 | 转法务/医学/专家/北美复核 |
| BLOCK | 命中明确红线（P0 级），或 P1/P2 中证据确凿的违规。 | 可附带修改建议 | 返回内容方修改后重新提交 |

正文（docx raw_content 第 170–172 行）另有「SUGGEST 规则」两行：

> 仅由 P3 层级（措辞与表达）或 P2 中轻微瑕疵触发。
> 飞书/系统回复时，在 PASS 结论下单独列一段“优化建议”。

docx 读数：7303 字 / 16523 B / `sha256=969d3d89…`，版本行 v1.4；
另注：§5.3.4 已改成「PASS（≤50字）／**PASS + SUGGEST（≤150字）**」两档样张，**不再有 `【SUGGEST】` 结论行**；
§17「附录：结论模板速查」现在是**空节** —— 也就是 10-19 登记的 PRD 内部冲突 S1，PRD 侧自己修掉了。

## 三、rev107 与 rev101 的差

| 项 | rev 101 | rev 107 |
|---|---|---|
| 列头 | 状态 / 定义 / 系统流转动作 | 主状态 / 定义 / 附属信息 / 动作 |
| 行数 | 4 行（含 SUGGEST） | 3 行 |
| PASS 定义 | 未发现已知底线风险。可包含 SUGGEST 建议。 | 未发现已知底线风险，或仅有无伤大雅的错别字。 |
| REVIEW 定义 | 存在边界模糊、需专业判断的问题。 | …（如医疗暗示、复杂场景安全）。 |
| SUGGEST | 自己一行，动作「随 PASS 一起流转」 | 只在 PASS 的附属信息格里 |

## 四、为什么旧判据没发现（这条比漂移本身更值得记）

`prd532_check` 的 A2c 比的是**两个本地文件**：

```
真源 meta.revision(=101)  vs  _prd-20261019/sheet-xcdTpv-rev101.json 的 revision(=101)
```

两个一起陈旧 ⇒ 互相印证 ⇒ 恒绿。实测：远端 107，闸门仍打印「PASS（三值＋标签＋四桶 六处一致）」、退出码 0。

10-19 那轮已经意识到「真源与快照一起陈旧」，但把报警器装在了**两个快照之间**，没装到**上游**。
一个会过期的读数，没有任何东西在它过期时变红 —— 这就是它。

## 五、本轮改了什么

- 真源：`kb/l7/registry/prd532-states.yaml` 升 rev107，`states` 三行 ＋ `attached` 列；
  新增 `suggest_rule`、`meta.revision_history`（96/101/107）、`drift_guard`；
  `label_semantics.label_not_a_row: true`；S1 标 `closed_by_rev107`（附现场证据）、S2 标 `open`。
- 判据：`kb/l8/prd532_check.py`
  A1 主状态=三行；**A1b SUGGEST 不许出现在 states 里**；A3b `attached` 非空；
  A2 逐字核「定义/附属信息/动作」三列；**A2d PASS 附属信息必须含 SUGGEST**；A9b `label_not_a_row` 为真；
  **新增 `--live`**：把远端表喂进同一套逐字与 revision 核对，拉不到记「未测」。
- 闸门：`ci/run_gates.py` 新增 `prd532_live`（core、非阻断）；真触发者＝每日 14:00 的 `com.kb.gates`。
- 快照：`_prd-20261022/`（远端表 ＋ docx 正文逐字）。

**引擎、渲染、落表一行未改**：rev107 与 rev101 在代码口径上是同一件事。

## 六、读数与反向对照

| 项 | 读数 |
|---|---|
| `prd532_check`（快照） | PASS，revision {registry:107, sheet:107} |
| `prd532_check --live` | PASS，`source: live` |
| `prd532_check --selftest` | 25 / 0 |
| `run_gates --only prd532 prd532_live` | 过 2/2，告警 无 |
| `owner_locks_check` | 45 条修复 45 条挂锁，全绿 |

反向对照用**真历史数据**：把 `KB_PRD532_SHEET` 指向 rev101 那份快照 ⇒ 退出码 3、红 10 条
（A2a 四行不同集 / A2a2 SUGGEST 又占一行 / A2b 三态定义与附属信息 6 条 / A2d 无 SUGGEST / A2c 101≠107）。

## 七、还没落

四桶分布（`bitable_stats.py:107` 仍 `TRI_STATE`）／回归集三态期望与 SUGGEST 样本 0 条／
结论行前缀 `【审查结论：X】` vs PRD 的 `【PASS】…`／守衡侧 `prd53.mjs` 词表（跨仓待同步，不判红）／
PRD 自身的「三态 vs 四态」混用（S2，走反馈单）。

## 八、复现

```bash
cd "<库根>"
sh kb/kbpy l8/prd532_check.py
sh kb/kbpy l8/prd532_check.py --live
sh kb/kbpy l8/prd532_check.py --selftest
```

## 九、边界

不能证明 rev107 是定稿（只是那一刻的读数）；不能证明四桶统计能算；不能证明守衡已同步；
不能证明 PRD 已改齐；不能替代 PRD 原文。
