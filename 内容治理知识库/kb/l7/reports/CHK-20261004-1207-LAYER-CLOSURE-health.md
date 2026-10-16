# 知识库统一闸门 · 逐层收口体检 · 2026-10-04 12:07

- **run_id**：`CHK-20261004-1207-LAYER-CLOSURE`
- **本次库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **档位**：**体检档**（六道闸门一次性跑完）—— 不是评审循环的 L7 档
- **被核的「最新一批」**：`RT-20261004-1133-LISTING`（L4 `11:37:36` → L5 `11:41:17` → L6 `11:50:07` → L7 `11:50:11`）
  —— 由 `kb/l4..l7/runs/RT-20261004-1133-LISTING-*.json` 的 `at` 字段与 mtime 认出来，**不是用户指定的 RUN**
- **本 skill 只报不改**：真坏项交 `kb-repair`，本表未修改任何数据
- **本次声明会写盘的两道**：门④ `kb/l8/workflow_check_RT-20261004-1133-LISTING.json`（已写入）；
  门⑥ `projection_reconcile.py` **没带 `--json-out` ⇒ 只读**（读代码确认：`json.dump` 只在 `a.json_out` 非空时执行，`kb/l8/projection_reconcile.py:266-267`）

---

## 0. 一句话结论

**有层没闭上，共 2 处真红 + 1 处跑不了：**

1. **L0 未闭上** —— 本层闸门红（真差异 2：两张表拉取失败，且**未在预期差异里声明**）；
2. **装载位 `kb/view` 未闭上** —— 权威库的 rules 在视图生成后变过，509 条条目的规则已漂移、2036 处治理字段没传导；
3. **门③ 路由对账跑不了** —— 赢家表缺失（缺输入 exit 2，**不是**「65 条全不一致」）。

另外一件**不是红、但必须说清**的事：`RT-20261004-1133-LISTING` 的 L4/L5/L6 **四层全是预演（dry_run=true / applied=false）**，
层侧没有一条非预演落章 ⇒ 这批只证明了「逐层调用机制通了」，**不构成「这些层真落盘过」的证据**（门④ 的 E5 黄）。

---

## 1. 逐层收口表（主表）

口径：`本层闸门` = `kb/kbpy l7/scripts/kb_pipeline.py --check`（零写档）的逐层行；
`基线指纹` = `kb/kbpy l8/workflow_check.py` 第 ② 段（冻结基线 = **2026-09-23**）；
`产物哈希` = 同脚本第 ③ 段（45 项，基线同为 **2026-09-23**）；
`评审链收口` = `kb/kbpy l7/scripts/skill_invocation_audit.py --run RT-20261004-1133-LISTING-<层>`。

| 层 | 本层闸门 | 基线指纹（09-23） | 产物哈希（09-23） | 评审链收口（本批） | 收口判定 |
|---|---|---|---|---|---|
| **L0** | ❌ **未过 exit=1** | ✅ 树指纹 `bd36cbb89dedb48f` 与基线一致（4007 文件） | — | 不适用（评审链从 L4 起跑） | **❌ 未闭** |
| L1 | ✅ 过 exit=0 | ✅ `099ad8afdc1a0be2` 一致（3152 文件） | — | 不适用 | ✅ 闭 |
| L2 | ✅ 过 exit=0 | ✅ `183f6265c0666688` 一致（887 文件） | — | 不适用 | ✅ 闭 |
| L3 | ✅ 过 exit=0 | ⚠️ **不符**：现 `l3_lines=1018`；首 1018 行 ≠ L6 记录、全 1527 行 ≠ L4 记录 | ❌ `kb/l3/candidates/rules.jsonl` 变了 | 不适用 | ⚠️ **基线漂移，需人确认** |
| L4 | ✅ 过 exit=0 | — | ❌ `kb/l4/registry/l4.json` 变了 | ✅ 过 ｜ 红 0 ｜ **黄 1（E5 预演）** | ⚠️ **机制闭，落盘未闭** |
| L5 | ✅ 过 exit=0 | — | ❌ `l5/registry/l5.json`、`l5/benchmark.json` 变了 | ✅ 过 ｜ 红 0 ｜ **黄 1（E5 预演）** | ⚠️ **机制闭，落盘未闭** |
| L6 | ✅ 过 exit=0 | — | ❌ **15 项全变**（bm25 / vectors / index / registry / retriever / selftest / benchmark） | ✅ 过 ｜ 红 0 ｜ **黄 1（E5 预演）** | ⚠️ **机制闭，落盘未闭** |
| L7 | ✅ 过 exit=0 | — | ❌ `l7/registry/l7.json`、`kb-content-review/SKILL.md`、`scripts/review.py` 变了 | ✅ 过 ｜ 红 0 ｜ 黄 0（跨层闸门豁免） | ⚠️ **机制闭，落盘未闭** |

