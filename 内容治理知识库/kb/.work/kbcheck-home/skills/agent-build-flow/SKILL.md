---
name: agent-build-flow
description: |
  把一个模糊业务需求推成能上线的 Agent 包：入口三筛 → 无情追问 → TUI 跑通 → 规格 → 垂直切片拆解 → TDD 开发 → 验证上线 → 交接迭代，全程 20 道门禁。
  当用户说"要做个 agent"、"建一个智能体"、"这个需求要不要做成 agent"、
  "agent 开发流程"、"从问题到上线"、"agent 规格"、"agent 契约"、
  "交付物定义"、"给 agent 出题"、"接缝怎么选"、"怎么拆工单"、
  "agent 上线判定"、"agent 交接"，或要给某个业务问题从头做一套 Agent 时使用。
  触发词：agent 立项、做个 agent、建一个智能体、agent 开发流程、从问题到上线、
  agent 规格、agent 契约、交付物定义、给 agent 出题、上线判定、接缝选择、
  工单拆解、agent 交接、build an agent、agent spec、agent contract、deliverables。
  不适用：只评测已完成的 agent 包（走 root-agents 家族的 root-agent-doctor / root-agent-eval，**不是** root-skills-eval——那个家族只认 SKILL.md）；**只要一个能跑的成品包、不要开发流程**（走 root-agents 家族的 root-agent-creater）；只创建 Skill 不是 Agent（走 root-skills-creator）；只把素材蒸成 Skill（走 蒸馏）；只拆工单、不涉及 Agent 立项（走 to-tickets）。
version: "1.1.1"
complexity: "complex"
enabled: "true"
disable-model-invocation: false
user-invocable: true
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
---

# Agent 从立项到上线

本技能管**流程**，不管评测标准。评测入口一律复用已有家族，本技能只负责让流程不跳步、产出物对得上。

**主链路**：入口三筛 → 追问 → TUI 跑通 → 规格 → 拆解 → 开发 → 验证上线 → 交接迭代

---

## 一、入口三筛：该不该做 Agent

三条**全中**才做，缺一条就停下并说明该走什么路：

| 筛子 | 通过条件 | 不通过走哪 |
|---|---|---|
| 结果是否不确定 | 同一输入不保证同一输出，靠判断不靠计算 | 确定性脚本 / 规则引擎 / 表格公式 |
| 是否需要人在回路 | 关键节点要人确认、校准、拍板 | 全自动批处理 |
| 是否会重复使用 | 这件事会反复发生（**≥3 次**） | 一次性任务，直接做完 |

**默认取向：垂类优先，不做通用。** 通用 Agent 行业属性弱、知识库散，做出来什么都不精。

产出《立项一页纸》四行：要解决的问题 / 现在谁在做、多久一次、错在哪 / 做出来谁用、什么场景用 / **不做的后果**。写不出第四行的，先别做。

三条全中 → 进阶段 1。不中 → 说清理由和替代路径，停。

---

## 二、七阶段主干与准出门禁

每阶段一行，细节读 `references/phases.md`。

| 阶段 | 做什么 | 准出门禁（不过就回退） |
|---|---|---|
| 1 问题与调研 | 无情追问，把模糊需求逼成可量化问题 | 7 问都有答案 + **需求方确认方向**（且方案**不限于一个**） |
| 2 方案与规格 | TUI 先跑通 → 原型验疑点 → 写 7 段规格 | **真跑通过一次** + 接缝已与用户确认 + 范围外写清 |
| 3 目标与拆解 | 拆垂直切片工单，声明阻塞边 | 切片纵向贯穿 + 阻塞边正确 + **用户批准后才发布** |
| 4 开发 | 在约定接缝上 TDD，一次一片 | 接缝未确认不写测试 + **红先于绿** |
| 5 验证与上线 | 双轴 review + 三级验证 + 门禁 | 双轴都过 + `composite_100 >= 85` + **明显优于裸模型** |
| 6 上线与沉淀 | 交接、迭代、蒸成 Skill | 留出集与强度门禁不下降；重复 ≥3 次的动作交给 `蒸馏` |

**阶段 1 的追问纪律**（细节见 `references/phases.md`）：把决策建成设计树，每轮只问 frontier（前置已定、现在就能问的）那一层，编号 + 附推荐答案，**然后停下等答复**。两条硬规矩：**查事实是 Agent 的活**（能自己查到的别问用户）；**决策是用户的**（不许替他拍板）。frontier 空了才算完。

**阶段 2 反共识的一条**：**不先写 PRD**。先用 TUI + 通用 Agent + 你的 RAG/Skill 把这个问题真解决一次，拿到一个真实可用的答案，再把解决路径逆推成多步工作流，**然后**才补规格与文档。原因：先跑通，"方案行不行"几十分钟就有答案；先写 PRD，要等工程做完才发现方案不成立。

