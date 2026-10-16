# 体检表 · CHK-20261004-0116-KBCK

- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**体检档**（`kb-check` §1 的 6 道闸门一次性跑完）—— 不是评审链里的「驱动循环档 L7」
- 触发：用户指令 `/kb-check` ⇒ 归口 `kb-check`（知识库统一闸门）
- 时间：2026-10-04 01:14:03 – 01:17（本地）
- run_id：`CHK-20261004-0116-KBCK`（本表所有结论只对本 run 的这一次落盘成立）
- 原始输出：`_chk-run-CHK-20261004-0116-KBCK/*.out` + `*.exit`（逐闸门 stdout/stderr/退出码）

> **解释权边界**：本表只跑 `kb-check` 的**体检档** 6 道闸门。
> **未跑** `ci/run_gates.py` 的 12 把闸门（含 `l0`–`l7` 逐层闸门、`conformance`、`freshness`），
> 也**未跑**评审链的层前置闸门（`kb_pipeline.py --gate-only`）。要做那两件事须另行指令。

## 一、体检表（闸门 → 退出码 → 结论 → 证据）

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表 | `kb/kbpy l7/scripts/skills_check.py` | **0** | ✅ 过 | 五类问题 `1=0 2=0 3=0 4=0 5=0`；本项目要用 40 个、已装 40 个、还差 0；扫描装载位 59 个目录 |
| ② | 层契约 | `kb/kbpy l7/scripts/layers_check.py` | **0** | ✅ 过 | 六类 `1..6 = 0`；8 层齐全（L0…L7），DAG 合法（`L7 ← L0/L3/L4/L5/L6`，非线形）；cwd 约定解析正确 |
| ③a | 路由表对账（**替代输入**：09-29 冻结用例集） | `kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_v2.winners.txt --cases _eval-kb-manage/cases_v2.json --alias` | **1** | 🔴 有对账不上 **6/115**（**输入是 09-29 快照，非今日**） | 逐条全轮命中 **109/115 = 94.8%**（门槛 F1 ≥ 0.90）；四节问题 ①=6 ②=6 ④=0 |
| ③b | 同上·**按 SKILL 正文原样命令** | `… routes_reconcile.py kb/l7/reports/CHK-20261004-0116-KBCK-routes-winners.json` | **2** | ⬜ 未判定（**缺输入**，不是假绿） | 「环境错：赢家表不存在」——库内**无任何** `<RUN>-routes-winners.json`（`find . -name "*winners*"` 只命中 `_eval-kb-manage/blind_*.winners.txt`） |
| ④ | 链路收口核验 | `kb/kbpy l8/workflow_check.py CHK-20261004-0116-KBCK` | **1** | 🟡 **合法变红**（legs ②③，判据冻结在 09-23/09-30/10-02，**不该修数据**） | 9 段 7 PASS；FAIL = `② 权威库 l0~l6 未被改动`、`③ 前序产物哈希（45 项，不符 20 项）` |
| ⑤a | 信封闸门 | `python3 tools/envelope_gate.py` | **0** | ✅ 过 | 扫 1856 个 `.py/.txt/.md`：**信封态 0**、读不到 0；两读者（Electron / PATH node）交叉一致 |
| ⑤b | 信封普查 | `kb/kbpy l8/envelope_census.py` | **0** | ✅ 过 | 8729 个 `.md` 中 1079 个信封态，**已全部归类**（刻意归档 569 / 可再生备份 510），无未归类 |
| ⑥ | 投影一致性 | `kb/kbpy l8/projection_reconcile.py` | **1** | 🔴 **真坏**（视图过期，可修但有前提） | 3/6 通过；漂移 **R1**（源文件 rules 在视图生成后变过）、**R2**（509 条条目权威规则已变）、**R4**（2036 处治理字段未传导） |

**红里：真坏 1 道（⑥）｜合法变红 1 道（④）｜有对账不上但输入陈旧 1 道（③a）｜缺输入未判定 1 道（③b）。**
全绿 3 道（①②⑤a⑤b —— ⑤ 分 a/b 两支，两支都绿）。

## 二、分类口径（`kb-check` §3，逐条对号）

