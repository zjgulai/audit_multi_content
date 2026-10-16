# 体检表 · CHK-20261004-0108-GATE

- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**体检档**（`kb-check` §1 的 6 道闸门一次性跑完）—— 不是评审链里的「驱动循环档 L7」
- 触发：用户单字指令「闸门。」⇒ 归口 `kb-check`（知识库统一闸门）
- 时间：2026-10-04 01:07:36 – 01:11:41（本地）
- 原始输出：`_chk-run-CHK-20261004-0108-GATE/*.out`（逐闸门 stdout/stderr）

> **本表的解释权边界**：「闸门。」未指明是哪一道。本表按 `kb-check` 的**体检档**理解并执行；
> **未跑** `ci/run_gates.py` 的 12 把闸门（含 `l0`–`l7` 逐层闸门、`conformance`、`freshness`），
> 也**未跑**评审链的层前置闸门（`kb_pipeline.py --gate-only`）。要做那两件事须另行指令。

## 一、体检表（闸门 → 退出码 → 结论 → 证据）

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表 | `kb/kbpy l7/scripts/skills_check.py` | **0** | ✅ 过 | 五类问题 `1=0 2=0 3=0 4=0 5=0`；本项目要用 40 个、已装 40 个、还差 0 |
| ② | 层契约 | `kb/kbpy l7/scripts/layers_check.py` | **0** | ✅ 过 | 六类 `1..6 = 0`；8 层齐全，DAG 合法（L7 ← L0/L3/L4/L5/L6，非线形） |
| ③ | 路由表对账 | `kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_v2.winners.txt --cases _eval-kb-manage/cases_v2.json --alias` | **1** | 🔴 有对账不上 6/115（**且输入是 09-29 快照，非今日**） | 逐条全轮命中 **109/115 = 94.8%**（门槛 F1 ≥ 0.90）；四节问题 ①=6 ②=6 ④=0 |
| ③b | 同上·按正文原样命令 | `… routes_reconcile.py kb/l7/reports/CHK-20261004-0108-GATE-routes-winners.json` | **2** | ⬜ 未判定（**缺输入**，非假绿） | 「赢家表不存在」——库内无任何 `<RUN>-routes-winners.json` |
| ④ | 链路收口核验 | `kb/kbpy l8/workflow_check.py CHK-20261004-0108-GATE` | **1** | 🟡 **合法变红**（②③，判据冻结在 09-23，**不该修数据**） | 9 段 7 PASS；FAIL = `② 权威库 l0~l6 未被改动`、`③ 前序产物哈希（45 项）` |
| ⑤a | 信封闸门 | `python3 tools/envelope_gate.py` | **0** | ✅ 过 | 扫 1853 个 `.py/.txt/.md`：**信封态 0**、读不到 0；两读者交叉一致 |
| ⑤b | 信封普查 | `kb/kbpy l8/envelope_census.py` | **0** | ✅ 过 | 8726 个 `.md` 中 1079 个信封态，**已全部归类**（归档 569 / 可再生备份 510） |
| ⑥ | 投影一致性 | `kb/kbpy l8/projection_reconcile.py` | **1** | 🔴 **真坏** | 3/6 通过；漂移 R1、R2、R4 |

**红里：真坏 2 道（③ 有条件、⑥）｜合法变红 1 道（④）｜未判定 1 道（③b 缺输入）。**
全绿 3 道（①②⑤）。

## 二、分类口径（`kb-check` §3，逐条对号）

- **真坏** = 路径不存在 / 副本不一致 / 退出码非 0 且非基线冻结所致 → 交 `kb-repair`。
- **合法变红** = 活库模式下冻结基线比对（`workflow_check` ②③）→ 结论写「基线漂移，非缺陷」。
- **判据缺陷** = 工具 bug → 写「判据缺陷，非数据缺陷」。本轮**未出现**该类的**新**实例。
- **未判定** = 缺输入，宁可标未判定，不猜。

