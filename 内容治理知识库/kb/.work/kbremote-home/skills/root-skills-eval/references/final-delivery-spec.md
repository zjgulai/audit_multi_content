# 最终交付物规格说明 (Final Delivery Spec)

> 本文是 `SKILL.md`「快速开始 → 最终交付物」的详细规格。正文只保留要点摘要，完整规则见本文。

## 主交付物

`{skill-name}-final-report.html`：单一 HTML + 顶部目录「📊 测试报告 / 🧭 评测过程 / 🧪 测试用例」。

### 📊 测试报告必须含

- 总结论
- 多次数据对比（轨道A/F1/P/R/flaky/error/轨道C）
- 三轮执行与评分总览（**轨道 A/B/C 计算公式分别放在对应轨道数据/分项表下方**）
- 用例分配比例
- 安全与组合标签汇总（并入「二、测试用例分配比例」）
- 修复问题清单
- Release 10 项（逐项判分 + 是否影响上线）

### 🧭 评测过程必须含

- 出题自检 / 3 轮 / 静态 / 低分修复 / B 卷门禁 / 输出前自检
- Step 5.5「输出前自检」结论

### 🧪 测试用例必须含

- 分配比例 / 通过率
- **最终版 A 卷、B 卷、调用、标签用例（安全/组合）**
- 全部用例与每轮 AI 原文——**逐字保留，禁止提炼**

## 生成规则

- `build-final-report.py` 合并 YAML；`--cases/--process` 传文件路径时内联。
- 生成前先加载 `root-skills-check`（`--validate-only` / `--check-only`，细则见 `trigger-eval-cases.md` Step 5.4）。
- 多版本时「🧪 测试用例」必须内联最终版本（最后一次重测）生成的 `{skill}-test-cases.html`（A 卷 + `--b-results` 的 B 卷 + 调用 + 标签）。
- `--cases` 禁止指向源版/旧版。
- v3.17.1 硬校验覆盖 A 卷四格对账、调用、标签、B 卷区。
- 🧪 内通过率 / 逐条用例 / AI 原文一律取最终版；📊 测试报告与 🧭 评测过程保留不变、不贴逐条。

## 版本一致性（v3.17.4 硬性）

最终报告最后一版 `eval_info.version` 必须等于交付 fix 目录的 `SKILL.md version`。Excel / 清单回填的 `修复版本 / 首次C / 修复后C / 上线` 必须取自**同一最终版评测**（分数与最终版 YAML / 最终报告对账）。

**生成最终报告后禁止再改 fix 而不重生成报告**：任何升版本 / 改 description / 修 B 卷门禁的动作，必须用新版本 YAML 重新生成并替换 `{skill-name}-final-report.html`。fix 目录版本 > 最终报告版本、或回填分数无最终报告支撑（含把「预估 / ≥」当实测）时，禁止标记上线与交付，先补最终版评测与报告。

## 中间产物

- `{skill-name}-test-cases.html`：由 `build-testcases-html.py` 生成（含原文回复自检：空/模板/摘要/截断拒绝）。**每次重测后都须用当轮 results.json 重新生成（已开卷加 `--b-results`），最终报告只内联最终版本那一份（v3.17.0）**。不独立交付。
- `{skill-name}-evaluation-process.html`：须含 Step 5.5「输出前自检」结论。不独立交付。

## 交付方式

只交最终 HTML 本身（目录跳转；静态托管或 file:// 均可）。`--cases/--process` 缺失或为 http(s) 时对应部分占位 + warning。

## 低分修复旗标

低分修复（多版本）时必须 `--require-desktop-fix`；一次达标不加此旗标、不要求 skill 已在桌面。