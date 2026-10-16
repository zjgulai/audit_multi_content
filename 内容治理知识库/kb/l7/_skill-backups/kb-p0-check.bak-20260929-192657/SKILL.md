---
name: kb-p0-check
description: |
  Momcozy 内容治理知识库 **L5（P0 判定层）** 的**只读查询**入口：
  回答「**这个是 P0 吗**」「这段命中哪些 P0 模式」「这条为什么被判最高优先级」。
  当用户问「这个是 P0 吗 / 算不算 P0 / 命中哪些 P0 模式 / P0 模式有哪些 /
  这段文字命中 P0 了吗 / 优先级是不是 P0 / 为什么是 P0 / L5 里有没有这条 /
  P0 清单给我看一下 / 这条触碰红线了吗（红线口径 = P0）」时使用。
  触发词：是不是 P0、这个是 P0 吗、命中 P0、P0 模式、P0 清单、P0 判定、最高优先级、
  p0_patterns、L5 查询、kb-p0-check。
  本 skill **只读**：只做确定性匹配与清单查询，不写库、不改 P0 模式表。
  重建 / 导出 P0 层是写操作，由 **kb-pipeline** 在 `--apply` 下编排
  `kb/.work/l5_prep.py RUN` → `kb/.work/l5_export.py RUN` 执行。
  不适用（各自点名）：
    · 查条款号 / 定稿了没有 → 走 **kb-canonical-lookup**；
    · 召回相关单元 / 查资料 → 走 **kb-recall**；
    · 判断一段内容能不能发（要三态结论）→ 走 **kb-review**；
    · 已经给出结论、要追问依据 → 走 **kb-content-review**；
    · 跑 L0 到 L7 / 同步知识库 → 走 **kb-pipeline**；体检 / 闸门 → 走 **kb-check**。
version: "1.0.0"
last_updated: 2026-09-29
license: "Proprietary — Momcozy internal use only"
complexity: "simple"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["长清单需分页"] }
  minimax: { status: "bridge", limitations: ["需中文优化"] }
  dsh: { status: "native", notes: "只读，kbpy 同机可用" }
  codex: { status: "native" }
---

# kb-p0-check —— L5 P0 判定层 · 只读查询

**一句话**：回答"**这个是 P0 吗**"。**只读**，只做确定性匹配。

## 1. 数据在哪

| 项 | 位置 |
|---|---|
| P0 模式表 | `kb/l5/p0_patterns.jsonl` |
| 匹配器（引擎） | `kb/l5/matcher.py` |
| 索引 | `kb/l5/index/` |
| 基准 | `kb/l5/benchmark.json` |
| 运行记录 | `kb/l5/runs/<RUN>-*.json` |
| 写操作（**本 skill 不调**） | `kb/.work/l5_prep.py RUN` → `.work/l5_export.py RUN` · `l5_bench.py` |

cwd 必须是 `kb/` 的上一级（`~/.dsh/Momcozy知识库`）。

## 2. 怎么判

```bash
cd ~/.dsh/Momcozy知识库
# ① 确定性匹配（给一段内容，看命中哪些 P0 模式）
kb/kbpy l5/matcher.py --text "<待判文本>" --json   # argparse：--text/--file/--json/--selftest
kb/kbpy l5/matcher.py --selftest                  # 自测：正例全命中、负例零误报（实测通过）
# ② 列 P0 模式清单
grep -c . kb/l5/p0_patterns.jsonl
# ⚠️ `kb/kbpy -` 不行（kbpy 只吃文件路径）。一次性片段用显式解释器：
KB_INTERP_OK=1 /usr/bin/python3 - <<'PY'
import json
for line in open('kb/l5/p0_patterns.jsonl',encoding='utf-8'):
    p=json.loads(line)
    print(p.get('anchor'), '|', p.get('authority'), '|units=', len(p.get('evidence_units') or []))
PY
```

**P0 的判据是"确定性命中"**：命中即 P0，不需要语义推断。
`p0_patterns.jsonl` 每条带 `anchor` + `authority` + `evidence_units[]`
（每个 unit 带 `unit_id` + `source_sha256`）——**引用时必须带上它们**。

## 3. 输出契约

```
是否 P0：是 / 否
命中模式：<anchor>（authority=<expert|...>）
命中片段：<逐字摘录>
证据单元：unit_id=<...> ｜ source_sha256=<...>
来源：kb/l5/p0_patterns.jsonl #<行号>
```

**"否"也要给出结论**：写"未命中任何 P0 模式"，并说明这**不等于**内容合规
（不命中 P0 只说明不是最高优先级，其余风险仍要按 `kb-review` 走）。

## 4. 红线

- **只读**：不调 `l5_prep.py` / `l5_export.py`，不改 P0 模式表。
- **不把"没命中"说成"没问题"**：P0 是"最高优先级"的口径，不是"合规"的口径。
- **不自己造模式**：清单里没有的说法，不许顺手归纳成一条新 P0；要加就交 `kb-pipeline` 走链路。
- **不给三态结论**：本 skill 只答"是不是 P0"，"能不能发"走 `kb-review`。

## 5. 何时停下来问人

- `matcher.py` 的命中结果与 `p0_patterns.jsonl` 不一致 → 报冲突，交 `kb-check`。
- 用户问的是一整段内容的合规性，而不是"是不是 P0" → 让位给 `kb-review`。
- P0 模式表为空（实测 `kb/l5/registry/` 下曾出现空数组）→ 如实报"P0 层为空"，
  不许用常见违规清单顶替。