**原生 Agent 判据**：每个点击 90%~100% 都在调大模型，而不是在执行确定性脚本。达不到这条，回入口三筛。

---

## 三、两条最值钱的转换规则

规格写完后要落到 `agent.yaml`。这一步模型默认会做错，必须逐字对照 `references/spec-to-contract.md`。

### 规则 1：实现决策 → 契约字段

| 规格里写的 | 映射到 | 常见错误 |
|---|---|---|
| 要建/改的模块、接口、架构决策、API 契约 | `interface` / `input` / `profile` / `task_types` / `tools` | 把散文整段抄进 yaml，字段对不上 |
| 技术澄清、schema 变更 | `deliverables[].fields` | 漏字段，导致评测覆盖不到真正要交的活 |
| 密钥、端点 | `env`，一律 `${managed}` | 写死字面量（硬门禁，直接不通过） |

### 规则 2：用户故事 + 交付物 → `deliverables[]`

**`deliverables` 决定"这个 Agent 能干几件活"，数活儿 = `len(deliverables)`。**

判据：**交出去的东西不一样 → 两件活；一样 → 一件活。**

不算活的东西（写进去会让数量虚高）：工具、skill、行为约束（安全 / 不编造）、同一交付物的变体。

硬校验：每件活都要能写出一条工作流（输入 → 步骤 → 交付物）。写不出的，不是一件活。

`acceptance` **必须用业务语言写**，不许写"函数返回 200"这类实现细节——业务方要看得懂，评测也要映射得上。完整规则与反例读 `references/deliverables-rules.md`。

---

## 四、必须停下来的四个点

这四处**不许替用户决定**，做完分析后停下等确认：

1. **需求方向**：7 问答完，方案方向（且给不止一个方案）→ 没确认不进阶段 2
2. **接缝**：在哪个边界上测试 → 写规格时就要确认，**改接缝等于返工**
3. **拆解粒度**：工单编号列出后问三件事——粒度合适吗 / 阻塞边对吗 / 有没有该合并或再拆的 → 迭代到批准为止
4. **上线判定**：`composite_100 >= 85` 且未环境降级且证据强度 strong 且明显优于裸模型 → 任一不满足就**不放行**

---

## 五、本技能能自己做的、和只能请用户做的

`/to-spec`、`/to-tickets`、`/implement`、`/handoff`、`/grill-with-docs`、`/setup-matt-pocock-skills` 是 **user-invoked**（`disable-model-invocation: true`）——**任何 skill 都调不动它们，只有人手动敲 `/命令`**。别写"本技能会调用 /to-tickets"，那是错的。

| 环节 | 处理方式 |
|---|---|
| 追问机制 | 若 `/grill-with-docs`、`/grilling` 已装 → **文字引导**用户跑；判据本技能也内置了一份，未装则直接自跑 |
| 规格 | 引导用户跑 `/to-spec`；未装则用 `assets/templates/spec.md` 兜底 |
| 原型 | 内置"一个原型只回答一个设计问题"的判据 |
| 拆解 | 内置垂直切片四规则 + 阻塞边写法 + expand–contract 例外 |
| 开发 | 引导用户跑 `/tdd`；内置接缝选择规则与红-绿-重构判据 |
| 双轴 review | 引导用户跑 `/code-review`；内置两轴判据 |
| 交接 | 引导用户跑 `/handoff`；内置交接文档契约 |

**动手前先跑一次 `bash scripts/check-flow.py --probe`**，看本机到底装了哪些命令，按实际结果引导——不要凭记忆假设。

**原则**：命令已装 → 只做文字引导，不假装能自己调；判据命令覆盖不到 → 一律内置。

---

## 六、产出物清单

| 阶段 | 产物 | 存放 |
|---|---|---|
| 0 | 立项一页纸 | 项目目录 |
| 1 | 解决方案文档 | 项目目录 |
| 2 | 规格（7 段） | issue tracker，打 `ready-for-agent` |
| 2 | 原型 | 一次性分支，不混进主代码 |
| 3 | 工单（**一票一文件**） | `.scratch/<slug>/issues/NN-slug.md` |
| 4 | 代码提交 + 交接文档 | 分支；交接文档放**系统临时目录** |
| 5 | 双轴 review 报告 + 评测报告（**只交付 HTML**） | 仓库 / `<agent>/evals/report.html` |
| 6 | 成长记录 | `memory/growth.json` + `growth.md` |

模板在 `assets/templates/`：`one-pager.md` `solution.md` `spec.md` `ticket.md` `handoff.md` `agent.yaml`。

