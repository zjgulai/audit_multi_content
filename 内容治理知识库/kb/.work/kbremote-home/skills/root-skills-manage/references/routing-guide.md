# Routing Guide - 路由决策详解

manage 的核心职责是**路由**：把用户请求分派给正确的家族成员。只路由，不越权执行。

## 路由表

| 用户意图示例 | 目标角色 | 成员 |
|--------------|----------|------|
| "创建/写一个新 skill"、"帮我做一个 skill"、"把这个流程变成 skill" | create | root-skills-creator |
| "这个 skill 有什么问题"、"为什么触发不准"、"帮我诊断" | diagnose | root-skills-doctor |
| "评估/评分这个 skill"、"质量怎么样"、"达到发布标准吗" | evaluate | root-skills-eval |
| "优化/改进这个 skill"、"根据报告修复" | optimize | root-skills-opt |
| "家族全景"、"成员列表"、"谁负责什么"、"帮我路由" | manage | 本 skill |

## 决策流程

```
1. 解析用户意图关键词
2. 匹配角色（create / diagnose / evaluate / optimize / manage）
3. 查注册表确认目标成员 status
   ├─ active   → 路由到该成员
   ├─ planned  → 告知"尚未创建"（当前所有家族成员均已建成 active）
   └─ 无匹配   → 询问澄清，或给出最接近的候选
4. 涉及多个角色时（如"创建并评估"），按依赖顺序串行路由：
   创建 → 结构质检（doctor，目录/规范问题） → 评估 → 优化
```

## 多角色请求示例

- "帮我写个 skill 并验证它好不好用"
  → 路由：root-skills-creator（创建 + Iron Law 真跑）
  → 随后：root-skills-eval（双轨评测，含输出前闸门）→ 低分则 root-skills-opt
- "这个 skill 一直误触发，帮我看看再改改"
  → 路由：root-skills-eval（先出报告）→ root-skills-opt（按报告修）；若只是目录乱则先 doctor

## 边界情况

| 情况 | 处理 |
|------|------|
| 请求模糊（"帮我看看 skill"） | 问一个澄清问题：是看质量、诊断问题、还是优化？ |
| 请求涉及非家族 skill | 不做家族路由，按普通请求处理 |
| 目标成员 planned | 提示未创建（当前无 planned 成员，全部 active） |
| 用户想创建新家族成员 | 走 manage 的 register 流程，不是 creator 的创建流程 |

## 原则

1. **只路由不执行**：manage 不实现创建/评估/优化的具体逻辑。
2. **家族版优先**：路由统一走家族版成员（eval/opt/doctor 均已 active），不再轻接外部生态。
3. **依赖顺序**：多角色请求按 create → diagnose（如需） → evaluate → optimize 顺序。
