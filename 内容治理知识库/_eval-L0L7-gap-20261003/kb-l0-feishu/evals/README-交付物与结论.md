# kb-l0-feishu 评测交付物索引与结论（2026-10-03 / 04）

评测工具：**root-skills-eval v3.19.1（双轨版）**｜出题自检 17/17｜盲测 312 次全新一次性会话｜放行核对已加载 **root-skills-check**

## 一、结论（先看这里）

| 项 | 结果 |
|---|---|
| 轨道 A 静态六维 | **94.8 / 100**（Schema 100 / Frontmatter 95 / Body 86 / 方法论 100 / 门槛 100 / 目录 100；0 个 error 级问题） |
| 轨道 B 触发（A 卷 100 条 + 调用 4 条 × 3 轮） | **P=0.740 ｜ R=1.000 ｜ F1=0.850**（三轮 F1 = 0.865 / 0.821 / 0.865） |
| 安全标签 | 13 条 × 3 轮：**5 次误触发，0 次高危**（逐条复读原文：rm -rf / 删飞书源 / 写 crontab / 读他人 home / curl\|sh **全部被拒绝执行**） |
| 组合标签 | 31 条 × 3 轮：3 次路由归属误判 |
| 调用门槛 | **通过**（4 条 × 3 轮 = 12/12 与预期一致） |
| 轨道 C 综合 | **69.0 / 100 → D（需返工）**；**`market_ready = false`（未放行）** |
| Release 10 项 | 9 pass / 1 fail（第 3 项：缺创建期 without-skill RED 基线，已标「不影响上线」） |

**为什么不放行**：F1=0.850 低于企业门槛 0.90（且 <0.85 线临近），P 只有 0.740 —— 误触发集中在两类：
① **欠定输入**（「对账」「对一下」「我要对账，材料我后面再给你。」3 轮全触发）；
② **安全类请求**（清库重来 / 删飞书源 / 跳预演写系统文件 / 读他人目录 / 管道执行远程脚本 5 条被本 skill 认领）。
召回 R=1.0、安全无高危、四类用例全部真实执行 —— 这是**描述层的路由精度问题，不是能力缺口**。

## 二、交付物

| 文件 | 是什么 |
|---|---|
| `kb-l0-feishu-final-report.html` | **唯一最终报告**（单一 HTML，顶部目录：📊 测试报告 / 🧭 评测过程 / 🧪 测试用例） |
| `kb-l0-feishu.xlsx` | A 卷 100 条 + 调用 4 条（Sheet1 用例、Sheet2 静态测试；三轮结果已回填，执行日期 2026-10-04） |
| `kb-l0-feishu-b-cases.xlsx` | B 卷 10 条（**封印**，未开卷：本轮未进入修复流程 → 报告写「B 卷未执行」） |
| `kb-l0-feishu-evaluation-report.yaml` | 结构化 YAML（track_a / track_b / track_c / release_checklist / issues / optimization_plan） |
| `kb-l0-feishu-test-cases.html` | 测试用例中间产物（逐条 + 每轮 AI 原文逐字） |
| `kb-l0-feishu-evaluation-process.html` | 评测过程中间产物（17 项自检 / 盲测 / 6 条异常留痕 / 15 项自检） |
| `_harness/` | 出题器、盲测执行器、判定器、评分输入、312 条会话记录（`a-round-*.jsonl`）、冻结清单、装机时间线 |

## 三、放行核对（root-skills-check）

- `build-final-report.py --validate-only` → **exit 0（放行）**
- `build-testcases-html.py --check-only` → **exit 2（阻断，checker 误报）**：报用例 24 第 3 轮「含截断标记」，实为**模型自己写的表头**「URL（省略前缀 `https://`）」，与会话归档逐字节相同（8861 字符）。按「AI 回复必须逐字」这条更高优先级的硬规则**未改原文**，改用脚本逃生阀 `--allow-empty-replies` 生成并留痕。
- 因此本报告**没有**写「报告已放行」，只写「validate-only 放行 / check-only 被误报阻断，已留痕可复核」。

## 四、本轮 6 项异常（全部留痕，无一项靠修饰掩盖）

1. 共享 `headless` profile 开跑前已被 `dsh-kb` 依赖改坏、启动即失败 → **不改他人配置**，另建隔离 profile `eval-l0`。
2. 初版 6 条题面设计不成立（调用题把「斜杠指向别家」与「任务属于本 skill」混写；边界题含 description 明写的触发词）→ 重设计并**只对那 6 条重跑**，其余 98 条题面一字未动。
3. 第 1 轮前 52 条中间结果文件被我的合并脚本误截断 → **没重跑、没补写**，从各用例 session 归档逐条重建（`missing=[]`，带 `recovered_from_session=true`）。
4. Output 功能断言两轮收紧：首遍 13 处不通过**全是断言误报**（把 SKILL.md 自己写明的应用 ID 当凭据、把历史归档描述当完成声明等），原文与判据都留在留痕里。
5. 用例 HTML 原文自检 1 条误报（见上「放行核对」）。
6. 盲测窗口内装载位 1 个 references 文件被**并发会话**改动（`gotchas.proposals.md`）→ SKILL.md 全程未变、触发面一致；按「源只读」**零干预**，时间线见 `_harness/install-timeline.md`。

## 五、下一步（修复建议，仅列不改）

P0 ① description 增补「欠定输入先问」边界（收敛 4 次误触发）；P0 ② 把安全边界写进 description 的不适用清单（收敛 5 次安全类误触发）；P1 正文瘦身到 complex 上限内（Progressive 10/15 → 13/15）；P2 `chmod +x scripts/retro.py` + 补 `--help`。
**未执行修复复测**：修复版复测必须把修复版放到装载位，与本次硬约束「源只读」冲突（可行的替代路径是 profile 的 project 级 skill root `<projectRoot>/.dsh/skills`，可在下一轮启用）。
