# Output Contract - 输出契约

**核心原则**: 每次任务明确交付物，不做无边界产出。

任务开始前明确"这次交付什么、明确不交付什么"，防止两种情况：
- 过度产出（把审计做成了重构，把探索做成了发布）
- 产出不足（交付了文件但没交付边界说明/理由）

## 三类任务契约

### 1. 构建 (build) —— 创建或改进 skill

交付物：
- `SKILL.md`（frontmatter + body）
- 对齐的接口（description 触发条件与正文一致）
- 有理由的资源（scripts/references/examples，每个都要能回答"为什么需要"）
- **边界/门禁小结**：做了什么、没做什么、评测结果、剩余风险

### 2. 审计 (audit) —— 评估/诊断现有 skill

交付物：
- findings（发现的问题，按严重程度分级）
- fixes（修复建议，具体到文件/位置）
- **仅当被明确要求时才修改文件**——审计默认只读，不动用户文件

### 3. no-skill —— 判断不该建 skill

交付物：**零文件** + 理由说明。

触发 no-skill 的情况（对照 `references/skill-design-boundaries.md`）：
- 一次性任务（没有 repeated use）
- 没有可复用的输出契约（每次产出都不同）
- 通用命令/常识，agent 不需要 skill 就能做对
- 模板填空式流程，没有非平凡判断

## 入口过滤

每次"创建 skill"请求，先跑这个判断：

```text
Q1: 这个工作会被反复使用吗？      否 → no-skill
Q2: 有稳定的输出契约吗？          否 → no-skill
Q3: 没有 skill 时 agent 会做错吗？ 否 → no-skill（或只是普通文档）
Q4: 是（→ 进入 build，模式分级见 operating-modes.md）
```

## 每次任务先采集

开始前确认五元组（能推断则推断，核心的才问）：

```text
job:         要做什么（一句话）
output:      交付物是什么
exclusions:  明确不做什么
constraints: 约束（路径、格式、依赖）
standards:   遵循什么标准（schema、命名、门禁）
mode:        explore / release
```

## 边界小结模板

每次 build 完成，交付一段小结：

```markdown
## 交付小结
- 已交付: [SKILL.md / scripts / references ...]
- 未交付: [明确没做的部分]
- 评测: [pass_rate, delta, 关键断言结果]
- 门禁: [通过/未通过项，release 模式]
- 剩余风险: [已知局限、待确认假设]
```
