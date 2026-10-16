---
name: root-skills-doctor
description: |
  检测 Skill 目录结构问题并执行自动修复的"结构医生"，支持单 Skill 和批量模式。
  当用户提及"修复 skill 结构"、"skill 目录整理"、"批量修复 skills"、
  "skill 结构检测"、"整理 skill 目录"、"修复目录结构"、"skill 体检"、
  "检查 skill 规范"或发现 Skill 目录存在文件乱放、目录缺失、路径引用失效、
  规范不合规时使用。
  触发词：修复 skill 结构、skill 目录整理、批量修复 skills、skill 结构检测、
  整理 skill 目录、修复目录结构、skill-doctor、skill 体检、规范检查。
  覆盖目录结构（D001-D007）与规范/安全静态检查（D100 系列，基于企业 Skill
  评测研究报告）：frontmatter 合规、description 触发质量、长度、脚本可执行、
  危险命令、硬编码密钥等。
version: "2.1.0"
complexity: "complex"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["File system operations need manual execution"] }
  minimax: { status: "bridge", limitations: ["File system operations need manual execution"] }
  dsh: { status: "native" }
  codex: { status: "native" }
---

# Skill 结构医生

本 Skill 的唯一职责：检测 Skill 目录结构问题并执行自动修复，确保 Skill 符合 Universal Skill Schema 规范与企业评测标准。

不负责 SKILL.md 内容质量（用 `root-skills-eval` + `root-skills-opt`），也不处理非 Skill 目录的通用文件整理。只回答一件事：

**这个 Skill 的目录结构是否符合规范，如果不符合，能否自动修复。**

---

## 何时使用 / When to Use

- 需要检测单个 Skill 的目录结构问题
- 需要批量检测 `skills/` 目录下全部 Skill 的结构问题
- 发现 Skill 根目录存在杂乱文件需要整理
- 需要自动创建缺失的目录或文件（README.md、manifest.yaml、.gitkeep）
- 文件迁移后需要更新 SKILL.md 中的路径引用
- 批量新建 Skills 后需要统一标准化目录结构

## 何时不该使用 / When Not to Use

- SKILL.md 内容质量问题（触发词不准确、语态错误、方法论同质化）→ 使用 `root-skills-eval` + `root-skills-opt`
- 需要完全重写 Skill → 建议重新设计
- 非 Skill 目录的通用文件整理
- 需要删除 SKILL.md 或已有内容的文件（本 Skill 禁止删除核心文件）

## 中文最终包（与 eval / opt 同步）

- **name 与目录一致**且为 Unicode 字母（含中文）→ D102 **通过**；kebab-case 记 **na**。ASCII 仍要求 kebab-case。
- **禁止把中文 name（及目录名）改回英文。**
- 单包 `skills._shared` 缺失 → **D115 warning**，不阻断、不为修它改 name。

---

## 核心能力

### 1. 结构扫描

扫描指定 Skill 或全部 skills，识别以下问题：

| 错误码 | 问题 | 等级 | 自动修复 |
|--------|------|------|---------|
| D001 | 缺少 README.md | warning | ✅ 生成模板 |
| E002 | 非 Skill 目录（缺少 SKILL.md） | error | ❌ 无法自动修复 |
| D003 | 缺少 manifest.yaml | warning | ✅ 生成模板 |
| D004 | complex Skill 缺少 references/ | warning | ✅ 创建目录 |
| D005 | 根目录存在杂乱文件 | warning | ✅ 分类迁移 |
| D006 | 路径引用失效 | warning | ✅ 自动更新 |
| D007 | 空目录缺少 .gitkeep | info | ✅ 自动添加 |

### 2. 规范与安全检查（D100 系列）

基于企业 Skill 评测研究报告（5.2 静态分析 / 4.3 frontmatter 规范 / 5.6 安全 / 6.1 评分锚点）补充的静态检查项。规范细则见 `references/enterprise-spec.md`。

