# 逐层收口核验表 — 统一闸门（kb-check 体检档）· run `CHK-20261004-1347-LAYERCLOSE`

- **run_id**：`CHK-20261004-1347-LAYERCLOSE`
- **测量窗口**：`2026-10-04 13:46:24 – 13:58:59 CST`（cwd = 库根）
- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **档位**：`kb-check` **体检档** —— 六道统一闸门 ＋ 八层闸门（`l0_gate`…`l7_gate`）＋ `kb_pipeline.py --check`（零写档）＋ 逐层落章探针
- **纪律**：**只报不改**。未 `--apply`、未 `--sync`、未 `--write-gate`、未改任何数据 / 台账 / 注册表 / 判据，未向飞书发布任何东西。
- **留底**：`_chk-run-CHK-20261004-1347-LAYERCLOSE/`（每道闸门一个 `.out` ＋ `.exit`，逐条可回放）；驱动脚本 `_chk-run-CHK-20261004-1347-LAYERCLOSE/driver.sh`
- **本会话唯一写进 `kb/` 的文件**：`kb/l8/workflow_check_CHK-20261004-1347-LAYERCLOSE.json`（门④ 无干跑档，开跑前已在 `00-declare.txt` 声明）＋ 本报告 `kb/l7/reports/CHK-20261004-1347-LAYERCLOSE-health.md`
- ★ 跑的时候**另有 ≥5 个会话在读写同一库**（含一个正在跑的整链批次）⇒ 本表是**活库快照**，不是独占环境下的冻结读数（见 §4）。

---

## 0. 先纠一条前提：「整条链路我刚跑完最新一批」——盘上没有这样一批

我按「有没有层侧落章 / 有没有记账」核了一遍 10-04 的全部批次，**没有一批是「跑完整条链且落了盘」的**：

| 批次 | 是什么 | 实际到哪 | 证据 |
|---|---|---|---|
| `PIPE-20261004-1257`（供给链 L0→L7） | `kb-pipeline` 整链 | **停在 L0 闸门，一层引擎都没进执行态**；本 BASE 在 `index.jsonl` **记账 0 行**，各层 `runs/` **无 1257 落章** | `整链同步-PIPE-20261004-1257-停在L0-阻断说明.md`（13:10）；`grep -c PIPE-20261004-1257 kb/l7/runs/index.jsonl` → **0** |
| `20261004-1357-L4/L5/L7`（认领 BASE `PIPE-20261004-1358`） | 另一会话 13:56 起跑的逐层批次 | **跑到一半就停了**：L4/L5/L7 已记账（**三层都是预演**，`layer_stamps_applied=[]`、`layer_stamps_dry=[…-dryrun.json]`；记账 `skill_evidence=registry_echo`，**无 `--invoked` 上报**），**L6 无落章、L0–L3 未跑**；14:03 该批认领转 **『陈旧（可 `--take-over`）』—— pid 74048 已不在** | `kb/l7/runs/20261004-1357-L{4,5,7}.json`；`kb/l4/runs/20261004-1357-L4-dryrun.json`、`kb/l5/runs/20261004-1357-L5-dryrun.json`；`kb_loop_claim.py status` |
| `P0MILK-20261004-1219`（评审链 L4→L7） | 逐层一 RUN 的评审前置 | 四层都跑了，**四层全是预演**（`dry_run=true / applied=false`） | `kb/l{4,5,6}/runs/P0MILK-20261004-1219-*-dryrun.json` |

**决定性读数**：`kb/l0…l6/runs/` 里，**10-04 13:00 之后新增的落章 = 0**（`find kb/l{0..6}/runs -newermt '2026-10-04 13:00'` 除 1357 批次外为空）。库里**最后一次真落盘**（`applied=true 且 dry_run=false`）逐层停在 **10-02 21:02（L0/L1/L3/L4/L6）、10-02 23:28（L5）、10-03 21:17（L2）**。

⇒ **「跑完」≠「收口」。** 本表因此给**两个口径**的答案，二者不矛盾、缺一个都会误导：

| 口径 | 问的是 | 本次答案（本会话亲跑） |
|---|---|---|
| **闸门口径** | 这层的**闸门**过没过 | **8 层里只有 L0 一道红**，L1–L7 全 `exit=0` |
| **收口语径** | 这层**真的把结果写进库**了吗 | 🔴 **8 层没有一层闭上** —— 本批（1357）L4/L5 是预演、L6 未落章、L0–L3 本批没跑 |

---

## 1. 六道统一闸门读数

