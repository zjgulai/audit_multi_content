# Registry Schema - 家族注册表规范

`registry/skills.json` 是 root-skills 家族状态的**单一事实来源**。

## 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `family` | string | 家族名，固定 `root-skills` |
| `root_dir` | string | 家族根目录（相对本文件），默认 `..` |
| `version` | string | 注册表自身版本 |
| `updated_at` | string | 最后更新时间（ISO 8601） |
| `members` | array | 成员列表 |

## 成员字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | kebab-case 成员名 |
| `path` | string | ✅ | 相对注册表文件的路径 |
| `status` | string | ✅ | `planned` / `active` / `deprecated` |
| `version` | string/null | ✅ | 成员 frontmatter 版本；未创建为 null |
| `role` | string | ✅ | `create` / `manage` / `diagnose` / `evaluate` / `optimize` / `check` / `orchestrate` |
| `description` | string | ✅ | 一句话职责说明 |
| `depends_on` | array | ✅ | 依赖的其他成员或外部 skill 名 |

## 状态枚举

| 状态 | 含义 | 路由行为 |
|------|------|----------|
| `planned` | 已登记未创建 | 路由时提示"尚未创建，请先创建" |
| `active` | 已创建、可加载 | 正常参与路由 |
| `deprecated` | 已停用 | 从路由候选移除，保留记录 |

## 一致性规则

1. `path` 必须存在且含可读的 `SKILL.md`
2. `version` 与 SKILL.md frontmatter 的 version 一致
3. 同一 `role` 最多一个 `active` 成员（评估/优化/诊断均已切换为家族版 root-skills-eval/opt/doctor，原 lute 生态成员记 `deprecated` 以 status 区分）
4. `depends_on` 中引用的成员必须已登记

## 校验命令

```bash
python scripts/manage.py check
```

输出：每条成员路径/版本/依赖的检查结果。
