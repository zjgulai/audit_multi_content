# kb-check 评测 · 终态（工作台 = 本目录）

- 对象：`kb-check` v1.1.0（被测副本 sha256 `77e6e6e8…`，与开测时源逐字一致）
- 复杂度：standard ⇒ A 卷 50（正16/负16/近似12/边界6）+ 调用 3 + B 卷 10（封印）× 3 轮 = 159 个真实一次性会话
- 工具：root-skills-eval v3.19.1（双轨）｜放行闸门：root-skills-check（--validate-only / --check-only 均 exit 0）

## 结果
- 轨道 A 94.3（Schema 100 / Frontmatter 92 / Body 96.7 / 方法论 100 / 门槛 100 / 目录 40）
- 轨道 B：P 0.617 / R 1.000 / F1 0.762（P、F1 未过企业门槛）｜安全标签 6 条 FP 3、高危 0｜组合 11 条 FP 4｜调用门槛 **未过**（9 次通过 3）
- 轨道 C **62.5（D）**，封顶前后同分；`market_ready = false`（两条独立成因：C<85 与调用门槛未过）
- Release 10 项：8 pass / 2 fail（第 3 项无 RED、第 10 项无停用条件，均「不影响上线」）/ 1 na

## 交付物
kb-check-final-report.html（唯一最终报告，顶部目录三大节）
kb-check-evaluation-report.yaml ｜ kb-check-test-cases.html ｜ kb-check-evaluation-process.html
kb-check.xlsx（A 卷 53 条，三轮已回填）｜ kb-check-b-cases.xlsx（B 卷 10 条，**封印未开**）
results-a.json ｜ _eval/（自检、取证、回填、账本、基线）

## 异常与降级（如实记录）
1. **源被改写**：`~/.dsh/skills/kb-check/SKILL.md` 与 `kb/l7/skills/kb-check/SKILL.md` 于 2026-10-03 22:59:11 由**第 1 轮 #17 被测会话**（kb-repair 路线）edit，sha 77e6e6e8→fd26fccb（纯新增 5 行注释，description/触发词未变）。回填员未写源，未还原。
2. **并发会话污染**：#33 被测会话（route 到 root-skills-eval）自行读 cases-a.json 跑了整轮评测，spawn 161 个同题面会话并写入 `_eval/results-r1-only.json` 等外来产物 → 统计已按 `parentSession` 隔离。
3. **降级**：无（3 轮均为真实独立会话，未串行降级、未编造）。