命令一律 `sh kb/kbpy <脚本> …`（⑤a 是 `python3 tools/envelope_gate.py`），cwd = 库根；原始输出见留底目录。

| # | 闸门 | 退出码 | 结论 | 结论类型 | 关键读数（13:46–13:58 实测） |
|---|---|---|---|---|---|
| ① | 登记表自检 | **0** | ✅ 过 | 过 | 五类问题 `1=0 2=0 3=0 4=0 5=0 ｜合计 0`；要用 **40** / 已装 **40** / 还差 0；未登记 selftest 62 条（**单独归类，不算错**）；跳过 12（登记 source 未安装，不做副本比对） |
| ② | 层契约自检 | **0** | ✅ 过 | 过 | 层 **8** 齐全；六类问题全 0；无干跑档清单 **0 条**；DAG 非线形（`L2←L0,L1`；`L7←L0,L3,L4,L5,L6`） |
| ③ | 路由表对账 | **2** | ⚠️ **未判定（缺输入）** | 缺输入 | 名义输入 `kb/l7/reports/CHK-20261004-1347-LAYERCLOSE-routes-winners.json` **不存在** ⇒ 按设计 `exit 2`，脚本自述「缺输入时**不得报绿**，也不得静默按『全不一致』跑」。**这不是「65 条路由全不一致」** |
| ④ | 链路收口核验 | **1** | 🟡 **9 腿 2 红（②③）** | ②③ 均为**冻结基线**（合法变红／判据缺陷） | 裁决 `FAIL（未过：['② 权威库 l0~l6 未被改动','③ 前序产物哈希（45 项）']）`；9 腿中 7 腿 PASS；装载位 509 / 信封 0 / 健康分 **79.2**（> 熔断线 60）；腿③ `checked=45`、**不符 20 项**（`kb/l3/candidates/rules.jsonl`、`kb/l4/registry/l4.json`、`kb/l5/**`、`kb/l6/**`、`kb/l7/registry/l7.json`…） |
| ⑤a | 信封闸门（`.py/.txt/.md`） | **0** | ✅ 过 | 过 | 扫 **2035** 个文件 ｜ 信封态 **0** ｜ 读不到 **0** ｜ 两读者（DSH 内置 Electron / PATH node）交叉核对**一致** |
| ⑤b | 信封普查（库自带，**只扫 `.md`**） | **0** | ✅ 过 | 过 | 扫 **10431** 个 `.md`，node 侧读不到 **1079** = 刻意归档 569 ＋ 可再生的过期备份 510，**活路径 0** ⇒ `结论：OK` |
| ⑥ | 投影一致性 | **1** | 🔴 **真坏 3/6** | 真坏 | ❌ `R1_source_sha256`（源 `rules` 在视图生成后变过 `f27a1409…→743dc623…`）❌ `R2_entry_fingerprint`（**509 条**条目权威规则已变）❌ `R4_governance_passthrough`（**2036 处**：owner / half_life_days / valid_until / effective_from **各 509**）；✅ R3 / R5 / R6 |
| — | `kb_pipeline.py --check`（八层全景） | **1** | 🔴 硬问题 1 条 = **L0 闸门未过** | 真坏 | **零写自证 ✅**：产出文件 mtime 快照 **4001** 个、变化 **0** 个 |

**结论口径（三种红分开说，不混）**：真坏 = ⑥ ＋ L0；合法变红 = ④ 腿②③（比的是 **2026-09-23** 的冻结基线，活库模式下必红）；未判定 = ③（缺今日输入）。**红里没有一条是「脚本坏了」。**

---

## 2. 逐层收口表（L0 → L7）—— 本表主体

「本层闸门」取自 `kb/l7/registry/layers.yaml` 各层 `gate:`（**唯一真源，本表未抄第二份**）；
退出码取自本会话亲跑（`l{0..7}_gate.py`）与 `kb_pipeline.py --check` 的只读白名单路径（**零写，已自证**）；
「最近一次真落盘」= 该层 `runs/` 里 `applied=True / dry_run=False` 的最新落章（**逐份读字段**，不是按文件名猜）。

