# kb-recall 评测 · 断点续跑状态（工作台：`_eval-L0L7-gap-20261003/kb-recall/evals/`）

- 对象：`kb-recall`（源 `/Users/lute/.dsh/skills/kb-recall`，**只读**；被测副本 = 上级 `kb-recall/SKILL.md`）
- 源 ↔ 副本逐字一致：`sha256 = 96f010037d3e1da79b4e64a420784262cd8f165015d52aec797c886732f740cc`（`_eval/source-baseline-*.sha256`）
- complexity: `standard` ⇒ A 卷 50（正 16 / 负 16 / 近似 12 / 边界 6）+ 调用 3 + B 卷 10（封印）× 3 轮
- 工具：root-skills-eval v3.19.1（`references/trigger-eval-cases.md` 为唯一权威步骤源）
- 被测会话：`DSH Desktop --profile eval-l0`（headless 一次性会话，**每个用例一个独立 cwd**，只发「提示词」列原文）
- 证据口径：`_eval/read_session.py` 读 `~/.dsh/sessions/<bucket>/<uuid>/session.jsonl.zstd`；触发 = `skill` 工具加载了 `kb-recall`
- **09-30 那批（`_eval-kb-recall-20260930/`）只用于了解探针做法，题面与结果一律从零重出/重跑，不复用。**

## 进度（以磁盘为准）

- [x] 0 建工作目录 + 源只读基线 + 会话证据器验证（smoke 会话实测加载 kb-recall）
- [x] 1 出题 A/B 卷 → JSON + Excel
- [x] 2 出题 17 项自检（首轮 14/17 → 修正后 17/17，见下）
- [x] 3 盲测 3 轮（第一遍作废 → 第二遍隔离 → 第三遍密封重跑；生效 189 条，答案键泄漏 0）
- [x] 4 轨道 B P/R/F1 + 标签统计（P 0.678 / R 1.0 / F1 0.807；调用门槛未过）
- [x] 5 轨道 A 静态六维 94.8 + 轨道 C 72.4 → YAML
- [x] 6 root-skills-check 硬校验（--validate-only exit 0；--check-only exit 2 误报已留痕）
- [x] 7 最终报告单一 HTML + score.json + README

## 事故记录 · 第一遍盲测作废（cwd 泄漏）

- **现象**：第一遍把每条用例的 cwd 放在 `evals/work/<paper><round>/item-XXXX`，被测会话
  从自身 cwd 用 `ls ..` 就能走到回填员侧产物，**38 个会话真读了 `cases-a.json` / `cases-b.json`**
  （含「预期结果」列）——另有 36 个只在目录列表里看见文件名。
- **取证**：`_eval/contamination_scan.py` 逐会话扫 `tool/call` 参数（严格）与 `tool/result`（宽松），
  结论落 `_eval/contamination-*.json`。典型样本：`a-r1 item-0053`（`/kb-recall` 那条）
  读了 `cases-a.json` + `STATE.md` + `rounds/a-round1.jsonl`。
- **处置**：全批作废、原件留在 `rounds-INVALID-cwdleak/` 与 `work-INVALID/`（留档可审，**不参与任何计分**）；
  `rt.py` 改为 cwd 落在**评测产物树之外**（`/tmp/kbrecall-eval-cwd/<paper><round>/item-XXXX`）；
  复核器必须用 `realpath`（macOS `/tmp` → `/private/tmp`，否则找不到会话目录）。
  第二遍**同题重跑**（题面未改：被测会话收到的始终只有「提示词」列原文，第一遍泄漏的是会话自己翻到的文件）。
- **口径**：本报告所有 A/B 卷数字**一律取自第二遍（隔离 cwd）**；第一遍数字不作为任何结论依据。

## 自检首轮不通过项的处置（留痕）

- 第 5 项（表头合规）：**自检器写错**（拿 JSON 键 `id` 去比 Excel 表头「序号」）→ 改为只比 Excel 表头。
- 第 14 项（B 卷独立性）：**自检器判据过粗**（3 字短句的 2-gram 覆盖率恒为 1.0）→ 改为 Jaccard 且短句不参与比较。
- 第 17 项（中英混写配额）：**题面不合规**（16 条正例只分出 4 条混写，目标 6）→ 重写第 10、11 题的题面
  （第 10 题补 `cleaning`/`unit`，第 11 题把 `semantic recall` 收回为中文，使汉字数 > 拉丁字母数且夹 ≥2 个业务英文词），
  重出后 8 纯中文 / 6 混写 / 2 全英文，17/17 通过。


## 最终结果（2026-10-04）

- 轨道 A **94.8**（0 error）｜轨道 B A 卷 **P 0.678 / R 1.000 / F1 0.807**（逐轮 0.80 / 0.842 / 0.78）
- 安全标签 6 条 × 3 轮，FP 4、**高危 0**；组合标签 9 条，FP 2；**调用门槛未过**（7/9）
- 轨道 C **72.4**（C 及格，Output 14.2 < 15 触发 ≤79 封顶但未抬分）；**market_ready = false**
- B 卷（封印，本轮按用户要求开卷执行）3 轮平均 **F1 0.786**，未过 0.85 门禁线
- 闸门：`--validate-only` **exit 0**；`--check-only` **exit 2**（用例 42 真实原文命中摘要启发式 → 经
  189/189 条逐字节比对判定误报，未改字，走 `--allow-empty-replies` 并留痕）
- 盲测完整性：生效记录 189 条，**答案键泄漏 0**；189/189 条回复与会话归档逐字节一致
- 产物：`kb-recall-final-report.html`（唯一最终报告）/ `kb-recall-evaluation-report.yaml` / `score.json` /
  `kb-recall.xlsx` / `kb-recall-b-cases.xlsx` / `README-交付物与结论.md`
- **未做修复**：源只读硬约束与「修复版落装载位并排交付」冲突 → 只出裁决，不建 fix 副本
