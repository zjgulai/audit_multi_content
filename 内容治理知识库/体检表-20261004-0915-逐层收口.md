# 逐层收口核验表 — 2026-10-04 09:05–09:18（统一闸门 = kb-check 体检档）

- **run_id**：`CHK-20261004-0905-CLOSE`
- **库根（cwd）**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **档位**：`kb-check` §1 **体检档**（六道统一闸门）＋ 逐层零写总检（`kb_pipeline.py --check`）＋ 本批 `skill_invocation_audit`
- **纪律**：**只报不改**。未修数据、未加 `--apply`、未带 `--write-gate`、未改任何判据、未发布任何东西到飞书。
- **留底**：`_chk-run-CHK-20261004-0905-CLOSE/`（每组 `.cmd` ＋ `.out` ＋ `.exit`，逐条可回放）
- ★ 跑的过程中**另有会话在写同一库**（见 §7），本表是**活库快照**，不是冻结基线。

---

## 0. 三条前提更正（第一条会改变你问的问题的答案）

**① 「我刚跑完最新一批」—— 它确实跑了，但一个字节都没写进库。**
最新一批 `REV-20261004-0855`（L4→L5→L6→L7，08:55:33 / 08:55:53 / 08:58:42 / 08:58:49）的四层落章
**全部** `dry_run=true / applied=false`；记账自述 `layer_stamps_applied=[]`、
`verdict="全走完（预演 · 未落盘 · 非执行证据）"`、`write_gate.resolved=false`。
八层版最新的 `PIPE-20261003-2354`（L0→L7）同样**八层全预演**。
⇒ **「跑完」≠「收口」**。库里最后一次**真落盘**停在 **10-02 21:0x / 10-03 21:17**（见 §2）。

**② 「每层收口没闭上」有两个口径，答案不一样，必须分开答。**

| 口径 | 问的是 | 本次答案 |
|---|---|---|
| **闸门口径** | 这层的闸门过没过 | **只有 L0 一道红**，L1–L7 全绿 |
| **收口语径** | 这层这次**真的把结果写进库**了吗 | 🔴 **八层没有一层闭上** —— 全部是预演 |

只报前者会误导（「七绿一红，基本没事」）；只报后者也会误导（「全没跑，那还查什么」）。两个都给你。

**③ 「最新一批」在盘上有三个候选，我没替你猜，把三个都列出来**（见 §2.0）。
我按「最近一次跨层调用」取 `REV-20261004-0855` 作为主批次；若你指的是整链 L0–L7，那是 `PIPE-20261003-2354`；
两个口径的收口结论**都是「没闭上」**，所以主批次的取法不影响结论，只影响归因。

---

## 1. 统一闸门（体检档）九条读数

命令一律 `sh kb/kbpy <脚本> …`（⑤a 为 `python3 tools/envelope_gate.py`），cwd = 库根；原始输出见 `_chk-run-CHK-20261004-0905-CLOSE/`。