- **真坏** = 路径不存在 / 副本不一致 / 退出码非 0 且非基线冻结所致 → 交 `kb-repair`。
- **合法变红** = 活库模式下冻结基线比对（`workflow_check` ②③）→ 结论写「基线漂移，非缺陷」。
- **判据缺陷** = 工具 bug → 写「判据缺陷，非数据缺陷」。本轮**未出现**该类的新实例。
- **未判定** = 缺输入，宁可标未判定，不猜。

## 三、失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 归类 | 要人做什么 | 复开条件 |
|---|---|---|---|---|---|
| 1 | `⑥ projection_reconcile` R1/R2/R4 | `projection_drift` | 🔴 真坏 | 视图 `kb/view` 是从**旧版 L3** 生成的，而权威 L3 已从 509 条增至 **1018 条**（`kb/l3/candidates/rules.jsonl`，mtime 10-02 22:45）；且权威侧治理字段本身**就是空的**：`owner` 键在 1018/1018 条上存在但**非空 0 条**，`half_life_days` / `valid_until` **键根本不存在**（实测见 §八）。⇒ 不是单纯「生成器没读字段」，而是**权威侧没有值可读**。需 owner 先裁「这 4 个治理字段归谁填、填什么」，再重跑 `kb/.work/gen-host-library.py` 到 staging 后回填 | `projection_reconcile.py` 退出码 0（R1/R2/R4 全绿）；在此之前 `kb_*` 工具读到的是过期视图 |
| 2 | `④ workflow_check` legs ②③ | `frozen_baseline_drift` | 🟡 合法变红 | **不要修数据**。root cause 已定位：leg ② 的判据是 `kb/.work/l6_integrity.json`（**记于 10-02 00:07**）里那条 `l3_candidates.sha256=7d00454e…`，而 L3 文件在 **10-02 22:45 被重写**（1018 条、2,778,872 B）；leg ③ 比的是 `kb/l4/runs/20260923-1445.json` 等 **09-23 冻结 run 记录**里的 45 项产物 sha。要转绿**只有改判据**（重录基线），属改闸门语义，须 owner 拍板单独走一轮 | 重录 `l6_integrity.json` / 冻结基线后复跑 `exit 0`；在此之前结论一律写「基线漂移，非缺陷」 |
| 3 | `③a routes_reconcile` 6 条不一致 | `route_mismatch` | 🔴 有对账不上（**输入陈旧**） | 赢家表是**触发评测的运行时产物**，库内没有今日版本，本轮用的是 **09-29 19:58** 冻结用例。6 条里 I1/I3/I4 是**改名前后错位**（旧表写 `AI 溯源与权利审查`（带空格），现装载目录名是 `AI溯源与权利审查`）；真需人裁的是 I2/I5 被 `图片安全审查` 抢走、`kb-manage-4` 第 3 轮被 `kb-pipeline` 抢走 | **重新生成今日赢家表**后再跑本闸门；在此之前本项只对 09-29 那一轮成立 |
| 4 | `③b` 原样命令 | `missing_input` | ⬜ 未判定 | 无。这是**判据设计使然**（缺输入不许报绿，也不许静默按「全不一致」跑）—— 记在这里是为了让「③b 是 2 不是 0」不被误读成假绿 | 提供 `<RUN>-routes-winners.json` 后复跑 |

## 四、闸门带出的附加观测（不构成闸门判据）

- 装载位：**509 条 / 信封 0 / E001 None / E046 None / 健康分 79.1**（≥ 熔断线 60）/ 检索 `[111, 1, 509, 0]`。
- 文档可见性：工作区 **5001** 个 `.md`，不可读 **510**（全部归因「他人产物 hostlib」）。
- 派生链：生成器 11:26:57 `408a6d079312b66f` 73520 B；沙箱产出 510 md / 信封 0；加载器直读 E001 None E046 None。
- 写入侧 [E026]：内容质量分 **52.1 < 60**（长度 0.4/20 · 密度 5/30 · 去重 20/20 · 语言 26.7/30）—— ⑨ 段仍判 PASS，**但这条分数是红边**，登记在此。落盘 0 个（信封 0）。

## 五、并发声明（**本表可复现性前提**）

跑本轮的同一时段，**同机至少还有 5 个会话在跑同一批闸门**（`ps` 实测，01:16）：

- `ci/run_gates.py --outdir ci/out`（`_chk-run-20261004-0110/ci-runner.out`，已跑 7 分钟）
- `l1..l7_gate.py` 逐层循环 **×2 份**（PID 10325 / 13410）
- `kb_pipeline.py --check` **×3**（PID 7607 / 14708 / 18199）
- `workflow_check.py CHK-20261004-0114-KBCK`（另一会话，PID 15403）
- 若干 `l6/retriever.py` 检索进程

