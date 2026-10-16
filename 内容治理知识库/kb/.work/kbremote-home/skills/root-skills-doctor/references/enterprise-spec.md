---
title: 企业评测规范检查项（D100 系列）
doc_type: reference
module: root-skills-doctor
topic: enterprise-spec
status: stable
created: 2026-08-27
updated: 2026-08-27
owner: self
source: 企业AI_Agent_Skill_创建评测研究报告_v1.1_20260827
---

# 企业评测规范检查项（D100 系列）

本文件定义 `root-skills-doctor` 基于《企业 AI Agent Skill 创建评测研究报告》（v1.1，2026-08-27）补充的静态检查项。原版 D001-D007 见 `fix-patterns.md` 与 `directory-spec.md`。

> **边界声明**: D100 系列只做**静态可检测**的规范/安全检查。触发准确率（F1）、A/B 质量（Pass Rate/Delta）、六维评分属于运行期评测，归 `root-skills-eval`。

## 检查项总览

| 错误码 | 问题 | 等级 | 自动修复 | 来源章节 |
|--------|------|------|---------|---------|
| D101 | name 与目录名不一致 | error | ❌ | 5.2 / 4.3 |
| D102 | name 格式（ASCII kebab-case；中文/Unicode 字母通过） | error | ❌ | 4.3 / 5.2 |
| D103 | description 超长（>1024） | warning | ❌ | 4.3 / 5.2 |
| D104 | description 缺触发条件/功能动词 | warning | ❌ | 3.1 / 5.2 |
| D105 | frontmatter 含 XML 尖括号 | error | ❌ | 4.3 |
| D106 | 正文超长（>500 行 / >5000 tokens） | warning | ❌ | 5.2 |
| D107 | scripts/ 无执行权限 | warning | ✅ chmod +x | 5.2 |
| D108 | 脚本含危险命令 | error | ❌ | 5.6 / 7.3 |
| D109 | 硬编码密钥 | error | ❌ | 7.3 |
| D110 | references/ 单文件超长 | warning | ❌ | 5.2 |
| D111 | assets/ 模板无占位符 | info | ❌ | 5.2 / 4.2 |
| D112 | 缺少 evals/ | info | ❌ | 4.2 / 5.3 |
| D113 | 缺 Constraints | info | ❌ | 3.1 / 5.2 |
| D114 | 缺 last_updated / version | info | ✅ 生成 | 7.2 |
| D115 | 单包 skills._shared 缺失 | warning | ❌ 不阻断、不为修它改 name | 单包 |

## 各检查项细则

### D101: name 与目录名不一致

**规范**: name 必须与父目录名完全一致（4.3 / 5.2 "无法被发现，或 /skill-name 对不上"）。

**处理**: 人工改 frontmatter 的 name 或重命名目录，保持二者一致。中文最终包：应对齐中文 name（改目录），**禁止把中文 name 改回英文**。

### D102: name 格式（ASCII kebab-case / 中文 Unicode 通过）

**规范**（4.3）:
- 1-64 字符
- ASCII：仅小写字母、数字、连字符；不能首尾连字符、不能连续连字符
- **中文 / Unicode 字母 name：与目录一致即通过；kebab-case 记 na**
- **禁止把已通过的中文 name 改回英文**
- 不能含保留词 claude、anthropic

**示例**:
- ✅ `pdf-processor`
- ✅ `品牌声音提取器`（与目录一致）
- ❌ `pdf_processor`（ASCII 下划线）、`PDF-Processor`（ASCII 大写）、`pdf--x`（连续连字符）

### D103: description 超长

**规范**: description ≤ 1024 字符（4.3）。description 是唯一常驻系统提示的部分，过长浪费上下文。

### D104: description 缺触发条件或功能动词

**规范**（3.1 / 5.2）: description 必须同时写清"做什么"（动作动词）和"何时用"（触发条件 + 关键词 + 负例边界）。

**低质量**: "处理文档"（无动作动词、无触发、无负例）
**高质量**: "处理 PDF 文档的提取、转换和合并。当用户提及 PDF转Word、提取PDF文字、合并PDF 或上传 .pdf 文件时使用。不适用：图片处理、扫描件 OCR。"

### D105: frontmatter 含 XML 尖括号

**规范**（4.3）: Frontmatter 禁止 XML 尖括号 `< >`。

### D106: 正文超长

**规范**（5.2）: SKILL.md 正文建议 < 5000 tokens、主文件 < 500 行。一触发就撑爆上下文 = 渐进式披露失败。

**处理**: 把按需加载的知识下沉到 references/，正文只留核心工作流。

### D107: scripts/ 无执行权限

**规范**（5.2）: scripts/ 有可执行权限；单一职责、可 --help。

**修复**: `chmod +x` 自动执行。

### D108: 脚本含危险命令

**规范**（5.6 / 7.3 禁止项）: scripts/ 不得包含 `rm -rf` 或破坏性命令。

**检测模式**: `rm -rf`、`del /f /s /q`、`format`、`shutdown`、`chmod -R 777`、`dd if=...of=/dev/`、`mkfs` 等。

### D109: 硬编码密钥

**规范**（7.3 禁止项）: SKILL.md 不得硬编码 API Key / 密码；scripts 同样。

**检测模式**: api_key / secret / password / token 赋长值、`sk-` 前缀、AWS `AKIA` 前缀等。

**处理**: 迁移到环境变量 / 凭据层 / DSH credential 配置。

### D110: references/ 单文件超长

**规范**（5.2）: references/ 单文件建议 < 3000 tokens。

**处理**: 拆分为多个主题文件，正文按需引用。

### D111: assets/ 模板无占位符

**规范**（5.2）: assets/ 模板用 `{{variable_name}}` 标记占位符，与指令分离。

### D112: 缺少 evals/ 目录

**规范**（4.2 / 5.3）: 生产级 Skill 应含 evals/（正例/反例/边界/注入用例）。

**处理**: 用 root-skills-creator 的评测循环补 evals.json 并运行。

### D113: 缺 Constraints

**规范**（3.1 / 5.2）: 正文含 NEVER / ALWAYS / IF…THEN 等确定性约束，提供安全边界。

### D114: 缺 last_updated / version

**规范**（7.2）: 语义化版本 + last_updated + Git commit。

**修复**: 自动写入 last_updated 字段（需人工补 version 时手动确认）。

### D115: 单包 skills._shared 缺失

**规范**: 独立 skill 包通常没有家族级 `skills._shared`。`scripts/` 出现 `from skills._shared` / `import skills._shared` 记 **warning**，不阻断、不为修它改 name。

## 与运行期评测的分工

| 检查 | 归属 | 工具 |
|------|------|------|
| 目录结构（D001-D007） | 静态 | root-skills-doctor |
| 规范/安全静态检查（D100 系列） | 静态 | root-skills-doctor |
| 触发准确率（Precision/Recall/F1） | 运行期 | root-skills-eval（触发评测） |
| 功能测试 / A/B Benchmark | 运行期 | root-skills-eval |
| 六维评分（100 分制） | 静态+人工 | root-skills-eval |
| 自动修复 | 静态 | root-skills-doctor / root-skills-opt |

---

**权威源**: 《企业 AI Agent Skill 创建评测研究报告》v1.1（2026-08-27）第 3.1 / 4.2 / 4.3 / 5.2 / 5.3 / 5.6 / 6.1 / 7.2 / 7.3 节
