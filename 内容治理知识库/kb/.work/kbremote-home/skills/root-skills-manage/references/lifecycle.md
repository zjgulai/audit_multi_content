# Lifecycle - 生命周期状态机

管理家族成员 skill 从登记到停用的完整状态流转。

## 状态机

```
                 create                 update
  (idea) ──────▶ planned ────────────▶ active ──────▶ active (新版)
                  │  ▲                    │
                  │  │ 重新激活            │ 停用
                  ▼  │                    ▼
               deprecated ◀──────────── active (停用)
```

## 状态说明

| 状态 | 进入条件 | 离开条件 |
|------|----------|----------|
| `planned` | 用户确认要建新成员，登记到注册表 | 目录创建完成 + SKILL.md 就绪 → active |
| `active` | SKILL.md 通过结构验证，可加载 | 主动停用 → deprecated |
| `deprecated` | 用户停用/被替代 | 重新启用 → active；或删除条目 |

## 流转规则

### planned → active

1. 用 `root-skills-creator` 创建成员（含评测）。
2. 确认成员路径存在、SKILL.md frontmatter 合法。
3. `manage.py set-status <name> active` 更新注册表。
4. 若该职责此前曾轻接外部生态（如 eval/opt 已从 lute 生态切换为家族版），记录切换说明。

### active 版本更新

1. 检查 SKILL.md frontmatter version 是否递增（semver）。
2. 同步注册表 version 字段。
3. 更新 `updated_at`。

### active → deprecated

1. 用户确认停用原因。
2. 从路由候选移除（routing-guide 不再推荐）。
3. 保留注册表记录（含停用原因），不物理删除目录。

## 升级门禁（参考）

成员从个人使用升级为团队发布时，门禁见 root-skills-creator 的 `operating-modes.md`（explore → release）。manage 只跟踪状态，不执行门禁。

## 一致性检查

每次状态变更后运行：

```bash
python scripts/manage.py check
```

确保：路径存在、版本一致、依赖已登记、状态合法。
