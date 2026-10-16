# 交付 · 问题数拆开（issue_count → 库内依据 ＋ 非权威候选）· 2026-10-12

改动件：`kb/l7/review-engine/core/review_engine.py`（产）｜`feishu_publish.py`、`kb/l8/review_run.sh`、`kb_api.py`（读）
｜`kb/l8/regression_run.py`、`kb/l8/workflow_smoke.py`（判据）｜登记件 `kb/l7/registry/report-output-contract.yaml`

## 0. 一句话

`issue_count` 一直是「**库内依据 ＋ 非权威候选**」混在一个数里 —— 实测素材 `RC-160a343ee259`
摘要写「共发现 **17** 处必须修改」，其中 **5 处**是源里自己写着 `authoritative: false`、
「已被 kb/l3 取代」的候选（3 条还标着 P0）。本轮把它**拆开**：新增
`candidate_count` / `authoritative_issue_count` / `issue_count_basis`，
**而 `issue_count` 的取值与三处分流行为一个字没动**。

## 1. 口径（只加不改）

| 字段 | 含义 | 取值 |
|---|---|---|
| `issue_count` | 总数 —— **契约值，语义未变** | `len(risk_items)` |
| `candidate_count` | 其中**非权威候选**（`authoritative is False`） | ≥ 0 |
| `authoritative_issue_count` | 其中**库内依据** | `issue_count − candidate_count` |
| `issue_count_basis` | 一句话把三个数写出来，人能直接读 | 如「issue_count（5）= 库内依据 3 ＋ 非权威候选 2；候选无库内条款号、只作排查线索，不构成依据」 |

判据**唯一真源** = `review_engine.is_candidate()`：判**显式 `False`**，不判「缺这个键」——
库内依据本来就没有 `authoritative` 键，把缺键当候选会把全部依据一起打成候选（⑦c 钉着）。

## 2. 为什么**不**顺手把 `issue_count` 改成「只算库内依据」

因为它是**对外契约**，三处行为按它分流：

1. `feishu_publish` 的**报告链接门槛**（PRD：问题数 <3 不建云文档）；
2. 守衡 `dual_track.mjs` 的**合并卡**；
3. PRD §5.3.3「问题数 **≥3** 只出汇总」。

改语义 = **静默改这三处行为** ⇒ 那不是「拆开」，是**另一次改动**，需 Owner 另裁。
本轮先让「真问题数」**直接读得出来**（不必让读者自己去减），语义变更留给裁量（见 §6）。

## 3. 谁读它（新字段不许躺在 JSON 里当注释）

| 读方 | 读成什么 |
|---|---|
| `feishu_publish.render` | 报告「完整清单（N 条，其中**非权威候选 M 条**）」；**缺键时回落现算** `is_candidate`（给存量 JSON 用，不是第二口径）；无候选时**不加噪音**（仍是「（N 条）」） |
| `kb/l8/review_run.sh` | 旁挂 `kb/.work/last_review_result.json` 加这两个字段（供守衡侧取用）；**取不到记 `None` 不记 0** |
| `kb_api.py` | 顶层三项 ＋ 逐条 `authoritative` / `superseded_by`（原先**整条抹平** ⇒ 调用方分不出候选） |
| `kb/l8/regression_run.py` | 每条 case 记 `candidate_n` / `authoritative_n`，跑批收尾打合计 —— **真实占比的唯一读数** |

★ **本库不代改守衡的卡**：它要显示这一行得改它自己；本库只保证取值可达。

## 4. 判据（含反向对照）

| 判据 | 内容 | 读数 |
|---|---|---|
| 引擎测试 `CandidateAuthorityTests` **c6/c7/c8** | c6 `issue_count` 仍 = 条目总数；c7 拆解只数显式声明（3 库内＋2 候选 ⇒ 5/2/3）；**c8 反向对照**：把候选声明改成权威 ⇒ 拆解**必须跟着动**（2/1/1 → 2/0/2），全候选也不许把 `issue_count` 改成 0 | 引擎 `pytest` **89 passed** |
| `regression_run.py --selftest` **⑦a/⑦b/⑦c** | ⑦b 反向对照：声明改权威 ⇒ 候选归零；⑦c 缺键**不算**候选 | **13/13** |
| `workflow_smoke.py` **S1 ＋ R6a/R6b/R6c** | S1 把两个字段纳入**旁挂契约**；R6 两方向都喂：生效时刻**之后**缺字段 ⇒ **必须红**；**之前**缺字段 ⇒ **不许红** | 冒烟 rc=0 ｜ 反向对照 **8/0** |

### ★ 踩坑一：契约加字段当场把 S1 判红（= 会影响工作流）

第一版把两个字段**无条件**加进 `SIDECAR_REQUIRED_NORMAL` ⇒ 盘上那份旁挂是**改动前**写的 ⇒ S1 红。
而 S1 红的后果不只是报错：`batch_scan.py` / `bitable_stats.py` 都调本件，**红了挡日更写库**
—— 那正是「改动影响了工作流」。
⇒ 改成**带生效时刻**（`_SPLIT_SINCE`）：只对**写于本改动之后**的旁挂要求，下一次真评审写新旁挂时
**自动生效、窗口自己关闭**；R6c 专门钉住「不追溯」这一半。

## 5. ★ 顺带查出并修掉**我自己跑手**的一个缺陷（本轮最重要的意外收获）

