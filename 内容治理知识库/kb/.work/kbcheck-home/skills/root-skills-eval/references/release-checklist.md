---
title: Release 发布前 10 项审查清单
doc_type: checklist
module: root-skills-eval
topic: release-checklist
status: stable
created: 2026-09-02
updated: 2026-09-01
owner: self
source: root-skills-creator/references/pre-launch-checklist.md（10 条标准同源；本文件另含评测已有 Skill 判分细则）
---

# Release 发布前 10 项审查清单

Skill 上线（release 模式）前必须逐项通过的 **10 项审查清单**。10 条标准与
`root-skills-creator/references/pre-launch-checklist.md` 同源。本文件额外规定
**评测已有 Skill** 时每条用什么证据判分，供 `root-skills-eval` 写入最终报告。

> **判分来源**：轨道 A 静态评估时对照「通过标准」；**最终版本**（含修复副本）必须先读本轮 `track_b`，再写 `release_checklist`。禁止不看本轮 A/B 卷就判第 3/9 项。
> 判分结果写入评测 YAML 的 `release_checklist` 字段，最终由
> `scripts/build-final-report.py` 渲染进唯一最终报告的「Release 发布前 10 项审查清单」区块。

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

## 判分规则

对每一项输出三态之一：

| 状态 | 含义 | 说明 |
|------|------|------|
| `pass` | ✅ 通过 | 该项满足「通过标准」 |
| `fail` | ❌ 未通过 | 该项不满足「通过标准」 |
| `na` | — 不适用 | 该项不适用于该 Skill（如 minimal Skill 无 runtime 文件时，第 7 项可判 na） |

每项必须附 `evidence`（一句话判分依据，须复述该条通过标准，禁止拿别条的修复当证据），渲染进报告「判分依据」列。

## 评测已有 Skill（v3.16.7 强制）

创建新 Skill 仍按上表原文（先 RED 再写正文）。**评测已存在的 Skill**（翻译包、存量包、本次评测才第一次跑触发用例）按下表取证。先打开本轮 YAML 的 `track_b.distribution` 与 `rounds`，再写 `status`。

第 3 项 ≠ 第 9 项：第 3 项只问创建时有没有 without-skill RED；第 9 项只问现在有没有正例/负例/边界与端到端评测。本轮轨道 B 满足第 9 项，不自动等于第 3 项。

| # | 先看这些证据 | pass | fail | 禁止 |
|---|----------------|------|------|------|
| 1 | description 有稳定触发边界；本轮触发门槛已跑完 | 领域任务会漏触发/误触发/口径漂移，不是通用命令或一次性上下文 | 纯通用命令、机械约束、一次性上下文 | 用「通用能力」打发；与第 3 项绑在一起；评测都跑完了仍写「不该做成 Skill」 |
| 2 | description「何时用」+「何时不用」 | 相邻不触发场景已写出 | 只有功能句、无负例边界 | — |
| 3 | `tests/` 或 `evals/` 里的 RED / without-skill 记录 | 有可重复的 without-skill 失败证据（创建时留下的） | 评已有 Skill 且目录里没有 RED：`fail` + `不影响上线` | 把「本轮没 A/B 卷」写成 fail 理由（那是第 9 项）；为过本项补造历史 RED 文件 |
| 4 | description 首句 | 触发时机/触发词在截断窗口内（中文家族版触发词前置即可） | 首句纯功能列表且触发词靠后会被截断 | — |
| 5 | description 触发词 | 写用户会怎么说 | 只写 Skill 内部步骤 | — |
| 6 | 正文 | 行为规则 / gotcha / 读取条件 | 大段常识、无行为改变 | — |
| 7 | 正文是否点名 runtime | 有 references/scripts/assets 则写明何时读；没有 runtime 则 `na` | 有 runtime 文件但正文未写读取条件 | 无 runtime 时不要 fail |
| 8 | description 或正文安全边界 | 注入/密钥/危险命令/越权 → 不触发并拒绝 | 无拒绝规则 | — |
| 9 | **本轮** `track_b.distribution`（正例/负例/近似命中/边界情况均 >0）且 `rounds` 已执行 | 四类主类型都有且已真实跑过（A 卷条数按复杂度：minimal 25 / standard 50 / complex 100） | 本轮还没出四类题，或四类缺一类 | 因 `tests/` 未在正文声明而 fail；把 25 条当成「没有 50 条所以没有 eval」；evidence 写「无 positive/negative」但 YAML 里已有四类 |
| 10 | 正文 gotcha/错误处理 + `version`/`last_updated` + 一句停用条件 | 维护闭环（gotcha 优先）+ 停用时怎么处理（description 注明停用、保留目录） | 无 gotcha、无版本、无停用说明 | 拿 `last_updated` 单独冒充完整状态机；去套 manage 家族注册表 `active→deprecated`（那是家族成员，不是业务 Skill） |

