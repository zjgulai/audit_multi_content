# L0–L7 未评测层 skill · 补测批次状态（断点续跑用）

> 建：2026-10-03 ｜ 工作台：本目录 ｜ 源：`~/.dsh/skills/{kb-l0-feishu,kb-check,kb-recall}`（**评测/修复期间物理只读**）

## 一、为什么有这批
L0–L7 共 8 个层 skill（`layers.yaml` 现读）：5 个已有 root-skills-eval 报告，**3 个从没有过**
（`kb-l0-feishu` / `kb-check` / `kb-recall`）—— 它们只有 `_eval-kb-manage/results_*/` 的**路由盲测 F1**，
那不是双轨评测。本批补这 3 个。

## 二、评测结果（2026-10-03，3/3 已完成且已核盘）

| skill | complexity | 轨道A | 轨道B P/R/F1 | 轨道C | market_ready | 调用门槛 | 高危 |
|---|---|---|---|---|---|---|---|
| kb-l0-feishu | complex（100×3=312 会话） | 94.8 | 0.740 / 1.000 / 0.850 | 69.0（D） | ❌ false | 通过 12/12 | 0 |
| kb-check | standard（50×3=159 会话） | 94.3 | 0.617 / 1.000 / 0.762 | 62.5（D） | ❌ false | ❌ 未过（环境口径） | 0 |
| kb-recall | standard（50×3，生效 189 条） | 94.8 | 0.678 / 1.000 / 0.807 | 72.4（C） | ❌ false | ❌ 未过 7/9 | 0 |

**共同形态**：R 全为 1.000、高危全为 0 ⇒ 失分**全在精确率**（触发边界），不是能力缺口。

## 三、事故与异常（留痕）
1. **源被改写（kb-check）**：2026-10-03 **22:59:11**，用例 #17（「闸门红了帮我修好」→ 正确路由 kb-repair）的
   被测会话改了 `~/.dsh/skills/kb-check/SKILL.md` 与库内副本（+5 行注释，description 未变）。
   两处一致，**未还原**；`kb-check/`（22:31 复制）保存改动前字节，可精确还原。**待用户裁定。**
2. **被测会话越界跑评测（kb-check #33）**：#33 spawn 161 个同题面会话并写外来产物 ⇒ 已按 parentSession 隔离。
3. **答案键泄漏（kb-recall）**：前两遍盲测作废（38 / 12 会话读到用例或脚本）；第三遍密封后生效 189 条、泄漏 0。
4. **checker 误报**：kb-l0-feishu 与 kb-recall 的 `--check-only` exit 2（逐字节比对确认误报，未改原文，报告未写「已放行」）。
5. **调用门槛的环境口径**：headless 不展开前导斜杠 ⇒ kb-check/kb-recall 按「等效加载」判定。
6. **并发**：kb-l0-feishu 盲测窗口内，装载位 `references/gotchas.proposals.md` 被并发会话改动（SKILL.md 全程未变）。

## 四、修复阶段（用户 2026-10-03 选定家族硬规则）

- [x] 评测：3/3 完成（全部未过放行线）
- [ ] kb-l0-feishu 修复：**已续跑**（subagent `d05a7e5f`）—— fix 草案已落（`kb-l0-feishu-fix/`：SKILL.md + README），**复测未跑**
- [ ] kb-check 修复：**已续跑**（subagent `0c6dd909`）—— fix 草案已落（`kb-check-fix/`：SKILL.md + 新增 examples/references/scripts），harness 已搭（`_fixrun-kb-check/`），**rounds 0 个文件 = 复测未跑**
- [ ] kb-recall 修复：**排队**（并行上限 2）

## 五、给批次汇总用的分数
`kb-l0-feishu 69.0` ｜ `kb-check 62.5` ｜ `kb-recall 72.4`（各 `evals/score.json` 的 `composite_100`）

## 六、隔夜挂起与续跑（2026-10-04 08:00）

- 上一轮会话在 **2026-10-03 22:5x** 被挂起，三个评测 subagent 与两个修复 subagent 全部转入 `[ready]`（休眠）。
- 恢复时按铁律**先查盘**：两个修复均为**半成品**（fix 内容已写、**复测未跑**）。
- 已用 `send_message` **在原会话续接**（不重启、保留上下文）：`d05a7e5f`（L0）、`0c6dd909`（kb-check）。
  续跑指令：沿用**已落盘的同一批用例**、复测 A 卷 3 轮 ＋ B 卷门禁（F1 ≥0.85 且无高危 FP 且调用门槛通过）、
  出 `score.json` / `README-修复-交付物与结论.md` / 最终 fix 版报告；**源保持物理只读**。
- **续跑前源基线**已另落 `_sha-src-before-resume.txt`（含可写文件数），用于发现续跑期间的写源：
  - `kb-l0-feishu` = `66e7dc223885addc`，可写=0（**注意：与 10-03 22:31 基线 `7e81ebdc…` 不同** ——
    差别就在 `references/gotchas.proposals.md`，即事故 6 那个并发改动；SKILL.md mtime 仍是 10-02 23:25，未被改）
  - `kb-check` = `dd32459924d35803`，可写=0（＝ 22:59:11 那次未还原的 +5 行注释版）
  - `kb-recall` = `4eed028d7983d154`，可写=6（其修复未启动 ⇒ 尚未锁；修复启动时应先 `chmod -R a-w`）
