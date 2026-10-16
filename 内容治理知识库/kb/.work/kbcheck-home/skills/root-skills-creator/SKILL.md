---
name: root-skills-creator
description: |
  创建生产级 Agent Skill 的工具。当用户说"创建 skill"、"写一个 skill"、
  "Iron Law 测试"、"CSO 优化"、"把流程变成 skill"或询问
  Skill 类型、渐进式披露 (Progressive Disclosure) 时使用。
  触发词：创建 skill、写一个 skill、做一个 skill、Iron Law、CSO、对比评测、Skill 类型。
  整合 Iron Law Testing、CSO 优化、Universal Skill Schema 标准，
  并内置真实运行验证（with/without 对比评测）、意图对话、模式分级与输出契约。
  创建完成后的质量评估走 root-skills-eval，内容优化走 root-skills-opt，目录结构走 root-skills-doctor。
version: "4.1.4"
complexity: "complex"
compatibility:
  claude:
    status: "native"
  kimi:
    status: "native"
  cursor:
    status: "native"
  gpt:
    status: "bridge"
    limitations: ["渐进式披露 (Progressive Disclosure) 需模拟"]
  minimax:
    status: "bridge"
    limitations: ["需中文优化"]
  dsh:
    status: "native"
    notes: "open agent skills 标准，SKILL.md 直接加载"
  codex:
    status: "native"
    notes: "open agent skills 标准，SKILL.md 直接加载"
---

# Root Skills Creator - Skill 创建工具

整合 Skill 创建（Iron Law Testing + CSO 优化）、设计边界、质量评估（六维度）、自动优化与真实运行验证的完整闭环。基于 Universal Skill Schema 标准，吸收 Accio 对比评测循环与 Yao 意图对话/模式分级/输出契约，支持 Claude + Kimi + Cursor 核心联盟及 GPT/MiniMax 桥接。

**创建**由本 skill 负责；**评估**走 `root-skills-eval`，**优化**走 `root-skills-opt`，**结构体检**走 `root-skills-doctor`。创建流程第 9/11 步会调用家族成员，不代替它们的触发入口。

## 何时不该使用 / When Not to Use

- 评估已有 skill 质量、跑触发评测、出最终报告 → `root-skills-eval`
- 根据评估报告优化 / 低分修复内容与触发 → `root-skills-opt`
- 只整理目录结构或规范体检 → `root-skills-doctor`
- 家族路由 / 注册表 / 生命周期 → `root-skills-manage`

## 快速开始

### 3步创建 Skill

1. **选择模板**
   ```bash
   cp -r assets/templates/standard-skill ./my-skill
   ```

2. **编辑 SKILL.md**
   - 填写 name（kebab-case）
   - 编写 description（功能 + 触发词）
   - 声明 complexity（minimal/standard/complex）

3. **验证**
   ```bash
   python scripts/validate-skill.py ./my-skill
   ```

## 核心原则 / Core Principles

### 1. Iron Law Testing（严格测试法）

**NO SKILL WITHOUT A FAILING TEST FIRST**

创建 Skill 前，必须先验证"没有该 Skill 时 agent 会失败"。

```
RED → GREEN → REFACTOR → PUBLISH
(基线失败) → (最小修复) → (加固闭环) → (通过后发布)
```

详细方法见 `references/iron-law-testing.md`

### 2. CSO 优化（可发现性优化）

**核心规则**: description 描述触发条件，而非工作流。

高质量的 description 包含：功能 + 时机 + 触发词

详细方法见 `references/cso-optimization.md`

### 2.5 Skill 设计边界

**核心规则**: 先证明行为会失败，再决定是否写 Skill。

创建或评审 Skill 时，读取 `references/skill-design-boundaries.md`，检查：

- 该能力是否真正改变 agent 行为，而不是普通文档。
- description 是否是路由触发器，而不是功能摘要。
- 正文是否只保留模型容易做错的判断、边界和 gotchas。
- 是否补齐 positive loading、negative loading 和 boundary evals。

### 3. 渐进式披露 (Progressive Disclosure)
```
Metadata (头部元数据) → SKILL.md (技能文档) → Resources (资源文件)
(始终加载)           → (触发时加载)      → (需要时加载)
```