**evidence 对号入座**：第 N 项的 evidence 必须回答第 N 项的通过标准。禁止把「references 落地」「run.py 自包含」「移除 vendor」写进第 3/9/10 项。

**最终版本（修复副本）**：本轮 A 卷四类已执行 → 第 9 项必须 `pass`。第 3 项缺历史 RED 可继续 `fail`（不影响上线），不得改口成「没评测」。第 1 项在本轮触发门槛已过时默认 `pass`，除非能指出它是通用命令/一次性上下文。

## YAML 字段定义

判分结果写入评测报告 YAML（最终版本），结构如下：

```yaml
release_checklist:
  - id: 1
    status: "pass"        # pass / fail / na
    evidence: "无该 Skill 时 agent 会漏触发，已记录 RED 基线"  # 必填，须复述该条标准
    impact: "不影响"      # 可选（pass/na 可不写或写「不影响」）
  - id: 2
    status: "fail"
    evidence: "description 首句为功能陈述，触发句式在第二句才出现"
    impact: "不影响上线（属剩余风险，建议下个版本将首句改为触发句式）"   # fail 项必填（v3.10.0 强制）
  # ... 共 10 项
```

> **impact（是否影响上线，v3.10.0 强制）**：`fail` 项必须标注 `impact`，取值 `影响上线` 或 `不影响上线`，并附一句话原因（如「影响上线（触发句式缺失会导致漏触发，须修复后复审）」）。`build-final-report.py` 校验 fail 项缺失 impact 即拒绝生成（exit 2）；报告渲染「是否影响上线」列——**🔴 影响上线 = 发布阻断项**（须修复后复审，作为剩余风险显著提示），**🟡 不影响上线 = 剩余风险**（建议补齐对应参考后再复审）。

> `build-final-report.py` 从最终版本的 YAML 读取 `release_checklist`（按 `id` 对齐静态清单）。
> **v3.8.1 起为强制校验**：最终版本 YAML 缺失 `release_checklist` 或 10 项不齐全时，
> `build-final-report.py` 直接拒绝生成最终报告（exit 2），不再降级输出「未判分」区块；
> 仅重建历史报告时可用 `--allow-missing-release` 逃生。

## 与发布门禁的关系

- **可发布**只看轨道 C：`market_ready`（封顶后 ≥85、Output ≥15、无 error 封顶、调用门槛通过；v3.17.4 与修复退出同一条放行线，研究报告 80 仅为 B 级等级参考）；
- 本清单是 release 模式下的**补充审查维度**，逐项判分结果随最终报告一并呈现，供用户决策；
- 任一项 `fail` 不影响轨道 A/B/C 的分数计算，但必须标注**是否影响上线**（impact）：
  - `影响上线`：视为**发布阻断项**，须修复后复审通过才可上线；
  - `不影响上线`：作为**剩余风险**记录，建议补齐对应参考后再复审。