| 层 | 本层闸门（`layers.yaml:gate`） | 闸门退出码 | 本批 `20261004-1357-L*` 落章 | 最近一次**真落盘** | **收口？** |
|---|---|---|---|---|---|
| **L0** | `l7/scripts/l0_gate.py` | **1** | 本批无 L0 落章 | `20261002-2101` **10-02 21:02:02** | 🔴 **没闭上**：闸门红 **＋** 本批未落盘（**两重**） |
| **L1** | `l7/scripts/l1_gate.py` | 0 | 本批无 L1 落章 | `20261002-2101` **10-02 21:02:03** | 🟡 闸门过；**本批未落盘** |
| **L2** | `l7/scripts/l2_gate.py` | 0 | 本批无 L2 落章 | `20261003-2117` **10-03 21:17:56** | 🟡 闸门过；**本批未落盘** |
| **L3** | `l7/scripts/l3_gate.py` | 0 | 本批无 L3 落章 | `20261002-2101` **10-02 21:02:07** | 🟡 闸门过；**本批未落盘** |
| **L4** | `l7/scripts/l4_gate.py` | 0 | `20261004-1357-L4-dryrun`（**预演**） | `20261002-2101` **10-02 21:02:08** | 🟡 闸门过；**本批未落盘** |
| **L5** | `l7/scripts/l5_gate.py` | 0 | `20261004-1357-L5-dryrun`（**预演**） | `20261002-2101` **10-02 23:28:45** | 🟡 闸门过；**本批未落盘** |
| **L6** | `l7/scripts/l6_gate.py` | 0 | **无落章、无记账**（该批没跑到 L6 就停了） | `20261002-2101` **10-02 21:03:02** | 🟡 闸门过；**本批未落盘** |
| **L7** | `l7/scripts/l7_gate.py` | 0 | 只有记账 `kb/l7/runs/20261004-1357-L7.json` | **无**（`skill_write=false`，跨层闸门不写数据，**口径如此**） | ⚪ 口径如此；本批仍是预演 |

**一句话**：**闸门口径 —— 8 层里只有 L0 一道红；收口语径 —— 8 层没有一层闭上。**

### 2.1 逐层闸门各自读了什么（不抹掉关键读数）

| 层 | 关键读数（原文摘） |
|---|---|
| L0 | `一致 612 ｜ 飞书多 10 ｜ L0多 0 ｜ 值变 0 ｜ 拉取失败 2`；分类 `预期内 10 ｜ 真差异 2`；未声明差异 2 条：**专家修订汇总表（tbl8AI00JZO1iZtp）**、**内容公式（仅供参考）（tblVdl0jdK9G4ld3）** 均「拉取失败」 |
| L1 | 单图缓存 **169** 条 ｜ 版本分布 `{'vision-jxa-2.0': 169}` ｜ 全部可复用 |
| L2 | 五项判据 **0 违规**；说明项（非红）：作废后仍留产物 306 个资源、滞后未切分 311 个资源 |
| L3 | 证据引用 3704 ｜ 候选 2730 条 / 产出 568 资源 ｜ 拒绝台账 10661 行 ｜ 自报键 12 个全已声明 |
| L4 | 定稿 **1365** ｜ 候选 632 ｜ L2 单元 12213 ｜ 条款号区间 `E-1.1 … W-3.99` ｜ `canonical/rules.jsonl` **0 字节**（应为 0）；C7/C8 本闸门不复算（要人抽检） |
| L5 | 实质 4 项全 PASS；`frozen_layers` / `l3_append_only` FAIL 但**已登记为判据过期、不判红**；P0 导出 7 条 == 可复算 7 条 |
| L6 | 可用单元复算 **4261** == 自报 == 索引行数 ｜ 向量 25874 行 ｜ 说明项：`bm25_failed = 1`、注册表计数器 4260 vs 产物 4261 |
| L7 | 规则候选 1018 条 ｜ 定稿 1365 条 ｜ 六要素齐备 **1365（100.0%）** ｜ 版本 `v0`（试用版，未发布） |

### 2.2 L0 那道红，红在哪、是谁的活

**先给结论**：L0 红是**活差异、要人处置**，但它**不是新缺陷** —— 库内 `kb/l7/registry/l0-expected-diffs.yaml` 的 `resolved[EX-2/EX-3].observed_20261004` 与 `kb/l7/registry/failure-playbook.yaml` 的 `gate_red.L0` **已登记这条失效模式会这样发作**，我的实测与登记逐项吻合：

- 两条判据同时坏：**bot 恒 `91403 you don't have permission`（整库级）** ＋ **回落身份（user）不可用**。回落机制（2026-10-03 加的 `L8_AS_FALLBACK`）依赖 user 令牌，而该令牌**无 refresh token**，到期即失效 ⇒ 回落这条路一断，两张表回到 `pull_failed`，而 EX-2/EX-3 已移入 `resolved` ⇒ 变成「未声明差异」⇒ 判红。
- **我独立复现的两条**（本会话亲跑，非引用他人报告）：
  - `lark-cli base +table-list --base-token SKkkbdZi9aRuMzs7ob0cpSYHnQg --as bot --profile dsh-kb` → `ok:false`、**code 91403**、`you don't have permission`（exit 1）；
  - `lark-cli auth status --profile dsh-kb` → **bot `ready` ｜ user `missing`**。
