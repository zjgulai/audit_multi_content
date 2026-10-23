---
id: ref-prd532-four-states-wiring-20261019
title: PRD §5.3.2 四态（PASS/SUGGEST/REVIEW/BLOCK）：登记件已存但代码零读方 —— 本轮把六处钉成一条会变红的线
collection: 3_措辞表达库
tier: L1
topic: 知识
kind: fact
summary: Owner 2026-10-19 发来 PRD §5.3.2 四态原文问「同步知识库了吗」：登记层（prd532-states.yaml）早已同步，但代码层零读方 —— 跨仓 S7 只有三条正则无 SUGGEST、统计侧仍是 TRI_STATE，删掉任一处都不会红。本轮把「真源↔决策集↔落表↔分级↔渲染↔守衡词表」六处钉在一起（新判据 kb/l8/prd532_check.py，gate id prd532，非阻断，自证 12/0；S7 补第四态与 R7e 反向对照，workflow_smoke --selftest 20/0）。冲突 K 取 Owner 裁定 ①（decision 可取 SUGGEST，覆盖 §6.3 规则 4）。生产侧 SUGGEST 仍 0 单（读数不判红）；§10.2 四态统计、§11 四态准确率、结论行前缀仍未落。
owner: 刘华丽
evidence_level: L2
data_level: L2
half_life_days: 180
created_at: 2026-10-19
valid_until: 2027-04-17
asks:
  - PRD §5.3.2 的四态是哪四个、各自定义与动作的逐字原文是什么
  - SUGGEST 到底能不能作为最终结论（decision 取四值还是三值）、Owner 怎么裁的
  - 什么情况下才会出 SUGGEST（哪一级 P 是它唯一的产者）
  - 四态现在在哪些地方各写了一份、哪一处在读真源
  - 删掉 SUGGEST 会不会有东西变红、是哪几条判据、反向对照怎么钉的
  - 生产侧到底出过几单 SUGGEST（能不能说四态已上线跑通）
  - 四态还差哪三半没落（统计、准确率、结论行前缀）
  - NEEDS_INPUT 算不算第五态、和四态是什么关系
  - 守衡的结论行解析器认不认 SUGGEST、它与 REVIEW 的唯一分界是哪几个字
not_proves: 不能证明生产侧出过 SUGGEST（2026-10-19 实测 0 单，四态是「能出」不是「出过」）；不能证明四态的判定质量（P3 边界与「非强制」如何认定属准确率问题，回归集 SUGGEST 样本 0 条）；不能证明 PRD 已被改齐（PRD 自身仍有 6 处写「三态」，改动权不在我方）；不能证明 NEEDS_INPUT 是 PRD 的四态之一（它是拒答态、是决策集第 5 个 token）；不能替代 PRD 原文（条款以 docx PXfBdjTwFokEQixtmTscqm7knNh / sheet xcdTpv rev 96 为准）；不能证明两条链之外的调用方（批跑脚本、看板）已按四态取数 —— 统计侧仍是 TRI_STATE。
source:
  kind: file
  ref: /Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/交付-PRD532四态接线与落库-20261019.md
  fingerprint: c28c8d334cd27d78
  captured_at: 2026-10-19
provenance:
  anchor: 交付-PRD532四态接线与落库-20261019.md#一、PRD §5.3.2 原文（逐字，含出处）
  confidence: 确定
sensitivity_level: L2
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为 PRD 口径、判据与实测读数，提及的是角色位与文件名
kb_class: []
evidence_group: rule
corroborated_by:
  - kb/l7/registry/prd532-states.yaml（§5.3.2 逐字真源，含冲突 K 裁定与 still_open）
  - kb/l7/review-engine/core/review_engine.py ＋ tiering.py ＋ feishu_publish.py（决策集/分级/落表三处代码）
  - tools/agent/prd53.mjs（守衡结论行解析器：STATES / LINE_RE / conforms，跨仓第二实现）
  - kb/l8/prd532_check.py ＋ kb/l8/workflow_smoke.py（本轮的判据与反向对照）
  - _prd-20261019/sheet-xcdTpv.json（PRD 内嵌表快照 rev 96，逐字核对用）
forbidden: 不许把「四态已接线」读成「四态已在生产跑通」（实测 0 单）；不许因为本条就把 NEEDS_INPUT 当成 PRD 第五态；不许把 SUGGEST 写成阻断（它随 PASS 一起进入下一步）；不许用本条替代 PRD 原文或改写 §5.3.2 的措辞；不许在没跑 prd532_check/workflow_smoke 的情况下声称「两边一致」。
---

## 一、这条讲什么

Owner 2026-10-19 把 PRD §5.3.2「四态定义与边界」原文发来，问「这个同步知识库了吗」。
查完的事实是：**登记层早已同步，代码层没有任何东西认它**。

- 真源 `kb/l7/registry/prd532-states.yaml` 全仓 **0 个读方**（只有 `review_engine.py:51` 一句注释提到它）；
- 跨仓那把尺子 `workflow_smoke.py::S7` 只有 PASS/REVIEW/BLOCK 三条正则，**没有 SUGGEST**；
- 统计侧 `bitable_stats.py:107` 仍是 `TRI_STATE`（三态）。

⇒ 谁把 `SUGGEST` 从任一侧删掉，**今天不会红**。本库自己的话：**散文没有失败信号；判据才有。**

## 二、PRD §5.3.2 原文（逐字）