### 4. 复杂度分级 (Complexity Levels)
- **minimal** (极简): < 2000 字符，简单任务
- **standard** (标准): < 4000 字符，大多数 Skill
- **complex** (复杂): < 8000 字符，复杂工作流

### 5. Skill Types（技能类型）

| 类型 | 定义 | 测试策略 |
|------|------|----------|
| **Technique** | 有明确步骤的方法 | 新场景执行题，验证步骤完整 |
| **Pattern** | 思维框架或决策模型 | 归因题，验证判断正确 |
| **Reference** | 可检索知识库 | 检索+应用题，验证信息准确 |

详细方法见 `references/skill-types.md`

### 6. 真实运行验证 (Runtime Verification)

**核心规则**: Iron Law 的 RED/GREEN/REFACTOR 必须**真跑**，不是手工填报告。

创建 Skill 时，用真实用户 prompt 同时运行 with-skill 和 without-skill 两个对比，用断言判定 PASS/FAIL，量化 pass_rate / token / 耗时差异。没有真实运行的对比结果，不得发布。

详细方法见 `references/eval-loop.md`，字段规范见 `references/schemas.md`

### 7. 意图对话 (Intent Dialogue)

**核心规则**: 需求澄清只问核心问题，不搞无限访谈。

- 每轮最多问 1 个核心分叉问题，最多 2 轮。
- 非核心缺口自行推断（合理默认），不要逐一追问。
- 2 轮后记录偏好推断，继续推进。

详细方法见 `references/intent-dialogue.md`

### 8. 模式分级 (Operating Modes)

**核心规则**: 按用途选择门禁轻重，不做一刀切。

| 模式 | 适用 | 门禁 |
|------|------|------|
| **explore** | 个人探索、原型 | 最小闭环：结构验证 + 一次评测 |
| **release** | 团队共享、发布 | 完整门禁：评测 + 触发测试 + DoD + 封顶后轨道 C >= 85 且调用门槛通过；未达标才在 `{skill}-fix/` 跑 opt，源目录不改 |

详细方法见 `references/operating-modes.md`

### 9. 输出契约 (Output Contract)

**核心规则**: 每次任务明确交付物，不做无边界产出。

- **构建 (build)**: SKILL.md + 对齐的接口 + 有理由的资源 + 边界/门禁小结。
- **审计 (audit)**: 只给 findings + 修复建议；仅当被要求时才修改文件。
- **no-skill**: 判断不该建 Skill 时，零文件产出，说明理由。

详细方法见 `references/output-contract.md`

## 创建流程 / Creation Workflow

简化版流程（详细版见 `references/step-by-step-guide.md`）：

0. **入口判断** - 是否 repeated use + 可复用输出契约？否则走 no-skill（见 `references/output-contract.md`）
1. **意图对话** - 核心分叉问题（每轮最多1个，最多2轮），非核心自行推断（见 `references/intent-dialogue.md`）
2. **选择模式** - explore / release，决定门禁轻重（见 `references/operating-modes.md`）
3. **需求分析** - 确定用例、触发词、Skill Type
4. **架构设计** - 选择 complexity 级别
5. **Iron Law RED** - **真实运行** without-skill 基线，记录失败输出（见 `references/eval-loop.md`）
6. **编写 SKILL.md** - frontmatter + body
7. **Iron Law GREEN** - **真实运行** with-skill，断言 PASS/FAIL
8. **添加资源** - scripts/, references/, examples/
9. **验证** - 运行验证工具（validate-skill.py）+ 六维度评估（root-skills-eval）
10. **Iron Law REFACTOR** - 压力场景变体真实运行
11. **评估优化** - root-skills-eval 评分；未达标则 root-skills-opt 只改 `{skill}-fix/` 副本（源只读，见 `references/eval-loop.md`）
12. **桥接** - 转换为 GPT/MiniMax 格式（如需要）

## 资源引用 / Resources