- 表→Base 归属也核过：`kb/l8/align_l0_feishu.py:81-82` 把这两张表列在 base `SKkkbdZi9aRuMzs7ob0cpSYHnQg` 下（与 `kb/l0/records/内容公式（仅供参考）/*.json` 的 `entry_url` 一致）。
- **未验证的部分（如实标注）**：我没有进一步隔离「是否**只有**这一个原因导致两张表拉取失败」—— 即 91403 是**最强解释**，但我没做「换身份单表重拉」的对照实验。**这一点是合理推测，不是已确认事实。**
- **明文禁止**（库内写死，不许绕）：不许把这两张表的 `pull_failed` 写进 `l0-expected-diffs.yaml` 的 `expected` 去「声明掉」——它是**回落失效的报警**；也不许改 `align_l0_feishu.py` 把 `pull_failed` 从四类差异里摘出去。

---

## 3. 失败项清单（对象 ＋ 原因码 ＋ 性质 ＋ 要人做什么 ＋ 复开条件）

| # | 对象 | 原因码 | 性质 | 要人做什么 | 复开条件 |
|---|---|---|---|---|---|
| 1 | `kb/l0` ↔ 飞书两张表（`tbl8AI00JZO1iZtp` / `tblVdl0jdK9G4ld3`） | `pull_failed ×2`（未声明） | 🔴 **真坏（活差异；库内已登记的失效模式按预期发作）** | 二选一：① **根治**（不用改代码）——飞书侧把「守衡」bot 加成该 Base 的**可阅读协作者**；② **临时**——`lark-cli auth login --profile dsh-kb --domain base --domain wiki`（Device Flow，**需人点浏览器授权**） | `l0_gate.py` **exit 0** |
| 2 | `kb/view` 投影（509 条 / 2036 处治理字段） | `R1` `R2` `R4` | 🔴 **真坏** | 先确认投影生成器是否从规则行读那 4 个治理字段（F8），再重跑 `kb/.work/gen-host-library.py` 到 **staging 后回填**；回填要写 `kb/view` ⇒ **需单独授权**。**不许 `rm -rf kb/view`**（`kb/view/_meta/` 住着活状态） | `projection_reconcile.py` **exit 0**（6/6） |
| 3 | 门④ 腿②③（45 项哈希 20 项不符） | 冻结基线 | 🟡 **合法变红／判据缺陷，非数据缺陷** | **不要修数据**。比对对象是 **2026-09-23** 的基线快照；20 项文件 mtime 全在 09-29～10-03。重新锚定基线或**显式豁免**属**机制改动，需人裁**（选项草案在 `kb/l7/registry/workflow-check-known-drift.yaml`） | 基线重锚后复跑；**登记本身不让它转绿** |
| 4 | 门③ 路由对账 | **缺今日输入** | ⚠️ **未判定** | 按 `kb-manage` 的触发电测**重新生成今日赢家表**，落到 `kb/l7/reports/<RUN>-routes-winners.json` | 拿到今日赢家表后 `routes_reconcile.py <表>` 才能判定 |
| 5 | 门④ 腿⑨ 恒真判据 | `CRITERION_TAUTOLOGY` | 🟡 **判据缺陷，非数据缺陷** | `kb/l8/workflow_check.py:271` = `add("⑨ 写入侧（ingest 闸门 + 落盘通道）", True, ing)` —— 第二参数**硬编码 `True`**（**本会话独立读码确认**），该腿**永远不可能 FAIL**，作为闸门没有鉴别力。是否改属**机制改动，需报批** | 改成真判据并做反向测试 |
| 6 | 8 层的**收口缺口**（全库自 10-02/10-03 起无新真落盘；在飞批次 1357 三层全预演） | `dry_run=true` / `skill_evidence=registry_echo` | 🟡 **收口缺口（流程性，非数据坏）** | 要真收口须：① 先在 **L0 上放行**（`break` 位于 `kb_pipeline.py` 的 `via_skill` 分支**之前**）；② 逐层用 **skill 工具真的加载**本层 skill 并执行；③ 每层带 `--invoked` / `--skill-session` 记账；④ 由**人开闸**（`--apply`，写档白名单见 `write-gate.yaml`）。**当前 1357 批次没有 `--invoked`** ⇒ 审计 `E1` 红 | 层侧落章出现 `dry_run=false / applied=true` **且** `skill_invocation_audit.py --run <各层RUN>` **红 0** |