## 三、失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 归类 | 要人做什么 | 复开条件 |
|---|---|---|---|---|---|
| 1 | `⑥ projection_reconcile` R1/R2/R4 | `projection_drift` | 🔴 真坏 | 先裁「L3 权威侧那 4 个治理字段该不该有」：`kb/l3/registry/l3.json → changes[2]`（run `20260929-1040`）**声称**回填 509 行，而实文件 `owner` 非空 **0/1018**、`half_life_days`/`valid_until` 键**根本不存在** ⇒ 注册表声明与实文件不一致，需 owner 拍板；R1/R2 视图过期，须重跑 `kb/.work/gen-host-library.py` 到 staging 后回填 | `projection_reconcile.py` 退出码 0（R1/R2/R4 全绿） |
| 2 | `③ routes_reconcile` 6 条不一致 | `route_mismatch` | 🔴 有对账不上（**输入陈旧**） | 三条是**旧名快照 artifact**：赢家表（2026-09-29 19:58）写的是 `AI 溯源与权利审查`（**带空格**），而当前装载目录名是 `AI溯源与权利审查`（无空格）⇒ I1/I3/I4 的「不一致」部分是改名前后错位，**不是** ALIAS 映射写错（与 00:45 轮独立复核结论一致）。真需人裁的是 I2/I5 被 `图片安全审查` / `视频安全审查` 抢走、以及 `kb-manage-4` 第 3 轮被 `kb-pipeline` 抢走 | **重新生成今日赢家表**后再跑本闸门；在此之前本项结论只对 09-29 那一轮成立 |
| 3 | `④ workflow_check` ②③ | `frozen_baseline_drift` | 🟡 合法变红 | **不要修数据**。要转绿必须**改判据**（冻结基线从 09-23 起未动），属改闸门语义，须 owner 拍板单独走一轮 | 改判据后复跑 `exit 0`；在此之前结论一律写「基线漂移，非缺陷」 |

## 四、闸门带出的附加观测（不构成闸门判据）

- 装载位：**509 条 / 信封 0 / E001 None / E046 None / 健康分 79.1**（≥ 熔断线 60）。
- 文档可见性：工作区 4998 个 `.md`，不可读 **510**（全部归因「他人产物 hostlib」）。
- 写入侧 [E026]：内容质量分 **52.1 < 60**（长度 0.4/20 · 密度 5/30 · 去重 20/20 · 语言 26.7/30）—— ⑨ 段仍判 PASS，**但这条分数是红边**，登记在此。
- 派生链：生成器 11:26:57 `408a6d079312b66f` 73520 B；沙箱产出 510 md / 信封 0。

## 五、并发声明（**本表可复现性前提**）

跑本轮的同一时段，**同机有别的会话在跑同一套体检档**（`_chk-run-CHK-20261004-0105` / `-0106` / `-0107-HLT`，
以及 `kb_pipeline.py --check` 与约 25 个 L6 检索进程）。要点：

- 无锁冲突：`kb/.work/.kb.lock` **不存在**，`kb/.work/*.lock` **不存在**（01:07 查）。
- 近 30 分钟有写入：`kb/.work/publish.log`（01:06）、`kb/.work/l5_integrity.json`（01:05）、
  `kb/l8/workflow_check_REPAIR-20261004-0103.json`（01:05）⇒ 按 `kb-check` §5 属「可能有另一批在跑」，
  已先确认再动，**未做任何 KB 写库动作**（唯一落盘 = 本表 + `kb/l8/workflow_check_CHK-20261004-0108-GATE.json`）。
- 结果自洽：`④` 的 FAIL 段与 00:50 起连续 8 轮完全一致（同为 ②③），未见并发导致的抖动。

## 六、复现命令

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
RUN=CHK-20261004-0108-GATE
kb/kbpy l7/scripts/skills_check.py                                            # ①  0
kb/kbpy l7/scripts/layers_check.py                                            # ②  0
kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_v2.winners.txt \
        --cases _eval-kb-manage/cases_v2.json --alias                          # ③  1
kb/kbpy l8/workflow_check.py $RUN                                             # ④  1（写 kb/l8/）
python3 tools/envelope_gate.py                                                # ⑤a 0
kb/kbpy l8/envelope_census.py                                                 # ⑤b 0
kb/kbpy l8/projection_reconcile.py                                            # ⑥  1
```

## 七、本 skill 交付物合规声明

- 本 skill「**只报不改**」：全程未跑任何写档参数，未动 `kb/l0`–`kb/l7` 数据。
- 本表**只由体检档产出**；评审驱动的 L7 档不写库（`skill_write: false`）。
- 落盘走 **node 通道**（`kb/.work/write_via_node.mjs`，写后读回逐字节比对），未用 python/sed 写 `.md`。
