# 知识库体检表 · CHK-20261004-1259-KBHLT

> 由 `kb-check` **体检档**产出（六道闸门 + 宿主尺子）。**只报不改**：本表未修改任何库数据。
> 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
> 体检时刻：2026-10-04 12:44–12:53 CST ｜ skill：#.dsh/skills/kb-check（预检查 `scripts/preflight.py` 结论：前置齐，可开跑闸门）
> 运行方式：层前置/驱动循环**未跑**（本档是体检档，不是 L7 层身份）；未加 `--apply`、未删任何锁或副本。

---

## 1. 六道闸门体检表

| # | 闸门 | 命令（cwd = 库根） | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | ✅ 过 | 五类问题 `1..5 = 0`；本项目要用 **40**／已装 **40**／还差 **0**；未登记 selftest 62 条（单独归类、不算错误）；3 跳过、3 备注 |
| ② | 层契约自检 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | ✅ 过 | L0…L7 共 8 层无重复；六类问题 `1..6 = 0`；DAG 无环（L7 ← L0/L3/L4/L5/L6）；「无干跑档清单」0 条 |
| ③-1 | 路由对账 · **缺输入契约** | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-1259-KBHLT-routes-winners.json` | **2** | ⚪ **契约内（缺输入）** | 明确报「环境错：赢家表不存在 …」并**拒绝报绿** ⇒ 正是 `references/gates.md` 门③ 输入契约要的行为：**缺输入 ⇒ exit 2，不是「65 条全不一致」** |
| ③-2 | 路由对账 · **默认口径**（喂现存赢家表） | `… routes_reconcile.py _eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt` | **1** | ⚪ **口径产物，非数据坏** | 逐条全轮命中 **0/65**（`①=65`）：现存赢家表存的是**中文装载名**，默认口径不折回 ⇒ 全不匹配。**不许**读成「路由表全坏」 |
| ③-3 | 路由对账 · **`--alias` 口径** | 同上 `+ --alias` | **1** | 🔴 **真坏（已登记、边界明确）** | 逐条全轮命中 **60/65 = 0.923**（门槛 F1 ≥ 0.90 ⇒ 聚合口径过）；不一致 **5 条，全部同一成员** `brand-ai-provenance-rights-review`（**0/5 条、2/15 轮**；被 video 抢 3、image 抢 3、CLARIFY 1、NONE 6）；**路由表结构自检（第④节）= 0 条** ⇒ 坏的是「期望 vs 实际」，不是路由表本身 |
| ④ | 链路收口核验 | `sh kb/kbpy l8/workflow_check.py CHK-20261004-1244` | **1** | 🟡 **混合** | 9 段：PASS **7**（①④⑤⑥⑦⑨）／FAIL **3**（②③⑧）。**⑧ 已复测排除为探针抖动**（见 §1.6）⇒ 实质 FAIL 只有 ②③，且 ②③ 是**判据过期**。另**新发现**：④① 段 `l4_canonical_bytes=0 / versions_rows=0 / kb_version=v0`（L4 canonical 为空，与契约 `productionReady=false` 互证）。⚠️ **本闸门无干跑档，本次写盘 `kb/l8/workflow_check_CHK-20261004-1244.json`（4794 B，12:50）** |
| ⑤a | 信封闸门（`tools/`，**默认范围**） | `python3 tools/envelope_gate.py` | **0** | ✅ 过 | 扫 **2002** 个 `.py/.txt/.md`：信封态 **0**｜读不到 **0**｜两读者交叉核对**一致** |
| ⑤a′ | 信封闸门 · **全工作区补扫** | `python3 tools/envelope_gate.py --reader consumer .` | **1** | 🔴 **真坏 1 只（不在 `kb/` 内）** | 扫 **3031** 个文件：信封态 **1**（`_envctl-20261004-125012/py-write.md`，python=109／consumer-node=4205，Δ=**-4096**）；两读者**读数不一致 ⇒ 报红**。**库本体（默认范围）干净** |
| ⑤b | 信封普查（库自带，**只扫 `.md`**） | `sh kb/kbpy l8/envelope_census.py` | **0** | ✅ 过 | 扫 **10413** 个 `.md`，**1079** 个 node 侧读不到（Δ 区间 `[4096]`），**全部已分类**（569 刻意归档 ＋ 510 可再生备份），活路径 **0** |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py`（不加写参数） | **1** | 🔴 **真坏 3/6** | ❌ `R1_source_sha256`：`f27a14091b2bd782… → 743dc62398311b02…` ❌ `R2_entry_fingerprint`：**509 条** ❌ `R4_governance_passthrough`：**2036 处**（`owner`/`half_life_days`/`valid_until`/`effective_from` 各 509）｜✅ `R3_id_set` `R5_manifest_bytes` `R6_tier_dir` |

