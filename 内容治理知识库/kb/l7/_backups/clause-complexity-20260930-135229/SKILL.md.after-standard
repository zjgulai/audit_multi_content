---
name: kb-clause-extractor
description: |
  Momcozy 内容治理知识库 **L3（规则层）的条款抽取与蒸馏入口**：把外部标准 / 平台政策 / 内部规则文本
  抽成条款级单元，再蒸馏成**可判定的规则候选**（命中表达 + 处理方式），并维护逐单元拒绝台账。
  当用户说「抽条款 / 条款级单元 / 规则蒸馏 / L3 蒸馏 / 规则候选 / 这条能不能成规则 /
  拒绝台账 / 蒸馏漏了没」时使用。
  触发词：抽条款、条款级单元、规则蒸馏、L3 蒸馏、规则候选、拒绝台账、条款抽取、
  clause extractor、kb-clause-extractor。
  不适用（各自点名）：
    · 发号 / 定稿 / canonical → 走 **kb-pipeline**（L4）；查条款号 → **kb-canonical-lookup**；
    · 判是不是 P0 → **kb-p0-check**；召回单元 → **kb-recall**；
    · 素材切成单元 → **kb-ingest-extractor**（L1/L2，不是本 skill）。
version: "1.0.0"
last_updated: 2026-09-30
complexity: "standard"
enabled: "true"
user-invocable: true
---

# kb-clause-extractor —— L3 条款抽取与规则蒸馏

**一句话**：条款文本 → 可判定的规则候选（含命中表达与处理方式），**候选不是定稿**。

## 1. 它管哪一层

| 项 | 值 |
|---|---|
| 层 | **L3**（规则层） |
| 幂等键 | `rule_id`；`evidence_digest` 未变 → `unchanged`（跳过） |
| 落盘 | `kb/l3/candidates/{rules,sample_cases,scoped_clauses}.jsonl`、`kb/l3/rejected.jsonl`、`kb/l3/manifest_l3.jsonl` |
| 闸门 | `kb/l7/scripts/l3_gate.py` |

## 2. 干活的引擎

```bash
# 蒸馏（★**没有干跑档**：运行即落盘）
kb/kbpy l8/l3_distill_run.py <RUN>

# 拒绝台账重建（收敛后必须重建，否则重演 11,860 → 1,053 行回归）
kb/kbpy l8/l3_reject_ledger_rebuild.py <RUN> [--apply]
```

## 3. 三条红线（第一条是血泪）

1. **跑之前先归档**：`l3_distill_run.py` 会以 `w` 模式覆盖 `kb/l3/rejected.jsonl`。
   跑前必须把它复制到 `kb/l3/_archive/rejected-pre-<RUN>.jsonl` 并校验 sha256
   （本库真的发生过：逐单元拒绝台账从 11,860 行掉到 1,053 行）。
   编排器 `kb-pipeline.py --sync` 已把这条做成了红线①（`ARCHIVE_BEFORE_WRITE`）。
2. **候选 ≠ 定稿**：`kb/l3/candidates/rules.jsonl` 是候选；`kb/l4/canonical/*.jsonl` 才是定稿。
   把候选说成定稿 = 引用越级（`kb-canonical-lookup` 的 note 里写着这条）。
   条款号由 **L4** 分配，本 skill **不自造条款号**。
3. **证据必须一条条回指**：每条规则的 `evidence_units[]` 都要能回指 L2 单元的
   `unit_id + source_sha256 + anchor` —— 这正是 `l3_gate.py` 每天逐条核的那 1,729 条。

## 4. 验收

| # | 判据 |
|---|---|
| A1 | `kb/kbpy l7/scripts/l3_gate.py` 退出 0（证据全可回指 + 注册表自报键全已声明） |
| A2 | 跑前归档存在且 sha256 与源一致 |
| A3 | 蒸馏只**追加**：既有候选行逐字节未变（L4 定稿只加不改，L3 同理） |
| A4 | `kb/kbpy l7/scripts/l7_gate.py` 仍过（六要素在定稿上可物化率 100%） |

## 5. 与其他成员的关系

| 关系 | 成员 | 说明 |
|---|---|---|
| 上游 | `kb-ingest-extractor`（L2 单元） | 蒸馏的原料 |
| 下游 | `kb-pipeline`（L4 发号 / L5 P0 / L6 索引） | 候选 → 定稿 → 可召回 |
| 只读查询 | `kb-canonical-lookup` / `kb-p0-check` / `kb-recall` | 不写库 |
| 依据 | `kb-content-review` | 评审链拿的就是本层产出的条款号与锚点 |
| 编排 / 体检 / 修复 | `kb-pipeline` / `kb-check` / `kb-repair` | 本 skill 是 L3 的 owner |