### 详细指南 (Detailed Guides)
- `references/step-by-step-guide.md` - 完整12步流程
- `references/iron-law-testing.md` - Iron Law Testing (RED→GREEN→REFACTOR)
- `references/eval-loop.md` - 真实运行验证：with/without 对比评测循环（新增）
- `references/schemas.md` - evals/grading/benchmark JSON 字段规范（新增）
- `references/intent-dialogue.md` - 意图对话：核心问题澄清法（新增）
- `references/operating-modes.md` - 模式分级：explore / release（新增）
- `references/output-contract.md` - 输出契约：构建/审计/no-skill（新增）
- `references/cso-optimization.md` - CSO 优化与触发词技巧
- `references/skill-design-boundaries.md` - Skill 设计边界、gotchas 与维护规则
- `references/pre-launch-checklist.md` - 上线前 10 项审查清单（发布门禁）
- `references/skill-types.md` - Skill 类型框架 (Technique/Pattern/Reference)
- `references/best-practices.md` - 最佳实践汇总
- `references/troubleshooting.md` - 常见问题解答
- `references/cross-model-adaptation.md` - 跨模型适配详情
- `references/universal-skill-schema.md` - Universal Skill Schema 规范

### 工具 (Tools)
- `scripts/validate-skill.py` - 验证工具 (Validation Tool)
- `scripts/eval-skill.py` - 评测编排工具：生成评测任务、聚合基准（新增）
- `scripts/convert-for-model.py` - 模型转换工具 (Model Conversion)

### 配套 Skills（家族版）
- `root-skills-eval` - 六维度质量评估 + 触发评测（家族版，双轨）
- `root-skills-opt` - 基于评估报告的自动修复优化（家族版，副本修复）

### 家族规划 (root-skills 框架)
- `root-skills-manage` - root-skills 家族管理器（注册表 + 路由 + 生命周期）
- `root-skills-doctor` - Skill 诊断（结构/触发/行为问题定位，家族版）

### 模板 (Templates)
- `assets/templates/minimal-skill/` - 最简结构 (Minimal Structure)
- `assets/templates/standard-skill/` - 标准结构 (Standard Structure)
- `assets/templates/complex-skill/` - 完整结构 (Complex Structure)

## 快速参考 / Quick Reference

### Frontmatter 模板 (Frontmatter Template)
```yaml
---
name: my-skill                        # Skill 名称（kebab-case）
description: |                       # 描述（功能 + 触发条件）
  [功能]。当用户[触发条件1]、[触发条件2]时使用。
version: "1.0.0"                     # 版本号（语义化版本）
complexity: "standard"               # 复杂度（minimal/standard/complex）
compatibility:                       # 兼容性声明
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
---
```

### 常用命令 (Common Commands)
```bash
# 验证 Skill 结构
python scripts/validate-skill.py ./my-skill

# 转换为 GPT/MiniMax 格式
python scripts/convert-for-model.py ./my-skill --target gpt
python scripts/convert-for-model.py ./my-skill --target minimax
```

### Token 效率 (Token Efficiency)

高频加载 < 200 词；普通 Skill < 500 行；重型参考放 `references/`。

### 质量门槛 (Quality Gates)

发布前必须通过（release 模式）：
- [ ] 意图对话完成（核心分叉已澄清或已记录推断）
- [ ] Iron Law Testing 真实运行通过（RED → GREEN → REFACTOR，含对比证据）
- [ ] `name` 符合 kebab-case
- [ ] `description` 描述触发条件（非工作流）
- [ ] 使用祈使语态（无第二人称）
- [ ] 运行 `root-skills-eval`：封顶后轨道 C >= 85 且调用门槛通过（家族版）
- [ ] 未达标时运行 `root-skills-opt`：只改 `{skill}-fix/` 副本，源目录保持原样；交付物是桌面与源并排的 `-fix`，不是把 opt 结果写回正在创建的目录。一次达标不必跑 opt
- [ ] 输出契约满足（交付物与边界小结）

> 完整 10 项上线前审查清单见 `references/pre-launch-checklist.md`。

---

**文档版本**: 4.1.3 | **框架**: root-skills | **核心联盟**: Claude 🤝 Kimi 🤝 Cursor
