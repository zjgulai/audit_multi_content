# 优化模式库 (Optimization Patterns)

基于 Universal Skill Schema v1.1.0 和六维度评估体系的标准优化模式。

---

## plan-fixes.py 用法

从评估报告生成按优先级排序的修复计划：

```bash
python3 scripts/plan-fixes.py {report}.yaml                  # text 输出（默认）
python3 scripts/plan-fixes.py {report}.yaml --format json    # JSON 输出
python3 scripts/plan-fixes.py {report}.yaml --min-severity error  # 只保留 error 级
python3 scripts/plan-fixes.py {report}.yaml --budget 5 \
  --rejected-edits ../{skill}-fix/.opt-state/rejected-edits.yaml \
  --training-log ../{skill}-fix/.opt-state/training-log.yaml
```

优先级→严重度映射：P0→error / P1→warning / P2→info；`--min-severity` 对 issues、optimization_plan 与 `release_checklist` fail 项均生效。`release_checklist` id 2/4/5/6/7/8/10 进 Skill 修复；id 1/3/9 只复判（见 R010）。

训练纪律参数（借鉴 SkillOpt，详见文末 G 系列）：
- `--budget N`：编辑预算，每轮最多输出 N 条修复（默认 0=不限；opt 流程默认 5）
- `--rejected-edits PATH`：拒绝编辑缓冲，排除已验证无效的修复指纹
- `--training-log PATH`：跨轮元记忆，effective 类型提前、ineffective/regression 延后

---

## Schema 合规性修复模式

### S001: name 格式修正

**问题**: ASCII name 不符合 kebab-case（包含下划线、大写字母或空格）。**中文 / Unicode 字母 name 与目录一致即通过；kebab-case 记 na。禁止把中文 name（及目录名、H1）改回英文。**

**检测方式**:
```yaml
issues:
  schema_compliance:
    - id: "S001"
      field: "name"
      message: "name 包含下划线，应使用 kebab-case"
```

**自动修复规则**:
```python
# 仅对 ASCII name：
# 下划线转连字符
"my_skill_name" → "my-skill-name"

# 大写转小写
"MySkillName" → "my-skill-name"

# 空格转连字符
"my skill name" → "my-skill-name"

# 驼峰转 kebab
"mySkillName" → "my-skill-name"

# 中文 name（含任何 Unicode 字母）：不执行本模式，记 na
```

**评分影响**: +3~5 分（仅 ASCII 非法时）

**风险**: 低（纯格式修改）；**对中文 name 执行本模式视为错误修复**

---

### S002: 添加 version 字段

**问题**: 缺少 version 字段

**检测方式**:
```yaml
issues:
  schema_compliance:
    - id: "S002"
      field: "version"
      message: "缺少 version 字段"
```

**自动修复**:
```yaml
version: "1.0.0"
```

**评分影响**: +2 分

**注意事项**:
- 使用语义化版本 (MAJOR.MINOR.PATCH)
- 新 Skill 从 1.0.0 开始

---

### S003: 添加 complexity 字段

**问题**: 缺少 complexity 字段

**自动判断规则**:
```python
body_chars = len(skill_body)
if body_chars < 2000:
    complexity = "minimal"
elif body_chars < 4000:
    complexity = "standard"
else:
    complexity = "complex"
```

**自动修复**:
```yaml
complexity: "standard"  # 根据实际长度
```

**评分影响**: +2 分

---

### S004: 添加 compatibility 字段

**问题**: 缺少 compatibility 字段

**默认修复方案**:
```yaml
compatibility:
  claude: { status: "native" }
  cursor: { status: "native" }
  kimi: { status: "native" }
```

**扩展方案**（如需要跨平台）:
```yaml
compatibility:
  claude: { status: "native" }
  cursor: { status: "native" }
  kimi: { status: "native" }
  gpt: { status: "bridge", limitations: ["渐进式披露需模拟"] }
  minimax: { status: "bridge", limitations: ["需中文优化"] }
```

