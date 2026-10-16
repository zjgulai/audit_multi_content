# 蒸完之后交给谁

本技能**只产出候选**。质量判定、结构体检、修复、注册全部交给已有家族，**绝不重造第二套标准**。

---

## 一、交接地图

```
蒸馏（本技能）
      │ 产出：<skill-name>/ + 蒸馏记录 + 触发词表 + 用例表 + 裸模型对照记录
      ▼
┌──────────────────────────────────────────────────────┐
│ root-skills-doctor   结构体检（D001-D007 + D100 系列）  │
│        │ 结构不合规 → 先修结构                        │
│        ▼                                              │
│ root-skills-eval     双轨评测（静态六维 + 触发盲测）    │
│        │ 封顶后轨道 C < 85 或调用门槛未过              │
│        ▼                                              │
│ root-skills-opt      低分修复（只改 {skill}-fix/ 副本） │
│        │ 达标后副本交付（不写回源）                    │
│        ▼                                              │
│ root-skills-check    报告核对 / 数据资产入库            │
│ root-skills-manage   家族注册、路由、生命周期           │
└──────────────────────────────────────────────────────┘
```

---

## 二、交给每个成员时的输入

| 交给谁 | 带什么 | 什么时候 |
|---|---|---|
| `root-skills-doctor` | skill 目录路径 | 刚蒸完，先体检结构 |
| `root-skills-eval` | skill 目录路径 | 结构合规后，要评分与触发盲测 |
| `root-skills-opt` | 评估报告 + skill 目录 | 评分不达标时（**只改副本**） |
| `root-skills-check` | 评测报告 | 报告出完，核对完整性 / 入库 |
| `root-skills-manage` | skill 名 + 归类 | 要注册进家族、改路由、停用 |
| `root-skills-creator` | — | 从零创建 Skill（**不是从素材蒸**）时用，不用本技能 |

---

## 三、交付物清单（交给家族之前必须齐）

| 交付物 | 模板 | 缺了会怎样 |
|---|---|---|
| `<skill-name>/SKILL.md` | `assets/templates/skill-skeleton.md` | 无法评测 |
| 蒸馏记录 | `assets/templates/distill-log.md` | 出处无法核验，淘汰决策无法复算 |
| 触发词表（含 5 条不触发） | `assets/templates/trigger-table.md` | 触发评测没有负例，无法测误触发 |
| 用例表（正例 3 / 负例 3 / 边界 1 起） | `assets/templates/eval-cases.md` | 盲测无题可出 |
| 裸模型对照记录 | 同蒸馏记录表附页 | 无法证明价值，默认不保留 |
| 淘汰率报告 | 蒸馏记录表统计行 | 无法判断是否放水 |

---

## 四、"不要做"清单

本技能**不做**这些事，做了就是越界：

| 不做 | 因为 |
|---|---|
| 给 Skill 打分 | 评分口径归 `root-skills-eval` |
| 修目录结构 | 归 `root-skills-doctor` |
| 改自己蒸出来的 Skill 的低分项 | 归 `root-skills-opt`（且只改副本） |
| 注册家族成员 | 归 `root-skills-manage` |
| 蒸自己的发言变行为规则 | 归 `self-distill` |
| 封装 lark-cli | 归 `lark-skill-maker` |
| 只整理会议纪要 | 归 `lark-workflow-meeting-summary` |

---

## 五、一句话记住

**本技能负责"把素材变成够格的候选"，不负责"判断这个候选好不好"。**

两件事分开，才不会造出两套打架的标准。