| # | 闸门 | 脚本 | **退出码** | 结论 | 结论类型 | 关键读数（本会话 09:05–09:18 实测） |
|---|---|---|---|---|---|---|
| ① | 登记表自检 | `l7/scripts/skills_check.py` | **0** | ✅ 过 | 过 | 五类问题 `1=0 2=0 3=0 4=0 5=0 ｜合计 0`；本项目要用 40 / 已装 40 / 还差 0；`status=参考 11`、`宿主通用 19` 不参与判定；跳过 12（登记了 source 但未安装，不做副本比对） |
| ② | 层契约自检 | `l7/scripts/layers_check.py` | **0** | ✅ 过 | 过 | 层 **8** 齐全（L0←外部源、L1←L0、L2←L1/L0、L3←L0/L2、L4←L2/L3、L5←L0/L2/L3、L6←L0/L2/L3、L7←L0/L3/L4/L5/L6）；六类问题 `1..6 全 0`；无干跑档清单 **0 条** |
| ③ | 路由表对账 | `l7/scripts/routes_reconcile.py <赢家表>` | **2**（无参）／**1**（套旧表） | ⚠️ **未判定（缺今日输入）** | 缺输入 | 无参 = argparse 缺必填位 `winners` ⇒ **exit 2**（按设计拒跑，**不是**「65 条全不一致」）。套盘上**最新**一份赢家表 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`（**03:24**）+ `--alias`：**60/65 = 92.3%**、四节问题 `①=5 ②=同上 ④=0` ⇒ **exit 1**。这是**过期口径的读数，不是今天的判定** |
| **④** | **链路收口核验** | `l8/workflow_check.py CHK-20261004-0905-CLOSE` | **1** | 🟡 **9 段 3 红（②③⑥）** | ②③=**合法变红**；⑥=**真坏（他会话产物）** | `裁决：FAIL（未过：['② 权威库 l0~l6 未被改动', '③ 前序产物哈希（45 项）', '⑥ 文档可见性']）`；逐段见 §3 |
| ⑤a | 信封闸门（`.py/.txt/.md`，消费方读者） | `python3 tools/envelope_gate.py` | **0** | ✅ 过 | 过 | 扫 **1925** 个文件 ｜ 信封态 **0** ｜ 读不到 **0** ｜ 两读者交叉核对**一致** |
| ⑤b | 信封普查（库自带，**只扫 `.md`**） | `l8/envelope_census.py` | **0** | ✅ 过 | 过 | 扫 **10336** 个 `.md`，读不到 **1079** = 刻意归档 569 ＋ 可再生的过期备份 510，**活路径 0** ⇒ OK |
| **⑥** | **投影一致性** | `l8/projection_reconcile.py` | **1** | 🔴 **真坏 3/6** | 真坏 | ❌ `R1_source_sha256` ❌ `R2_entry_fingerprint`（509 条）❌ `R4_governance_passthrough`（**2036 处**）；✅ R3 / R5 / R6 |
| — | **逐层零写总检** | `l7/scripts/kb_pipeline.py --check` | **1** | 🔴 **L0 闸门红** | 真坏 | L0 `exit=1`；**L1–L7 全 `exit=0`**；**零写自证 ✅**（产出文件 mtime 快照 **4001** 个，变化 **0** 个）；硬问题 1 条 = L0 闸门未过 |
| — | 宿主体检 `kb_check`（面三） | MCP | —（无退出码） | ⏸ **本轮未自跑** | 未跑 | ④ 第⑤段带出了它的健康分 **79.2**（六维：新鲜度 1.0 / 三件套 1.0 / 一致性 1.0 / 孤岛率 0.9411 ❌ / 覆盖率 0.9211 / 利用率 0.2309），但那**不等于**跑过 `kb_check` |

**红 2 道（④⑥）＋ 未判定 1 道（③）＋ 逐层 L0 1 道。没有一条红是「脚本坏了」。**

### 1.5 一条作废的读数（如实更正，别引用它）

`kb_pipeline.py --check` 在**后台作业里**首跑时拿到 **exit 143（SIGTERM）且 stdout 为 0 字节**；
**前台复跑**得 **exit 1 ＋ 2901 字节完整输出**（即上表那一行）。
⇒ 143 那次是**进程被终止**、不是闸门结论，**已作废**，本表只用前台复跑那次。原因未定位（不猜）。

---

## 2. 逐层收口表（L0 → L7）—— 本表主体

### 2.0 先对齐「本批」是哪一个（三个候选，盘上实测）

| 候选 BASE | 覆盖面 | 层侧落章时点 | 层侧落章性质 |
|---|---|---|---|
| **`REV-20261004-0855`**（本表主批次） | **L4 / L5 / L6 / L7** | 08:55:33 / 08:55:53 / 08:58:42 / 08:58:49 | 四层**全 `-dryrun`** |
| `PIPE-20261003-2354` | **L0–L7 全八层** | 10-03 23:56 → 10-04 00:19 | 八层**全 `-dryrun`** |
| `PIPE-20261004-0217` | 声称整链 | 只有 `kb/l7/runs/PIPE-20261004-0217-L0.json`（02:18） | **无任何层侧落章** —— 连预演都没留下 |

### 2.1 收口总表

「本层闸门」取自 `kb/l7/registry/layers.yaml` 各层 `gate:`（唯一真源），退出码取自 `kb_pipeline.py --check` 的
只读白名单路径（**零写**，已自证）。「最近一次真落盘」= 该层 `runs/` 里 `applied=True / dry_run=False` 的最新落章（我逐份读了 `dry_run` / `applied` 字段，不是按文件名猜）。

| 层 | 本层闸门（`layers.yaml:gate`） | 闸门退出码 | 本批落章 | 最近一次**真落盘** | 该层真落盘落章总数 | **收口？** |
|---|---|---|---|---|---|---|
| **L0** | `l7/scripts/l0_gate.py` | **1** | `PIPE-…-2354-L0-dryrun`（10-03 23:56） | `20261002-2101-l0-feishu-reconcile` **10-02 21:02** | 12 | 🔴 **没闭上**：闸门红 **＋** 本批未落盘（两重） |
| **L1** | `l7/scripts/l1_gate.py` | 0 | `PIPE-…-2354-L1-dryrun`（10-03 23:59） | `20261002-2101-manifest-reconcile` **10-02 21:02** | 11 | 🟡 闸门过；**本批未落盘** |
| **L2** | `l7/scripts/l2_gate.py` | 0 | `PIPE-…-2354-L2-dryrun`（10-04 00:00） | `20261003-2117` **10-03 21:17** | 22 | 🟡 闸门过；**本批未落盘** |
| **L3** | `l7/scripts/l3_gate.py` | 0 | `PIPE-…-2354-L3-dryrun`（10-04 00:03） | `20261002-2101` **10-02 21:02** | 14 | 🟡 闸门过、本批未落盘；**但 ⑥ 指它的数据是真坏**（§4-F2） |
| **L4** | `l7/scripts/l4_gate.py` | 0 | `REV-…-0855-L4-dryrun`（10-04 08:55） | `20261002-2101` **10-02 21:02** | 14 | 🟡 闸门过；**本批未落盘** |
| **L5** | `l7/scripts/l5_gate.py` | 0 | `REV-…-0855-L5-dryrun`（10-04 08:55） | `20261002-2101` **10-02 23:28** | 14 | 🟡 闸门过；**本批未落盘** |
| **L6** | `l7/scripts/l6_gate.py` | 0 | `REV-…-0855-L6-dryrun`（10-04 08:58） | `20261002-2101` **10-02 21:03** | 15 | ⚠️ 闸门过、本批未落盘；**另有一条「层自检块疑似沿用」的存疑项**（§5） |
| **L7** | `l7/scripts/l7_gate.py` | 0 | **无层侧落章**（`skill_write:false`，跨层闸门不写数据，口径如此） | 不适用 | — | ✅ 闸门过；本批四层审计**红 0 / 黄 1** |

**一句话**：**闸门面只红 L0 一道；收口面八层无一层闭上**（全部预演，`applied=false`）。

### 2.2 本批的逐层 skill 审计（`skill_invocation_audit.py --run …`）

| RUN | 退出码 | 结论 | 黄 |
|---|---|---|---|
| `REV-20261004-0855-L4` | 0 | ✅ 过（声明 = 记账 = 落章 三方一致） | 🟡 `E5` ×1 |
| `REV-20261004-0855-L5` | 0 | ✅ 过（同上） | 🟡 `E5` ×1 |
| `REV-20261004-0855-L6` | 0 | ✅ 过（同上） | 🟡 `E5` ×1 |
| `REV-20261004-0855-L7` | 0 | ✅ 过 | 无（L7 三重代码级豁免） |

★ **`E5` 照抄工具自己的话**：落章**全部来自预演台账**（`dry_run=true / applied=false`）
⇒ 这个绿**只能**读成「逐层调用**机制**通了」，**不能**读成「这些层真落盘过」。
⇒ 所以 §2.1 的「收口」列不能拿这张表的绿来兑。

---

## 3. ④ `workflow_check` 九段逐段（**退出码 1**）

**命令**：`sh kb/kbpy l8/workflow_check.py CHK-20261004-0905-CLOSE`
**产物**：`kb/l8/workflow_check_CHK-20261004-0905-CLOSE.json`（`at=2026-10-04 09:15:37`，`verdict=FAIL`）
**⚠️ 该脚本无干跑档**：不加任何参数也会写上面那份 JSON —— 本轮**已声明并接受**这次写盘。

| 段 | 结果 | 关键读数（取自本轮 JSON 的 `legs[].detail`） |
|---|---|---|
| ① 环境与版本纪律 | **PASS** | 装载位 `02:02:55`；生成器 `11:26:57 408a6d079312b66f 73520B`；`l7/review.py` `12:44:03 ed47c8f4b9bbc93f 84943B`；hostlib `22:45:11`；`l7/reports 09:15:23`；`l4_canonical_bytes=0`、`versions_rows=0`、`kb_version=v0` |
| **② 权威库 l0~l6 未被改动** | **FAIL** | l0 `bd36cbb89dedb48f` 4007 件 `match_L5_baseline=true`；l1 `099ad8afdc1a0be2` 3152 件 `true`；l2 `183f6265c0666688` 887 件 `true`；**`l3_lines=1018`、`l3_base1018_matches_L6=false`、`l3_whole1527_matches_L4=false`** ⇒ 漂移**只在 L3** |
| **③ 前序产物哈希（45 项）** | **FAIL** | 核 45 项、**20 项 mismatch**：`kb/l3/candidates/rules.jsonl`、`kb/l4/registry/l4.json`、`kb/l5/registry/l5.json`、`kb/l5/benchmark.json`、L6 的 12 项（`runs/build_runs.jsonl`、`bm25/{docs,meta,postings_zh,postings_en}.jsonl`、`vectors/{vectors.jsonl,matrix.npy,meta.json}`、`index/l6.jsonl`、`registry/l6.json`、`retriever.py`、`selftest.json`、`benchmark.json`）、`kb/l7/skills/kb-content-review/{SKILL.md,scripts/review.py}`、`kb/l7/registry/l7.json` |
| ④ 分层库 → 生成器 → 视图 | **PASS** | 沙箱重生成 **510 md / 信封 0**；加载器直读 `entries=509` `fm_ok=453`；`E001=None` `E046=None`；沙箱侧健康分 76.5 |
| ⑤ 装载位 → 加载器 | **PASS** | 530 文件 / 513 md / 信封 0；`entries=509`、`fm_ok=453`、`kb_class_ok=453`；健康分 **79.2**；六维 `新鲜度1.0 三件套1.0 一致性1.0 孤岛率0.9411 覆盖率0.9211 利用率0.2309`；检索探针 `[[W-2.1,111,true],[乳腺组织,1,true],[合规替代,509,true],[量子纠缠配色调参,0,true]]`；码史 `W020=2218 W021=10 E026=454` |
| **⑥ 文档可见性（agent 能否读到）** | **FAIL** | 工作区 **6180** md，不可读 **513**，`buckets={'其他': 3, '他人产物 hostlib': 510}` ⇒ `其他` 必须为 0，实为 **3**（三个路径见 §4-F3） |
| ⑦ 消费侧 skill 可用 | **PASS** | 入口闸门生效（无 `KB_ENTRY` ⇒ `entry_gate_rc=2` 拒跑）；真入口 `with_kb_evidence.py` ⇒ `real_entry_rc=0`；`review_py_plaintext_write_patch=true` |
| ⑧ 工作台与服务 | **PASS** | `workbench_4317=200`、`kb_hostlib_4508_health=200`、`launchd_jobs=5` |
| ⑨ 写入侧（ingest 闸门＋落盘通道） | **PASS** | 闸门生效 `[E026] 内容质量分 52.1 < 60`；**`landed=[]`、`landed_enveloped=0`** |

**②③ 为什么是「合法变红」**：`kb/l8/workflow_check.py` 第②段拿「前 1018 行」的 sha 比
`kb/.work/l6_integrity.json` 的基线、再拿「前 1527 行」比 **`kb/l4/runs/20260923-1445.json`**（**09-23** 那份 run）；
第③段只遍历 **4 份 09-23 的 run 记录**声明的 `artifacts`，要求**今天仍逐字节相等**。
L3 现文件**正好 1018 行** ⇒「前 1018 行」**就是整个文件**，结构上不可能等于旧哈希。
⇒ **一条「09-23 之后一个字节都不许动」的判据，遇上每天在跑的活库，必然 FAIL 且复跑仍 FAIL。**
登记处：`kb/l7/registry/failure-playbook.yaml → gate_red.workflow_check`（**判据过期，不是数据坏了**）。

---

## 4. 失败项 / 未判定项清单（对象 ＋ 原因码 ＋ 要人做什么 ＋ 复开条件）

处置口径一律取自本库真源 `kb/l7/registry/failure-playbook.yaml` 与 `kb/l7/registry/l0-expected-diffs.yaml`；
**没有登记处置办法的项不给你自造流程**，只标「待裁」。

### F1 🔴 L0 闸门红 —— 真差异 2（**真坏**，唯一红的层）
- **读数**：`l0_gate.py` exit=1；`未过 ｜ 真差异=2 ｜ 预期内=0`；未声明差异两条 =
  `专家修订汇总表（tbl8AI00JZO1iZtp）`、`内容公式（仅供参考）（tblVdl0jdK9G4ld3）`。
- **原因码**：`l0-expected-diffs.yaml → resolved[EX-2/EX-3]` —— **两张表都是 91403 资源级 ACL**。
- **要人做什么**（二选一，取自真源）：
  ① **根治**（不改代码）：在飞书侧把「守衡」bot 加成这两张表的**可阅读协作者**；
  ② **临时**：`lark-cli auth login --profile dsh-kb --domain base --domain wiki`（Device Flow，**需人授权**）。
- **不许做的**：把这两条写进 `expected`「声明掉」（该文件 `not_exemptable` 明令禁止），
  或把 `pull_failed` 从对账器四类差异里摘掉。
- **复开条件**：`l0_gate.py` 退出 **0**（两表 `拉取失败 0`；`飞书多 10` 仍由 `EX-1` 覆盖）。

### F2 🔴 ⑥ 投影漂移 3/6 —— **根因在权威侧 L3**（**真坏**）
- **读数**：❌ `R1_source_sha256`、❌ `R2_entry_fingerprint`（509/509）、❌ `R4_governance_passthrough`（**2036 处** = `owner`/`half_life_days`/`valid_until`/`effective_from` 各 509）。
- **原因码**：`finding.l3_governance_backfill_lost` —— `kb/l3/registry/l3.json` 的 `changes[2]`（run `20260929-1040`）
  **声称**已把四个治理字段回填进 509 行，**实文件却是空的**（注册表声明与实文件不一致）。
- **★ 本会话独立复算**（不是抄闸门输出）：

  ```
  kb/l3/candidates/rules.jsonl   2,778,872 B   mtime 2026-10-02 22:45:07   1018 行 / 509 唯一 rule_id
  sha256 = 743dc62398311b0287e1e99fbcc438397ca8c721a0556d534cc69f3ee6eff840
    owner            键存在 1018   非空 0     effective_from   键存在 1018   非空 0
    half_life_days   键存在    0   非空 0     valid_until      键存在    0   非空 0
    article_no       非空 509                p_level 分布 {P0:0, P1:986, P2:32, P3:0}
  ```
  ⇒ R1 属实且**不是并发伪红**：`rules.jsonl` mtime **10-02 22:45**，**不在**本轮窗口（09:05–09:18）内。
- **要人做什么**（真源三步）：① **报批**（改 `kb/l0…l6` 数据 ⇒ `kb-repair` 无权自行动手）→
  ② 重跑 `kb/.work/fix_f7_backfill.py` ＋ `fix_f7_verify_c4.py` 复核（确认不动 `rule_text`/`anchor`）→
  ③ **补一条 L3 run 记录**（本次丢失正是「改了没落章」）→ ④ 重出视图 `kb/kbpy l8/build_view.py --out kb/view` →
  ⑤ 复跑本闸门与 `l3_gate`。
- **★ 红线（真源 `forbidden` 原文口径）**：**不要**按脚本自带的「重跑生成器回填」提示直接重生成视图 ——
  （1）**修不了 R4**（判据是「md 字段 == 权威 head 行字段」，权威侧全空 ⇒ 等价于要求 md 也留空）；
  （2）**会造假绿**：视图现值是**逐条、有区分**的，兜底写的是**统一常量**且 `valid_until = 今天 + 180`
  ⇒ 会把逐条治理值换成常量、把有效期时钟归零，正是 `half-life-policy.json` 明令禁止的那一类。
  **也不许**为让 R4 变绿把视图的 `owner/half_life_days/valid_until` 清空。
- **复开条件**：`projection_reconcile.py` 退出 **0**（R1/R2/R4 同时绿）。

### F3 🔴 ④第⑥段的 3 件活路径信封 —— **全部是另一会话的 eval 副本**（**真坏，归属他人**）
用与闸门同一把尺子（宿主 Electron `statSync().size` vs python `getsize()`）**逐文件独立复算**，三件全为真，差值恒 **+4096**：

| 文件 | host | python | 差 | mtime |
|---|---|---|---|---|
| `_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md` | 21469 | 17373 | **+4096** | 10-04 **08:57:02** |
| `_eval-L0L7-gap-20261003/kb-l0-feishu-fix/references/CHANGELOG.md` | 22112 | 18016 | **+4096** | 10-04 **08:02:44** |
| `_eval-L0L7-gap-20261003/kb-check-fix/SKILL.md` | 13037 | 8941 | **+4096** | 10-04 **08:58:06** |

- **三件都不是 `kb/l0…l6` 数据、也不是投影/权威库内容**；是本窗口内**另一个会话**（skill eval）写出的工作区产物。
  `kb-l0-feishu-fix/SKILL.md` 的 mtime **08:57:02** 就在 `REV-20261004-0855` 那批的窗口里 ⇒ **这段红是移动靶**。
- **为什么 ⑤a / ⑤b 都不报它们**（我读了源码，不是推测）：⑤a 的
  `DEFAULT_ROOTS`（`tools/envelope_gate.py:65-66`）= `kb/l0…l8`、`kb/.work`、`kb/view`、`kb/versions`、`tools`、`_eval-kb-manage`
  —— **不含** `_eval-L0L7-gap-20261003`；⑤b 只走 `kb/`。**④第⑥段是唯一覆盖工作区根 `_eval-*` 的那把尺子。**
  ⇒ 三把尺子**判据不矛盾，是覆盖面不同**。
- **要人做什么**：**不要**由本轮动手 —— 该目录**正在被那个会话写**。等它跑完再按**写通道**重写这 3 件，或与那个会话协调同轮修。
  **不许为消红而删目录**（尤其不许删 `_eval-L0L7-gap-20261003/` 与 `kb/l8/_archive/**`）。
- **复开条件**：④第⑥段 `其他` = **0**（复跑 `workflow_check`）。

### F4 🟡 ④ 第②③段（20 项 mismatch）—— **合法变红，不用修数据**
- **原因码**：`gate_red.workflow_check`（判据冻结在 2026-09-23）。
- **要人做什么**：**不用修数据**。要转绿只能**单独走一轮「改判据」**（改 `kb/l8/workflow_check.py`，**不是**登记文件），且须做**反向测试**证明仍能抓到「未落章改写」。
- **复开条件**：改判据轮完成（或按真源 `reopen_when` 第二路：本轮只做登记 ⇒ 结论写「基线漂移，非缺陷」＋附本表与原始读数）。
- ★ **②③ 里的真发现（别被「合法变红」四个字盖掉）**：`kb/l7/registry/l7.json` 原地改写**未落章**（无 run 记录记过现 sha）。
  ⇒ 开闸后跑 `kb/.work/l7_article_source_refresh.py <RUN> --apply` ＋ **补一条 L7 run 记录**（属写 `kb/l7` 登记面，**要独占**）。

### F5 ⚠️ ③ 路由对账 —— **未判定（缺输入）**
- **原因码**：无今日赢家表。赢家表是**触发评测的运行时产物**，**全库没有任何脚本会自动生成它**。
  盘上最新一份是 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`（**03:24**）。
- **要人做什么**：按 `kb-manage` 重跑触发电测产出**本 RUN** 的赢家表，放进 `kb/l7/reports/`。
- **复开条件**：`routes_reconcile.py <今日赢家表> --alias` 退出 **0**（或 1 = 有真结论）。
- **待裁（不是缺陷）**：**绿线定义** —— 92.3% 算过（`F1 ≥ 0.90`）还是要求「不一致须为 0」？判据维护人未裁。

### F6 ℹ️ 「本批八层全预演」本身不是「坏」，但它是「没闭上」的直接原因
- **原因码**：`write_gate.resolved=false`（**未带 `--write-gate` 凭据**）＋ 层引擎未带 `--apply`。
- **要人做什么**：要真收口必须**另跑一轮**并带写凭据（`--apply` / `--write-gate`），**且要单独报批**。
- **复开条件**：各层 `runs/` 出现 `applied=true / dry_run=false` 的落章，且 RUN 名与本批一致。

---

## 5. ⚠️ 一条本轮新发现的存疑项：L6 落章的 `integrity` 块**疑似沿用**

**这不是闸门红**（`l6_gate.py` 只读四项全过），但它可能让「L6 收口了」这句话**没有证据**。

- **实测**：`kb/l6/runs/REV-20261004-0855-L6-dryrun.json → integrity.vector_traceability`：
  `verdict=FAIL`、`bad_count=392`、`p0_in_vector` **321 条**（该块**没有 `counts` 键**）。
- **对不上现行盘**（独立复算，只读）：
  1. `kb/l3/candidates/rules.jsonl` 全 1018 行 `p_level` = `P1 986 / P2 32`，**没有任何一行是 P0**；
     `grep -c half_life …` = **0**。
  2. `kb/l6/registry/l6.json`（现行）记的是 `vector_skipped_p0: 0`。
- **旁证（本会话新算的）**：把 `integrity` 块按 `sort_keys` 序列化后比 sha ——
  **与另外 33 份落章逐字节相同**，横跨 **10-02 00:13 → 10-04 08:58**（含 `20261002-2101`、`PIPE-20261003-2354-L6-dryrun`、`REV-20261004-0855-L6-dryrun`）。
- **判定：未判定成因**，两种可能都不排除 ——
  (a) 该块被**沿用**，本批 L6 自检不是活读数；
  (b) P0 口径与 `l6_scope_lib` 现行实现**不一致**，自检读错了源。
- **要人做什么**：跑一次**只读**复算对比 392/321 与现行盘。⚠️ **不要带 `--apply`** ——
  `kb/.work/l6_integrity.py` 的 `idempotent_rerun` 段会带 `--apply` 重跑建索引并**写库**。
- **复开条件**：落章里的 P0 读数能被现行盘复现，且 `l6.json` 与 run 记录不再互相矛盾。
- **不建议**读成「L6 今天坏了」，**同样不建议**读成「L6 今天没问题」。

**★ 顺带更正一份兄弟表的一处数字**：`体检表-20261004-0058-逐层收口.md` §3.5 写的是
「`p0_in_vector` 392 条 ｜ `counts.vector_skipped_p0` 321」。按本会话实测，该块里
**`bad_count` = 392**、**`p0_in_vector` = 321 条**、**没有 `counts` 键**。
两处数字**疑似对调**。我以实测为准，并如实标注这处分歧（不改他人文件）。

---

## 6. 三种「红」的分类（`kb-check` §4 口径）

| 类别 | 本次命中 | 说明 |
|---|---|---|
| **真坏** | **F1** L0 闸门红（ACL）／**F2** ⑥ R1/R2/R4（根因 `finding.l3_governance_backfill_lost`）／**F3** ④⑥段 3 件活路径信封（他会话产物） | F2 须**先报批**才动手；F3 要**与那个会话协调**；F1 要**飞书侧加协作者或授权** |
| **合法变红** | **F4** ④ 第②③段（判据锚在 2026-09-23） | 结论写「基线漂移，非缺陷」，**不许**当缺陷去「修数据」 |
| **判据缺陷** | **0 类** —— `skills_check` 登记过的 `~` 路径误报**本轮未触发** | 本表**没有**把工具 bug 报成数据缺陷 |
| **未判定（缺输入 / 成因未定）** | **F5** ③（缺今日赢家表，exit 2）／**§5** L6 `integrity` 块疑似沿用 | 宁可标「未判定」，不猜 |
| **未跑（不得读成「默认都过了」）** | 面二 `ci/run_gates.py` 十二把、面三宿主 `kb_check` | 前者会写 `kb/l7/runs/index.jsonl` **记账（双计风险）**；见 §7 |

---

## 7. 并发与写入披露（**事实，不是推断** —— 读数要连这一节一起读）

- `kb/.work/.kb.lock` **不存在**；`kb/.work/.kb.loop-claim.json` **不存在**。**本会话未抢锁、未认领、未跑任何持锁命令、未加 `--apply`。**
- **但库确实在被别的会话写**：`kb/l7/runs/` 在 **09:07 / 09:08 / 09:08 / 09:11 / 09:13 / 09:14** 连续新增
  `20261004-09*.json`，`source=l0_daily`、`trigger=L0 对齐（每日只读）`、`verdict=未过 ｜ 真差异=2 ｜ 预期内=0`；
  `kb/.work` ＋ `kb/l7/runs` 近 10 分钟内有 **10** 个文件变动。
- **同一题目已有一份他会话产物**：`kb/l7/reports/CHK-20261004-0855-health.md`（覆盖 08:55–09:05，09:03:06 定稿）。
  我**独立复跑**后读数**逐条一致**，**唯一差异**是 ④ 段红数 **4 → 3**：它那次 ⑧ 段（工作台与服务）报红，
  我这次 ⑧ **PASS**（`workbench_4317=200`）—— 属**负载敏感的时点抖动**，不是数据差异。
- **结论不受并发影响**：① 0 / ② 0 / ⑤a 0 / ⑤b 0 / ⑥ 3-6 / ④ ②③ 与 **08:06、08:11 两次独立体检**逐项一致。
  **受并发影响的只有**：④第⑥段的红项集合（§4-F3，08:06→08:11→09:15 实测 **3 / 2 / 3 件**，是移动靶）。
- **本会话没跑**：`ci/run_gates.py`、各层 `l*_gate.py` 的**独立写档档**、`daily_health.py`、宿主 `kb_check`（均会写台账或与并发窗口冲突）。

---

## 8. 本轮写盘清单（**只这三处**）

| # | 落点 | 为什么 |
|---|---|---|
| 1 | `_chk-run-CHK-20261004-0905-CLOSE/**`（9 组 `.cmd` ＋ `.out` ＋ `.exit`） | 闸门 stdout 与**退出码**留底，逐条可回放 |
| 2 | `kb/l8/workflow_check_CHK-20261004-0905-CLOSE.json` | ④ **无干跑档**（不加参数也写）。**跑 ④ = 接受这一次写盘**（已在 §3 声明） |
| 3 | `kb/l7/reports/CHK-20261004-0905-CLOSE-health.md` ＋ 库根 `体检表-20261004-0915-逐层收口.md` | 本报告（**node 通道写 ＋ 两读者 size 读回校验**） |

**没有碰**：`kb/l0…l6` 数据、任何台账/registry、任何 skill 描述、任何飞书写入、任何判据、任何锁、任何他人的 eval 副本。

---

## 9. 复算命令（只读；cwd = 库根）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"

# —— §1 九条读数 ——
python3 .dsh/skills/kb-check/scripts/preflight.py              # 前置：输入齐不齐
sh kb/kbpy l7/scripts/skills_check.py            ; echo "①  exit=$?"
sh kb/kbpy l7/scripts/layers_check.py            ; echo "②  exit=$?"
sh kb/kbpy l7/scripts/routes_reconcile.py        ; echo "③  exit=$?  (无参 ⇒ 2，按设计拒跑)"
sh kb/kbpy l8/workflow_check.py CHK-20261004-0905-CLOSE ; echo "④ exit=$? (会写 kb/l8/)"
python3 tools/envelope_gate.py                   ; echo "⑤a exit=$?"
sh kb/kbpy l8/envelope_census.py                 ; echo "⑤b exit=$?"
sh kb/kbpy l8/projection_reconcile.py            ; echo "⑥  exit=$?  (只读)"
sh kb/kbpy l7/scripts/kb_pipeline.py --check     ; echo "逐层 exit=$?  (零写，会自证 mtime 变化 0)"

# —— §2.1 每层「最近一次真落盘」独立复算 ——
python3 - <<'PY'
import os,glob,json,time
for L in range(0,7):
    hits=[]
    for p in glob.glob(f'kb/l{L}/runs/*.json'):
        try: d=json.load(open(p,encoding='utf-8'))
        except Exception: continue
        if d.get('dry_run') is False or d.get('applied') is True: hits.append((os.path.getmtime(p),os.path.basename(p)))
    hits.sort(reverse=True)
    print(f'L{L}', time.strftime('%m-%d %H:%M',time.localtime(hits[0][0])) if hits else '无真落盘', hits[0][1] if hits else '', f'共{len(hits)}份')
PY

# —— §4-F2 的独立复算 ——
python3 -c "import hashlib;print(hashlib.sha256(open('kb/l3/candidates/rules.jsonl','rb').read()).hexdigest())"
#   期望 743dc62398311b0287e1e99fbcc438397ca8c721a0556d534cc69f3ee6eff840
python3 -c "
import json
r=[json.loads(l) for l in open('kb/l3/candidates/rules.jsonl',encoding='utf-8') if l.strip()]
print('行数',len(r),'唯一id',len({x['rule_id'] for x in r}))
print({k:sum(1 for x in r if x.get(k) not in (None,'')) for k in ('owner','effective_from','half_life_days','valid_until')})"
#   期望 1018 / 509 / 四字段非空全 0

# —— §4-F3 的独立复算（唯一可信的信封判据：两读者比 size）——
DSHBIN=$(ls -d "/Applications/DSH Desktop"*/Contents/MacOS/"DSH Desktop" | head -1)
ELECTRON_RUN_AS_NODE=1 "$DSHBIN" -e 'const fs=require("fs");console.log(fs.statSync(process.argv[1]).size)' <路径>
python3 -c "import os,sys;print(os.path.getsize(sys.argv[1]))" <路径>

