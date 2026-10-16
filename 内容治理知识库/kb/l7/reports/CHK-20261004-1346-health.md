# 体检表 · CHK-20261004-1346 ｜ 全库六道闸门（体检档）

- 交表时点：2026-10-04 CST（RUN 起 13:45:5x，止 13:48）
- 库根（cwd）：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**体检档**（六道闸门一次跑完）；本 skill **只报不改**
- 本单写盘：**仅一处** —— `kb/l8/workflow_check_CHK-20261004-1346.json`（门④ 无干跑档，开跑前已声明，见 `kb/.work/kbcheck-CHK-20261004-1346/00-declare.txt`）
- 预检查：`preflight.py` 退出码 0，六道脚本齐；并预告「门③ 缺输入 ⇒ exit 2」

## 0. 一句话结论

> 六道闸门：**① ② ⑤ 过**；**③ 缺输入（exit 2）**；**④ exit 1，3 段红（②③⑧）**；**⑥ exit 1，3/6 红（R1/R2/R4）**。
> 红的六项里：**④-② 是结构性假红（判据口径错位）**；**④-③ 是期望值过期**；**④-⑧ 是间歇性抖动**；
> **⑥-R1/R2 是视图滞后（真滞后）**；**⑥-R4 是口径题（权威行本无该字段）**；**③ 是环境错（缺输入）**。
> **没有一项能被定性为「权威库 l0~l6 被改坏」** —— l0/l1/l2 与 L5 冻结基线逐字节一致，L3 的 509 行基线与 L5 记录逐字节一致。

## 1. 体检读数

| # | 闸门 | 命令 | 退出码 | 结论 | 关键读数 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | **过** | 五类问题 1=0 2=0 3=0 4=0 5=0；本项目要用 40 / 已装 40；另 62 条「未登记 selftest」单独归类、不算错误 |
| ② | 层契约 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | **过** | 8 层齐（L0…L7）；六类问题全 0；DAG 非线形（L7←L0,L3,L4,L5,L6） |
| ③ | 路由表对账 | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-1346-routes-winners.json` | **2** | **红 = 环境错（缺输入）** | 「赢家表不存在」；脚本自述缺输入时不得报绿、不得静默按「全不一致」跑 ⇒ fail-closed 行为正确 |
| ④ | 链路收口 | `sh kb/kbpy l8/workflow_check.py CHK-20261004-1346`（**无干跑档、写盘**） | **1** | **红 3 段** | 9 段中 6 段 PASS；FAIL = ② 权威库 l0~l6 未被改动、③ 前序产物哈希（45 项）、⑧ 工作台与服务 |
| ⑤ | 信封闸门 | `python3 tools/envelope_gate.py` ＋ `sh kb/kbpy l8/envelope_census.py` | **0 / 0** | **过** | 活路径扫 2034 个 `.py/.txt/.md`，信封态 **0**（两读者交叉一致）；普查扫 10431 个 `.md`，1079 个读不到但已全部分类（569 刻意归档 + 510 可再生备份）⇒ 结论 OK |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py` | **1** | **红 3/6** | R1 ❌ R2 ❌ R3 ✅ R4 ❌ R5 ✅ R6 ✅ |
| 尺 | 宿主 kb_check（**非六道闸门**，仅辅证） | 工具调用，**不带** `accept_baseline` | — | **不通过** | 健康分 **79.2**（熔断线 60）；新鲜度 1.00／三件套 1.00／一致性 1.00 OK；**孤岛率 0.94 标 `!!`（阈值 ≤0.2）**；覆盖率 0.92 OK（未命中 Q21/Q22/Q38）；利用率 0.23 OK（零结果 121/532=22.7%，从未命中 423/509）；错误 E026×454、W020×2218、W021×10、H005×1；条目基线 消失 0／治理字段被原地改 0／正文有改动 0／未入基线 0 |

> ⚠ 宿主 kb_check 的「一致性 1.00」是**条目级**，**不等于** ⑥ 的「投影一致性」。两把尺子，**不许互相顶替**。

## 2. 红项逐条：为什么红

### ③ 路由表对账（exit 2）—— 环境错，不是数据坏