**评分影响**: +2 分

---

### S005: 修复 description 格式

**问题**: 
- 包含 XML 标签 `< >`
- 使用第二人称
- 描述 workflow 而非功能

**自动修复**:
```yaml
# 修复前
description: "<b>处理</b> PDF 文档，你可以使用此技能"

# 修复后
description: "处理 PDF 文档"
```

**评分影响**: +2~4 分

---

## Frontmatter 质量优化模式

### F001: 优化 description（Pushy 技巧）

**问题**: description 触发词不足，覆盖不全面

**检测标准**:
- 触发词 < 3 个
- 单一场景描述
- 长度 < 150 字符

**自主判断修复**:

**原始描述**:
```yaml
description: "处理 PDF 文档"
```

**优化方向**:
```yaml
description: |
  处理 PDF 文档的提取、转换和合并。
  当用户提及以下任何内容时使用：
  - "PDF转Word"、"PDF转Excel"、"PDF转Markdown"
  - "提取PDF文字"、"提取PDF内容"
  - "合并PDF"、"把多个PDF合并"
  - 上传 .pdf 文件
```

**Pushy 技巧要点**:
1. 多行描述，每行一个场景
2. 多种表达方式（英文 + 中文触发词）
3. 覆盖同义词、变体、隐含需求
4. 明确说明不适用场景（防过度触发）

**评分影响**: +5~10 分

---

### F002: 添加防过度触发说明

**问题**: 缺少不适用场景说明

**修复方案**:
```yaml
description: |
  处理 PDF 文档的提取、转换和合并。
  适用场景：文字提取、格式转换、页面合并拆分。
  不适用场景：图片文件处理、纯文本编辑、扫描件 OCR。
  当用户提及...时使用。
```

**评分影响**: +3~5 分

---

## Body 内容质量优化模式

### B001: 修复写作语态

**问题**: 使用第二人称（"你应该"、"您可以"）

**自动修复规则**:
```markdown
# 修复前
你应该运行脚本验证输入格式。
你可以查阅 references/api-guide.md。

# 修复后
运行脚本验证输入格式。
查阅 references/api-guide.md 获取端点详情。
```

**常见替换**:
- "你应该" → 删除
- "你可以" → 删除
- "你需要" → 删除
- "建议您" → 删除

**评分影响**: +3~6 分

---

### B002: 添加 When to Use 章节

**问题**: 缺少 When to Use / 何时使用 章节

**自动修复模板**:
```markdown
## When to Use / 何时使用

- 场景 1: 具体描述
- 场景 2: 具体描述
- 场景 3: 具体描述
```

**质量要求**:
- 至少 2-3 个具体场景
- 场景描述清晰可理解
- 覆盖主要使用场景

**评分影响**: +5~8 分

---

### B003: 添加 When Not to Use 章节

**问题**: 缺少 When Not to Use / 何时不该使用 章节

**自动修复模板**:
```markdown
## When Not to Use / 何时不该使用

- 不适用于场景 1，建议使用替代方案 X
- 不适用于场景 2，建议使用替代方案 Y
```

**评分影响**: +3~5 分

---

### B004: 优化核心工作流

**问题**: 核心工作流不清晰或过于简单

**优化策略**:

**minimal 级别** (3-4 步):
```markdown
## Core Workflow / 核心流程

1. **理解需求** - 确认任务类型和约束
2. **执行处理** - 应用处理逻辑
3. **验证结果** - 检查输出质量
4. **输出交付** - 生成最终产物
```

**standard 级别** (4-6 步，分阶段):
```markdown
## Core Workflow / 核心流程

### Phase 1: 准备
1. 收集输入
2. 验证约束

### Phase 2: 处理
3. 执行核心逻辑
4. 中间验证

### Phase 3: 输出
5. 生成报告
6. 最终确认
```

**complex 级别** (分阶段，每阶段 2-3 步，含详细子步骤)

**评分影响**: +5~10 分

---

