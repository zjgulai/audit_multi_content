---
title: 蒸馏 - 快速开始
doc_type: readme
module: 蒸馏
topic: quickstart
status: stable
created: 2026-09-15
updated: 2026-09-15
owner: self
source: human+ai
---

# 蒸馏

把**一段素材**（会议纪要、白板、逐字稿、文档、教程、聊天记录、代码仓库）蒸馏成**能被路由调用的 Skill**。

## 一句话说明

管质量，不管评分：用**三重验证**拦住同质化、拦住"把文档转成 markdown 就叫蒸馏"、拦住把常识和事实写进正文。

## 核心纪律

> **只抄结论不抄判断，换场景立刻失效。**

蒸出来的是"**遇到 X 时先看 Y**"，不是"这篇讲了什么"。

## 三重验证（淘汰 50%~75% 属正常）

候选要进正文，必须三条同时满足：

1. **≥2 处独立佐证**（跨章节 / 跨时间戳）
2. **有预测力**（能回答素材没明说的新场景）
3. **非常识**（裸模型自己说不出来）—— **这一条必须实测，不能凭感觉**

**淘汰率低于 30% 时，先怀疑自己放水了。**

## 六阶段

```
值不值得蒸 → 整体理解 → 五路提取 → ★三重验证 → RIA++ 结构化 → 链接索引 → 压力测试
```

## 什么时候用

| 用 | 不用（走谁） |
|---|---|
| 把这场会议蒸成 skill | 蒸自己的发言 → `self-distill` |
| 资料变 skill / 万物皆可 skill | 创建 lark-cli Skill → `lark-skill-maker` |
| 白板整理成 skill | 评测已有 Skill → `root-skills-eval` |
| 重复三次的工作萃取成 skill | 只整理会议纪要 → `lark-workflow-meeting-summary` |

## 快速开始

```bash
# 1. 生成骨架
python3 scripts/scaffold.py my-new-skill --out ~/.dsh/skills

# 2. 填内容（必须过三重验证），填完自检
python3 scripts/check-skill.py ~/.dsh/skills/my-new-skill
```

## 交付物（缺一不可）

| 交付物 | 模板 |
|---|---|
| `SKILL.md` | `assets/templates/skill-skeleton.md` |
| 蒸馏记录（含淘汰率） | `assets/templates/distill-log.md` |
| 触发词表（含 5 条不触发） | `assets/templates/trigger-table.md` |
| 用例表（正例 3 / 负例 3 / 边界 1） | `assets/templates/eval-cases.md` |
| 裸模型对照记录 | 同蒸馏记录表附页 |

## 蒸完之后交给谁

```
root-skills-doctor（体检）→ root-skills-eval（评测）→ root-skills-opt（低分修复，只改副本）
```

**本技能不评分。** 评分口径归 `root-skills-eval`——不造第二套标准。

## 文件导航

| 我想…… | 读 |
|---|---|
| 知道这类素材怎么提取 | `references/distill-patterns.md` |
| 过三重验证 | `references/triple-verification.md` |
| 分清判断和事实 | `references/judgment-vs-fact.md` |
| 防同质化 / 找竞争壁垒 | `references/homogenization.md` |
| 做裸模型对照 | `references/baseline-compare.md` |
| 标出处 | `references/provenance.md` |
| 交接给家族 | `references/handoff-to-family.md` |
| 看一个完整样例（淘汰 62%） | `examples/20260915-meeting-to-skill/` |

## 维护

- 误触发 → 收紧 `description`，补负例
- 漏触发 → 补真实意图词
- 正文太长 → 搬到 `references/`
- 判断失效 → 补 gotcha，**不重写整篇**
