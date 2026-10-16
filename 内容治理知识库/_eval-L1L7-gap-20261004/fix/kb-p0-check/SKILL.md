---
name: kb-p0-check
description: |
  当用户说「这个是 P0 吗/算不算 P0/命中哪些 P0 模式」时使用。 Momcozy 内容治理知识库 **L5（P0 判定层）**的**只读查询**入口。查询档只读：不写库、不改 P0 模式表。 ★**以下优先于上面的触发词，一律不加载**： ① 欠定：只打本名、只有名词、指代不明、没说判哪段内容、只要判据不要判定 → 先追问； ② 写档/破坏性：重建或导出 P0 层、改 P0 模式表、写库、--apply、rm -rf、清空 → 直接拒绝（写档归 kb-pipeline）； ③ 不是本件：要条款号→kb-canonical-lookup；要召回→kb-recall；要依据→kb-content-review。 判归：能不能发→kb-review；整链/同步→kb-pipeline；体检/闸门→kb-check；改 skill 质量→root-skills-eval。 触发词：P0 模式有哪些、这段文字命中 P0 了吗、优先级是不是 P0、为什么是 P0、P0 清单给我看一下、这条触碰红线了吗（红线口径=P0）、L5 里有没有这条、kb-p0-check。
version: "1.5.0"
last_updated: 2026-10-04
license: "Proprietary — Momcozy internal use only"
complexity: "minimal"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["长清单需分页"] }
  minimax: { status: "bridge", limitations: ["需中文优化"] }
  dsh: { status: "native", notes: "查询档只读；写档档位由 kb-pipeline 以层身份调用；kbpy 同机可用" }
  codex: { status: "native" }
---

# kb-p0-check —— L5 P0 判定层 · 只读查询（+ 被调用时的写档档位）

**一句话**：回答「**这个是 P0 吗**」。**查询档只读**，只做确定性匹配。
被 `kb-pipeline` 以层身份调用时，另走本文 §4 的写档档位（重建 / 导出 P0 层）。

## 1. 数据在哪

| 项 | 位置 |
|---|---|
| P0 模式表 | `kb/l5/p0_patterns.jsonl`（每条带 `anchor` + `authority` + `evidence_units[]`） |
| 匹配器（运行时只读器） | `kb/l5/matcher.py`（`--text` / `--file` / `--json` / `--selftest`，**不写盘**） |
| 索引 / 基准 / 运行记录 | `kb/l5/index/` · `kb/l5/benchmark.json` · `kb/l5/runs/<RUN>-*.json` |

cwd 必须是**本次库根**（批次23 起派生于库根，占位符 `{kb_root}`）。
**判法（含 bash 样例）、输出契约、写档细目 → `references/layer-playbook.md`。**

## 2. 红线

- **查询档不写**：不调 `l5_prep.py` / `l5_export.py`，不改 P0 模式表。写档只在 §4 的档位下发生。
- **不把「没命中」说成「没问题」**：P0 是「最高优先级」的口径，**不是「合规」**的口径；
  未命中只说明不是最高优先级，其余风险仍走 `kb-review`。
- **不自己造模式**：清单里没有的说法，不许顺手归纳成一条新 P0；要加就交 `kb-pipeline` 走链路。
- **不给三态结论**：本 skill 只答「是不是 P0」，「能不能发」走 `kb-review`。
- 引用必须带 `anchor` + `authority` + `evidence_units[].unit_id` + `source_sha256`。

## 3. 何时停下来问人

- `matcher.py` 的命中结果与 `p0_patterns.jsonl` 不一致 → 报冲突，交 `kb-check`。
- 用户问的是一整段内容的合规性，而不是「是不是 P0」→ 让位给 `kb-review`。
- P0 模式表为空（实测 `kb/l5/registry/` 下曾出现空数组）→ 如实报「P0 层为空」，
  **不许用常见违规清单顶替**。

## 4. 写档档位（只被 kb-pipeline 以层身份调用时走）

**三条件缺一不可**：① 由 `kb-pipeline` 以层身份调用 ② 带 `--apply` ③ 人开闸。
**它不是给用户直接触发的入口** —— 本 skill **刻意不加**「重建 / 导出」类触发词，
用户问「把 P0 层重建一下」仍走 `kb-pipeline`。

跑哪几个引擎**不写在本文**：读 `kb/l7/registry/layers.yaml` 的 **L5 层 `engine`**（唯一真源）；
`RUN` 用调用方传进来的 run_id。写档红线（**旧模式表必须人工归档** / 基线两项须登记
`l5-known-drift.yaml` / `pattern_id` 不许手改 / 选取口径不许放宽 / 跑完回 `l5_gate.py`）
→ `references/layer-playbook.md` §写档。

## 5. 停用条件（什么时候该下线本 skill）

- L5 被并入 `kb-review` 的判定入口、P0 不再单独成层 → **停用**。
- `kb/l5/p0_patterns.jsonl` 长期为空且无人维护（模式表失去可信度）→ **停用**，并把「是不是 P0」让回 `kb-review`。
- **停用前交接**：把 `p0_patterns` 现状结论、`matcher.py` 用法与写档红线迁进 `references/`，交 `kb-check` 归档。

**Gotchas（错误 → 修正）→ `references/gotchas.md`**