### B005: 添加 Error Handling 章节

**问题**: 缺少错误处理说明

**修复模板**:
```markdown
## Error Handling / 错误处理

### 错误名称
**症状**: [描述现象]
**原因**: [解释原因]
**解决**: [具体步骤]
```

**评分影响**: +3~5 分

---

### R010: 维护与退役（Release 第 10 项）

**问题**: `release_checklist` id=10 fail——无维护闭环与停用说明。

**适用**: 评测已有业务 Skill。不要去写 manage 家族注册表的 `active → deprecated`。

**自动修复**（写入 SKILL.md 正文，并确保 frontmatter 有 `version` 与 `last_updated`）:

```markdown
## 维护与退役

- 维护：gotcha 与错误处理优先；行为变更时递增 version，更新 last_updated。
- 退役：被替代、长期误触发、或职责并入其他 Skill 时，在 description「何时不用」注明停用，保留目录不删除。
```

**不要做**: 补造 Iron Law RED 文件（第 3 项）；新造 A/B 卷凑第 9 项；把 license 单独当成完整生命周期。

**评分影响**: 不改轨道 C；清单第 10 项复测应变 pass

---

## 方法论审计模式

### M001: 添加竞争壁垒声明

**问题**: 未体现差异化价值，同质化风险高

**自主判断流程**:

1. **从现有材料识别壁垒类型**：
   ```
   请选择此 Skill 的竞争壁垒类型：
   [1] 私有数据（内部 SOP、客服记录）
   [2] 行业洞察（深耕行业的特殊判断）
   [3] 失败案例（常见坑、踩雷点）
   [4] 反共识框架（与通用建议不同但更有效）
   [5] 其他（请描述）
   [0] 无明显壁垒
   ```

2. **生成内容**:
   ```markdown
   ## Methodology Audit / 方法论审计

   ### 竞争壁垒

   本 Skill 基于 [壁垒类型]，提供以下独特价值：
   - [具体说明]
   - [与通用方案的区别]

   ### 同质化检测

   通过以下问题验证独特性：
   - [ ] 是否为公开教科书式流程？
   - [ ] 是否几乎任何 AI 都会给出类似步骤？
   - [ ] 是否主要靠模板填空？
   - [ ] 是否没有行业语境？
   ```

**评分影响**: +5~10 分

---

### M002: 添加 DoD（完成定义）

**问题**: 缺少质量门槛检查清单

**修复模板**:
```markdown
## Definition of Done / 完成标准

- [ ] SKILL.md frontmatter 完整
- [ ] Body 内容符合 complexity 级别
- [ ] 包含 When to Use 和 When Not to Use
- [ ] 目录结构符合标准
```

**评分影响**: +2~4 分

---

## 质量门槛达标模式

### Q001: 添加可测试说明

**问题**: 缺少验证方法

**修复模板**:
```markdown
## Testing / 测试方法

验证此 Skill 是否正常工作：

1. 测试查询: "..."
   期望输出: "..."

2. 测试查询: "..."
   期望输出: "..."
```

**评分影响**: +2 分

---

## 目录结构补全模式

### C001: 创建缺失目录

**自动修复操作**:
```bash
# 创建目录并添加 .gitkeep
mkdir -p references/ examples/ scripts/
touch references/.gitkeep examples/.gitkeep scripts/.gitkeep
```

**评分影响**: +1 分/目录

---

### C002: 生成 README.md

**自动提取内容**:

| 内容 | 来源 |
|------|------|
| 标题 | frontmatter.name |
| 副标题 | description 第一行 |
| 简介 | description 完整内容 |
| 功能 | When to Use 章节 |
| 使用 | Core Workflow 章节 |
| 结构 | 扫描现有目录 |
| 版本 | frontmatter.version |
| 兼容性 | frontmatter.compatibility |

