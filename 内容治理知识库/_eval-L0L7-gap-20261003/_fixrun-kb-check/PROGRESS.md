# kb-check 修复 · 进度（以磁盘为准）

| 阶段 | 状态 | 落盘 |
|---|---|---|
| 建 fix 副本 + 源 chmod 只读 | 完成 | `kb-check-fix/`（SKILL.md + references/ + scripts/ + examples/） |
| 隔离装载（project 级 skill root） | 完成 | `<库根>/.dsh/skills/kb-check/`（rank 100 遮蔽用户级 rank 400） |
| 冒烟（接线核对） | 完成 | `rounds/_smoke.json`、`rounds/_smoke2.json` |
| 关键发现：目录只渲染前 500 字 | 完成 | `DISCOVERY-目录截断500字.md` |
| 作废：被中断半轮 / 描述被截断轮 | 留档 | `rounds/DISCARDED-*.json`、`ABORT-NOTE.md` |
| **A 卷第 1 轮** | **完成** | `rounds/a-round1b.json` → **P=0.889 R=1.000 F1=0.941**，调用 3/3 |
| A 卷第 2 轮 | 待跑 | |
| A 卷第 3 轮 | 待跑 | |
| B 卷门禁 10×3 | 待跑 | |
| score.json / README / 最终报告 | 待做 | |

## 计数口径
- 只统计 `parentSession == 0c6dd909-2376-42a7-a91a-7478fc6a4b84`（本修复会话）的会话；
  旁支 parent（上批评测 f41c4909、越界会话 92c12bd1、批驱动 session-29c8 等）一律**不计入**。
- 每个轮次用 `--since <起点ms>` 划窗口，冒烟/作废轮不会被算进正式轮。
- 有效性闸门：无回复（被中断）的会话既不算触发也不算不触发。
- 触发判定 = `skill` 工具调用 **或** `source.kind=="skill-invocation"` 的注入（斜杠调用走后者，无工具调用）。
