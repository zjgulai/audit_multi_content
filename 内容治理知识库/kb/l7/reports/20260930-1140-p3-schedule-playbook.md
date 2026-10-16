# P3 · 分层调度与「人可读的失败清单」—— 变更记录

- **时间**：2026-09-30（P1-3、P2 之后）
- **交付**：
  - `kb/l7/registry/failure-playbook.yaml` —— 失败清单的**唯一真源**（18 条处置 + 3 档调度）
  - `kb/l7/scripts/kb_pipeline.py` —— `--sync` 每个失败点都打对应的处置条目（8 个调用点）
  - `kb/l7/scripts/daily_health.py` —— 日报「要人做什么」每条都挂上**谁 / 命令 / 做什么 / 不许 / 复开条件**
- **结论**：调度三档写清；失败清单**从「某层红了」变成「谁、跑哪条命令、不许做什么」**；
  演练台新增 D2 用例（红闸门 → 日报点名到人）——**9/9 通过**。

---

## 1. 分层调度（三档，写进 `failure-playbook.yaml → schedules`）

| 档 | 什么时候 | 跑什么 | 谁跑 | 写什么 |
|---|---|---|---|---|
| **只读档**（已在跑） | 每日 08:30（launchd `com.kb.pipeline-daily`） | `kb/kbpy l7/scripts/daily_health.py` | 无人值守 | 只有 `kb/l7/reports/` 两份 |
| **预演档** | 需要时，任何时间（建议看完日报就跑） | `… kb_pipeline.py --sync --only L2` | 任何人 / 任何 agent | 无（引擎走干跑档） |
| **写档** | 人看过预演输出之后；当前口径＝两周只读观察期 | `… kb_pipeline.py --sync --only L2 --apply` | **人**（agent 不得自行开闸） | `kb/l2/**`（按层幂等键） |

写档的前置条件也写在同一处：无锁、本层闸门在预演里是「过」、在白名单内（当前只有 L2）。

## 2. 失败清单：18 条处置，覆盖到「下一步动作」

每条都有六件：`symptom / owner / do / command / forbidden / reopen_when`。
**`forbidden` 是条目的一部分** —— 写明不许怎么绕过（绕过的代价通常比红着更大）。

| 类别 | 条目 |
|---|---|
| 闸门红 | `gate_red.L1` … `gate_red.L7` + `gate_red.*` 兜底（逐层：谁、跑哪条闸门、不许怎么消红） |
| 闸门掉线 | `gate_missing.*`（回到「未执行/声明式」＝故障，因为 P1-3 已把 8 层全换成可执行闸门） |
| 写档过程 | `engine_failed.*`、`archive_failed.*` |
| 锁（红线②） | `lock.held_alive`、`lock.stale_declared`、`lock.held_dead` |
| 策略 | `policy.beyond_whitelist` |
| 新鲜度 | `backlog.L3`、`stale.L5`、`stale.*` |
| 并发 | `external_writer` |

两处消费，口径一致（不现编）：

- `--sync` 失败的那一刻，**当场**打出对应条目（红闸门 / 归档失败 / 锁 / 越界 / 引擎非 0，共 8 个调用点）；
- 日报的每条待办下面挂同一份条目；**取不到条目就如实说「没有登记的处置办法（sig）→ 补进 failure-playbook.yaml」**，
  连终端摘要也这么打（这条一开始只在日报正文里做，终端漏了，已对齐）。

顺手清掉两处会误导人的旧文案：`TODO_MAP` 里 `未执行/声明式` 还写着「P1-3 待办」——
P1-3 已经做完，现在这两态意味着**闸门掉线**，属故障；而 `未过` 那条泛泛的「某层闸门红了」会
盖住逐层那条更具体的，故删除，闸门状态一律由逐层遍历负责。

## 3. 演练 9/9（新增 D2）

`kb/kbpy l7/scripts/_sync_drill.py`：

| 用例 | 结果 |
|---|---|
| 0/A/B/C/D/E/E2/F（P2 的 8 例） | ✅ 全过（写档幂等、三条红线、真库 sha256 未动） |
| **D2 失败清单点名到人** | ✅ 把夹具里的 L2 闸门改成必红 → 日报里出现「**L2 闸门红**」，并挂上「谁：**L2 层主** ｜ 命令：`kb/kbpy l7/scripts/l2_gate.py`（明细）→ `… --sync --only L2`」 |

### D2 暴露的第三个夹具陷阱（前两个在 P2 记录里）

**`kbpy` 也必须换成夹具里的真副本。** 它按**自己的真实路径**反推库根；夹具里若只是软链，
`kbpy` 会解析回真库 —— 夹具里的 `daily_health.py` 于是驱动了**真的** pipeline，
结论自然「没有红闸门」。第一版就是这么假绿的。

连带修掉第二支：`realize()` 原先只处理「夹具里已有这个路径（软链）」，
而 MIRROR 只镜像目录树 —— `kbpy` 在 `kb/` 根下、**根本不在夹具里**，
于是 `<KB>/kbpy` 命令直接失败、日报照写不误但内容是空的。现在两支都覆盖了。

## 4. 复验

| 项 | 结果 |
|---|---|
| `kb_pipeline.py --check` | 全过（12 道只读闸门；零写自证 4001 个产物变化 0） |
| `layers_check.py` | 全过 |
| 日报 | **过 8 / 红 0 / 未判 0**，零写 True；「要人做什么」3 条**每条都带谁+命令** |
| 信封闸门（本轮改过的 4 个文件） | `daily_health.py` / `kb_pipeline.py` / `_sync_drill.py` / `failure-playbook.yaml` 全部 python=node，差 0 |

### 一个**不属于本轮**的红（如实报，不动它）

`skills_check.py` 第 3 类「副本不一致」报 1 条：`kb-l0-feishu` 的**安装位**
（`~/.dsh/skills/kb-l0-feishu/`）与源（`kb/l7/skills/kb-l0-feishu/`）不一致，8 个文件，
其中 4 个是安装位**多出来**的（`references/CHANGELOG.md`、`references/gotchas.proposals.md`、
`scripts/retro.py` 等）。实测 mtime：安装位 `SKILL.md`/`CHANGELOG.md` 是 **10:40**、
`retro.py` 是 **10:31**，而源是 09-29 18:16 —— 也就是**有另一个写入者正在改那个 skill**。
本轮没碰它，也不去「同步副本」（那会把人家写到一半的东西盖掉或替它签字）。
处置见 `failure-playbook.yaml`：等对方收工后由 `kb-repair` 走「副本一致」修复，或由登记表负责人确认新版本。

## 5. 三件事的边界（说清没做什么）

1. **写档从未在真库上跑过** —— 按人已拍板的「两周只读观察期」，实测只在**夹具库**里做
   （`_sync_drill.py`，真库 sha256 前后复核）。真库第一次 `--apply` 要人开闸。
2. **预演档没有进定时任务**：只读档每天自动跑；预演档目前手动（或 agent 按需跑）。
   要不要每天自动出一份「写档计划」，等观察期结束再定 —— 现在自动跑它没有增量信息（L2 报 +0 行）。
3. `kb/l0…l6` 一个字节没动；本轮所有改动都在 `kb/l7/**`。
