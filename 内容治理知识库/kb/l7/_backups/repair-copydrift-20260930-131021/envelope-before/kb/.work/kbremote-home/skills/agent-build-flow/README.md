---
title: agent-build-flow - 快速开始
doc_type: readme
module: agent-build-flow
topic: quickstart
status: stable
created: 2026-09-15
updated: 2026-09-15
owner: self
source: human+ai
---

# agent-build-flow

把**一个模糊业务需求**推成**能上线的 Agent 包**。全程 7 个阶段、20 道门禁，4 个必须停下来等用户确认的点。

## 一句话说明

管流程，不管评测标准：拦住"先写 PRD"、"跳过 TUI 验证"、"接缝乱选"、"交付物数错"、"没跑过裸模型就上线"这些默认会犯的错。

## 什么时候用

| 用 | 不用（走谁） |
|---|---|
| 要做个 agent / 建一个智能体 | 只评测已完成的 agent 包 → `root-agents` 家族（`root-agent-doctor` 体检 / `root-agent-eval` 评分） |
| 这个需求要不要做成 agent | 只创建 Skill（不是 Agent）→ `root-skills-creator` |
| agent 规格、agent 契约、交付物定义 | 只把素材蒸成 Skill → `蒸馏` |
| 接缝怎么选、怎么拆工单 | 只写业务文档、不涉及 Agent → 不触发 |
| agent 上线判定、agent 交接 | |

## 三条最值钱的规则

1. **TUI 先行**：先用终端把问题真解决一次，再补规格。**没跑通过不进阶段 3。**
2. **交出去的东西不一样才算两件活**：`deliverables` 决定这个 agent 能干几件活；工具、skill、行为约束、变体都不算活。
3. **判分只用确定性方法**：拿不出可校验的作答一律判 `fail`，绝不编造标准答案。

## 快速开始

```bash
# 1. 先看本机装了哪些配套命令（user-invoked 的命令只能人手动敲）
python3 scripts/check-flow.py --probe

# 2. 规格写完后生成 agent.yaml 草稿
python3 scripts/render-contract.py spec.md -o agent.yaml

# 3. 校验阶段产出物与契约合规
python3 scripts/check-flow.py <项目目录>
```

## 文件导航

| 我想…… | 读 |
|---|---|
| 走某个阶段、要模板和准出判据 | `SKILL.md` → `references/phases.md` |
| 过 20 道门禁 | `references/gates.md` |
| 把规格落成 agent.yaml | `references/spec-to-contract.md` |
| 数清能干几件活 | `references/deliverables-rules.md` |
| 选接缝 / 拆工单 / 遇宽重构 | `references/seams-tickets.md` |
| 定模型分工 | `references/model-routing.md` |
| 分清修 / 交付 / 发布 | `references/release-gates.md` |
| 看别人怎么踩的坑 | `references/gotchas.md` |
| 看一个完整样例 | `examples/brand-pr-walkthrough.md` |

## 配套依赖

`/grill-with-docs`、`/to-spec`、`/to-tickets`、`/implement`、`/tdd`、`/code-review`、`/handoff` 等是 **user-invoked**——**任何 skill 都调不动它们**，只能写文字请用户自己敲 `/命令`。命令覆盖不到的判据已全部内置在 `references/` 里。

## 边界

- **不管评测标准**：评分、出题、修复分别走 `root-agents` 家族的 `root-agent-eval` / `root-agent-opt`（**Agent 包不走 `root-skills-eval`**，那是 Skill 家族，只认 `SKILL.md`）。
- **不重复造门禁**：本技能只执行门禁，不定义门禁。

## 维护

失败模式沉淀 → 追加到 `references/gotchas.md`（"错误 + 修正"格式），**不重写整篇**。
