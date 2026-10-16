# Root Skills Manage

root-skills 家族管理器：统一管理 `root-skills-creator`、`root-skills-doctor`、`root-skills-eval`、`root-skills-opt` 等家族成员 skill 的注册、路由、生命周期、版本与状态。

## 家族全景

| 成员 | 职责 | 状态 |
|------|------|------|
| `root-skills-creator` | 创建生产级 skill（Iron Law + 真实运行验证 + 意图对话 + 模式分级 + 输出契约） | active (v4.1.3) |
| `root-skills-manage` | 家族管理器（本 skill） | active (v1.0.2) |
| `root-skills-doctor` | 诊断 skill 结构/触发/行为问题（D001-D007 + D100 系列） | active (v2.0.4) |
| `root-skills-eval` | 双卷全自主评估 + 唯一最终 HTML；check `--validate-only` 放行；低分修复才 `--require-desktop-fix` | active (v3.17.3) |
| `root-skills-opt` | 全自主副本修复 + 留出门禁 + 桌面副本交付（不写回原文） | active (v3.5.7) |
| `root-skills-check` | 报告放行入口 + 知识蒸馏（`--validate-only` / `--check-only`） | active (v1.0.1) |

## 快速开始

```bash
# 查看家族全景
python scripts/manage.py status

# 校验注册表一致性
python scripts/manage.py check

# 路由建议
python scripts/manage.py route "帮我评估这个 skill 好不好"
```

## 目录结构

```
root-skills-manage/
├── SKILL.md                      # 家族管理器定义
├── README.md                     # 本文件
├── .skill-meta/manifest.yaml     # 元数据
├── registry/
│   └── skills.json               # 家族注册表（单一事实来源）
├── references/
│   ├── registry-schema.md        # 注册表字段规范
│   ├── routing-guide.md          # 路由决策详解
│   └── lifecycle.md              # 生命周期状态机
├── scripts/
│   └── manage.py                 # 家族管理 CLI
├── tests/                        # 测试用例
└── examples/                     # 使用示例
```

## 核心原则

1. **只路由不执行**：manage 不实现创建/评估/优化的具体逻辑。
2. **单一事实来源**：registry/skills.json 是家族状态的唯一权威记录。
3. **路径与一致性硬门禁**：check 拒绝路径逃逸、非法 name/role/status、重复 active role、frontmatter 名称或版本漂移，以及未登记依赖。
4. **家族版统一**：eval/opt/doctor 均为家族版（active），不依赖原生态 lute 生态。
5. **依赖顺序**：多角色请求按 create → evaluate → optimize 路由。
6. **全程自主**：eval/opt 不设置用户确认节点；副本达标 + B 卷门禁通过后复制到桌面与源并排交付，**不写回被测 skill 原文**（含桌面源保持原样）。

---

**版本**: 1.0.2 | **框架**: root-skills