要点：

- **无锁冲突**：`kb/.work/.kb.lock` 与 `kb/.work/*.lock` **均不存在**（01:14 / 01:17 两次查）。
- 近 30 分钟有写入：`kb/.work/publish.log`（01:12）、`kb/.work/l5_integrity.json`（01:13）、
  `kb/l7/runs/index.jsonl`（01:11，已累计 1085 个 run）⇒ 按 `kb-check` §5 属「可能有另一批在跑」，
  已先确认再动，**未做任何 KB 写库动作**（本轮唯一落盘 = 本表 + 本 run 目录 + `kb/l8/workflow_check_CHK-20261004-0116-KBCK.json`）。
- **结果自洽**：④ 的 FAIL 组合（legs ②③）与 00:50 起连续多轮完全一致；③a 的 109/115、6 条不一致清单与 01:08 轮**逐条相同**；⑥ 的 R1/R2/R4 与 01:08 轮相同 ⇒ 未见并发导致的抖动。

## 六、复现命令

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
RUN=CHK-20261004-0116-KBCK
kb/kbpy l7/scripts/skills_check.py                                            # ①  0
kb/kbpy l7/scripts/layers_check.py                                            # ②  0
kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_v2.winners.txt \
        --cases _eval-kb-manage/cases_v2.json --alias                          # ③a 1
kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/$RUN-routes-winners.json  # ③b 2（缺输入）
kb/kbpy l8/workflow_check.py $RUN                                             # ④  1（写 kb/l8/）
python3 tools/envelope_gate.py                                                # ⑤a 0
kb/kbpy l8/envelope_census.py                                                 # ⑤b 0
kb/kbpy l8/projection_reconcile.py                                            # ⑥  1
```

## 七、独立复核点（本表自己算过的，不是抄闸门的）

| 复核点 | 我算出来的 | 与闸门说法是否一致 |
|---|---|---|
| L3 文件当前形态 | `kb/l3/candidates/rules.jsonl` = **1018 行 / 2,778,872 B**，全部行可 `json.loads`，**无空行** | 与 ④ leg② `l3_lines=1018` 一致 |
| L3 append-only 基线是否被破坏 | `sha256(前 509 行 以\n连接+末尾换行)` = **`acf77a6a0b05937d…`** = `kb/.work/l5_integrity.json → checks.l3_append_only.prefix_sha256` **逐字符相同** | ✅ 一致 ⇒ **L3 的 509 条基线前缀未被动过**，leg② 的红**不是** L3 数据损坏 |
| 让 leg② 变红的那条记录 | `l6_integrity.json`（记于 **10-02 00:07**）写 `lines=2036 / bytes=5762300 / sha=7d00454e…`；当前文件 `lines=1018 / bytes=2778872 / sha=743dc623…` | ⚠️ **对不上，且 2036↔1018 恰好差一倍**。L5 侧（01:13 刚复核）认的正是 1018 行 ⇒ 判为**冻结记录陈旧**（记的是 10-02 22:45 重写**之前**的中间态），**不是**当前文件异常 |
| R4 说的 4 个治理字段 | 权威 L3 实测：`owner` 键 1018/1018 存在但**非空 0**；`half_life_days` / `valid_until` **键不存在**；`effective_from` / `effective_to` 存在但**全空** | 与 ⑥ R4 的 `{owner:509, half_life_days:509, valid_until:509, effective_from:509}` 方向一致（509 = 视图条目数）⇒ R4 的根因在**权威侧缺值**，不只是生成器漏读 |

## 八、本 skill 交付物合规声明

- 本 skill「**只报不改**」：全程未跑任何写档参数，未动 `kb/l0`–`kb/l7` 数据。
- 本表**只由体检档产出**；评审驱动的 L7 档不写库（`skill_write: false`）。
- 落盘走 **node 通道**（`kb/.work/write_via_node.mjs`，写后读回逐字节比对），未用 python/sed 写 `.md`。
- 本表带 **run_id + 时间戳**（§ 头部），可据此在 `kb/l7/runs/index.jsonl` 与 `kb/l8/workflow_check_<RUN>.json` 对账。