### 1.6 门④ 第⑧段「工作台与服务」：**判据抖动，非服务坏**（本轮已排除）

闸门读数 `{'workbench_4317': '000', 'kb_hostlib_4508_health': '200', 'launchd_jobs': '5'}` ⇒ 判 FAIL。**同一条 curl 立即复测**：

| 复测项 | 读数 |
|---|---|
| `http://127.0.0.1:4317/` × 6 次 | **200 / 200 / 200 / 200 / 200 / 200** |
| `http://127.0.0.1:4508/health` × 3 次 | 200 / 200 / 200 |
| `launchctl list \| grep -cE 'kb-hostlib\|workbench'` | **5** |
| `lsof` 监听 | `127.0.0.1:4317`（DSH Desktop，launchd `com.workbench.app`）＋ `127.0.0.1:4508`（Python，`com.kb-hostlib`）均在 LISTEN |

⇒ 与 `CHK-20261004-1158` 轮同型：`000` 系**探针抖动**（判据 `--max-time 4`），**不是服务坏**。**不进失败项清单**。

### 1.3 门③ 三种口径必须分开看（口径产物 ≠ 数据坏）

| 口径 | 结果 | 性质 |
|---|---|---|
| 缺输入（`kb/l7/reports/*routes-winners*` 不存在） | exit **2** | 契约内：**缺输入**，全库无生成者（赢家表是触发评测的**运行时产物**） |
| 默认口径（喂现存赢家表、不折回 alias） | exit 1，**0/65** | **口径产物**：中文装载名 vs 英文别名，逐条全不匹配 |
| `--alias` 口径 | exit 1，**60/65**（0.923），5 条不一致 | **真坏**（已登记、边界明确）：全部同一成员 |

