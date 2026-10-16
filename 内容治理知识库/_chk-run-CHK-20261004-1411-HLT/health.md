# 知识库体检表 · CHK-20261004-1411-HLT

- **档位**：`kb-check` **体检档**（六道闸门一次跑完）；**不是**评审循环档（循环档只跑 `layers.yaml` 本层 `engine:` 的 3 道）
- **run_id**：`CHK-20261004-1411-HLT`
- **窗口**：`2026-10-04 14:11:02 → 14:13:14 CST`（六道闸门逐项命令见下表；每条读数的文件时间戳可回源）
- **库根（cwd）**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **本 skill 只报不改**：未修任何东西、未删锁、未删副本、未 `--apply`、未 `--write-gate`、未抢循环认领、未写任何 run 记录、未改 `kb/l0~l6` 一行数据或台账、未向飞书发布任何东西。
- **标注约定**：【事实】= 命令/文件实测可回源；【推测】= 有依据未闭合；【观点】= 判断不是结论；【未判定】= 现有材料判不了，留给人。

## 0. 并发观察（skill §6 ALWAYS：先确认有没有另一批在跑）

【事实】跑前发现另一批 kb-check 会话 `_chk-run-CHK-20261004-1412-G6ALL`（14:10:03 启动）在同一库根上跑同一档位，
14:11 时它正在门④；本会话**未删任何锁**（`kb/.work/.kb.lock` 实测不存在）、**未抢写**、
门④ 等它 14:11:39 收工后才跑（本会话门④ 14:12:09 起、14:12:48 止）。
【事实】两批的六道退出码**逐项相同**（另一批 `01=0 02=0 03=2 04=1 05a=0 05b=0 06=1`；见 `_chk-run-CHK-20261004-1412-G6ALL/`），
即本表读数**可被独立复现**，不是单次抖动。

## 1. 体检表

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `kb/kbpy l7/scripts/skills_check.py` | **0** | **过** | 五类问题 `1=0 2=0 3=0 4=0 5=0`｜本项目要用 40 个、已装 40、还差 0｜62 条未登记 selftest **单独归类、不算错误**；3 备注（lark-base 本地版本超前于 CLI）、3 跳过（12 个只登记未安装的参考件） |
| ② | 层契约 | `kb/kbpy l7/scripts/layers_check.py` | **0** | **过** | 8 层齐（L0–L7）；六类 `1..6` 全 0；DAG 非线形（L2/L3/L4/L5/L6 各有上游分支）；无干跑档清单 0 条 |
| ③ | 路由表对账 | `kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-1411-HLT-routes-winners.json` | **2** | **缺输入**（**不是**数据坏；skill 样例把这一类归入「判据缺陷」栏） | 【事实】脚本原文：「环境错：赢家表不存在 …；缺输入时本闸门**不得报绿**，也不得静默按『全不一致』跑」。预检查亦报：`kb/l7/reports/` 下无 `*routes-winners*`，**全库无生成者**。带 `--alias` 变体同为 2。⇒ **exit 2 与「65 条全不一致」是两件事** |
| ④ | 链路收口 | `kb/kbpy l8/workflow_check.py CHK-20261004-1411-HLT` | **1** | **合法变红**（判据过期／已登记漂移）＋**内含 1 项真发现** | 【事实】9 段 **7 PASS / 2 FAIL**，FAIL = ② 权威库 l0~l6 未被改动、③ 前序产物哈希（45 项）。② 的 `l0/l1/l2` 三树与 L5 基线**均相符**（`bd36cbb8…/099ad8af…/183f6265…`），红在 `l3_lines=1018`、`base1018_matches_L6=false`、`whole1527_matches_L4=false` ⇒ 拿 09-23 冻结基线比活库；③ `checked=45 / mismatch=20`。定性依据 `kb/l7/registry/failure-playbook.yaml → gate_red.workflow_check`：「只有第 ②③ 段红 … 属**判据过期**，不是数据坏了」「②③ 属**已登记判据漂移 ⇒ 无需修数据**」。★ 但该条**另注**：③ 里 `kb/l7/registry/l7.json` 那一项是**真发现**（原地改写未落章、计数落后现库）——见 §2 |
| ⑤a | 信封闸门（`.py/.txt/.md`） | `python3 tools/envelope_gate.py` | **0** | **过** | 扫 **2061** 个文件｜信封态（\|差值\|==4096）**0** 个｜两读者交叉核对（DSH 内置 Electron 判据读者 vs PATH 里的 node）**一致** |
| ⑤b | 信封闸门（库自带，**只扫 `.md`**） | `kb/kbpy l8/envelope_census.py` | **0** | **过** | 扫 **10447** 个 `.md`，其中 1079 个 node 侧读不到，**全部已分类**：刻意归档 **569**（信封机制的证据本体）+ 可再生的过期备份 **510**（hostlib 可 1.8 秒重生成）｜结论 `OK`。⚠ 覆盖面与 ⑤a 不同，**不能互相替代** |
| ⑥ | 投影一致性 | `kb/kbpy l8/projection_reconcile.py` | **1** | **真坏** | 【事实】**3/6**：`R1_source_sha256`（源 `rules` 在视图生成后变过：`f27a14091b2bd782… → 743dc62398311b02…`）、`R2_entry_fingerprint`（**509 条**条目权威规则已变）、`R4_governance_passthrough`（**2036** 处治理字段未传导：`owner/half_life_days/valid_until/effective_from` 各 509）；`R3_id_set`/`R5_manifest_bytes`/`R6_tier_dir` 过。根因**本轮独立复核**（见 §3） |