| 错误码 | 问题 | 等级 | 自动修复 |
|--------|------|------|---------|
| D101 | name 与目录名不一致 | error | ❌ 需人工对齐（中文包应改目录对齐中文 name，禁止把中文 name 改回英文） |
| D102 | ASCII 须 kebab-case；中文/Unicode 字母（与目录一致）通过，kebab 记 na；禁止把中文 name 改回英文 | error | ❌ 仅 ASCII 非法时改名 |
| D103 | description 超长（>1024 字符） | warning | ❌ 需人工精简 |
| D104 | description 缺少触发条件（无"何时用"/触发词/负例边界） | warning | ❌ 需人工补写 |
| D105 | frontmatter 含 XML 尖括号 < > | error | ❌ 需人工去除 |
| D106 | SKILL.md 正文超长（>500 行 或 >5000 tokens） | warning | ❌ 建议下沉 references/ |
| D107 | scripts/ 存在无执行权限的脚本 | warning | ✅ chmod +x |
| D108 | scripts/ 含危险命令（rm -rf / 破坏性操作） | error | ❌ 需人工审查 |
| D109 | SKILL.md 硬编码密钥（api_key/secret/password/token） | error | ❌ 需人工迁移到凭据层 |
| D110 | references/ 单文件超长（>3000 tokens） | warning | ❌ 建议拆分 |
| D111 | assets/ 模板缺 {{placeholder}} 占位符标记 | info | ❌ 建议规范化 |
| D112 | 缺少 evals/ 目录或 evals.json | info | ❌ 建议用 creator 补评测 |
| D113 | 缺少 Constraints（NEVER/ALWAYS/IF…THEN） | info | ❌ 建议补安全边界 |
| D114 | 缺 last_updated / 版本字段 | info | ✅ 生成模板 |
| D115 | 单包 scripts 依赖 skills._shared（目录下通常不存在） | warning | ❌ 不阻断；不要为修它改 name |

### 3. 自动修复

对可自动修复的问题直接执行：
- 创建缺失目录
- 按扩展名分类迁移根目录文件
- 生成 README.md / manifest.yaml 模板
- 更新 SKILL.md 中的失效路径引用
- 为空目录添加 .gitkeep
- 为无执行权限脚本 chmod +x（D107）
- 生成 last_updated 模板（D114）

### 4. 批量模式

一次性扫描 `skills/` 目录下的全部 Skill，输出汇总报告：
- 问题统计（error / warning / info 分布）
- 按 Skill 排序的问题清单
- 优先修复队列
- **评测前批量预检（preflight，供 root-skills-eval 批量评测前调用）**：先做编码统一 UTF-8 / frontmatter / 章节完整性 / `scripts/*.py` 可 parse 预检；可自动修复的共性静态缺项（license、last_updated、安全边界、错误处理等标准件）**批量补到副本目录**（不写回原目录，源保持只读）；预检前先读 `../root-skills-check/scripts/ingest.py --export-top-defects`，把知识库已沉淀缺陷纳入检查项。

评测前批量预检命令：

```bash
# 预览（不写盘；把每个 skill 复制到临时目录演练，输出将修复项报告）
python scripts/doctor-preflight.py /path/to/source --out /path/to/prepared --dry-run

# 执行：复制到 prepared/ 并在副本上批量补标准件（源目录只读，不写回）
python scripts/doctor-preflight.py /path/to/source --out /path/to/prepared
```

### 5. 安全机制

- **自动备份**：每次修复前创建 `.doctor-backup/{timestamp}/`
- **--dry-run 预览**：只展示操作，不修改文件
- **--check 检测**：纯检测，不生成修复计划
- **回滚支持**：`--rollback` 恢复到最近一次备份
- **禁止删除**：绝不删除 SKILL.md、.git/ 或已有内容的文件

---

## 标准工作流

### Step 1: 扫描诊断

运行检测，识别结构问题：

```bash
# 单 Skill 检测
python scripts/skill-doctor.py /path/to/skill --check

# 批量检测
python scripts/skill-doctor.py /path/to/skills --batch --check
```

生成分类问题清单：
- error：必需文件/目录缺失（阻塞发布）
- warning：推荐文件/目录缺失或根目录杂乱（推荐修复）
- info：可选优化建议

### Step 2: 预览修复计划（推荐）

执行 --dry-run 预览：

```bash
python scripts/skill-doctor.py /path/to/skill --dry-run
```

输出将要执行的操作清单，确认无误后再执行实际修复。

### Step 3: 执行修复

```bash
# 单 Skill 修复
python scripts/skill-doctor.py /path/to/skill

# 批量修复（逐个执行，每批次确认）
python scripts/skill-doctor.py /path/to/skills --batch
```

修复按优先级排序：
1. P0 安全：创建备份
2. P1 结构：根目录文件迁移
3. P2 必需：README.md / manifest.yaml 生成
4. P3 推荐：缺失目录补全 / .gitkeep 添加
5. P4 验证：路径引用更新 / 重新扫描

### Step 4: 验证