**生成模板**:
```markdown
# {name}

> {description-first-line}

## 简介

{description-full}

## 功能

{when-to-use-items}

## 使用

{basic-usage}

## 目录结构

```
{name}/
├── README.md
├── SKILL.md
├── .skill-meta/
│   └── manifest.yaml
├── references/
├── examples/
├── scripts/
└── tests/
```

## 版本

- 当前版本: {version}

## 兼容性

{compatibility-table}
```

**评分影响**: +2 分

---

## 批量优化模式

### 高优先级批量修复（Schema 合规性）

**执行顺序**:
```
1. S001 修复 name 格式（仅 ASCII；中文 name 跳过）
2. S002 添加 version
3. S003 添加 complexity
4. S004 添加 compatibility
5. S005 修复 description 格式
```

**预期提升**: +10~15 分

---

### 中优先级批量修复（内容质量）

**执行顺序**:
```
1. B001 修复写作语态
2. B002 添加 When to Use
3. B003 添加 When Not to Use
4. B004 优化核心工作流
```

**预期提升**: +10~18 分

---

### 人工协作批量修复（方法论）

**执行顺序**:
```
1. M001 添加竞争壁垒声明
2. M002 添加 DoD
3. F001 优化 description
```

**预期提升**: +10~18 分

---

### 结构补全批量修复

**执行顺序**:
```
1. C001 创建缺失目录
2. C002 生成 README.md
```

**预期提升**: +3~5 分

---

## 训练纪律模式（借鉴 microsoft/SkillOpt）

SkillOpt 把 skill 文档当作可训练参数：候选编辑只在**严格提升留出验证分**时接受（held-out gate），
每步有编辑预算（learning_rate），被拒编辑进缓冲（rejected-edit buffer），跨轮有元记忆（meta skill）。
以下 G001-G006 把同套纪律落进 opt 的修复闭环。

### 副本状态目录（.opt-state）

跨轮状态统一放 `{skill}-fix/.opt-state/`（与副本同路径并排，写回时不进入源文件）：

```
{skill}-fix/.opt-state/
├── gate-baseline.json     # 修复前留出集 F1 基线
├── rejected-edits.yaml    # 拒绝编辑缓冲
├── training-log.yaml      # 跨轮元记忆
└── split-map.json         # （可选）每用例所属集合
```

### G001: 留出验证门（held-out validation gate）

**问题**: 触发用例同一批既引导修复又当验收标准 → 修复过拟合（实例：bm-brand-voice-extractor 修复后
F1 在三轮间 0.878~0.915 波动、flaky 用例 6→1，正是同批用例复评的噪音）。

**机制**: 按用例 id + seed 确定性切分为引导集（生成候选）与留出集（验收），默认留出 20%（如 50 条 → 40/10；A 卷总数按复杂度 25/50/100 条）。

```bash
# 修复前记录基线（只跑一次）
python3 scripts/split-gate.py {results}.json --seed 42 --baseline-out {skill}-fix/.opt-state/gate-baseline.json
# 每轮修复后复检：留出集 F1 不降（容差 0.005）；回归 → exit 2，本轮回合被拒
python3 scripts/split-gate.py {results}.json --seed 42 --baseline {skill}-fix/.opt-state/gate-baseline.json
# 查看切分 / 输出每用例归属
python3 scripts/split-gate.py {results}.json --seed 42 --split-map {skill}-fix/.opt-state/split-map.json
```

**规则**:
1. 同 seed 切分跨轮一致（可复现）；改 seed 需重建基线
2. 留出集 F1 降幅 > 0.005 → `regressed`，exit 2：撤销本轮回合修复，修复记入拒绝缓冲（G003）
3. 留出集持平或提升 → 通过，继续回归验证与复评
4. 输入为触发评测结果 JSON/Excel（score-trigger-eval.py 输入格式）
5. **与 eval B 卷的关系**：本门的留出集是从 A 卷（按复杂度 25/50/100 条）内按 seed 抽出的留出集（默认 20%），用于**修复过程**的逐轮门禁（gate_no_regression）；eval 的 **B 卷是独立封印的固定 10 条题**（修复全程不可见），用于**副本交付前最终门禁**（F1 ≥ 0.85）。opt 修复轮用本门，交付门禁由 eval 执行，opt 不得读取 B 卷题面。

