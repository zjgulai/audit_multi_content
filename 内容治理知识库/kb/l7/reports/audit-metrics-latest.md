# 审计指标 · PRD §10 七项 · 2026-10-15

- **采样时点**：`2026-10-15T17:24:55`（本地）　｜　**audit_id**：`AUDIT-20261015-172455`
- **生成命令**：`node kb/l8/audit_metrics.mjs`　｜　**只读**：只读 kb/l0…l7；只写 kb/l7/reports/
- **一单口径**：一次评审运行（不是素材数）；**本次样本**：1525 单 / 447 份报告 JSON / 778 个命中条目

> ⚠ 本产物**不合成一个「审计总分」**。七项各自有独立口径与阈值来源，
> 有的量得出来、有的**结构上量不出来** —— 后者写 `no_data` + 原因，
> 那不是「还没做」，是**现在给不出可信数字**。

## 0. 七项总览

| # | 指标（PRD §10） | 状态 | 本次读数 |
|---|---|---|---|
| 1 | PASS / REVIEW / BLOCK 比例 | ✅ measured | 三态 50.13% BLOCK / 32.98% REVIEW / 16.89% PASS |
| 2 | 各优先级层级命中率 | ✅ measured | P0 43 / P1 52 / P2 17 / P3 0 |
| 3 | 人工复核负担 | ✅ measured | 需人看 1270 单（83.28%） |
| 4 | 规则命中率 | ✅ measured | 66 个条款被命中（L3 共 509 条规则） |
| 5 | 审查覆盖率 | ⛔ no_data | —（分母不存在） |
| 6 | 误报 / 漏报 | ⛔ no_data | —（等金标集） |
| 7 | 知识库回流数量 | 🔌 no_data（已接线·等输入） | —（**已接线**，等首批人工复核；对照样本 0 条） |

## PASS / REVIEW / BLOCK 比例

- **状态**：`measured`
- **出处**：kb/l7/runs/index.jsonl → verdict（`STATE ｜ issue_count=N`）
- **口径**：按 verdict 前缀归三态；NEEDS_INPUT 是拒答态，**单列**（不计入三态分母，见下）

```json
{
  "n_runs": 1525,
  "n_three_state": 1510,
  "counts": {
    "PASS": 255,
    "REVIEW": 498,
    "BLOCK": 757,
    "NEEDS_INPUT": 15,
    "其他": 0
  },
  "ratio": {
    "PASS": 0.1689,
    "REVIEW": 0.3298,
    "BLOCK": 0.5013
  },
  "percent": {
    "PASS": 16.89,
    "REVIEW": 32.98,
    "BLOCK": 50.13
  },
  "needs_input_not_in_denominator": 15
}
```

## 各优先级层级命中率