- 缺的输入：`kb/l7/reports/CHK-20261004-1346-routes-winners.json`。
- 赢家表是**触发评测的运行时产物**（每条 prompt 每轮实际被谁接走），**全库无生成者**（`find` 全库只找到 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`，115 行、03:27、alias 口径，**未采用**）。
- ⇒ exit 2 是脚本**正确的 fail-closed**：既没报绿，也没静默按「0 条 ⇒ 全不一致」跑完。
- **要人做什么**：按 `kb-manage` 的触发电测重新生成今天的赢家表，或明确本闸门本轮不参与判定。**复开条件**：`kb/l7/reports/<RUN>-routes-winners.json` 就位。

### ④-② 权威库 l0~l6 未被改动 —— **结构性假红（判据口径错位 + 基线停在旧序列化版本）**

证据链（全部为本次实测）：

1. l0/l1/l2 **未被改**：`match_L5_baseline` 三层全 `true`（`bd36cbb8…` / `099ad8af…` / `183f6265…` 与 L5 冻结基线逐字节一致）。
2. 红**只来自 L3 的两处比较**，且**单位对不上**（`kb/l8/workflow_check.py:113-125`）：
   - 取「当前文件前 1018 行」的 sha（`b1018`）去比 L6 记录的**整份文件** sha（`l6rec`）。当前 `kb/l3/candidates/rules.jsonl` 恰好只有 1018 行 ⇒ `b1018` = 整份 = **2,778,872 B**；而 L6 记的那份是 **2,036 行 / 5,762,300 B**。**字节长度就不同 ⇒ 永不可能相等**。
   - `l3_whole1527_matches_L4` 同理：拿同一个 2,778,872 B 的 blob，去比 L4 `20260923-1445` 记的 **1,527 行 / 2,778,734 B** 的 sha。
   - 而且 `kb/.work/l6_integrity.py:158` 里与 L5 对齐用的是**前 509 行**口径；`workflow_check` 用的是**前 1018 行** —— 两处魔数（509/1018/1527/2036）本就不一致。
3. L3 的当前状态**是登记在册的**：我复算当前文件前 509 行 sha = `acf77a6a0b05937db01661cb3bd03dd4400ffa6915b3ccd2d264bd6213489c0d`，与 `.work/l5_integrity.json` 的 `l3_append_only.prefix_sha256` **逐字节一致**；当前整份 sha `743dc623…` 也等于同处的 `prep_baseline_sha256`（行数 1018 亦一致）。
4. 时间线：`kb/l3/runs/20260929-1300.pre-snapshot.json` 记 2026-09-29 12:52 该文件为 509 行 / 1,489,166 B / `f27a1409…`；L6 在 2026-10-02 00:07 记到 2,036 行 / `7d00454e…`；现文件 2026-10-02 22:45 写入、1,018 行 / `743dc623…`。⇒ **同一批 509 条规则被多次重新序列化，冻结基线没跟着刷新**。

⇒ **不是权威库被改坏，是这条腿的比较口径错位 + 基线过期**。**要人做什么**：改 `workflow_check.py` 该腿的比较单位（并对齐 `l6_integrity.py` 的 509 行口径），或按当前 1018 行口径重录基线 —— 属**机制改动，待裁**。
**附注（独立小问题，本轮未动）**：`.work/l5_integrity.json` 自己的 `l3_append_only` 判定也是 `FAIL`；按 `kb/.work/l5_integrity.py:134-138` 的判据，原因是**追加的 509 行 `distiller_version` 为 `None`、不是约定的 `l3-0.2`**（`by_version = {"None": 1018}`）。与本六道闸门无关，登记备查。

### ④-③ 前序产物哈希（45 项）—— **期望值过期（结构性红），非产物被篡改**

- 20/45 不符：`kb/l3/candidates/rules.jsonl`、`kb/l4/registry/l4.json`、`kb/l5/registry/l5.json`、`kb/l5/benchmark.json`、`kb/l6/{bm25/docs.jsonl,bm25/meta.json,bm25/postings_zh.jsonl,bm25/postings_en.jsonl,vectors/vectors.jsonl,vectors/matrix.npy,vectors/meta.json,index/l6.jsonl,registry/l6.json,retriever.py,selftest.json,benchmark.json,runs/build_runs.jsonl}`、`kb/l7/skills/kb-content-review/SKILL.md`、`kb/l7/registry/l7.json`、`kb/l7/skills/kb-content-review/scripts/review.py`。
- 期望值锚在**代码里硬编码的 4 个 2026-09-23 历史 run**（`workflow_check.py:129-131`：`kb/l4/runs/20260923-1445.json`、`kb/l5/runs/20260923-1430.json`、`kb/l6/runs/20260923-1440.json`、`kb/l7/runs/20260923-1500.json`）。
- 而列出的文件 mtime 全在 **2026-09-29 ~ 10-03**（例：`kb/l6/bm25/docs.jsonl` 10-01 10:55、`kb/l6/index/l6.jsonl` 10-02 22:47、`kb/l7/skills/kb-content-review/scripts/review.py` 10-03 12:44、`kb/l4/registry/l4.json` 10-03 21:18）⇒ **这些产物在 09-23 之后被合法重建/打过补丁，登记哈希未刷新**。
- 诚实边界：仅凭哈希**无法排除篡改**，但 mtime 与本仓 09-29~10-03 的已知重建活动一致，**没有任何证据指向篡改**。
- **要人做什么**：决定这条腿的去留 —— 要么给它一个刷新机制（每次重建后重录基线），要么改成只比对"未被下游写坏"的可判定子集。**复开条件**：基线刷新机制落地或该腿改判据。

### ④-⑧ 工作台与服务 —— **间歇性抖动（现象真实，判"服务坏了"证据不足）**

- 读数 `workbench_4317: "000"`；探针 = `curl -s --max-time 4`（`workflow_check.py:228-234`）。
- 我按**同一探针**连测 8 次：`200, 200, 000, 000, 000, 000, 200, 200`（000 每次耗满 4.19~4.24 s；200 耗时 0.12~0.69 s）⇒ **服务在，只是会间歇性地 4 秒内不回**。
- 今日 18 次 `workflow_check` 里 ⑧ 只红 **3 次**（13:36:31、13:36:37、13:46:02），其余（含 12:52~13:17 一连串）全绿 ⇒ **不是新坏，是抖动**；本次恰落在抖动窗口。
- 监听方：`lsof` 显示 127.0.0.1:4317 ← PID 2827（DSH Desktop 内进程）；`launchctl list` 里 `com.workbench.app`(2827) 与 `com.workbench.kb`(2862) 的上次退出状态均 **-15（SIGTERM）**，另有 `com.workbench.kb-keepalive` 在守。
- **要人做什么**：查 workbench 日志、给探针加重试/放宽超时；**要我先去看日志请单独说**。**复开条件**：探针连续多轮稳定 200，或该腿改为带重试。

### ⑥ 投影一致性（R1/R2/R4）

- **R1 源文件指纹**：视图派生记录 `kb/view/_meta/derivation.json` 的 `generated_at = 2026-09-29`，其 `sources.rules.sha256 = f27a14091b2bd782…`；当前 `kb/l3/candidates/rules.jsonl = 743dc62398311b02…`（`p0` 源 `470e3fba…` **一致**，未漂移）。⇒ **视图是 09-29 生成的，权威 L3 在那之后被重写过，视图未重新生成**。
- **R2 条目指纹**：同一根因（比的是每条 head 行的 JSON 指纹，源一改 509 条全变）。样本：`cg-r-006445396c95aa10` recorded `25e97a156c126e39…` → current `8e7fcfed442ea490…`。
- **R4 治理字段**：2036 处 = 509 × 4（`owner` / `half_life_days` / `valid_until` / `effective_from`）。**方向要先看清**：样本显示 `view` **有值**（`法务 + 产品负责人` / `365` / `2027-09-29` / `2026-09-29`），`authority` 是**空字符串** ⇒ **权威 L3 行里这 4 个字段本来就是空的**，视图里那些值是生成器给的默认值（`derivation.json` 的 `derived_defaults` 只声明 data_level/sensitivity_level，`governance_fallbacks` 为空数组）。
  ⇒ R4 的措辞「未传导」字面成立，但**不是「视图漏了数据」，而是「权威行没有这个字段可传」**。这是**口径题**：给权威行补字段，还是把判据改成只比非空字段 —— **待裁**，本 skill 不替它定性为「视图坏了」。
- 脚本给的修法：重跑 `kb/.work/gen-host-library.py` 到 staging 后回填（= **写 kb/view**）。**本轮未执行**（写库需单独授权）。
- **复开条件**：重生成并回填视图；且 R4 的口径先定下来。

## 3. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| 1 | `kb/l7/reports/<RUN>-routes-winners.json` 缺失 | 环境错 · 缺输入（exit 2） | 按 `kb-manage` 触发电测重出赢家表，或声明本闸门本轮不判定 | 赢家表就位 |
| 2 | ④-② 权威库比对 | 判据口径错位（1018 前 vs 2036 整份）+ 基线过期 | 改比较单位对齐 `l6_integrity.py` 的 509 行口径，或按现口径重录基线（机制改动，**待裁**） | 口径统一或基线重录 |
| 3 | ④-③ 20/45 产物哈希不符 | 期望值锚死 2026-09-23 硬编码 run | 决定该腿去留：给刷新机制，或改判据 | 刷新机制落地／判据改判 |
| 4 | ④-⑧ `workbench_4317` 间歇 000 | 服务抖动（非稳定故障） | 查 workbench 日志；探针加重试／放宽超时 | 连续多轮稳定 200 |
| 5 | ⑥-R1/R2 视图滞后 | 真滞后（视图 09-29 未重生成） | 重跑 `kb/.work/gen-host-library.py` 到 staging 后回填 kb/view（**需授权**） | 回填后 R1/R2 转绿 |
| 6 | ⑥-R4 2036 处 | 口径题（权威行无该 4 字段） | 先定口径：补权威字段 or 判据只比非空 | 口径定案 |
| 7 | 尺：孤岛率 0.94（阈值 ≤0.2） | 宿主 kb_check 维度不达标 | 冷条目靠扩充词表／补 asks 关键词（**不要靠删**） | 孤岛率回到 ≤0.2 |
| 8 | `.work/l5_integrity.json` 的 `l3_append_only` FAIL | 追加 509 行 `distiller_version` 为 None | 补版本戳或改判据 | 判定转 PASS |

## 4. 并发状况（必须一并读）

- 开跑前预检查报「前置齐、可开跑」，但**同一时刻至少有 4 个会话在跑同一套闸门**（实测进程：13:44:57 一个会话在跑 ①②；13:45 一个会话在跑 `CHK-20261004-1344` 的 ①；另一会话在跑 `workflow_check.py 20261004-1340` 与 `kb/l8/audit_l0_duplicates.py 20261004-1340`）。
- `sh kb/kbpy l7/scripts/kb_loop_claim.py status` = **无认领**（会话级认领未生效，但按库自己的并发纪律，同一条循环同一时间只准一个会话跑）。
- 本轮**未抢认领、未删任何锁**（`.kb.lock` 只存在 `kb/.work/.kb.lock.stale-20260930-152758`，按「陈旧锁」口径未处置）；只跑自己 RUN 的闸门，产物文件名带本 RUN id，不与并发会话冲突。
- ⑧ 的抖动**可能**与并发重负载相关 —— 这是**推测**，不是结论；要证实需查 workbench 日志。

## 5. 本轮写盘声明

| 路径 | 说明 |
|---|---|
| `kb/.work/kbcheck-CHK-20261004-1346/` | 本 RUN 的逐门 stdout/stderr 与退出码（`01.out`…`06.exit`、`00-declare.txt`） |
| `kb/l8/workflow_check_CHK-20261004-1346.json` | 门④ **无干跑档**，跑前已在 `00-declare.txt` 声明 |
| `kb/l7/reports/CHK-20261004-1346-health.md` | 本表（体检档产物） |

**未做**：未改任何 `kb/l0…l7` 数据、未回填 `kb/view`、未删锁、未跑 `kb-repair`、未执行任何修复动作。
