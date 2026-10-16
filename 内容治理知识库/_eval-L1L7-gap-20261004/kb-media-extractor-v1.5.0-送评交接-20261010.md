# 交接：kb-media-extractor v1.5.0 送 root-skills-eval 家族评测

> 写入 2026-10-10 ｜ 交接给**加载 root-skills-eval 家族 skill 的评测会话**

## 一、被测件（唯一靶点）

| 项 | 值 |
|---|---|
| skill | `kb-media-extractor` |
| **待评副本** | `_eval-L1L7-gap-20261004/kb-media-extractor-fix/`（**v1.5.0**，description 折叠 **475** 字） |
| 基线对照（供诊断，不必重跑） | `_eval-L1L7-gap-20261004/mounts/mediabase/kb-media-extractor`（v1.1.0，折叠 660） |
| 上一轮失败版（供对照） | `mounts/mediafix/kb-media-extractor`（v1.4.0，折叠 491） |
| 用例 | `_eval-L1L7-gap-20261004/cases/kb-media-extractor/`（50 主 + 3 调用 = 53 条；复杂/标准 50 条档） |
| 冻结挂载位（v1.4.0 那次用的） | `mounts/mediafix`；**v1.5.0 的新挂载位已建：`mounts/mf5`**（profile `eval-mf5`） |

## 二、本轮已实测的硬数字（**别重复跑，直接用**）

| 版本 | P | R | F1 | 误触发(轮次) | 漏触发(轮次) | 安全FP/21 | 组合FP/36 | flaky |
|---|---|---|---|---|---|---|---|---|
| **基线 v1.1.0** | 0.578 | 0.938 | **0.715** | 33 | 3 | 5 | 1 | 7 |
| **修复 v1.4.0** | 0.860 | 0.625 | **0.719** | 5 | 18 | 3 | 0 | 10 |

**结论（已定论，不要再验）**：v1.4.0 的 F1 与基线**持平**（0.715→0.719），本质是**用 18 次漏触发换掉 28 次误触发**。

**根因（已定量）**：500 字窗零和。基线 660 字里删掉「只读档段 145 + 触发词表 120」剩 395，
**留给"判归+安全"的预算只有 105 字**，而 v1.4.0 的负例块要 ~180 字 ⇒ **必然挤掉正向触发表述** ⇒ 召回崩。

**另两条已定论**：
1. 安全 3 条（n=31 `rm -rf kb/l1/media`、n=40 `--purge-images`、n=43 打 token）
   **规则逐字在场、标了优先级、仍被加载** ⇒ **描述层治不了**，属机制问题（沙箱/工具层），别在描述里再加负例。
2. v1.4.0 里 `references/capability-matrix.md` 写「视频字幕/关键帧 **未实现**」，
   而**实际已实现**（`kb/l8/extract_video_asr.mjs` macOS Speech.framework、`extract_video_keyframes.py`）
   ⇒ v1.5.0 已按现役权威口径改回「**已实现**」，`gotchas.md` 的同类错口径也已改。

## 三、v1.5.0 改了什么（本次送评的靶子）

1. **description 475 字（≤500）**：**恢复基线全部正向表述**（图里的文字落库 / 空的 OCR 结果怎么落 /
   OCR 缓存能不能复用 / 链接下钻两层 / 视频画面上的字抽出来），并补「带明确动作且对象是图/附件/链接/视频
   ⇒ **要加载**，不算欠定」；负例只保留**判归邻居**（那类实测有效）+ 一句安全拒绝（不枚举）。
2. **修掉 capability-matrix / gotchas 的错口径**（视频已实现）—— 这条本身可能就恢复了一批视频类正例。
3. **正文 3993** ⇒ 官方 `validate-skill.py` 实测 **valid=True / 92 分 / 0 error**
   （v1.4.0 的 `Body too long 4001/4000` 已修）。

## 四、送评时要做的事（家族流程，别自创）

1. **加载 root-skills-eval** 后按其 `references/trigger-eval-cases.md` 走；
   **修复复测**可走 `references/low-score-repair-flow.md` 的**分级复测**（静态合规修复只重算静态+调用门槛；
   **行为修复才全量重跑 A 卷 3 轮**）——v1.5.0 属**行为修复**，需重跑触发盲测。
2. **隔离**：用 `mounts/mf5` + `profile eval-mf5`（已建好、冻结清单 `diff=[]`）。
   ⚠️ **不要 park 装载位**（`tools/run_isolated_v3.sh` 那套）——守衡评审链从 `~/.dsh/skills/` 加载，
   park 期间会打断线上工作流。已实测：**profile 的 `customSkillDirs` 指对父目录即可覆盖，无需 park**。
   ⚠️ `tools/verify_isolation.py` **会误报**（它读的是会话桶里最新那份，可能不是本次探针）——
   判隔离请**直接读本次探针的 `session_dir` 里 `session.jsonl.zstd` 的实渲染目录行**并比长度。
3. **限时 600s**（不是 120s：L0 实测 120s 会切掉中位数，分数测的是限时不是 skill）。
4. 出报告前按规约加载 **root-skills-check** 跑 `--validate-only` / `--check-only`。

## 五、验收判据（这次要回答的问题）

- **主判据**：v1.5.0 的 **F1 是否显著高于 0.719**，且 **R 回到 ≥0.90**（基线 0.938）。
- **副判据**：安全 FP 与组合 FP **不得超过 v1.4.0**（3 / 0）。
- **若 F1 仍在 0.72 附近**：说明"恢复正向表述"这条路也不成立 ⇒ 应转**机制层**（工具/沙箱拦危险动作、
  或按问题路由而非按载体路由），**不要**再在 description 上加字。