## 2. 门④ 里的那一项「真发现」（别被「合法变红」这四个字盖住）

- 【事实】③ 的 20 项 mismatch 清单里含 `kb/l7/registry/l7.json`；`failure-playbook.yaml:151-152` 明写这一项是**真发现**（原地改写未落章、计数落后现库），修法是 `kb/.work/l7_article_source_refresh.py <RUN> --apply` + 补 L7 run 记录。
- 【事实】本轮用**干跑档**独立复核（`kb/kbpy .work/l7_article_source_refresh.py CHK-20261004-1411-HLT`，无 `--apply`，退出码 0，自述「未落盘」）⇒ **该项仍真**，干跑要改 6 个块，例如：
  `candidate_rows` **1997 → 2730**、`read_at` **2026-09-30 17:45:27 → 2026-10-04 14:13:14**、
  `total_outputs_note` 里 canonical 落盘 **1242 → 1365**、`field_lives_in` 与 `refreshed_by` 亦变。
- 【观点】所以门④ 的正确读法是：**② 段是判据过期（不能当数据坏），③ 段里 19 项同属判据漂移、1 项（`l7.json`）是真发现**。把它整段当「长期红、无需处理」会漏掉这一项。

## 3. 门⑥ 的根因（本轮自测，不转述他单）

- 【事实】按 playbook 指定的只读探针复核 L3 权威侧：`kb/l3/candidates/rules.jsonl` **1018 行**，
  但 `owner` 键存在 1018 / **非空 0**、`effective_from` 键存在 1018 / **非空 0**、
  `half_life_days` 与 `valid_until` **键都不存在**。
- 【事实】与 `finding.l3_governance_backfill_lost` 登记的读数**逐项相符**；且 `kb/l3/registry/l3.json` 的
  `changes[2]`（run 20260929-1040）**声称**已回填 509 行 ⇒ **注册表声明与实文件不一致**。
- ⇒ 门⑥ 的红**有根因、可回源**，属**真坏**；但**修法落在 `kb/l0~l6`（补 L3 治理字段）⇒ 先停、报批**，
  不是 kb-check 也不是 kb-repair 能自行动手的（playbook `forbidden` 明写「kb-repair 无权直接改 kb/l0…l6」）。
- ⚠ 【事实】**不许按门⑥ 脚本自带的 `fix` 提示（「重跑生成器到 staging 后回填」）直接重生成视图**：
  playbook 实测它是**陷阱** —— ① 修不了 R4（L3 四字段全空 ⇒ 重生成后 R4 照样红）；② **会造假绿**
  （把视图里**逐条**的 `owner`/`half_life_days` 换成统一常量、`valid_until` 归零为「今天 +180」）。