修复后重新运行检测，确认问题已解决：

```bash
python scripts/skill-doctor.py /path/to/skill --check
```

同时运行 `validate-skill.py` 进行二次验证：

```bash
python ../root-skills-creator/scripts/validate-skill.py /path/to/skill
```

---

## 修复模式详解

完整定义见 `references/fix-patterns.md`。正文只留改变行为的确认门槛与迁移规则：

| 码 | 需确认 | 规则 |
|----|--------|------|
| D001 | 是 | 从 frontmatter 生成 README 模板；用户须补用法示例 |
| D003 | 是 | 从 frontmatter 生成最小 manifest；compatibility 须用户核实 |
| D005 | 是 | 按扩展名迁移：`.py/.sh/.js`→`scripts/`，`.md/.yaml/.json/.txt/.csv`→`references/`，`.png/.jpg/.svg`→`assets/`；迁移后更新 SKILL.md 与 README 相对路径；先展示文件列表再执行 |
| D006 | 否 | 引用的 `references/`、`scripts/`、`examples/` 不存在时，在对应目录搜同名文件并更新；纯机械替换 |

---

## 安全机制

安全机制完整定义见 `references/safety-rules.md`。

### 核心原则

不破坏、可回滚、先预览、后执行。

### 备份策略

- 备份位置：`.doctor-backup/{timestamp}/`
- 保留数量：最近 10 个
- 备份内容：被修改的原始文件 + 操作日志

### 禁止操作

| 禁止项 | 原因 |
|--------|------|
| 删除 SKILL.md | 核心文件，任何情况不删除 |
| 删除 .git/ | 版本控制目录，完全禁止触碰 |
| 操作非 Skill 目录 | 扫描前验证目录结构 |
| 覆盖已有内容的文件 | 只覆盖空文件或 .gitkeep |

---

## 与 Eval/Opt 的分工

| 工具 | 职责 | 不处理 |
|------|------|--------|
| **root-skills-doctor** | 目录结构 + 规范/安全静态检查与修复 | 内容质量、触发词优化 |
| **root-skills-eval** | 六维度质量评估 + 触发评测 | 自动修复 |
| **root-skills-opt** | 基于评估报告的优化 | 结构问题 |
| **validate-skill.py** | 快速验证 | 批量修复 |

**推荐组合使用**：

```bash
# 1. 修复结构问题
python root-skills-doctor/scripts/skill-doctor.py ./my-skill

# 2. 评估内容质量
/root-skills-eval ./my-skill

# 3. 优化内容
/root-skills-opt ./my-skill-evaluation-report.yaml
```

## 家族注册表同步

修复后保持 `root-skills-manage/registry/skills.json` 与 frontmatter 一致（name/path/version/role/status/depends_on）：

```bash
python ../root-skills-manage/scripts/manage.py check
python ../root-skills-manage/scripts/manage.py register <skill-name> --path <path> --role <role> --description "<desc>"
```

---

## 常见错误

| 错误 | 为什么错 |
|------|---------|
| 跳过 --dry-run 直接修复 | 可能产生非预期修改，preview 是零成本保险 |
| 修复后不验证 | 修复可能引入新问题，必须二次确认 |
| 对 non-skill 目录运行 doctor | 脚本会拒绝操作，但应提前确认目录合法性 |
| 忽略 E002（非 Skill 目录，缺少 SKILL.md） | 这是 error 级别，意味着根本不是合法 Skill |
| 不清理旧备份 | 备份目录会累积，定期清理 `.doctor-backup/` |
| 把 doctor 当 opt 用 | doctor 不管内容质量，只管目录结构 |
| 把中文 name 改回英文 | D102 对中文合法 name 记 na；改回英文是错误修复 |

---

## 速查手册

**先 --check → 再 --dry-run → 执行修复 → 重新验证。定期批量：`--batch --check`。**

---

## 依赖 / Dependencies

- `scripts/skill-doctor.py` — 核心检测修复脚本
- `../root-skills-creator/scripts/validate-skill.py` — 基础验证工具（家族内路径）
- `references/fix-patterns.md` — 修复模式库
- `references/safety-rules.md` — 安全机制
- `references/directory-spec.md` — 目录规范速查
- `references/enterprise-spec.md` — 企业评测研究报告检查项（D100 系列）

---

## 版本历史 / Changelog

见 `references/CHANGELOG.md`。

---

**版本**: 2.0.4 | **Schema 版本**: 1.1.0 | **类型**: Technique | **框架**: root-skills
