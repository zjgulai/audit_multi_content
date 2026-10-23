---
asks:
  - PRD §5.3.2 里 SUGGEST 到底是「第四态」还是「PASS 的附属标签」、依据是哪几处原文
  - decision 能不能取 SUGGEST、冲突 K 的裁定 ① 现在什么状态（被谁覆盖、在哪留痕）
  - 「四态」在 PRD 里指的是什么（取值数还是统计桶）、四个桶分别怎么落
  - 卡片上带建议的 PASS 单长什么样（结论行写什么、建议段写什么）
  - P3（非强制）命中时结论、置信度、建议集各怎么变
  - 「PASS＋建议」这个桶的机器判定式是什么（哪个字段）
  - 删掉哪个东西会让哪条判据变红（三值＋标签的反向对照清单）
  - 守衡侧还欠哪几处改动、不同步会不会出事
  - §5.3.4 样张与 §17 字数表里的 SUGGEST 行还要求改吗
collection: 3_措辞表达库
corroborated_by:
  - kb/l7/registry/prd532-states.yaml（rev 101 四行逐字 ＋ label_semantics ＋ 冲突 K 的 superseded 留痕）
  - kb/l7/review-engine/core/review_engine.py ＋ tiering.py ＋ feishu_publish.py（决策集／建议集／渲染／落表四处代码，`_result` 是唯一出口）
  - tools/agent/prd53.mjs（守衡侧仍是 rev96 的四态词表 —— 本轮**只读**，改单在交付件第四节）
  - kb/l8/prd532_check.py（七面判据 ＋ 17 条真变异自证）＋ kb/l8/workflow_smoke.py（S7 非法样本 ＋ R7e）
created_at: 2026-10-19
data_level: L2
evidence_group: rule
evidence_level: L2
forbidden: 不许把「四态」读成 decision 四值（rev101：三个取值 + 一个标签）；不许再让 【审查结论：SUGGEST】这一行出现在任何产物里（建议只能以附段形式跟在 PASS 行后）；不许把 P3 的 effect 改回 suggest（那会重新出现第四态）；不许把「四态统计桶」当成「四态准确率」（§11.2 明写三态一致数）；不许在本轮就声称守衡侧已同步（只读）；不许用本条替代 PRD 原文（sheet xcdTpv rev 101）。
half_life_days: 180
id: ref-prd532-suggest-as-pass-label-20261019
kb_class: []
kind: fact
not_proves: 不能证明守衡侧已按新口径改完（本轮**只读**那边工作区，三处改动单在交付件第四节；未同步期间 prd532_check::F2 与 S7 各报一句「跨仓待同步」，**都不判红**）；不能证明四桶分布已能算出来（`bitable_stats.py:107` 仍是 `TRI_STATE`，第二桶的输入 suggest_label 已就位但没人读）；不能证明生产侧出过「PASS＋建议」单（今天 0 单，能力已接通、样本未出现）；不能证明 PRD 已被改齐（§5.3.4 样张仍印 【SUGGEST】、§17 仍给 SUGGEST 单列一行 ⇒ 已登记为内部冲突 S1，走反馈单）；不能证明「SUGGEST 不再作为状态」在别的部署/别的仓也成立（描述的是 2026-10-19 这一台、这一版代码）；不能替代 PRD 原文（条款以 docx PXfBdjTwFokEQixtmTscqm7knNh / sheet xcdTpv rev 101 为准）。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为 PRD 口径、代码路径与实测读数
provenance:
  anchor: 交付-PRD532-标签口径-与守衡改单-20261019.md#一、PRD 原文（rev 101，逐字）
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-19
  fingerprint: a462c8c085ebfd28
  kind: file
  ref: /Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/交付-PRD532-标签口径-与守衡改单-20261019.md
summary: PRD §5.3.2 当天从 rev 96 改到 rev 101：SUGGEST 从「第四态」降为「PASS 的附属标签」（§6.3 规则4 / §10.1 三值 / §11.2 三态准确率 / §10.2 随 PASS 流转 四处同向）。口径定案 = 三值（PASS/REVIEW/BLOCK）+ 一个标签（suggest_label = decision=PASS ∧ suggest_count>0）+ 四个统计桶。KB 侧已落：DECISIONS 去 SUGGEST、P3 不改结论但必须留下 suggestions[]、PASS 卡追加「建议（不阻断，随 PASS 流转，共 N 条）：」附段、render_summary('SUGGEST') 硬失败、STATUS_PASS 回三态；判据 prd532_check 改七面并补 revision 三比对（原判据拿旧快照当真值，真源与快照一起陈旧 ⇒ 恒绿）。实测：prd532 --selftest 17/0、workflow_smoke rc0 + --selftest 20/0、prd53_format 22/0、pytest 101 passed、锁 25/25。守衡侧三处（prd53.mjs / dual_track.mergedState / prd17.mjs）在另一会话工作区，本轮只读，未同步期间只报「跨仓待同步」不判红。
title: PRD §5.3.2 rev101：SUGGEST 降为「PASS 的附属标签」—— 三值＋标签＋四桶，KB 侧已改完、守衡侧有改单
tier: L1
topic: 知识
valid_until: 2027-04-17
---

## 一、这条讲什么

Owner 2026-10-19 贴来 PRD §5.3.2 **rev 101** 原文并问「suggest 作为 PASS 的附属标签，你觉得要如何优化」，随后「按照 A 开工」。