现存唯一赢家表 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt` 至本轮已**陈旧 9.47 小时**（03:24 → 12:53）。

### 1.4 宿主尺子 `kb_check`（DSH 侧加载器体检）

| 项 | 读数 | 性质 |
|---|---|---|
| 健康分 | **79.2**（熔断线 60） | **未触发熔断** |
| 结论 | **不通过** | 判据是 `ok = (错误数 == 0) && !熔断`；本轮**错误项非空**（`E026 ×454` 等）⇒ 判失败。**「79.2 所以还行」「孤岛率超标所以判失败」两种说法都不成立** |
| 维度 | 新鲜度 1.00 ✅／三件套 1.00 ✅／一致性 1.00 ✅（未裁决冲突 0）／**孤岛率 0.94 ❌（阈值 ≤ 0.2）**／覆盖率 0.92 ✅（35/38，未命中 Q21/Q22/Q38）／利用率 0.23 ✅ | 孤岛率是**维度告警**，不参与上一条判定 |
| 活跃码 | `E026 ×454`（内容质量分 < 60）／`W020 ×2218`（疑似重复，**机器只报疑似、判归人**）／`W021 ×10`（疑似数值矛盾）／`H005 ×1`（提醒：检索排序未经 UAT 复核） | — |
| 条目基线 | **消失 0／治理字段被原地改 0／正文有改动 0／未入基线 0** | 未带 `accept_baseline` ⇒ 这是真比对结果，不是被抹平 |
| 验收契约 `content-governance-hostlib-20260923` | `status=derived-view`／`maturity=draft`／**`productionReady=false`**；谓词 `no_duplication=false`；未达条件 **3/3**；生效阻断码 **3** 个；负例自检 **0/3 未跑** | 契约自己说不达标，不是谦虚 |
| 接线审计 | `_meta/*.yaml` 顶层键全部已接线或已声明为判据散文 | ✅ |
| 无数据维度 | 幻觉率（未进分母） | 口径缺口 |

---

## 2. 失败项清单（对象 ＋ 原因码 ＋ 要人做什么 ＋ 复开条件）

> **原因码取值纪律**：唯一真源 = `kb/l7/registry/failure-playbook.yaml`（27 条）。取不到就退到同前缀的 `*`；
> **连兜底都没有就写「没有登记的处置办法」——不许现编 owner／办法**。下表凡标「无登记」的，就是取不到。

| # | 对象 | 原因码 | 归口（playbook id） | 要人做什么 | 复开条件 |
|---|---|---|---|---|---|
| 1 | 门⑥ 投影 `R1/R2/R4`（`kb/view` ⇄ 权威分层库） | `PROJECTION_DRIFT` | `gate_red.projection_reconcile` → 内容治理数据组（刘华丽）＋ L3 层主（**判定**）；kb-repair 只做分类与登记 | ★ **不要**按脚本自带 fix 提示（「重跑生成器到 staging 后回填」）直接重生成视图 —— playbook 实测它是**陷阱**：(1) **修不了 R4**（L3 四个治理字段现全空，兜底分支写常量 ⇒ 重生成照样红）；(2) **会造假绿**（把逐条治理值降级为统一常量、`valid_until` 变成「今天+180」，正是 `half-life-policy.json` 禁止的 `never_resets_on_regeneration` 那一类）。**正确顺序**：先补 L3 治理字段（报批动作，见 `finding.l3_governance_backfill_lost`）→ 再重出视图（`kb/l8/build_view.py --out kb/view`，生成到 /tmp staging ＋ `repack_write.mjs` 明写回填）→ 最后复跑本闸门与 `l3_gate` | `kb/l8/projection_reconcile.py` 退出 **0**（R1/R2/R4 同时绿） |
| 2 | 门④ 第②③段（② 权威库 l0~l6 未被改动／③ 前序产物哈希 45 项） | `BASELINE_DRIFT`（**判据过期，已登记、不给豁免**） | `gate_red.workflow_check` → 维护 `kb/l7/registry` 的人（判定）＋ 数据面归各层层主 | **不需要修数据**：② 只在 L3 漂（`l3_lines=1018`），③ `checked=45 / mismatch=20`——判据写在**已经过去的时点**，登记在 `kb/l7/registry/workflow-check-known-drift.yaml`（该文件自述「今天没有任何闸门读本文件」，**登记≠豁免**，复跑必然 FAIL）。要人**裁决**：「更新冻结基线」还是「接受永久红」。**不许**：改历史 run 记录里的 artifact sha（伪造台账）／把 L3 回滚到 1527 行时代（毁 10-02 蒸馏成果）／就地改宽判据而不同时报批 | 改判据后复跑 **exit 0**；或本轮只做登记 ⇒ 结论写「基线漂移，非缺陷」并附该登记文件与原始读数 |
| 3 | 门④ 第③段内的**真发现**：`kb/l7/registry/l7.json`（原地改写未落章，计数落后现库；实测差异 6 字段） | `L7_REGISTRY_STALE`（**playbook 无同名条目**，按 `gate_red.workflow_check` 的 `do` 第 3 句处置） | `gate_red.workflow_check` 同条（L7 层主） | 开闸后跑 `kb/.work/l7_article_source_refresh.py <RUN> --apply` **并补 L7 run 记录**。⚠️ 本库当前是「两周只读观察期」，`--apply` 是**写档动作，需人批准**；`total_rules` **不在**差异清单里（那句「632 vs 1018」单位不可比，已由第 8 轮撤回，别照抄旧句子） | 该文件 sha 与现库一致，且 L7 run 记录落章齐 |
| 4 | 门③ 的输入位置 | `MISSING_INPUT` | `gate_missing.*` 不精确覆盖（该前缀管「层闸门未判」）；**按 `references/gates.md` 门③ 输入契约处置** | 赢家表**不在** `kb/l7/reports/`；现存唯一一份在 `_eval-kb-manage/results_alias/`，**已陈旧 9.47 小时** ⇒ 要当天数据须按 `kb-manage` 的**触发电测**重新生成并放进 `kb/l7/reports/<RUN>-routes-winners.json` | 该文件存在且格式可解析（txt `id|r1|r2|r3` 或 json `[{id,winners}]`）⇒ 门③ 默认口径 exit 0 |
| 5 | 成员 `brand-ai-provenance-rights-review` 的 5 条路由期望 | `ROUTE_EXPECT_MISMATCH`（前缀退到 `conformance.red` → 该技能的作者） | `conformance.red` → 该技能的作者（或 `kb-manage` 指派的成员 owner） | 改该成员 `description`／触发词：5 条全挂、**2/15 轮**（被 `brand-video-safety-review` 抢 3 次、`brand-image-safety-review` 抢 3 次、`CLARIFY` 1 次、`NONE` 6 次）。**路由表结构自检 = 0 条** ⇒ 别去改路由表结构 | 重跑触发电测生成新赢家表后，门③ `--alias` ＝ **0 条**（`skill_conformance.py` 退出 0） |
| 6 | `_envctl-20261004-125012/py-write.md`（全工作区 ⑤a′） | `ENVELOPE_STATE_NEW`（真坏，**1 只**） | 无 playbook 条目；处置口径同上一轮同类项：**由产生它的那一路**处置 | 该目录是**并发会话的「信封负控探针」**（同目录另有 `bash-write.txt`/`cp-write.txt`/`node-write.txt`/`py-write.txt`），**不在 `kb/` 内**：python 通道写的 `.md` 带 4096 信封 ⇒ 用 `node`／`/bin/cp` 通道重写，或探针用完即清／移出扫描范围。**不许**动 `kb/l0…l7` | `envelope_gate.py --reader consumer .` 信封态 **0** 且两读者**读数一致**（默认范围早已为 0） |
| 7 | 宿主尺子「不通过」的总闸：**错误项非空**（直接原因 `E026 ×454`） | `HOST_CHECK_FAIL` | **无登记的处置办法**（27 条条目里 `E026`／`host_check`／`质量分` 全部取不到，前缀也退不到） | ⇒ 按纪律**不现编**：需先由知识库负责人把这一类（宿主错误码清零）**登记进 `failure-playbook.yaml`** 并指派 owner，再谈处置。在此之前任何人按「错误码」分派都是无据分派 | `kb_check` 错误项 **0** ⇒ 结论转「通过」 |
| 7a | `E026 ×454`（内容质量分 < 60，例 55.6／长度 1.9/20） | `E026` | **无登记**（同上） | 分数结构是「长度＋密度＋去重＋语言」；454 条普遍卡在**长度**（1.x/20）与**语言**（~20/30）⇒ 逐条扩写正文是内容动作，需 owner 定夺；**不许**为了清零而删条目 | `E026 = 0` |
| 7b | `W020 ×2218`（疑似重复，「要么合并、要么把分工写进 summary」） | `W020` | **无登记** | **机器只报疑似、判归人**：逐对裁决「新建 + supersedes 留痕」或「写明分工」。**不许原地改写** | `W020` 归零，或每对给出裁决留痕 |
| 7c | `W021 ×10`（疑似数值矛盾） | `W021` | **无登记** | 逐条人裁（例：同键「命中表达」本条 1 条、对端 3 条） | `W021` 归零或逐条留痕 |
| 7d | 孤岛率 **0.94**（阈值 ≤ 0.2）；`423/509` 条目从未被检索命中 | `ISLAND_RATE_HIGH` | **无登记** | 库内口径明确：靠**扩充词表**或补 `asks` 关键词解决，**不要靠删**。⚠️ 它是**维度告警**，不是「不通过」的原因 | 孤岛率 **≤ 0.2** |
| 7e | 验收契约 `content-governance-hostlib-20260923` 三阻断码 | `OWNER_ACCEPTANCE_INCOMPLETE`／`FINAL_RECEIPT_MISSING`／`DATASET_NOT_BUSINESS_AUTHORIZED` | **无 playbook 条目**；契约文件自身 `owner: 刘华丽`（`kb/view/_meta/acceptance.yaml` 与 `kb/l8/meta_src/acceptance.yaml`） | 补三条件：`owner_acceptance`、`final_receipt`、`fixed_eval_set`；另 `no_duplication=false` 与 7b 同源；负例自检 **0/3 未跑**（`roundtrip_check.py`） | 三条件齐 ⇒ `productionReady` 才可为 `true` |

**已排除、不进清单**：门④ 第⑧段（探针抖动，§1.6）；门④ 第⑥段（本轮 PASS，`其他` 桶 = 0，510 只 hostlib 属判据容忍桶）；门⑤ 默认范围（0）；`H005 ×1`（提醒，不是错误）。

---

## 3. 三种「红」的口径（分派前必须先分类，否则会派人去修不该修的东西）

1. **真坏** → 交 `kb-repair`：清单 #1、#5、#6（#7′ 见「无登记」）。
2. **合法变红（基线漂移，非缺陷）** → 清单 #2：**不许修数据**，要的是「更新基线 or 接受永久红」的裁决。
3. **判据缺陷／契约内** → 门③-1（缺输入 exit 2）、门④第⑧段（探针抖动）。
4. **无登记的处置办法** → 清单 #7 系列：**按纪律不现编 owner**，先登记再分派。

**不许做的（摘自 playbook `forbidden`，逐字）**：不许为了让 ②③ 变绿去改写历史 run 记录里的 artifact sha；不许把 L3 回滚到 1527 行时代；不许就地改宽判据而不同时报批；不许在 L3 治理字段仍为空时重生成视图并宣布「修好」；不许把视图的 `owner`/`half_life_days`/`valid_until` 清空换绿。

---

## 4. 与上一轮 `CHK-20261004-1158` 的差异（可核）

| 项 | 11:58 轮【引用】 | 本轮【实测】 | 归因 |
|---|---|---|---|
| ⑤a′ 全工作区信封 | exit 1，信封态 **2**（扫 2880） | exit **1**，信封态 **1**（扫 3031），对象换成并发会话的**探针** | 那 2 份修复副本**已被并发会话在 12:14–12:16 修掉且未复发**；新增 1 只是探针 |
| 门④ 第⑥段 | FAIL，`其他 = 2` | **PASS**，`其他 = []`（不可读 510 全在 hostlib 容忍桶） | 同一件事已修 |
| 门④ 第⑧段 | PASS（200） | FAIL（**000**），**立即复测 6/6 = 200** | **探针抖动**，与 11:45 轮同型 |
| 门③ `--alias` | 60/65、同一成员 | **逐字相同** 60/65、同一成员 | **未变**（期望已 ~9.5 小时未动） |
| 门⑥ 投影 | 3/6 漂移 | **逐字相同** 3/6（R1 同 sha 对、R2 509、R4 2036） | **未变、未被任何人修** |
| 宿主健康分 | 79.2、孤岛率 0.94、`E026 ×454` | **相同**（`W020 ×2218`／`W021 ×10`／`H005 ×1` 亦相同） | **未变** |
| 条目基线 | 消失 0／治理字段被改 0 | **相同** | 知识库本体**干净** |

---

## 5. 并发披露【实测】（kb-check §5.4 纪律：凡「层已跑完」类结论必须带 run_id + 时间戳）

- **同一工作区存在另一路并发会话正在跑同类扫查**，实测证据：`_chk-run-CHK-20261004-1244-REG5/`、`_chk-run-CHK-20261004-1250-CLOSE/`、`_chk-run-CHK-20261004-1251-REG5/`、`_envctl-20261004-125012/`、`kb/l7/reports/CHK-20261004-1244-REG5-health.md`（12:49）、`CHK-20261004-1256-ENV-health.md`；且 **12:51 有 `kb_pipeline.py --check` 进程在跑**。
- **RUN 名撞车**：并发那一路也用了 `CHK-20261004-1244` 前缀 ⇒ 本表改用 `CHK-20261004-1259-KBHLT`；**本轮的 `kb/l8/workflow_check_CHK-20261004-1244.json` 与并发那一路的 RUN 字面相同**，若后者也跑门④，同名产物会互相覆盖 —— 分派时以本表的读数与时间为准。
- `kb/.work/.kb.lock` **不存在**，`kb_loop_claim.py status` 报「无认领」，但 **kb/ 近 30 分钟有 74 个文件被写入** ⇒ 属于「另一批在跑」，**已按纪律不按『删锁』处置、未动任何锁**。
- **本轮写盘披露**：门④ 无干跑档，写 `kb/l8/workflow_check_CHK-20261004-1244.json`（4794 B，12:50）。⑤a/⑤a′/⑤b/⑥ 均只读。**未加 `--apply`，未改任何 `kb/l0…l7` 数据**。

## 6. 未判定项（宁可标未判定，不猜）

- `_envctl-20261004-125012/` 的完整用途与清理时机 ⇒ 归并发那一路，本轮**未动**。
- 门④① 段 `l4_canonical_bytes=0` 是「尚未定稿」还是「登记缺口」⇒ 需 L4 层主判定，本表只报读数。

*本表由 `kb-check` 体检档产出，**只报不改**。真坏项交 `kb-repair`；本表未改任何东西。*
