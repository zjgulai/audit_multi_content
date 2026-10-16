# Root Skills Opt

> Skill 优化师 - 基于结构化评估报告的全自主副本优化（流水线闭环最后一环）

## 简介

`root-skills-opt` 读取 `root-skills-eval` 生成的**结构化 YAML 评估报告**，全自主完成副本修复、回归验证、B 卷门禁与桌面副本交付，输出优化后的 Skill 副本与优化报告（**不写回被测 skill 原文**）。

## 核心特性

- **解析结构化报告**: 读取 YAML 格式评估报告，提取问题和修复建议
- **自动修复**: 自动修复 Schema 合规性、格式、语态等问题
- **自主判断**: 复杂问题采用有证据的最佳默认并记录假设，不编造业务事实
- **评分验证**: 优化后自动评估，验证是否达到目标分数
- **循环优化**: 支持 Eval-Opt 自动循环，直到达标
- **训练纪律（借鉴 SkillOpt）**: 留出验证门（防过拟合）、编辑预算（小步更新）、拒绝编辑缓冲（不重复无效修复）、跨轮元记忆、达标后压缩打磨与 dsh/codex 双端验收

## 快速使用

```bash
# 方式 1: 从评估报告优化（推荐）
/root-skills-opt /path/to/evaluation-report.yaml

# 方式 2: 直接优化（自动评估）
/root-skills-opt /path/to/skill-folder --auto-eval

# 方式 3: 自动循环优化
/root-skills-opt /path/to/skill --eval-loop --target-score=85
```

## 输出

- 优化后的 Skill 副本文件（所有修复先在 `{skill}-fix/` 副本上进行，达标 + B 卷门禁通过后复制到解析出的**交付目标**（`references/batch-delivery.md`；缺省 `~/Desktop`）交付，**不写回被测 skill 原文**）
- `optimization-report.md` - 详细优化报告（优化项清单、前后对比、验证结果、修复问题逐条列出）

## 支持的修复类型

### 自动修复

| 问题 | 修复 | 示例 |
|------|------|------|
| name 格式错误（仅 ASCII） | 替换下划线 | `my_skill` → `my-skill`；中文 name 不改 |
| 缺少 version | 添加默认值 | `version: "1.0.0"` |
| 缺少 complexity | 自动判断 | 根据 body 长度 |
| 第二人称语态 | 自动移除 | "你应该" → 删除 |
| 目录缺失 | 自动创建 | `mkdir examples/` |
| Release 第 10 项维护/退役 | 补 gotcha、last_updated、停用条件 | 见 R010；不写家族注册表 |

### 自主判断

| 问题 | 协作方式 |
|------|----------|
| description 优化 | 生成候选并选择回归得分最高者 |
| 方法论审计 | 仅写入现有材料可证实的差异 |
| 核心流程优化 | 采用最小改动，回归失败自动撤销 |

## 目录结构

```
root-skills-opt/
├── README.md                 # 本文件
├── SKILL.md                  # Skill 定义（优化流程）
├── .skill-meta/
│   └── manifest.yaml         # 元数据
├── scripts/                  # 验证 shim（家族内优先）
├── references/               # 参考文档（优化模式库/人机协作/历史修复报告）
├── examples/                 # 示例报告
└── tests/                    # 测试用例
```

## 依赖

- `root-skills-eval` - 生成评估报告（前置）
- `root-skills-doctor` - 结构/规范静态检查（优化前诊断，可选）
- `root-skills-creator` - validate-skill.py 权威实现来源（家族内）
- `references/universal-skill-schema.md` - 优化标准

## 与 Eval 的联动

```
Eval → 生成 YAML 报告 → Opt 解析 → 自动修复（副本上）→ 回归验证 → 重新评估 → B 卷门禁 → 副本复制到交付目标（缺省桌面，可配置）交付（不写回）→ 输出
```

支持自动循环模式，直到评分达标（默认目标 85 分）。每轮先过**留出验证门**（触发用例引导/留出切分，留出集 F1 不降）再验证回归问题（无新问题引入）再重新评估；评分只升不降否则回滚；连续多轮无提升则停止并报告用户，无效修复自动记入拒绝缓冲不再重复提议。

