---
title: Skill 结构医生 - 快速开始
doc_type: readme
module: root-skills-doctor
topic: quickstart
status: stable
created: 2026-05-27
updated: 2026-08-27
owner: self
source: human+ai
---

# root-skills-doctor

检测并修复 Skill 目录结构问题，并基于企业评测研究报告补充规范/安全静态检查。

## 一句话说明

扫描 Skill 目录结构，自动修复缺失目录、杂乱文件、失效路径引用等问题；同时检查 frontmatter 规范、description 触发质量、脚本权限、危险命令与硬编码密钥。

## 何时触发

- "修复 skill 结构"
- "skill 目录整理"
- "批量修复 skills"
- "skill 结构检测"
- "skill 体检"
- "检查 skill 是否符合规范"

## 快速用法

```bash
# 检测单个 Skill（含 D001-D007 + D100 系列）
python scripts/skill-doctor.py /path/to/skill --check

# 预览修复
python scripts/skill-doctor.py /path/to/skill --dry-run

# 执行修复
python scripts/skill-doctor.py /path/to/skill

# 批量检测全部 Skills
python scripts/skill-doctor.py /path/to/skills --batch --check

# 回滚
python scripts/skill-doctor.py /path/to/skill --rollback
```

## 核心能力

| 能力 | 说明 |
|------|------|
| 结构扫描 | 检测目录缺失、杂乱文件、失效引用（D001-D007） |
| 规范检查 | frontmatter/name/description 合规（D101-D106） |
| 安全检查 | 危险命令、硬编码密钥（D108-D109） |
| 资源检查 | references 长度、assets 占位符、evals、Constraints（D110-D113） |
| 自动修复 | 创建目录、迁移文件、更新路径、生成模板、chmod、last_updated |
| 批量模式 | 一次性处理全部 Skills |
| 安全机制 | 自动备份、--dry-run、回滚支持 |

## 修复模式

| 代码 | 问题 | 自动修复 |
|------|------|---------|
| D001 | 缺少 README.md | ✅ |
| D003 | 缺少 manifest.yaml | ✅ |
| D004 | complex 缺 references/ | ✅ |
| D005 | 根目录杂乱文件 | ✅ |
| D006 | 路径引用失效 | ✅ |
| D007 | 空目录缺 .gitkeep | ✅ |
| D107 | 脚本无执行权限 | ✅ chmod +x |
| D114 | 缺 last_updated / version | ✅ 生成字段 |

D100 系列其余检查项（D101-D106、D108-D113）为只读检测，需人工处理，详见 `references/enterprise-spec.md`。

## 参考资源

- `references/fix-patterns.md` — 修复模式详解
- `references/safety-rules.md` — 安全机制
- `references/directory-spec.md` — 目录规范
- `references/enterprise-spec.md` — 企业评测规范检查项（D100 系列）

## 家族关系

本 skill 是 `root-skills` 家族成员，由 `root-skills-manage` 统一管理。

---

**版本**: 2.0.4 | **框架**: root-skills | **D001-D007**: 自 v1.0.0 起保留（修复模式库见 `references/fix-patterns.md`）