拉表核对：内嵌 sheet `xcdTpv` 当天从 **rev 96 → rev 101**，四行定义全改、列头「动作」→「系统流转动作」、PASS 定义新增「**可包含 SUGGEST 建议**」、SUGGEST 定义改成「**作为 PASS 的附属标签**」。

⇒ 口径定案：**三值 + 一个标签 + 四个桶**。

| 维度 | 取值 |
|---|---|
| `decision` | PASS / REVIEW / BLOCK（+ 拒答 `NEEDS_INPUT`，**不是 PRD 的态**） |
| `SUGGEST` | **PASS 的附属标签**，判定式 `decision=PASS ∧ suggest_count>0`（字段 `suggest_label`） |
| 统计「四态」 | **四个桶**：PASS ／ PASS＋SUGGEST ／ REVIEW ／ BLOCK（§10.2「汇总四态结论」） |
| 卡面 | 结论行**恒三态**；建议以附段形式跟在 PASS 行之后：「建议（不阻断，随 PASS 流转，共 N 条）：」 |

**五处同向（这不是我的解释，是 PRD 自己写在五处的）**：§5.3.2 rev101（附属标签）／§6.3 规则4（「只有 SUGGEST 时，最终状态为 PASS（附 SUGGEST 建议）」）／§10.1（`decision` 三值）／§11.2（准确率 = **三态**结论一致数）／§10.2 注（「SUGGEST 随 PASS 流转，不计入人工复核工单」）。唯一站在另一侧的是 §5.3.4 样张那句 `【SUGGEST】…`（与 §17 字数表里 SUGGEST 那一行）—— 已登记为 PRD 内部冲突 S1，走《反馈单》，我方不回改 PRD。

## 二、KB 侧落了什么（2026-10-19 第二轮）

- 真源 `kb/l7/registry/prd532-states.yaml` 升 rev 101 四行逐字，新增 `label_semantics`（`decision_values` / `label_state` / `predicate` / `buckets`）；冲突 K 的历史裁定 ① 加 `superseded_by` / `superseded_at` / `supersede_reason` 留痕（AP14：改主意不静默覆盖）。
- `review_engine.DECISIONS` 回到三态＋拒答；**`_result` 这一处唯一出口**统一挂 `suggestions[]` / `suggest_count` / `suggest_label`；`render_summary("PASS", …)` 追加建议附段；`render_summary("SUGGEST", …)` **抛 ValueError**（第四态不许从渲染这条路复线）。
- `tiering.decide_effect(["P3"])` → `none`（P3 不改结论，但必须留下建议集）。
- `feishu_publish.STATUS_PASS` 回到三态（建议条数走 `suggest_count` 那一格，不靠多一个状态值）。
- S7：撤掉 `_PRd_SUGGEST_RE`；把 `【审查结论：SUGGEST】…` 从「合规样本」改成**非法样本**；R7e 改成「旧版产者复线 ⇒ 必须红」。
- 判据 `kb/l8/prd532_check.py` 从「六处一致」改成「三值＋标签＋四桶」七面，并**修掉它自己的一个缺陷**：原先拿 rev 96 快照逐字比对，真源与快照**一起陈旧、互相印证 ⇒ 恒绿**，发现不了这次漂移；现加 **revision 三比对**。

## 三、实测读数（2026-10-19 第二轮）

`prd532_check` PASS（跨仓标记「待同步」不判红）｜`prd532_check --selftest` **17/0**｜`workflow_smoke` rc **0** ＋ `--selftest` **20/0**｜`prd53_format.test.py` **22/0**｜`test_tiering` **23 passed**｜`tiering --selftest` **55/55**｜`pytest l7/review-engine/tests` **101 passed**｜`p0_fastpath --selftest` **60/0**｜`owner_locks_check` **25 修复 / 25 挂锁**｜`ci/run_gates.py --only prd532 prd_card_conformance` 过 **2/2**。

## 四、守衡侧改动单（本轮只读，未改）

`tools/agent/prd53.mjs`（STATES 去 SUGGEST、`conforms()` 删 SUGGEST 分支、`LINE_RE` 收窄）、
`tools/agent/dual_track.mjs::mergedState`（四态单调回三态 ＋ 出 `suggest_labels`、「PASS＋建议」桶）、
`tools/agent/prd17.mjs`（SUGGEST 那一档改作**建议附段**的字数口径），必要时 `model_side.mjs`（模型侧 SUGGEST ⇒ `action: advice`，不得回写 `decision`）。

**当前无害**：KB 已不再产出 SUGGEST 行，守衡多认一个不会出现的词；未同步期间 `prd532_check::F2` 与 S7 各报一句「跨仓待同步」，**都不判红**（缺三态才红）。

## 五、仍未落

§10.2 四态分布统计（`bitable_stats.py` 仍是 `TRI_STATE`，第二桶需读 `suggest_label`）／§11 四态准确率（回归集 SUGGEST 样本 0 条，现按 §11.2 三态口径算）／§5.3.4 样张与 §17 SUGGEST 行（走反馈单）。

## 六、边界

不能证明守衡侧已同步（本轮只读）；不能证明四桶分布已能算出来（统计侧仍是三态）；不能证明生产侧出过「PASS＋建议」单（今天 0 单）；不能证明 PRD 已被改齐（§5.3.4/§17 仍是旧形状）；不能替代 PRD 原文（sheet `xcdTpv` rev 101 / docx `PXfBdjTwFokEQixtmTscqm7knNh`）。