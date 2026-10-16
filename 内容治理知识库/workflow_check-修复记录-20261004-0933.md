# workflow_check 修复记录 · 2026-10-04 09:33（第 5 轮）

**用户指令**（与前 4 轮同一句）：「workflow_check 没过，帮我把失败项按原因码修掉，修完复跑。」

## 0. 一句话结论

**修完了能修的那一项，剩下两项修不动** ——
本轮复跑 `workflow_check` 的失败项**只剩 ②③**，而 ②③ 在**不改判据**的前提下
**数学上不可能变绿**（§3 给了实测数字，不是推论）。要它们转绿**只有报批改判据一条路**，
本轮**没有授权 ⇒ 未动判据、未写任何 run 记录、未改任何库数据**。

## 1. 修前 / 修后对照（同一条闸门）

| | 命令 | 退出码 | 失败段 |
|---|---|---|---|
| 修前（本会话读到的读数） | `sh kb/kbpy l8/workflow_check.py 20261004-0925` | 1 | ② ③ **⑥** |
| 修后（本会话复跑） | `sh kb/kbpy l8/workflow_check.py REPAIR-20261004-R5` | 1 | ② ③ |

修后逐段：

```
知识库工作流体检 · REPAIR-20261004-R5 · 2026-10-04 09:33:11
  PASS  ① 环境与版本纪律
  FAIL  ② 权威库 l0~l6 未被改动
  FAIL  ③ 前序产物哈希（45 项）
  PASS  ④ 分层库 → 生成器 → 视图
  PASS  ⑤ 装载位 → 加载器（读工具+体检）
  PASS  ⑥ 文档可见性（agent 能否读到）      ← 本轮由红转绿
  PASS  ⑦ 消费侧 skill 可用
  PASS  ⑧ 工作台与服务
  PASS  ⑨ 写入侧（ingest 闸门 + 落盘通道）
  可见性：工作区 6193 md，不可读 510 {'他人产物 hostlib': 510}
  裁决：FAIL（未过：['② 权威库 l0~l6 未被改动', '③ 前序产物哈希（45 项）']）
```

原始件：`kb/l8/workflow_check_REPAIR-20261004-R5.json`
（副本：`kb/l7/_backups/kb-repair-workflow-R5-20261004-0933/`）

## 2. 失败项按原因码分类

| 段 | 原因码 | 判据 | 本轮处置 |
|---|---|---|---|
| **⑥ 文档可见性** | 信封态（python 与 node 读数差值 == 4096） | 实红，判据好 | **已修，复跑绿**（非本会话所修，见 §4 并发披露） |
| **② 权威库 l0~l6 未被改动** | `BASELINE-STALE`（判据过期） | 判据写死在过去的时点 | 已登记，**不修数据**（§3 证明不可满足） |
| **③ 前序产物哈希（45 项）** | `BASELINE-STALE`（判据过期）＋1 条真发现 | 同左 | 已登记；其中 `l7.json` 那项要**开闸**才能补落章 |

⑥ 的修法（**这是 kb-repair 权限内唯一能修的一项**）：
3 个 `.md` 被 python 写成了信封态，判据读者（DSH 内置 Electron 的 `statSync().size`）比 python
多读到 4096 字节。修法只能是**用 `cp` 从内容重写**（python 直写会再次落成信封）。
修后独立复核：

```
$ python3 tools/envelope_gate.py _eval-L0L7-gap-20261003
结论：活路径上没有信封。  正常：104 ｜ 信封态：0 ｜ 读不到：0   退出码：0
$ sh kb/kbpy l7/scripts/skills_check.py
五类问题：1=0 2=0 3=0 4=0 5=0 ｜合计 0   结论：全过。  退出码：0
```

## 3. ② 为什么「修不动」—— 从推论升级为实测数字

判据代码（`kb/l8/workflow_check.py`）：

- L115 `b1018 = sha256(前 1018 行)`，L116 `b1527 = sha256(前 1527 行)`；
- L124 `l3_base1018_matches_L6 = (b1018 == kb/.work/l6_integrity.json 记的 sha)`；
- L124 `l3_whole1527_matches_L4 = (b1527 == kb/l4/runs/20260923-1445.json 记的 sha)`；
- L125 ② 要绿 = 三条**同时**为真。

实测（本会话独立复算）：

```
L3 现行行数                 = 1018                ← 少于 1527
两条前缀哈希 == 整文件哈希   = True（b1018 == b1527 == 743dc62398311b02…）
基线 l6_integrity 记的      = 7d00454e…, lines = 2036   ← 2036 行时代的整文件哈希
基线 L4 09-23 run 记的      = aa83d1f9…                 ← 1527 行时代的整文件哈希
b1018 == l6rec ?  False
b1527 == l4sha ?  False
```

⇒ 只有 1018 行时，**「前 1018 行」和「前 1527 行」都是整文件**，
却被拿去比 2036 行 / 1527 行时代的**整文件**哈希。要它相等，
只能把 L3 **回滚到 09-23** —— 而那是 `failure-playbook.yaml` 明令禁止的
（会毁掉 2026-10-02 那轮蒸馏）。**所以 ② 不是"还没修"，是"判据自相矛盾"。**

