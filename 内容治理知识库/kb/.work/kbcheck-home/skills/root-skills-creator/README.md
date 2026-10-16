# Root Skills Creator

> 创建生产级 Agent Skill：Iron Law Testing + CSO 优化 + **真实运行验证（对比评测）** + 意图对话 + 模式分级 + 输出契约

基于 `lute-skills-creator` v3.1.0 全量保留并增强：在原 Iron Law / CSO / Universal Skill Schema / 六维度评估闭环之上，吸收 Accio 的 with/without 对比评测循环与 Yao 的意图对话/模式分级/输出契约，把"验证"从手工填报告升级为真实运行。

## 新增能力（相对 lute 原版）

| 能力 | 说明 | 参考文件 |
|------|------|----------|
| 真实运行验证 | Iron Law 的 RED/GREEN/REFACTOR 用 with/without 并行评测真跑，断言 PASS/FAIL，量化 pass_rate/token/耗时 | `references/eval-loop.md` |
| 评测数据结构 | evals/grading/benchmark/timing JSON 字段规范 | `references/schemas.md` |
| 意图对话 | 每轮最多 1 个核心问题、最多 2 轮，非核心自行推断 | `references/intent-dialogue.md` |
| 模式分级 | explore / release 两级门禁，不搞一刀切 | `references/operating-modes.md` |
| 输出契约 | 构建/审计/no-skill 三类交付物边界 | `references/output-contract.md` |
| 评测编排脚本 | `eval-skill.py`：校验评测集、生成 with/without 任务、聚合 benchmark | `scripts/eval-skill.py` |

**配套家族 Skill**：评估与优化走家族版 `root-skills-eval`（双轨评测 + 低分自动修复流程）与 `root-skills-opt`（副本修复，源只读）。

## 快速开始

### 创建 Skill

```bash
# 1. 选择模板
cp -r assets/templates/standard-skill ./my-skill

# 2. 编辑 SKILL.md（name / description / complexity）

# 3. 结构验证
python scripts/validate-skill.py ./my-skill

# 4. 真实运行验证（评测循环）
python scripts/eval-skill.py validate ./my-skill/evals/evals.json
python scripts/eval-skill.py tasks ./my-skill/evals/evals.json --out tasks.json
# 派发 with/without 任务给并行 subagent → 收集 grading.json
python scripts/eval-skill.py aggregate <workspace>/iteration-1 --out benchmark.json
python scripts/eval-skill.py summary benchmark.json

# 5. 六维度评分（家族版）
root-skills-eval ./my-skill   # 评分 < 85 → root-skills-opt 自动修复
```

## 创建流程（12 步）

```
0 入口判断（repeated use + 输出契约，否则 no-skill）
1 意图对话（每轮1个核心问题，最多2轮）
2 选择模式（explore / release）
3 需求分析 → 4 架构设计 → 5 Iron Law RED（真实运行 without）
6 编写 SKILL.md → 7 Iron Law GREEN（真实运行 with）
8 添加资源 → 9 验证 → 10 Iron Law REFACTOR（压力场景）
11 评估优化（root-skills-eval → root-skills-opt，家族版）
12 跨模型桥接（可选）
```

## 目录结构

```
root-skills-creator/
├── SKILL.md                  # Skill 定义（核心文档）
├── README.md                 # 本文件
├── .skill-meta/manifest.yaml # 元数据
├── references/               # 14 个指南（原 9 个 + 新增 5 个）
├── scripts/                  # validate / eval-skill / convert
├── assets/templates/         # minimal / standard / complex
├── examples/                 # 使用示例
└── tests/                    # 测试用例
```

## 核心原则

1. **Iron Law Testing**：NO SKILL WITHOUT A FAILING TEST FIRST
2. **真实运行验证**：RED/GREEN/REFACTOR 必须真跑，带对比证据，不手工填报告
3. **CSO 优化**：description 描述触发条件，而非工作流
4. **设计边界**：先证明行为会失败，再决定是否写 Skill
5. **渐进式披露**：Metadata → SKILL.md → Resources
6. **意图对话**：只问核心分叉，不无限访谈
7. **模式分级**：explore 默认，release 需要时再加
8. **输出契约**：构建/审计/no-skill 边界清晰

## 质量门槛（release 模式）

- [ ] 意图对话完成（核心分叉已澄清或已记录推断）
- [ ] Iron Law Testing 真实运行通过（RED → GREEN → REFACTOR，含对比证据）
- [ ] `name` 符合 kebab-case
- [ ] `description` 描述触发条件（非工作流）
- [ ] 使用祈使语态（无第二人称）
- [ ] `root-skills-eval` 封顶后轨道 C >= 85 且调用门槛通过（家族版）
- [ ] 未达标才跑 `root-skills-opt`（只改 `{skill}-fix/` 副本，源只读；一次达标不必 opt）
- [ ] 输出契约满足（交付物与边界小结）

## 家族关系

本 skill 是 `root-skills` 家族成员，由 `root-skills-manage` 统一管理。

---

**文档版本**: 4.1.3 | **框架**: root-skills | **基于**: lute-skills-creator 3.1.0（全量保留）