# —— §5 的独立复算 ——
python3 -c "
import json,hashlib,glob,os
def blk(p): return json.dumps(json.load(open(p,encoding='utf-8')).get('integrity'),sort_keys=True)
h=hashlib.sha256(blk('kb/l6/runs/REV-20261004-0855-L6-dryrun.json').encode()).hexdigest()
n=sum(1 for p in glob.glob('kb/l6/runs/*.json') if os.path.isfile(p) and hashlib.sha256(blk(p).encode()).hexdigest()==h)
print('integrity 块逐字节相同的落章份数 =',n)"
#   期望 34

# —— §2.2 本批四层审计 ——
for R in REV-20261004-0855-L4 REV-20261004-0855-L5 REV-20261004-0855-L6 REV-20261004-0855-L7; do
  sh kb/kbpy l7/scripts/skill_invocation_audit.py --run "$R"; echo "$R exit=$?"; done
```

---

## 10. 无法验证 / 待判（**如实列出，不猜**）

1. **今天真实的路由状态** —— ③ 只能给「**03:24** 那份赢家表口径下」的 60/65；今天好不好要重跑触发电测。
2. **③ 的绿线定义**（92.3% ≥ 0.90 算过，还是「不一致须为 0」）—— **判据维护人未裁**，属**待裁**不是缺陷。
3. **那 3 件信封是「生成时就是信封」还是「拷贝时带上」** —— 全机只找到这一份 `kb-l0-feishu-fix` / `kb-check-fix` 副本，
   **没有源文件可比**，故不做推断。
4. **§5 的 L6 `integrity` 块**：是沿用还是活读数读错源 —— **两种可能都不排除**，须只读复算才能定。
5. **`kb_pipeline.py --check` 首跑 exit 143 的成因** —— 未定位（前台复跑正常），**不作推断**，该读数已作废。
6. **面二 CI 十二把、面三宿主 `kb_check`** —— 本轮**未由我自跑**（写台账 / 双计与并发窗口风险），要请**单会话窗口**另开一轮。
7. **`kb/l7/registry/l7.json` 那次原地改写是「哪一次」** —— ④③ 只证明「无 run 记录记过现 sha」，
   **未定位到具体那一次写入**，不编。
8. **「最新一批」到底指哪个 BASE** —— 盘上有三个候选（§2.0），我按「最近一次跨层调用」取 `REV-20261004-0855`。
   若你指的是别的，请点名；**但三种取法下「收口没闭上」这个结论都不变**（见 §2.0）。
