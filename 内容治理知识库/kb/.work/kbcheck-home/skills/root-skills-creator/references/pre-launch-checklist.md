---
title: Pre-Launch Checklist（上线前审查清单）
doc_type: checklist
module: root-skills-creator
topic: pre-launch-checklist
status: stable
created: 2026-08-31
updated: 2026-09-01
owner: self
source: human+ai
---

# Pre-Launch Checklist（上线前审查清单）

Skill 上线（release 模式）前必须逐项通过的 **10 项审查清单**。任何一项不通过，禁止发布，回到对应参考补齐后再复审。

## 10 项审查清单

| # | 审查项 | 通过标准 | 对应参考 |
|---|--------|---------|---------|
| 1 | 真的有必要做成 Skill 吗 | 无该 Skill 时 agent 会稳定犯错 / 误触发 / 漏触发；非通用命令、一次性上下文、机械约束 | `skill-design-boundaries.md`「创建前检查」、Iron Law |
| 2 | 适用 / 不适用边界是否清楚 | description 明确「何时用」+「何时不用」，相邻但不应触发的场景已列出 | `skill-design-boundaries.md`「Description 边界」 |
| 3 | 是否先写了 eval | 先有 RED 失败基线（真实运行 without-skill 失败证据），再写正文 | `iron-law-testing.md`、`eval-loop.md` |
| 4 | description 是否以「Load when」开头 | 第一句描述触发时机（中文家族版等效写法「当用户…时使用」），而非功能列表；关键触发词前置 | `cso-optimization.md`、`cross-model-adaptation.md` |
| 5 | 是否描述用户意图而非功能 | description 写用户会怎么说 / 何时需要，而非 Skill 内部能做什么 | `cso-optimization.md` |
| 6 | SKILL.md 是否只保留高信号内容 | 只留行为改变规则、领域判断、gotchas、读取条件；通用背景 / 常识已删 | `skill-design-boundaries.md`「Body 边界」 |
| 7 | runtime 文件是否有明确读取条件 | references / assets / scripts 何时读取在主文件写明，无默认全量加载 | `skill-design-boundaries.md`「Progressive Loading」 |
| 8 | 是否定义权限与审批边界 | 明确安全边界（恶意请求不触发）、危险操作与越权读取的拒绝规则 | `skill-design-boundaries.md`、doctor D108-D109 |
| 9 | 是否有 positive / negative / e2e eval | 补齐 positive loading、negative / forbidden loading、boundary 与端到端真实运行评测 | `eval-loop.md`、`loading-routing-evaluation.md` |
| 10 | 是否准备了维护与退役机制 | 有维护闭环（gotcha 优先）与生命周期状态机（active → deprecated） | `skill-design-boundaries.md`「维护规则」、manage `lifecycle.md` |

## 审查结论

```text
□ 全部通过（可发布）
□ 存在异常（异常项：#___，说明：________）
  → 禁止发布，回到「对应参考」补齐后复审。
```

> 评测**已有** Skill（非本次创建）时，第 3/9 项怎么取证见 `root-skills-eval/references/release-checklist.md`「评测已有 Skill」。创建新 Skill 仍按本清单：先 RED 再写正文。