复核拆解读数时发现：本次跑批 100 条里 **10 条**报出 `orphan_non_p3` / `unbacked` 的差异
（`orphan_non_p3` 0→10 条 case、`unbacked` 22→29 条 case），而**三态、`issue_count`、`items_n` 一条都没变**。

### 根因（证据链完整）

1. `regression_run.run_case` 默认写/读**同一份** `kb/.work/_regression_findings_cache.json`，
   且读的时候是 `json.loads(...)` **裸读**、**不验 `text_sha256`**（`regression_run.py:172`）；
2. 同一时段**另一个跑批也在跑**：实测 `kb/.work/regression-SCOPE-BEFORE-20261012.jsonl`
   13:15:00 落盘（我当时那条 pid 11425 的引擎子进程正用着**同一个缓存路径**），
   而我这次跑批是 13:05–13:13 ⇒ **窗口重叠**；
3. ⇒ 缓存里躺着**另一条文案**的依据，而本跑手照单全收 ⇒ 把别人的依据算成本条的
   `orphan`/`unbacked`（三态与条目数来自各自子进程的 stdout，所以没被污染）；
4. **复现**：把同两条 case 单独重跑（独占缓存路径）⇒ 立刻回到 `ev=5 / orphan=0 / unbacked=0`，
   两次一致（确定性）；即那次差异是**污染**，不是引擎行为变了。

★ 而引擎**早就防住了**这一手：`evidence_cache.read_cache()` 带 `text_sha256` 校验，
它的报错原文逐字是「**拒绝复用，否则会把另一条文案的依据算到这条上**」
—— **是本跑手绕过了那把锁**。（同因不同处：又一次证明「口径只有一处」这条纪律的价值。）

### 修法（两层，缺一不可）

① **每条 case 一个独占的临时缓存路径** ⇒ 并发跑批、同 RUN 内前后条目**都不可能互相踩**；
② 证据侧改走引擎那把**带校验**的读法；校验不过 ⇒ `evidence_probe ∈ {rejected/unavailable/error}`，
   并且 `orphan_*` / `unbacked_*` / `evidence_n` 一律记 **None（未测）** —— **fail-closed，不 fail-open**。

判据：`regression_run.py --selftest` **⑧a/⑧b/⑧c** —— ⑧a 缓存是这一条 ⇒ 正常读；**⑧b 反向对照**：
缓存属于另一条文案 ⇒ **必须拒绝**（报错里含「不符」）；⑧c 钉住 `run_case` 确实走那把带校验的读法。

> 影响边界（照实说）：这次污染**只影响诊断计数**（`orphan`/`unbacked`），
> **不影响**三态、`issue_count`、回归基线闸门（闸门读的是三态）。
> 但「把另一条素材的依据算到这条上」这件事本身是**结论级**的错误类型 —— 早发现比晚发现好。
>
> **留档**：被污染的那份产物**没删**，原样留在 `kb/.work/regression-20261012-candsplit.jsonl`
> （13:13，10 条假差异的原始证据）；干净的那份是 `kb/.work/regression-20261012-candsplit2.jsonl`
> （13:23，本交付件所有读数都取自它，也是回归闸门当前取件的那一份）。

## 6. 待裁（我给了推荐，但需要 Owner 一句话）

1. **`issue_count` 要不要改成「只算库内依据」**？改了会同时改报告门槛 / 守衡卡 / PRD §5.3.3 分流。
2. **非权威候选要不要参与三态判定**？（现在**参与**，但已被就地标注）
   → 这两条都登记在 `kb/l7/registry/report-output-contract.yaml::split_issue_count_20261012.open_questions`。

## 7. 影响面（100 条回归集实测；用修好后的跑手重跑一遍）

| 比对 | 结果 |
|---|---|
| 改动前后逐字段比对（除 `elapsed_s`） | **只有三个新增字段不同**（`candidate_n`/`authoritative_n`/`evidence_probe`，改动前根本没有这三个键）；其余字段 —— 含三态 `got`、`issue_count`、`items_n`、`orphan_p3_n`、`orphan_non_p3`、`unbacked_n` —— **100 条全同，差异条数合计 0** |
| 自洽 | `authoritative_n + candidate_n == items_n` **100/100 成立** |
| **真实读数（这就是拆开的意义）** | 候选命中合计 **9 条**，落在 **5 条 case** 里；其中 `RC-160a343ee259` = **5 / 17** —— 正是当初暴露这个问题的**那一条素材**，现在在机读记录里直接看得见 |
| 回归基线闸门 | **GREEN**（与基线 solid 80 条逐条一致）；**未重采基线**（差异为空） |

## 8. 尺子读数（本批改动后实测）

| 尺子 | 读数 |
|---|---|
| 引擎 `pytest` | **89 passed**（c6/c7/c8 是新增） |
| `regression_run.py --selftest` | **13/13**（⑦a–c、⑧a–c 是新增） |
| `workflow_smoke.py` / `--selftest` | rc=0（S1 绿且打出「拆分字段」读数）｜ 反向对照 **8/0**（R6a–c 是新增） |
| `l5_gate` / `matcher --selftest` / `l5_report --selftest` | rc=0 ｜ 正例 18/负例 13 ｜ 4/4 |
| `p0_fastpath --selftest` / `watch_review_readiness --selftest` | 32/0 ｜ 87/0 |
| `envelope_census` / `check_source_readonly` / `check_agents_md_drift` | OK / rc=0 / rc=0 |
| `regression_gate` / `--selftest` | GREEN ｜ rc=0 |