## 4. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| 门③ 的赢家表 `<RUN>-routes-winners.json` | `MISSING_INPUT`（【事实】`failure-playbook.yaml` **未登记**该情形，无对应原因码） | 按 `kb-manage` 的**触发电测**重新生成赢家表、放进 `kb/l7/reports/`（**不在 kb-check / kb-repair 的动作面**） | 文件存在且格式可解析（`<id>\|轮1\|轮2\|轮3` 或 `[{id,winners}]`）⇒ 门③ 得 exit 0 |
| 门④ 的 ②③ 两段 | `BASELINE_STALE`／`gate_red.workflow_check`（**已登记判据漂移**） | 三选一**要人点**：(A) 授权改判据（单独走一轮，需带反向测试：故意原地改一个层产物不落章 ⇒ 新判据必须仍判红）／(B) 裁定维持长期红／(C) 只登记 | playbook `reopen_when`：「改判据后复跑 exit 0；或本轮只做登记 ⇒ 结论写『基线漂移，非缺陷』并附本文件与原始读数」 |
| 门④③ 里的 `kb/l7/registry/l7.json` | **真发现**（非判据漂移） | 开闸后跑 `kb/kbpy .work/l7_article_source_refresh.py <RUN> --apply`，并补一条 L7 run 记录 | 该项从 ③ 的 mismatch 清单消失（干跑不再有 diff） |
| 门⑥ 的 R1 / R2 / R4 | `gate_red.projection_reconcile` ＋ 根因 `finding.l3_governance_backfill_lost` | **报批**后按序：`fix_f7_backfill.py` → `fix_f7_verify_c4.py` → `kb/kbpy l8/build_view.py --out kb/view` → 复跑 `l3_gate` + `projection_reconcile`。**顺序不许颠倒** | playbook `reopen_when`：`fix_f7_probe` 显示四字段 **509/509 非空**，且 `projection_reconcile.py` 退出 0 |
| `kb/.work/fix_f7_probe.py` 的 cwd 契约 | **判据缺陷（工具/文档 bug，不是数据缺陷）** | playbook `gate_red.projection_reconcile.command` 把探针写成库根相对路径 `python3 kb/.work/fix_f7_probe.py`，实测**在库根跑即 `FileNotFoundError: l3/candidates/rules.jsonl`**；须 `cd kb/` 再跑 `python3 .work/fix_f7_probe.py` | 按库根调用不再抛 `FileNotFoundError`（改探针的路径解析或改 playbook 的命令） |
| 门④ 第 ⑨ 段 | **判据缺陷（常真腿，无信号能力）** | 【事实】`kb/l8/workflow_check.py:271` 是 `add("⑨ 写入侧…", True, ing)` —— **判据硬编码为 `True`**，该段**在任何输入下都 PASS**。本次 detail 显示入库被 `[E026] 内容质量分 52.1 < 60` 拦下、落盘 0 个 ⇒ 行为符合设计（闸门生效、不留半成品），但**这一段本身不带信号**，不能当成「写入侧一切正常」的证据 | 判据改为按 `detail` 判定（如「落盘 0 个 **或** 落盘件信封 0」二者皆真）⇒ 该段才具备失败能力 |

## 5. 未判定 / 易误读（宁可标未判定，不猜）

1. **门④ 第 ⑧ 段有已知瞬时性**：【事实】本轮 ⑧ PASS（`workbench_4317=200`、`kb_hostlib_4508_health=200`、`launchd_jobs=5`）；同库已登记的旧坑是**探针在高负载下超时**会给出 `000`（见 `kb-repair-修复记录-20261004-1400-四道红分类与登记.md` §4.1）。
   ⇒ **别把该段的单次红当「服务坏了」报出去**。
2. **门⑤ 的两个计数差不是矛盾**：【事实】⑤a 扫 2061 个文件、⑤b 扫 10447 个 `.md` —— ⑤b 扫的是**全工作区**（含 `.work/hostlib` 等他人产物），不是同一集合；**覆盖面不同，不能互相替代**。
3. **门④ ① 段的「PASS」不是「库健康」**：【事实】该段判据是 `l4_canonical_bytes == 0 且 versions_rows == 0 且 kb_version == "v0"` —— 它判的是「**未启用态**」而非「数据正确」，绿不绿**不能**当健康证据。
4. **未跑的东西**（本档位不含，别当成「已体检」）：`kb/l7/scripts/{l0..l7}_gate.py` 各层闸门、`pipeline_check`、收口四件套。
   【事实】他单在同一窗口实测 `l0_gate.py → 1`（真差异 2：两张表 `pull_failed`，根因是 user 令牌不在）——**本表未复核该项**，故**不纳入本次结论**。

## 6. 写盘清单（先声明后跑）

1. `kb/l8/workflow_check_CHK-20261004-1411-HLT.json` —— 门④ 自身产物（**该闸门无干跑档，跑它必写**；本 RUN 专属，不覆盖他人）
2. `/tmp/l8-wfcheck/{wfcheck-CHK-20261004-1411-HLT,ingest-CHK-20261004-1411-HLT}/`、`/tmp/l8-wfcheck/ingest_probe_CHK-20261004-1411-HLT.mjs` —— 库根**之外**的沙箱
3. `_chk-run-CHK-20261004-1411-HLT/` —— 本会话证据（各门 `.out`/`.exit`、写盘声明、L7 干跑读数）
4. 本文件 —— 工作区 `.md` 记录（**写通道：`write` 工具落草稿 → `/bin/cp` 进 `kb/l7/reports/`**，避开 python 的 4096 字节信封）

**未写**：`kb/l0~l6` 任何数据与台账、任何 run 记录、`kb/l7/runs/index.jsonl`、任何锁文件、`kb/view` 任何一行、任何副本、任何服务配置、飞书任何东西。

## 7. 一句话收口

> 六道闸门 **3 过（①②、⑤a/⑤b 计两道）、1 缺输入（③）、1 合法变红但内含 1 项真发现（④）、1 真坏（⑥）**；
> **没有一道是"跑个脚本就能修绿"的** —— 它们的合规路径分别是：③ 交 `kb-manage` 触发电测、
> ④②③ 要人授权改判据（或只登记）、④③ 的 `l7.json` 是开闸后的 `--apply`、⑥ 要先报批补 L3 治理字段。
> 本 skill **只报不改**；真坏与失败项交 `kb-repair`，缺输入交 `kb-manage`。