取数：飞书 PRD 内嵌 spreadsheet `B1aUs2Vuah8YwjtwWO6cr5MFnUd` / sheet `xcdTpv`，`A1:C5`，**revision 96**；留底 `_prd-20261019/sheet-xcdTpv.json`。与 Owner 贴文逐字一致。

| 状态 | 定义 | 动作 |
|---|---|---|
| PASS | 未发现已知底线风险，或仅有无伤大雅的错别字 | 转 sign-off / brief 提交方 |
| SUGGEST | 存在非强制性问题（措辞优化、轻微常识瑕疵、非核心卖点描述） | 提示内容方，不阻断流程，随 PASS 一起进入下一步 |
| REVIEW | 存在边界模糊、需专业判断的问题（如医疗暗示、复杂场景安全、无明确规则覆盖的争议点） | 转法务/医学/专家/北美复核 |
| BLOCK | 命中明确红线（P0 级），或 P1/P2 中证据确凿的违规 | 返回内容方修改后重新提交 |

## 三、冲突 K 与 Owner 裁定

PRD 对「`decision` 能不能取 SUGGEST」自相矛盾：§5.3.2 把 SUGGEST 列进**状态**并给了动作、§17 样张的结论行就是 `【SUGGEST】…`；而 §6.3 规则 4 写「只有 SUGGEST 时，最终状态为 PASS」、§10.1 的 `decision` 只列三值。

**Owner 2026-10-19 裁定取 ①**（`decision` 可取 `SUGGEST`，即四态）⇒ §6.3 规则 4 被本裁定覆盖。登记处：`prd-v1.3-alignment.yaml::changes[A].owner_ruling_20261019`。

## 四、本轮落地的六处（每处都有判据钉着）

1. 真源 `kb/l7/registry/prd532-states.yaml`：四态定义＋动作＋边界逐字、冲突 K 的裁定、落地清单与 `still_open`。
2. `review_engine.DECISIONS` 收 `SUGGEST`；**只有 P3 ⇒ SUGGEST**；`render_summary` 出「发现 N 处建议优化，不阻断发布。」；`_next_action` 带「不阻断流程」。
3. `tiering.decide_effect(["P3"])` 由 `none` 改 `suggest` —— **P3 是 SUGGEST 唯一的产者**，这一条断了第四态永远空着。
4. `feishu_publish.STATUS_PASS` 收进 `SUGGEST`（它是合法结论，可以落表）。
5. 守衡 `tools/agent/prd53.mjs`：`STATES` 四态、`LINE_RE` 认 `SUGGEST`、`conforms()` 校验「不阻断发布」（那是它与 REVIEW 的唯一分界）。
6. `kb/l8/workflow_smoke.py` 的 S7：补 `_PRd_SUGGEST_RE`（逐字照抄守衡）、`kb_prd_conforms` 增分支、真输出 SUGGEST 样本、新增反向对照 R7e。

新增判据 `kb/l8/prd532_check.py`（闸门 id `prd532`，接进 `ci/run_gates.py` 的 core，**非阻断**）：把「真源 ↔ 决策集 ↔ 落表 ↔ 分级 ↔ 渲染 ↔ 守衡词表」六处钉在一起。

## 五、实测读数（2026-10-19）

`prd532_check.py` PASS（跨仓实读 `['PASS','SUGGEST','REVIEW','BLOCK']`）｜`--selftest` **12/0**（6 条真变异＋2 条缺件口径＋1 条逐字核对）｜`workflow_smoke.py` 退出码 **0**｜`--selftest` 反向对照 **20/0**（含 R7e）｜`prd53_format.test.py` 19/0｜`test_tiering.py` 23 tests OK｜`ci/run_gates.py --only prd532 prd_card_conformance` 过 2/2。

**生产侧 SUGGEST 单量 = 0**（`kb/l7/runs/index.jsonl` 0 命中）—— 这是读数，不判红：四态刚落地，回归集 100 条期望态仍是三态、SUGGEST 样本 0 条，做成红判据只会第一天就红。

## 六、没落的三半（登记在 `prd532-states.yaml::landing.still_open`）

1. §10.2 四态分布统计 / §15 统计验收：`bitable_stats.py:107` 仍是三态。
2. §11 四态准确率：回归集期望态仍是三态（BLOCK 44 / REVIEW 23 / PASS 13 / 拒答 20），SUGGEST 样本 0 条 ⇒ 「整体四态准确率 ≥90%」当前量不出来。
3. 结论行前缀仍是 `【审查结论：X】`，不是 §5.3.4 样张的 `【PASS】`（`deliberately_not_followed.items[C]`）；「四态没落」这个拖延理由已失效，现在剩的代价是两仓＋297 份存量报告＋回归基线要同批改。
4. PRD 自身仍有 6 处写「三态」（§1.2/§4/§5.1×2/§10.1/§11.2）—— 改动权不在我方，走《反馈单》。

## 七、边界（这条不能证明什么）

- 不能证明生产侧出过 SUGGEST（今天是 0 单）：四态是「**能出**」，不是「**出过**」。
- 不能证明四态的判定质量（P3 边界、什么算「非强制」属准确率问题，需要样本与金标）。
- 不能证明 PRD 已被改齐；本件只保证我方两侧与 §5.3.2 一致。
- **`NEEDS_INPUT` 不是 PRD 的态**：它是拒答态（fail-closed），是决策集的第 5 个 token。「卡片态必须是 4 态」≠「决策集只能有 4 个值」。
- 不能替代 PRD 原文：条款以 docx `PXfBdjTwFokEQixtmTscqm7knNh` / sheet `xcdTpv` rev 96 为准。