- **状态**：`measured`
- **出处**：kb/l7/reports/*.json → risk_items[].priority_tier
- **口径**：**只算 2026-10-10 起**的报告（分层接线日，见 core/tiering.py）；更早的报告单列在 all_time 里做对照

```json
{
  "wired_from": "2026-10-10",
  "n_items": 112,
  "n_reports": 47,
  "counts": {
    "P0": 43,
    "P1": 52,
    "P2": 17,
    "P3": 0,
    "未标层": 0
  },
  "rate": {
    "P0": 0.3839,
    "P1": 0.4643,
    "P2": 0.1518,
    "P3": 0,
    "未标层": 0
  },
  "percent": {
    "P0": 38.39,
    "P1": 46.43,
    "P2": 15.18,
    "P3": 0,
    "未标层": 0
  },
  "all_time_for_contrast": {
    "n_items": 778,
    "counts": {
      "P0": 319,
      "P1": 442,
      "P2": 17,
      "P3": 0,
      "未标层": 0
    }
  },
  "distinct_article_no": 66,
  "caveat": null
}
```

## 人工复核负担

- **状态**：`measured`
- **出处**：kb/l7/runs/index.jsonl → human_involved / verdict；kb/l7/reports/*.json → risk_items
- **口径**：「需要人看的单」= REVIEW + BLOCK + NEEDS_INPUT（PASS 转 sign-off 确认，不算逐条复核）

```json
{
  "n_runs": 1525,
  "needs_human_runs": 1270,
  "needs_human_ratio": 0.8328,
  "needs_human_percent": 83.28,
  "by_state": {
    "PASS": 255,
    "REVIEW": 498,
    "BLOCK": 757,
    "NEEDS_INPUT": 15
  },
  "reports_with_items": 207,
  "issue_items_total": 778,
  "issues_per_reviewed_report": 3.76,
  "human_involved_true": 0,
  "human_involved_all_false": true,
  "caveat": "`human_involved` 全库仍为 false ⇒ **复核动作本身还没回流**。本项量的是「机器判下来有多少单需要人看」，**不是**「人实际花了多少时间」。后者要人真的复核过 —— 回流通道已于 2026-10-12 接线（见第 7 项 `wiring`），**只差人判**。"
}
```

## 规则命中率

- **状态**：`measured`
- **出处**：kb/l7/reports/*.json → risk_items[].evidence.article_no
- **口径**：条款号去重计数 + 命中频次 Top12；分母用「命中条目总数」而不是「规则总数」（PRD 原文只写「规则命中率」，未定义分母 ⇒ 本产物**把两种可算的都给出**，不替 PRD 选）

```json
{
  "n_items": 778,
  "n_distinct_articles_hit": 66,
  "n_rules_in_l3": 509,
  "rules_ever_hit_ratio": 0.1297,
  "top_articles": [
    {
      "article_no": "W-1.8",
      "n": 71
    },
    {
      "article_no": "W-1.33",
      "n": 59
    },
    {
      "article_no": "W-1.53",
      "n": 42
    },
    {
      "article_no": "W-1.18",
      "n": 41
    },
    {
      "article_no": "W-1.1",
      "n": 37
    },
    {
      "article_no": "W-1.31",
      "n": 37
    },
    {
      "article_no": "W-1.35",
      "n": 34
    },
    {
      "article_no": "W-1.11",
      "n": 33
    },
    {
      "article_no": "W-1.9",
      "n": 33
    },
    {
      "article_no": "W-1.13",
      "n": 28
    },
    {
      "article_no": "W-1.55",
      "n": 27
    },
    {
      "article_no": "W-1.26",
      "n": 27
    }
  ],
  "hits_by_p_level": {
    "P0": 41,
    "P1": 290,
    "P2": 298
  },
  "caveat": "「规则总数」取 L3 候选 509 条。**它不是「该被命中的全集」** ——分母换一个（比如只算 P0 规则）结论就变，故本产物只报**可算的两个比**，不合成一个「命中率」。"
}
```

## 审查覆盖率

- **状态**：`no_data`　—　**结构上算不了**：分子（被审的素材）有，分母（应当被审的全集）**在库里不存在**。PRD §1.1 给的规模是「广告二创月均约 500 条、高峰约 3000 条」「红人内容月均 100-200 条」—— 那是**口头规模**，不是可复算的台账；库里没有「本期应审素材清单」这种东西。

```json
{
  "numerator_available": 1525,
  "denominator_available": null,
  "what_would_make_it_measurable": [
    "① 需方侧给出「本期应审素材清单」（飞书表 / NAS 路径 / 投放计划），落进 L0 一张表；",
    "② 送审侧每条素材带唯一素材 ID（现在 content_id 是哈希形态，同一素材多次送审算多单，见目标 9）；",
    "③ 有了 ①②，覆盖率 = 已审素材 ID ∩ 应审清单 / 应审清单。"
  ]
}
```

## 误报 / 漏报

- **状态**：`no_data`　—　**结构上算不了，且必须等金标集**：误报 = 机器判 BLOCK/REVIEW 而人判 PASS；漏报 = 机器放行而人判有问题。两个都要**人工标准答案**当对照。任务拆解 11/30 那行才建金标集（文字 40 / 图片 30 / 视频 30），且现状视频 0 条、预期答案是 agent 判读 v0 而非人工答案（`fixed_eval_set: missing`）。**在那之前给出任何误漏报数字都是编的。**

```json
{
  "gold_set_status": {
    "contract": "kb/view/3_措辞表达库/tests/ 的黄金问题集（现测 35/38 = 0.92）",
    "contract_fixed_eval_set": "missing（验收契约未达条件之一）",
    "human_labels": null,
    "video_items": 0
  },
  "what_would_make_it_measurable": [
    "① 100 条**人工标准答案**入库并进验收契约（`fixed_eval_set`）；",
    "② 每条评审记录能回指金标条目（现在没有这个外键）；",
    "③ 有了 ①②，误报率 = 机器拦 ∧ 人放 / 机器拦；漏报率 = 机器放 ∧ 人拦 / 人拦。"
  ],
  "downstream_blocked": [
    "任务拆解 12/14 那行要的「错放率 ≤5%」——算不出",
    "任务拆解 12/14 那行要的「复核召回 ≥95%」——算不出"
  ]
}
```

## 知识库回流数量

- **状态**：`no_data`　—　**机制已接线，但没有人判过** —— 差异台账（append-only）已建、三态已实现，可判定的对照样本（既有机器结论、又有人判）**为 0 条** ⇒ 现在给不出数量。★ 卡点已从「机制未建」变成「**等首批人工复核**」（PRD §11.2 每周抽检 100 条／§11.3 金标集），**两项输入都已就绪、只差人填「人判」栏**。
- **出处**：kb/l7/registry/return-flow.ndjson（append-only 事件台账） → kb/l8/return_flow.py status
- **口径**：人工判定 ≠ 机器结论、且人工给出**明确三态** ⇒ 一条事件（人判 NEEDS_INPUT 与「机人一致」都**不算**事件）；数量 = 事件条数（按 target_layer 分组）。口径真源 kb/l7/registry/return-flow.yaml。

```json
{
  "reflow_events": 0,
  "n_comparable_samples": 0,
  "ledger_events": 0,
  "inputs": [
    {
      "input": "l7/reports/audit-sample-ALL.csv",
      "exists": true,
      "comparable": 0,
      "human_col": "人判",
      "machine_col": "机器结论",
      "rows": 100
    },
    {
      "input": "l7/reports/gold-set-60.csv",
      "exists": false,
      "comparable": 0
    }
  ],
  "what_would_make_it_measurable": [
    "① 往 kb/l7/reports/audit-sample-ALL.csv 的「人判」栏填判定（100 条已就绪）；",
    "② 或把 60 题金标集的三态回填进库；",
    "③ 有了人判，`kb/l8/return_flow.py ingest --apply` 生成事件，本项即为 measured。"
  ],
  "note": "**接线 ≠ 有读数。** 此时报 `0` 会退回本项要消灭的那个错读法（「核过了，没有回流」）；⇒ 分开写：机制在，输入未到。"
}
```

## 附：本次样本指纹

```json
{
  "n_runs_total": 7912,
  "n_runs": 1525,
  "n_runs_excluded_as_test": 12,
  "excluded_run_ids": [
    "20261010-153704",
    "20261010-153953",
    "20261010-154007",
    "20261010-154024",
    "20261010-154040",
    "20261010-154100",
    "20261010-160153",
    "20261010-160213",
    "20261010-160449",
    "20261010-160835",
    "20261010-162416",
    "20261010-162451"
  ],
  "n_reports": 447,
  "n_rule_items": 778,
  "n_rules_in_l3": 509
}
```
