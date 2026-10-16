# 变更记录

## v1.1.1 — 2026-09-16（路由修正）

依据：现场实测——把含 `agent.yaml` 的 agent 包喂给 `root-skills-eval` 的校验器，得到
`ERROR [structure]: SKILL.md not found (case-sensitive)`，结构未通过、**分数封顶 30/100**；
同一个包喂给 `root-agents/root-agent-doctor` 则正常返回 `verdict`。

| # | 改动 | 针对什么 |
|---|---|---|
| 1 | `SKILL.md` 边界「只评测已有的 agent 包」：`root-skills-eval` → **`root-agents` 家族**（②`root-agent-doctor` / ③`root-agent-eval` / ④`root-agent-opt` / ⑤`root-agent-check`），并写明**不是** `root-skills-eval` 的原因 | 原指向把 agent 包送进只认 `SKILL.md` 的 Skill 家族，属功能性误路由 |
| 2 | `SKILL.md` 边界「只体检 agent 包结构」：「交给评测侧」→ 点名 `root-agent-doctor` | 「评测侧」两家族都适用，含糊 |
| 3 | `description` 的「不适用」段：评测与造包两条路由都写全家族名 | 与 `root-skills-eval`、`root-agents` 各自 frontmatter 的反向声明对齐 |
| 4 | `README.md` 两处（什么时候用 / 边界）同步改 | 同 1 |
| 5 | `.skill-meta/manifest.yaml` 的 `related_skills` 补 `root-agents` | 元数据里原本没有 Agent 家族任何成员 |
| 6 | `version` 1.1.0 → 1.1.1 | — |

根因：`root-skills-*`（Skill 家族，装在 `~/.agents/skills/`）与 `root-agents/root-agent-*`
（Agent 家族，装在 `~/.dsh/skills/root-agents/`）名字只差一个词。v1.1.0 补边界时加了
「只要成品包 → root-agents」，**漏改了同一段的评测路由**，于是同一个 frontmatter 里造包指向
Agent 家族、评测却指向 Skill 家族。

未改动：正文判断、`references/` 判据、`scripts/` 逻辑。

## v1.1.0 — 2026-09-15（评测后修复）

依据：`agent-build-flow-final-report.html`（轨道 A 95.3 / 轨道 B F1 0.894 / 轨道 C 91.2）

| # | 改动 | 针对什么 |
|---|---|---|
| 1 | `description` 的「不适用」段补两条边界：**只要成品包不要流程 → root-agents**；**只拆工单不涉及立项 → to-tickets** | 组合标签 8 次 FP 中多数是本 Skill 与 `root-agents` 的职责冲突；收紧后触发精度应改善 |
| 2 | 新增 `tests/red-baseline.md` + `tests/red-out.json` | 补 Release #3 缺失的 without-skill RED 失败基线（真实运行取证） |
| 3 | 删除 `.DS_Store` | DoD「可打包：无无效文件」 |

未改动：正文判断、references 判据、scripts 逻辑。判据层零改动。