**判别提示（避免把「机制证据」当「落盘证据」）**：`skill_invocation_audit.py` 对 1357 批次三层实测 —— L4/L5 `E1` 红＋`E5` 黄（「落章来自预演」）、L7 `E1` 红（L7 免 `E5`），结论一律 **「本 run 声称的『逐层调了』，证据不成立」**，退出码 1。

---

## 4. 并发披露与零写自证（读这张表前必须知道）

- **测量窗口内环境不是独占的**：同刻有 ≥5 个会话在跑 KB 相关命令（`l{0..7}_gate.py`、`workflow_check.py`、`audit_l0_duplicates.py`、`envelope_gate.py`、`l1_status.py`、`lark-cli` 拉数…），另有会话在写 `kb/l7/reports/CHK-20261004-{1344,1345,1346,1349,1350,1351,1355,1358}-*.md`。
- **另有一会话跑过整链，且它中途死了**：`kb_loop_claim.py status` 在 13:56–14:02 全程显示 **进行中 ｜ 会话 `20c8e588-…` ｜ pid 74048 ｜ BASE `PIPE-20261004-1358`**，**14:03 转为『陈旧（可 `--take-over`）：pid 已不在且已过宽限期（6 分钟）』** —— 即该批只跑到 L4/L5/L7 记账就断了（L6 无落章、L0–L3 未跑），并**留下一个未释放的认领**。⇒ 我**没有**去认领、没有抢锁、没有 `--take-over`、没有触碰它的批次（`kb-check` 是只读档，接手属别人的决策）；`kb/.work/.kb.lock` 全程**不存在**。
- **零写自证**：
  - 7 项层数据产物 sha256 前后**逐项一致**（`00-pre.sha` ⇄ `99-post.sha`，`99-sha-diff.txt` 为空，`diff` 退出码 0）。**诚实标注**：我的指纹清单里 `kb/l1/units.jsonl` 一项记为 **MISSING** —— 该路径本就不存在（L1 的数据产物是 `kb/l1/manifest_l1.jsonl`），**这是我的清单路径写错，不是数据缺失**；L1 未变由下一条的全量快照覆盖。
  - `kb_pipeline.py --check` 自证：产出文件 mtime 快照 **4001** 个、**变化 0** 个。
  - `kb/l7/runs/index.jsonl` 行数 **1426 → 1434（+8）**，**8 行全部来自其它会话**（6 条 `kb-l0-feishu · l0_daily`「未过｜真差异=2」＋ 2 条 `kb-check · daily_health`「过0/红0/未判8｜零写=True」）；**本会话未向 `kb/l7/runs/` 写任何行**。
- **本会话写盘仅两处**：`kb/l8/workflow_check_CHK-20261004-1347-LAYERCLOSE.json`（门④ 按设计写）＋ 本报告文件。
- ⇒ 本次读数是**活库快照**，可作为「L0 红 / ⑥ 真坏 / 收口缺口」的复现证据（与 12:53、13:40 两单**逐项同值**），但**不构成冻结基线口径的独占判定**。

---

## 5. 留底与单条回放

- 原始输出：`_chk-run-CHK-20261004-1347-LAYERCLOSE/`（`01` `02` `03` `04` `05a` `05b` `06` `g-l0`…`g-l7` `pc` 各含 `.out` ＋ `.exit`；`00-declare.txt` / `00-claim-before.txt` / `00-pre.sha` / `99-post.sha` / `99-sha-diff.txt` / `07-layer-stamps.txt` / `99-claim-after.txt`）
- 驱动脚本：`_chk-run-CHK-20261004-1347-LAYERCLOSE/driver.sh`；落章探针：`_chk-run-CHK-20261004-1347-LAYERCLOSE/layer_stamps.py`
- 单条回放（cwd = 库根）：
  ```bash
  sh kb/kbpy l7/scripts/skills_check.py
  sh kb/kbpy l7/scripts/layers_check.py
  sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json   # 缺输入 ⇒ exit 2
  sh kb/kbpy l8/workflow_check.py <RUN>        # 无干跑档，会写 kb/l8/workflow_check_<RUN>.json
  python3 tools/envelope_gate.py ; sh kb/kbpy l8/envelope_census.py
  sh kb/kbpy l8/projection_reconcile.py
  for g in l0 l1 l2 l3 l4 l5 l6 l7; do sh kb/kbpy l7/scripts/${g}_gate.py; echo "$g exit=$?"; done
  sh kb/kbpy l7/scripts/kb_pipeline.py --check
  ```
