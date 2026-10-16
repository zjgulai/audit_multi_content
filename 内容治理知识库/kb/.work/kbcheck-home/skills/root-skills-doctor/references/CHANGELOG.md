# root-skills-doctor 版本历史

## v2.1.0 (2026-09-03)

- **评测前批量预检（preflight）**：新增 `scripts/doctor-preflight.py`——把整批源复制到 `--out` 副本目录，在副本上统一编码（UTF-8）、补 frontmatter 默认值（缺 license 补 MIT、缺 last_updated 补当天）、补「安全边界 / 错误处理」标准章节、`scripts/*.py` 语法检查、嵌套目录展平；源目录只读不写回。`--dry-run` 预览不落盘。评测/opt 前先跑它，让静态标准件缺项不进评测，减少"修复→全量重测"。
- **知识库缺陷预检**：preflight 读取 `root-skills-check` 的 `--export-top-defects`，把已沉淀缺陷列入待人工复核，避免下批重复踩坑。

## v2.0.4 (2026-09-01)

- **正文去沉积（规则不删）**：修复模式详解改为确认门槛表（D005 扩展名映射仍在正文）；家族注册表同步压缩为两条命令。D001–D007 / D100 全表未删。

## v2.0.3 (2026-09-01)

- **中文 name（与 eval / opt 同步）**：D102 对 Unicode 字母（含中文）且与目录一致记通过，kebab-case 记 na；禁止把中文 name 改回英文
- **D115**：单包 `skills._shared` 缺失记 warning，不阻断、不为修它改 name

## v2.0.2 (2026-09-01)

- **D108 误报修复**：危险命令检测增加否定语境过滤（`无/不/禁止/避免/请勿/不要 rm -rf` 等说明性文案不再误判为危险命令），修复 `build-html-report.py` 内「无 rm -rf」安全说明被误报为 error 的问题

## v2.0.1 (2026-08-31)

- **清理遗留引用**：旧名 `lute-skills-eval` / `lute-skills-opt` / `lute-skills-creator` 全部替换为 `root-skills-*` 家族名
- **失效路径修复**：二次验证脚本路径改为 `../root-skills-creator/scripts/validate-skill.py`
- **Skills 索引同步章节重写**：原指向不存在的 CSV 索引与 sync 脚本，改为「家族注册表同步」——使用 `root-skills-manage` 的 manage 命令（check / register）维护家族注册表

## v2.0.0 (2026-08-27)

- 新增 D100 系列检查项（D101-D114）：基于企业 AI Agent Skill 创建评测研究报告
- 新增规范检查：name 一致性/kebab-case、description 触发质量与长度、XML 尖括号、正文长度
- 新增安全检查：脚本危险命令、硬编码密钥
- 新增结构补充：references 长度、assets 占位符、evals 缺失、Constraints、last_updated
- 归属 root-skills 家族，由 root-skills-manage 管理

## v1.0.0 (2026-05-27)

- 初始版本
- 基于 2026-04-03 / 04-09 / 04-10 三次大规模 Skill 目录结构修复经验固化
- 支持 7 种修复模式（D001-D007）
- 批量检测与修复模式
- 自动备份与回滚机制
- --dry-run 预览模式
