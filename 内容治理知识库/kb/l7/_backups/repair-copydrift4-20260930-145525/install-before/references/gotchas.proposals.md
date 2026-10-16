---
title: Gotchas Proposals（升级候选 · 机械生成）
doc_type: reference
module: kb-l0-feishu
topic: gotchas-proposals
status: generated
created: 2026-09-30
updated: 2026-09-30
owner: self
source: ai
---

# 升级候选（`scripts/retro.py` 每次收口自动追加）

**这一份是"候选"，不是"已确认的坑"。** 分开放是故意的：

| 文件 | 谁写 | 性质 |
|---|---|---|
| `gotchas.md` | **人**（或人确认后的落盘） | 已确认的坑与事故台账 —— 可当依据引用 |
| `gotchas.proposals.md`（本文件） | **脚本**（`retro.py`） | 机械推导出的候选 —— **未经确认，不许当依据** |

生成的三种候选：

1. **`new_reason_code`** —— 本轮首次出现的原因码（可能是数据状态，也可能是工具缺陷）
2. **`repeat>=2`** —— 同一原因码累计出现 ≥2 轮（按 gotchas §四 维护闭环，够格升红线/硬规则）
3. **`stage_not_run`** —— 本轮该有的阶段产物**哪儿都没有**（"以为跑了其实没跑"是最贵的一类失误）
4. **`run_id_split`** —— 本轮有阶段产物落在**别的 RUN** 下（性质是 run_id 口径不统一，**不是漏跑**）

**怎么用**：人看完候选后，**要么**确认并手工落进 `gotchas.md` / `SKILL.md` 红线（落盘时按 SKILL.md §8.3
留痕：备份 + CHANGELOG + bump version），**要么**在候选下写一行否决理由。
**脚本永远不会自己动 `gotchas.md` 正文或任何闸门。**

## ⚠ 历史更正（`retro 1.2.0` 的误报，已作废）

**2026-09-30 10:27–10:29 之间的候选块全部作废，请勿据此行动。** `retro.py` 当时有两个自身缺陷：
阶段产物文件名写死（三处与真实名不符）、且"缺跑"判定循环写反（遍历了已找到的键），
于是把**已经跑过的阶段**报成 `stage_not_run`（实测误报 8–9 个），还漏掉了 `stages_elsewhere` 这一类。
`retro 1.2.1` 起改为按关键词从 `kb/l8/runs` 与 `kb/l6/runs` **实际发现**，
并把"本 RUN 没有、别的 RUN 下有"单列为 `run_id_split`。作废块的标题里没有 `· retro 1.2.1` 标记，
以此区分；台账侧的更正说明见 `kb/l8/retro/ledger.ndjson` 的 `correction: true` 行。
**教训（已落 `gotchas.md` §二）：工具 bug 不许报成数据缺陷 —— 收口脚本尤其要背这条。**

## 20260930-0950（2026-09-30 10:27:24）

- **stage_not_run** `schema`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `nonrecord`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `nonrecord2`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `scope_gaps`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `video`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `urls`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `shingles`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `l0_ingest`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `l6_scope`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1140（2026-09-30 10:27:41）

- **stage_not_run** `align`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `schema`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `nonrecord`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `nonrecord2`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `video`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `urls`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `shingles`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `l0_ingest`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `l6_scope`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1140（2026-09-30 10:27:41）

- **stage_not_run** `schema`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `nonrecord`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `nonrecord2`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `video`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `urls`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `shingles`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `l0_ingest`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **stage_not_run** `l6_scope`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1140（2026-09-30 10:28:48）

- **stage_not_run** `scope_gaps`：该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）
- **run_id_split** `1 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1140（2026-09-30 10:28:56）

- **run_id_split** `8 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1140（2026-09-30 10:29:52）

- **run_id_split** `8 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1140（2026-09-30 10:31:12）

- **run_id_split** `8 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1140（2026-09-30 10:31:32 · retro 1.2.1）

- **run_id_split** `8 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1258（2026-09-30 13:05:30 · retro 1.2.3）

- **new_reason_code** `drift`：首次出现的原因码：确认是数据状态还是工具缺陷；若属工具缺陷，按 §7 记入 gotchas 的『脚本自身缺陷』一栏，不要报成数据缺陷
- **new_reason_code** `forbidden`：首次出现的原因码：确认是数据状态还是工具缺陷；若属工具缺陷，按 §7 记入 gotchas 的『脚本自身缺陷』一栏，不要报成数据缺陷
- **new_reason_code** `no_scope`：首次出现的原因码：确认是数据状态还是工具缺陷；若属工具缺陷，按 §7 记入 gotchas 的『脚本自身缺陷』一栏，不要报成数据缺陷
- **new_reason_code** `not_verified`：首次出现的原因码：确认是数据状态还是工具缺陷；若属工具缺陷，按 §7 记入 gotchas 的『脚本自身缺陷』一栏，不要报成数据缺陷
- **new_reason_code** `unreachable`：首次出现的原因码：确认是数据状态还是工具缺陷；若属工具缺陷，按 §7 记入 gotchas 的『脚本自身缺陷』一栏，不要报成数据缺陷
- **run_id_split** `5 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1340-bot（2026-09-30 13:34:56 · retro 1.2.3）

- **run_id_split** `8 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1343-bot（2026-09-30 13:46:59 · retro 1.2.3）

- **run_id_split** `8 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1430（2026-09-30 14:35:12 · retro 1.2.3）

- **repeat>=2** `drift`：同一原因码累计 ≥2 轮：按 gotchas §四 维护闭环，考虑升为 SKILL.md 红线或阶段内硬规则
- **repeat>=2** `forbidden`：同一原因码累计 ≥2 轮：按 gotchas §四 维护闭环，考虑升为 SKILL.md 红线或阶段内硬规则
- **repeat>=2** `no_scope`：同一原因码累计 ≥2 轮：按 gotchas §四 维护闭环，考虑升为 SKILL.md 红线或阶段内硬规则
- **repeat>=2** `not_verified`：同一原因码累计 ≥2 轮：按 gotchas §四 维护闭环，考虑升为 SKILL.md 红线或阶段内硬规则
- **repeat>=2** `unreachable`：同一原因码累计 ≥2 轮：按 gotchas §四 维护闭环，考虑升为 SKILL.md 红线或阶段内硬规则
- **run_id_split** `7 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。

## 20260930-1449（2026-09-30 14:50:59 · retro 1.2.3）

- **run_id_split** `8 个阶段落在别的 RUN 下`：一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯

> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。