**交付口径：给用户只给 `.html`，不附 `.json`。** `report.json` 是内部机器契约。

---

## 七、三条不能碰的铁律

1. **判分只用确定性方法**。期望写成 `must_contain` / `must_not_contain` / `answer_non_empty`；判不了的不留中间态——拿不出可校验的作答一律判 `fail`，**绝不编造标准答案**。
2. **工具不够的题在出题期就剔除**。`case.tool_required ⊆ agent.tools` 不成立就不出这道题，如实记进 `cases.json` 的 `ineligible`。
3. **环境问题不能伪装成能力或成长**。缺模型端点时如实标 `environment_degraded` / `insufficient_evidence`，**绝不跳过输出、绝不谎报提升**。

## 七点五、三个不能混的口径

| 你问的 | 看什么 |
|---|---|
| 要不要修？ | 看分数低不低 |
| 能不能交付？ | 看两道门禁：**留出集 + 判定强度** |
| 能不能发布？ | **只看 `composite_100`** |

混着用会得出错误结论——最常见的是「分数够了就以为能交付」。详见 `references/release-gates.md`。

## 八、其他必守细节

- **判分走完整 stdout**（`stdout_full`）；`stdout_head` 只用于报告展示。拿截断串解析会让大输出 Agent 恒判 error。
- **非零退出码不等于崩溃**：它是结论信号（unhealthy / fail 时退出非零）。判据是"能否解析出 JSON 对象"。
- **`evals/` 目录不算被测方缺陷**：密钥与静态扫描都要跳过它，否则安全用例的假密钥夹具会反过来把评测器自己判成不达标。
- **判定强度**：`real` / `structural` / `none`。**任何一轮都没有 `real` 用例时，必须写明"本次评测不代表能力水平"。**
- **内容类问题绝不自动修**：改提示词让某个 `must_contain` 通过是针对测试集过拟合。`structural` 可自动修，`content` 交还人工，`environment` 改码无效。
- **修复只改副本，源只读**；回归通过才放行；封顶轮数超限如实标"修复失败"。

---

## 什么时候读哪个文件

| 情况 | 读 |
|---|---|
| 走具体某个阶段、要模板和准出判据 | `references/phases.md` |
| 要过 20 道门禁的逐条判定 | `references/gates.md` |
| 规格要落成 `agent.yaml` | `references/spec-to-contract.md` |
| 数不清这个 Agent 能干几件活 | `references/deliverables-rules.md` |
| 选接缝 / 拆工单 / 遇到宽重构 | `references/seams-tickets.md` |
| 不知道哪个环节该用哪个模型 | `references/model-routing.md` |
| 踩到坑、想先看看别人怎么错的 | `references/gotchas.md` |
| 分不清「要不要修 / 能不能交付 / 能不能发布」 | `references/release-gates.md` |
| 要一个走完全程的样例 | `examples/brand-pr-walkthrough.md` |

## 常用命令

```bash
python3 scripts/check-flow.py --probe                    # 探测本机装了哪些配套命令
python3 scripts/check-flow.py <项目目录>                  # 校验阶段产出物 + 契约
python3 scripts/check-flow.py <项目目录> --contract-only  # 只校验 agent.yaml 契约
python3 scripts/render-contract.py spec.md -o agent.yaml  # 规格 → agent.yaml 草稿
python3 tests/test_check_flow.py                          # 自检脚本的回归测试
python3 tests/test_render_contract.py
```

## 边界（不做什么）

- 只评测已有的 agent 包 → **`root-agents` 家族**：②`root-agent-doctor` 体检（`verdict` / `blockings`）、③`root-agent-eval` 评分出 `evals/report.html`、修复走 ④`root-agent-opt`、跨轮成长走 ⑤`root-agent-check`。
  **不是 `root-skills-eval`**——那是 Skill 家族，只认 `SKILL.md`；把含 `agent.yaml` 的包喂进去会判「SKILL.md not found」，结构不通过、分数封顶 30。
- 只体检 agent 包结构 → `root-agents` 家族的 `root-agent-doctor`，本技能不重复
- 只创建 Skill（不是 Agent）→ `root-skills-creator`
- 只把素材蒸成 Skill → `蒸馏`
- 只是写业务文档、不涉及 Agent → 不触发本技能

## 维护与停用

- **维护**：踩到新失败模式 → 追加进 `references/gotchas.md`（"错误 + 修正"格式），**不重写整篇**；判据变了 → 改 `references/phases.md` / `gates.md`，不在正文堆细节。
- **停用**：本技能被更新的流程取代时，在 `description` 开头标 `【已停用，改用 <替代技能>】`，保留目录不删（历史项目的 `agent.yaml` 与门禁判据仍需可查）；同时把 `version` 递增并在此处记一行停用原因与日期。