③ 同理：它拿 **2026-09-23 四份 run 记录**的 45 个产物哈希当「不许变」的基线，
活库此后每被合法重建一次就多红一项。本轮 45 项里 20 项 mismatch，
**20 项全部有改动出处**（17 项有更新的 run 记录、3 项有登记文档出处），
**没有一项是"无人认领的黑改"**（详见 `kb/l7/registry/workflow-check-known-drift.yaml → stale_criteria[1]`）。

## 4. 并发披露（重要，且本轮与前 4 轮不同）

- **⑥ 不是我修的**：09:31:20–26 期间**另一个并发会话**已把这 3 个信封态 md 修掉，
  证据留痕在 `_repair-run-20261004-093101-envelope/`
  （`05a-envelope-F1-BEFORE.txt`：信封 3 个；`…-AFTER.txt`：信封 0）。
  本轮只做了**独立复核**（§2 的命令），没有重复劳动。
- 本轮跑闸门时，**另有两个 `workflow_check.py` 进程在跑**
  （`REPAIR-20261004-0933`、`CHK-20261004-HLT-A`）。本轮 RUN 名不同，**未与它们抢任何文件**。
- 循环认领：`kb_loop_claim.py status` 报「陈旧（可 `--take-over`）」，pid 45984 已不在
  ⇒ **单槽已空**。本轮**没有**认领、**没有**写 run 记录。

## 5. 变更记录（变更协议 5 问）

本轮**只改了 1 个文件**：

`kb/l7/registry/workflow-check-known-drift.yaml`（登记件，非判据、非数据）

| 五问 | 答案 |
|---|---|
| **读者** | 跑 `kb-check` 体检的人 / 看 workflow_check 报告的人 / 写日报的人 |
| **写者** | 本轮 kb-repair 会话；后续由维护 `kb/l7/registry` 的人按 `owner_action` 更新 |
| **判据** | 本文件**不被任何脚本读**（`meta.read_by_gate: none`，本轮 grep 复核：命中全在 `.md` 报告、`.yaml` 注释与 `_backups/` 里）⇒ **不改变任何闸门判定**，登记后 ②③ **仍然是 FAIL** |
| **通道** | `edit` 工具写 `.yaml`（不走 4096 字节信封；写后已用 `envelope_gate` 复核） |
| **回滚** | `cp kb/l7/_backups/kb-repair-workflow-R5-20261004-0933/workflow-check-known-drift.yaml.before kb/l7/registry/workflow-check-known-drift.yaml` |

改动内容：`meta.last_reverified` 追加第 5 次复现与算术证据；
`raw_readings.repro_runs` 追加第 5 条（run `REPAIR-20261004-R5`）；
`pending_decision` 追加 `still_unanswered_at`（把卡点收窄为"只有要不要批"）。
写后 `yaml.safe_load` 复核：6 个顶层键、`repro_runs` 5 条、`stale_criteria` 2 条，解析正常。

**回滚基线**：`kb/l7/_backups/kb-repair-workflow-R5-20261004-0933/`
（含 `.before` 原件 + 本轮 run 的原始 json）

## 6. 未决事项（**要一次人的点头，本会话问不到人**）

②③ 要永久转绿只有一条路：按 `owner_action` 改 `kb/l8/workflow_check.py` 的判据
（改成「**最新** run 记录 + 来源审计，查不到出处的改动仍判红」）。

| 选项 | 做什么 | 结果 |
|---|---|---|
| **A** | 授权改判据 **＋** 为 3 项补落章 | ②③ 转绿，④ 得 exit 0 —— **唯一能让本闸门变绿的路** |
| **B** | 维持现状 | ②③ 长期红、体检恒 FAIL（合规，但闸门失去信号价值） |
| **C** | 只补 3 项落章 | ②③ **仍是 FAIL**（判据没改，改的是留痕） |

- **A / C 的共同动作**是补落章 ⇒ 要写 `kb/l7/runs/` 与 `index.jsonl` ⇒ 属**开闸写档 + 独占循环**。
  本轮实测单槽已空，**不再需要 `--take-over` 抢锁**，剩下的唯一阻塞就是**要不要批**。
- 本会话是**被委派的子 agent**，`ask_user_question` 被宿主拒绝
  （`human interaction is unavailable while the calling agent is owned by another live agent`）
  ⇒ 该决定原样带回给委派方。
- 纪律提醒：`kb-repair` 铁律「同一条闸门修了两次还红 ⇒ 停，报『判据可能有缺陷』」——
  本单已是**第 5 轮**（若把 `kb/l7/reports/` 里各体检会话的复现也算上，是第 7 次以上），
  故本轮**执行的就是这一条**：停下来报判据缺陷，而不是继续"修"。

## 7. 本轮明确**没有**做的事

- 没有改 `kb/l8/workflow_check.py` 的 ②③ 判据（无授权）。
- 没有改写 `kb/l4|/l5|/l6|/l7/runs/20260923-*.json` 里的 artifact sha（伪造台账，明令禁止）。
- 没有回滚 L3（会毁掉 2026-10-02 蒸馏成果，明令禁止）。
- 没有碰 `kb/l0…l6` 的任何数据或台账。
- 没有写任何 run 记录、没有认领循环、没有开 `--apply`。
