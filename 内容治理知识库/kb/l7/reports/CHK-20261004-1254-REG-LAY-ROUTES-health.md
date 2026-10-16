# 体检表 CHK-20261004-1254-REG-LAY-ROUTES —— 门① 登记表自检 / 门② 层契约 / 门③ 路由对账

- **RUN**：`CHK-20261004-1254-REG-LAY-ROUTES`
- **时间**：2026-10-04 12:53:59 → 12:54:15（本机时钟）
- **cwd / 库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **档位**：体检档（人触发）。**只跑用户点名的三道（①②③）**，全部只读：脚本内只有 `open(..., "r")`。
- **前置**：`python3 .dsh/skills/kb-check/scripts/preflight.py` → 退出码 0；已预告「赢家表输入：**无**（门③ 将 exit 2）」。
- **原始输出**：`_chk-run-CHK-20261004-1254-REG-LAY-ROUTES/`（`00-declare.txt` `00-exits.txt` `01-skills_check.out` `02-layers_check.out` `03a/03b/03c*.out`）

## 1. 体检表

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | ✅ **过** | 五类问题 `1=0 2=0 3=0 4=0 5=0 ｜合计 0`；登记 71 行（本项目 52 / 宿主通用 19），装载位扫到 59 个目录；本项目要用 40 个、已装 40、还差 0。3 条备注（lark-base 本地版本超前，不告警）、3 条跳过（12 个登记了 source 的条目未安装，未比对） |
| ② | 层契约自检 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | ✅ **过** | 层数 8（L0…L7）；六类问题 `1=0 2=0 3=0 4=0 5=0 6=0 ｜合计 0`；DAG 非线形（L2←L0,L1；L3←L0,L2；L7←L0,L3,L4,L5,L6） |
| ③-a | 路由对账 · **契约路径**（`references/gates.md` 规定的输入） | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-1254-REG-LAY-ROUTES-routes-winners.json` | **2** | ⚪ **缺输入（非数据坏、也非绿）** | 脚本原话：`环境错：赢家表不存在 …`＋`缺输入时本闸门不得报绿，也不得静默按「全不一致」跑`。**本维度按契约口径没有结论** |
| ③-b | 路由对账 · 库内唯一一份真赢家表（`--alias`，与冻结基线可比口径） | `… routes_reconcile.py _eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt --alias` | **1** | 🔴 **真红，但已登记、边界明确** | 逐条全轮命中 **60/65 = 0.923**；不一致 **5 条全部同一成员** `brand-ai-provenance-rights-review`（**0/5 条、2/15 轮**）；被抢走计数 `NONE 6 · 视频安全审查 3 · 图片安全审查 3 · CLARIFY 1`；工具第 ④ 节**路由表自检 = 0 条** |
| ③-c | 路由对账 · 同一份表 **strict**（对照口径） | 同 ③-b 去掉 `--alias` | **1** | ⚪ **口径不匹配，非路由全错** | `0/65`、`①=65`。成因：赢家表存**中文装载名**，strict 只认逐字相等的**英文登记 id** ⇒ 与 ③-b 是同一份数据的两种口径，不是第二个发现 |

**加色说明**：③-b 的红**不是本轮新发现** —— `kb/l7/registry/routes.yaml` 已自记该成员未过门槛（`measured_20260929.by_member.brand-ai-provenance-rights-review: 0.440`，行 230）并写明根因（`known_conflict`，行 238–255：I1↔G3 近重复、I5↔F5 近重复为主因、I2 欠定义；结论是**用例边界问题**，明确写「不再继续改用例、也不再调 description」）。

## 2. 「缺哪道」—— 三道各自的可得性

| 门 | 缺不缺 | 为什么 |
|---|---|---|
| ① 登记表自检 | **不缺** | 输入是 `kb/l7/registry/skills.yaml` + 装载位 `~/.dsh/skills`，都在库内 |
| ② 层契约 | **不缺** | 输入是 `kb/l7/registry/layers.yaml`，在库内 |
| ③ 路由对账 | **缺「契约路径」的输入** | 契约输入是 `kb/l7/reports/<RUN>-routes-winners.json`，而赢家表是**触发评测的运行时产物**（每条 prompt 每轮实际被谁接走），**全库无生成脚本**（全库 `grep routes-winners` 只命中 SKILL/文档/历轮体检表，无生产者）。现存唯一一份在**契约路径之外**：`_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`（115 行，mtime **03:24:57**，由 2026-10-04 03:27 那轮触发盲测产出）。至本轮 **陈旧 9 小时 29 分** ⇒ ③-b 的读数是**当时**的路由数据，不是**今天**的 |

**因此**：③ 的**契约口径**这一格只能记「缺输入 / exit 2」，**不许**记成「65 条全不一致」；把 ③-b 的 exit 1 当门③的最终读数时，必须同时标注「输入陈旧 9h29m、且用的是库内非契约路径的那一份」。

## 3. 未跑的三道（本次不跑的理由）

| 闸门 | 状态 | 理由 |
|---|---|---|
| ④ 链路收口 `l8/workflow_check.py` | **未跑** | 用户本轮只点名 ①②③；且本闸门**无干跑档，不加参数也写** `kb/l8/workflow_check_<RUN>.json`（`references/gates.md` 门④）；另：**本机此刻有另一批在跑它**（见 §4） |
| ⑤ 信封闸门 `tools/envelope_gate.py` + `l8/envelope_census.py` | **未跑** | 用户本轮未点名（只读，随时可补跑） |
| ⑥ 投影一致性 `l8/projection_reconcile.py` | **未跑** | 用户本轮未点名；**无干跑档**，且会写盘 |

## 4. 并发观察（只读结论，未做任何处置）

- 本次运行时（12:52–12:53）**另有会话在跑同一批闸门**：进程实测有 `kb/l8/workflow_check.py CHK-20261004-1258-KBCHK`、`kb/l7/scripts/kb_pipeline.py --check`、`with_kb_evidence.py`（评审引擎）；工作目录 `kb/.work/kbcheck-CHK-20261004-1245-KBCG/*.out` 与 `kb/.work/l5_integrity.json` 在 40 分钟内被写。
- 库内**无** `kb/.work/.kb.lock`。
- 本次三道闸门全部只读，**不与之争抢写盘**；按纪律**未做任何删锁/接管动作**。

## 5. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| 1 | 门③ 的**契约输入** | `MISSING_INPUT`（机制缺口） | 按 `kb-manage` 的触发电测**重新生成**赢家表并落到 `kb/l7/reports/<RUN>-routes-winners.json`（txt/json 两种形态都认） | 该文件存在且被解析 ⇒ 门③ 契约口径可重跑；`--alias` 退出 0 才算过 |
| 2 | `brand-ai-provenance-rights-review` 路由 | `ROUTE_F1_BELOW_THRESHOLD`（**已登记**） | **不需要**再改 description（`routes.yaml` 已判为「过拟合 judge」）；要动的是**用例集边界**（I1↔G3 合并、I5↔F5 去重、I2 补模态）—— 属机制改动，**待裁** | 用例修订后重跑触发盲测 → 门③ `--alias` 退出 0 |
| 3 | 门③ 数据的**时效** | `STALE_INPUT`（9h29m） | 要「今天」的路由结论就必须重生成；沿用现成表时报告须写明陈旧时长 | 同第 1 行 |

## 6. 口径纪律（本表遵守）

- ① **缺输入 ≠ 表坏**：exit 2 是设计行为（`RouteReconcileError`），不得报绿、也不得静默降级为「全不一致」。
- ② **不许把工具/口径问题报成数据缺陷**：③-c 的 `0/65` 是**口径不匹配**（中文装载名 vs 英文登记 id），已按 `references/gotchas.md` 归为「判据口径」。
- ③ 三道闸门脚本实测**只读**（`skills_check.py` / `layers_check.py` / `routes_reconcile.py` 内 `open()` 全为 `"r"`），本轮**零写库**（除本体检表本身）。
- ④ 本表所有退出码、命中数、被抢走计数均为**脚本原话**，无手工折算。