**跨层（不属于任何单层，但决定「层与层之间闭上没有」）**

| 对象 | 状态 | 证据 |
|---|---|---|
| **装载位 `kb/view` ⇄ 权威库** | ❌ **未闭** | 门⑥ exit 1：R1 源 rules `f27a14091b2bd782… → 743dc62398311b02…`；R2 509 条条目规则已变；R4 2036 处治理字段未传导（owner/half_life_days/valid_until/effective_from 各 509） |
| **L3 ⇄ L4/L6 行级指纹** | ⚠️ 不符 | 门④ 第②段 `l3_base1018_matches_L6=false`、`l3_whole1527_matches_L4=false` |
| **L4→L7 逐层调用机制** | ✅ 通 | 四层 `skill_invocation_audit` 全 exit 0、红 0（L4/L5/L6 各带 1 条 E5 黄） |
| **层产物可读性（信封）** | ✅ 活路径干净 | 门⑤a 1985 文件信封 0；门⑤b 10394 md 中 1079 信封态**全部已分类**（569 刻意归档 + 510 可再生备份） |

---

## 2. 统一闸门六道（体检档）

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `kb/kbpy l7/scripts/skills_check.py` | **0** | 过 | 五类问题 `1=0 2=0 3=0 4=0 5=0`；本项目要用 40 个、已装 40 个、还差 0；62 条未登记 selftest 属单列（不算错误） |
| ② | 层契约 | `kb/kbpy l7/scripts/layers_check.py` | **0** | 过 | 六类问题全 0；L0–L7 八层齐；DAG 非线形（L7 ← L0/L3/L4/L5/L6） |
| ③ | 路由表对账 | `kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | **跑不了（缺输入）** | `kb/l7/reports/` 下无 `*routes-winners*` 文件；脚本原话：「赢家表是**触发评测的运行时产物**，不是静态资产；缺输入时本闸门**不得报绿**」。**缺输入 ≠ 数据坏** |
| ④ | 链路收口 | `kb/kbpy l8/workflow_check.py RT-20261004-1133-LISTING` | **1** | **混合**（见 §2.1） | 9 段：PASS ①④⑤⑦⑧⑨ ｜ FAIL ②③⑥。装载位 509 条 / 信封 0 / 健康分 79.2 / 检索 `[111, 1, 509, 0]` |
| ⑤a | 信封闸门（.py/.txt/.md） | `python3 tools/envelope_gate.py` | **0** | 过 | 扫 1985 文件：正常 1985 ｜ 信封态 **0** ｜ 读不到 0；两读者交叉核对一致 |
| ⑤b | 信封普查（只扫 .md） | `kb/kbpy l8/envelope_census.py` | **0** | 过（数字大但已分类） | 扫 10394 md，1079 个 node 侧读不到：569 刻意归档 + 510 可再生备份，**未分类 0** |
| ⑥ | 投影一致性 | `kb/kbpy l8/projection_reconcile.py` | **1** | **真坏** | 3/6 通过；漂移 R1 / R2 / R4；`R3_id_set` `R5_manifest_bytes` `R6_tier_dir` ✅ |

### 2.1 门④ 三个红段的定性（逐段，不合并说）

| 段 | 判据 | 本次实测 | 定性 |
|---|---|---|---|
| ② 权威库 l0~l6 未被改动 | l0/l1/l2 树指纹 + L3 行级指纹对 **09-23 基线** | l0/l1/l2 **全一致**；L3 三项不符（1018 行 vs 基线 1527 行） | **合法变红为主**（活库 11 天必漂移）＋ **L3 需人确认一处**：文件从 1527 行变 1018 行，方向是**变少**，本闸门**判不出**是「重建」还是「丢数据」 |
| ③ 前序产物哈希（45 项） | 45 项产物对 **09-23 记录**逐项 sha256 | **20 项不符**（清单见 §4） | **合法变红**：基线是 09-23，库此后一直在动；本段只能报「变了」，**不能报「坏了」** |
| ⑥ 文档可见性 | 工作区 md 是否被宿主读得到 | 6289 md，512 信封态：**510** `.work/hostlib.bak-*`（门⑤b 已归类为「可再生的过期备份」）＋ **2** `_eval-L0L7-gap-20261003/kb-{l0-feishu,check}-fix/SKILL.md`（**未分类**） | **已知条件 + 2 个待分类**：510 个备份不影响任何读取方；那 2 个在评测沙箱目录里，建议归入已分类桶 |

> ⚠️ **纪律**：门④ 的第②③段是**冻结基线**判据，活库变红**合法**（见 `references/gotchas.md`）。
> 不许把这两段当「数据被改坏」往上报；要判「坏没坏」看**消费侧**（门④ 第④⑤⑦段 + 门① ② ⑤ ⑥）。

---

## 3. 失败项清单 —— 对象 / 原因码 / 要人做什么 / 复开条件

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| **L0 闸门**（`kb/l7/scripts/l0_gate.py`） | `L0_FETCH_FAIL` | 查**专家修订汇总表 `tbl8AI00JZO1iZtp`** 与**内容公式（仅供参考）`tblVdl0jdK9G4ld3`** 为什么拉不下来（权限回落？表被改？bot 身份？）。二选一：修好拉取，或按 `l0-expected-diffs.yaml` 的纪律补一份**带 `evidence` + `owner_action` 的预期差异声明** | 真差异 = 0 ⇒ exit 0。注：`l0-expected-diffs.yaml` 的 `latest_run`（2026-10-03 22:2x）记的是「拉取失败 0」⇒ 本次是**回退**，不是常态 |
| **装载位 `kb/view`** | `PROJECTION_DRIFT` | 重跑 `kb/.work/gen-host-library.py` 到 staging 后**回填**（这是脚本自己给的修法），把权威库当前 rules（`743dc62398311b02…`）与 4 个治理字段传进视图 | 门⑥ exit 0（R1/R2/R4 转 ✅）。**在此之前 `kb_*` 工具读到的是 509 条陈旧条目** |
| **门③ 输入** | `MISSING_INPUT` | 按 `kb-manage` 的触发电测重新生成 `<RUN>-routes-winners.json` 放进 `kb/l7/reports/`（全库没有任何脚本会自动生成它） | 文件存在且格式可解析 ⇒ 重跑门③ 得 exit 0 |
| **门④ 第②段 L3 行数** | `BASELINE_DRIFT`（待裁） | 确认 L3 从 1527 行 → 1018 行是**有意重建**（`kb/l3/candidates/rules.jsonl` mtime 10-02 22:45，`kb/.work/l3_stats.json` 记 rules=1018，与该文件行数**自洽**）还是异常丢失 | 人工确认为重建 ⇒ 更新冻结基线；确认丢了 ⇒ 交 `kb-repair` / 从 `kb/l3/_archive/` 捞 |
| **门④ 第③段 20 项产物** | `BASELINE_DRIFT` | 确认这批漂移就是「最新一批重跑 L4/L5/L6」造成的 | 人工确认后更新冻结基线即可 |
| **门④ 第⑥段 2 个未分类信封** | `UNCLASSIFIED_ENVELOPE` | 把 `_eval-L0L7-gap-20261003/` 下 2 个 `SKILL.md` 归入「刻意归档」或删（删要先报批） | 信封桶未分类数 = 0 |

---

## 4. 门④ 第③段漂移清单（20 项，全列，不摘要）

```
kb/l3/candidates/rules.jsonl
kb/l4/registry/l4.json
kb/l5/registry/l5.json
kb/l5/benchmark.json
kb/l6/runs/build_runs.jsonl
kb/l6/bm25/docs.jsonl
kb/l6/bm25/meta.json
kb/l6/bm25/postings_zh.jsonl
kb/l6/bm25/postings_en.jsonl
kb/l6/vectors/vectors.jsonl
kb/l6/vectors/matrix.npy
kb/l6/vectors/meta.json
kb/l6/index/l6.jsonl
kb/l6/registry/l6.json
kb/l6/retriever.py
kb/l6/selftest.json
kb/l6/benchmark.json
kb/l7/skills/kb-content-review/SKILL.md
kb/l7/registry/l7.json
kb/l7/skills/kb-content-review/scripts/review.py
```

---

## 5. 本表**没有**判定的东西（免得被读成「都过了」）

1. **门③ 路由对账**：**没跑**（缺输入）。所以「routes.yaml ↔ 实际接单」这件事，本次**一无所知**，不是「过」。
2. **L0–L3 供给链有没有真跑**：本次只核了**闸门**，没核「这批数据是谁写的」。`kb_pipeline.py --check` 是零写档（4001 个产物 mtime 快照变化 **0** 个），它证明的是**只读体检没写坏库**，不是「层跑过了」。
3. **评审结论本身对不对**：本表只核**收口与闸门**，不评 `rv-*` 三态判定质量（那走 `审查流程评测`）。

---

## 6. 需要人裁决的两件事

1. **L3 从 1527 行变 1018 行** —— 我**判不了**是重建还是丢数据（§3 第 4 行）。库内 `l3_stats.json` 与文件行数自洽、且 `_archive/` 有 33 个归档件，**倾向于「有意重建」**，但这是**推测**，不是结论。
2. **门④ 第②③段要不要更新冻结基线** —— 基线是 **2026-09-23** 的，到今天 11 天。按库纪律「不许为了变绿改判据」，更新基线要人点头；不更新则这两段会**长期红**，日报会天天报同一个红（`l0-expected-diffs.yaml` 开头正是为这个问题写的）。

---

## 7. 并发与重复劳动的提示（本库有前科，见 AGENTS 的并发纪律）

- 本次跑闸门期间（12:02–12:10）**另有多条会话在跑同一批闸门**：`ps` 实测 12:02 有 11 个相关进程
  （`skills_check.py` / `envelope_census.py` / `l1_status.py` / `l2_status.py` / `l2_split_run.py` 各若干）。
- `kb/l7/reports/` 在 12:00–12:10 之间被别的会话写进了 `CHK-20261004-1158-health.md`、`CHK-20261004-1159-HEALTH.md`、
  `CHK-20261004-1203-SUB-health.md`、`CHK-20261004-1205-health.md`、`CHK-20261004-1206-health.md`、
  `CHK-20261004-1210-REG-LAY-ROUTES-health.md`，`kb/l8/` 里另有多份 `workflow_check_CHK-20261004-12*`。
  ⇒ **用户很可能会收到好几份内容相近的体检表**，请以一份为准。
- **本次没有认领循环槽**（`kb_loop_claim.py status` 实测「无认领」）：理由是 `kb-check` 体检档**不碰**循环的共享写资源
  （`kb/.work/.kb.lock` 全程不存在、未写 `kb/l7/runs/index.jsonl`、未跑 `--apply`），
  反过来**认领会把正在跑的其他会话挡在 exit 3**。⇒ 这是**有意不认领**，不是忘了。

---

## 8. 「层已跑完」类结论的 run_id 与时间戳（本库存在并发写入者，必须带）

| 结论 | run_id | 时间戳 | 依据文件 |
|---|---|---|---|
| 最新一批 = RT-20261004-1133-LISTING | `RT-20261004-1133-LISTING-L4/L5/L6/L7` | `11:37:36` / `11:41:17` / `11:50:07` / `11:50:11` | `kb/l4..l7/runs/RT-20261004-1133-LISTING-*.json` |
| 逐层闸门 | `--check`（自带 run 名 `20261004-1150` 同款工具） | `2026-10-04 12:0x` 本次实跑 | 会话输出（零写自证：4001 产物 mtime 变化 0） |
| 链路收口 | `RT-20261004-1133-LISTING` | `2026-10-04 12:05:12` | `kb/l8/workflow_check_RT-20261004-1133-LISTING.json` |
| L0 闸门 | `l0_gate.py --json` | `2026-10-04 12:0x` 本次实跑 | 会话输出（真差异 2） |
| 投影一致性 | `projection_reconcile.py`（无 run 概念、只读） | `2026-10-04 12:0x` 本次实跑 | 会话输出 |