## 相关 Skill（家族关系）

| Skill | 关系 |
|-------|------|
| `root-skills-creator` | 上游：创建 skill + 评测循环 |
| `root-skills-doctor` | 上游：结构/规范静态检查 |
| `root-skills-eval` | 上游：生成评估报告（本 skill 输入源） |
| `root-skills-manage` | 家族管理器：注册表 + 路由 + 生命周期 |

## 版本

- 当前版本: 3.5.7
- 结构版本: 1.0
- 配套 Eval 版本: 3.17.3

### 版本历史

**v3.5.7** (2026-09-02): 出 HTML 前 check 用 `--validate-only` / `--check-only`，不重走出题；配套 Eval 3.17.2。

**v3.5.6** (2026-09-01): 读取 `release_checklist` fail 项——可补的改 SKILL.md（含 R010 维护与退役）；第 1/3/9 项只复判，不补造 RED/评测文件。
**v3.5.5** (2026-09-01): 跨成员引用口径——不再把 eval 的低分修复流程写成 opt 本地 `references/` 路径。规则未改。
**v3.5.4** (2026-09-01): 调用门槛——新 YAML `call_tag.passed_gate=false` 不可发布、不能退出修复；旧 YAML 无 call_tag 不挡。配套 Eval 3.16.5。
**v3.5.3** (2026-09-01): 正文去沉积（规则不删）；配套 Eval 3.16.1。
**v3.5.2** (2026-09-01): 达标读封顶后轨道 C——`effective_track_c()`：YAML 88 + Output 12 → 有效 79，未达 85；配套 Eval 3.16.0。
**v3.5.1** (2026-09-01): 中文最终包——S001 禁止把中文 name 改回英文；单包 `skills._shared` 缺失不为修它改 name；配套 Eval 现为 3.15.0。
**v3.5.0** (2026-09-03): 移除「安全写回」——所有修复只在 `{skill}-fix/` 副本上进行，达标 + B 卷门禁通过后复制到桌面与源并排交付，被测 skill 原文（含桌面源）任何情况下不写回；配套 Eval 版本 3.10.1 → 3.12.0 → 3.13.0。

**v3.4.1** (2026-08-31):
- 同步配套 eval v3.10.1，并接入家族根的一键依赖与验证门禁

**v3.4.0** (2026-09-02):
- 借鉴 microsoft/SkillOpt 引入训练纪律：留出验证门（scripts/split-gate.py）、编辑预算（--budget）、拒绝编辑缓冲（rejected-edits.yaml）、跨轮元记忆（training-log.yaml）、达标后压缩打磨与 dsh/codex 双端验收
- plan-fixes.py 新增 --budget / --rejected-edits / --training-log 参数；新增 tests（17 用例）

**v3.3.0** (2026-09-01):
- 全程自主：判断型问题采用最佳默认并记录假设，不设置用户确认节点
- 达标后自动备份、写回与验证，失败自动回滚

**v3.2.0** (2026-08-30):
- 引入同路径副本修复、逐条修复清单与回归验证；旧版写回规则已由 v3.3.0 取代

**v3.1.0** (2026-08-29):
- 低分自动修复闭环：封顶后轨道 C 未达 85 分自动循环修复（副本上），先回归验证再重新评估，直到达标；YAML 88 + Output 12 视为 79

**v3.0.0** (2026-08-29):
- 归属 root-skills 家族，由 root-skills-manage 管理
- 输入源切换为 root-skills-eval（含触发评测 + 综合评分维度）
- 流水线闭环：创建 → 质检 → 优化

**v2.0.0** (2026-04-02):
- 支持六维度评估报告格式
- 新增自动循环优化模式
- 优化人机协作流程

**v1.0.0**:
- 初始版本

## 兼容性

| 平台 | 状态 | 备注 |
|------|------|------|
| Claude | native | 完整支持 |
| Cursor | native | 完整支持 |
| Kimi | native | 完整支持 |
| GPT | bridge | 支持，需适配 |
| MiniMax | bridge | 支持，需适配 |

---

**全程自主** | **Schema 标准** | **框架**: root-skills