**评分影响**: 不直接加分，但防止"修复被教到 A 卷用例上"的虚假达标

### G002: 编辑预算（learning_rate = 每轮最大修复数）

**问题**: 一批次同时改大量内容，回归失败难定位，一次大改引入新问题。

**机制**: `plan-fixes.py --budget N`（opt 流程默认 5），超出截断留待下一轮；随轮次可递减（如 5→4→3）。

```bash
python3 scripts/plan-fixes.py {report}.yaml --budget 5
```

**规则**: 每轮只执行预算内修复 → 留出验证门 → 回归验证；全通过再进入下一批。小步更新等效于
SkillOpt 的梯度裁剪，直接降低回归验证失败率。

### G003: 拒绝编辑缓冲（rejected-edit buffer）

**问题**: 停滞检测只数"连续 3 轮无提升"，不记忆失败修复；plan-fixes 每轮从同一报告重新生成，
可能重复提交已被证明无效的修复。

**机制**: 被验证门拒绝 / 回归失败 / 停滞轮次未提升的修复，记入 `rejected-edits.yaml`：

```yaml
rejected_edits:
  - fingerprint: "a1b2c3d4e5f6"      # field|message 的 SHA-1 前 12 位
    field: "description"
    message: "触发词不足"
    round: 3
    reason: "修复后留出集 F1 0.85→0.82，被验证门拒绝"
```

**规则**: plan-fixes 加 `--rejected-edits` 后自动排除；停滞结论附「已试修复清单」。

### G004: 跨轮元记忆（meta skill）

**问题**: 每轮修复相互独立，无"哪类修复上次有效"的记忆，反复评测时重复犯同类错误。

**机制**: 每轮结束更新 `training-log.yaml`，plan-fixes 参考后把 effective 类型提前、无效类型延后：

```yaml
training_log:
  - round: 1
    fix_type: "schema_compliance"
    score_before: 78.0
    score_after: 83.0
    outcome: "effective"      # effective / ineffective / regression
    holdout_f1_before: 0.80
    holdout_f1_after: 0.82
```

### G005: 压缩打磨 epoch（best_skill.md 紧凑化）

**问题**: 8000 字符只是上限阈值，达标后没有自动瘦身步骤，正文冗余。

**机制**: 副本综合分数 ≥85 后、副本交付前，加一轮压缩：去冗余、合并章节、压缩示例，保持 ≥85 且
无新 error/warning，取最短可用版本留在副本。等效于 SkillOpt 产出紧凑 best_skill.md。

### G006: 双端冒烟验收（跨 harness 迁移）

**问题**: 验收只看 dsh 侧 eval 分，跨执行环境（codex 等）无回归验证。

**机制**: 副本交付前在 dsh 与 codex CLI 各跑一遍触发用例冒烟，双端无回归才算达标（等价于 SkillOpt
在 direct chat / Codex / Claude Code 多 harness 评估的迁移验证）。

---

## 优化风险与规避

### 高风险修改

| 修改 | 风险 | 规避策略 |
|------|------|----------|
| 修改 name | 破坏引用 | 同时更新所有内部引用 |
| 修改 complexity | 可能需要大量内容调整 | 先评估内容长度 |
| 删除内容 | 丢失重要信息 | 先迁移到 references/ |
| 修改核心流程 | 改变 Skill 行为 | 最小改动 + 回归验证；失败自动撤销 |

### 修改前检查清单

- [ ] 是否已备份原文件？
- [ ] 是否理解修改的影响范围？
- [ ] 是否有回滚方案？
- [ ] 是否已记录判断依据、备份与回滚点？

---

**模式库版本**: 2.1.0 | **配套 Skill**: root-skills-opt v3.4.0 | **Schema 版本**: 1.1.0
