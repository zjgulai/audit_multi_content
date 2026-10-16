# L4 层执行留痕 · RUN=RT-20261005-PLAYARD-VIDEO-L4

- 层：L4（定稿与发布层）
- RUN：`RT-20261005-PLAYARD-VIDEO-L4`（未改名）
- 档位：**预演档 / 只读**（全程未加 `--apply`、未加 `--write-gate`、未加 `--allow-beyond-policy`）
- 执行时间：2026-10-05 10:40 → 10:41:42（预演落章件最后一次写入时刻；本机时区）

## exit_code 逐条

| # | 命令 | exit_code |
|---|---|---|
| 3 | `sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L4 --gate-only --run RT-20261005-PLAYARD-VIDEO-L4` | **0** |
| 4-1 | `sh kb/kbpy .work/l4_ledger_repair.py RT-20261005-PLAYARD-VIDEO-L4` | **3** |
| 4-2 | `sh kb/kbpy .work/l4_article.py RT-20261005-PLAYARD-VIDEO-L4` | **0** |
| 4-3 | `sh kb/kbpy .work/fix_l4_repromote.py --run RT-20261005-PLAYARD-VIDEO-L4` | **0** |
| 4-4 | `sh kb/kbpy .work/l4_integrity.py RT-20261005-PLAYARD-VIDEO-L4` | **1** |
| 4-5 | `sh kb/kbpy .work/l4_report.py RT-20261005-PLAYARD-VIDEO-L4 --skill kb-canonical-lookup` | **0** |

第 3 步编排器 stdout 另有一行落章结果：`[L4] 落章引擎 exit=0 ｜ 产物变化 0 个`。

### 各引擎前 20 行要点（原文摘录）

**4-1 `l4_ledger_repair.py` → exit 3**（脚本自带的 fail-closed 拒绝，非崩溃）

```
[dry-run] l4_ledger_repair.py 未落盘。
现库台账 run_id=daily-20261005-0957-L4｜issued 段 ['E-1', 'E-2', 'S-1', 'W-1', 'W-2', 'W-3']
归档台账 scheme_version=article-no-2｜issued 段 ['E-1', 'S-1', 'W-1', 'W-2', 'W-3']｜assignments 1242
现库 canonical：1365 行
逐号对账：一致 1242｜不符 0｜归档查不到 123
★逐号对账不通过 → 拒绝落盘（归档不是现库的正确台账，不得用它修复）
```

**4-2 `l4_article.py` → exit 0**（干跑：算完打印差异再退出）

```
首次分配 0 条｜沿用台账 1365 条｜分段：{'E-1': 375, 'E-2': 123, 'S-1': 201, 'W-1': 56, 'W-2': 453, 'W-3': 157}
[dry-run] —— 差异（未落盘）——
```

**4-3 `fix_l4_repromote.py` → exit 0**（预演；判据 8/9 通过）

```
判据: 8/9 通过 {'C1_article_no_unique': True, 'C2_cite_triple_complete': True, 'C3_body_nonempty': True,
 'C4_verbatim_with_candidates': True, 'C5_evidence_resolvable': True, 'C6_evidence_rule_eligible': True,
 'C7_kb_version_v0': True, 'C8_idempotent': True, 'C9_no_field_regression': False}
★ 判据未全过：C9_no_field_regression
[dry-run] 预演 → kb/l4/runs/RT-20261005-PLAYARD-VIDEO-L4-canonical-dryrun.json（**未写** canonical、**未写** registry）
```

C9 报的字段回退（原文摘录，5 个形态全中）：

```
clause                 baseline_date（键消失）  × 123 条
clause                 never_resets_on_regeneration（键消失）  × 123 条
sample_case            baseline_date（键消失）  × 358 条
sample_case            never_resets_on_regeneration（键消失）  × 358 条
scoped_clause          baseline_date（键消失）  × 375 条
scoped_clause          never_resets_on_regeneration（键消失）  × 375 条
wording_entry          baseline_date（键消失）  × 56 条
wording_entry          never_resets_on_regeneration（键消失）  × 56 条
wording_revision_pair  baseline_date（键消失）  × 453 条
wording_revision_pair  never_resets_on_regeneration（键消失）  × 453 条
```

**4-4 `l4_integrity.py` → exit 1**（6 项 + 2 项附加；PASS 5 / FAIL 3）

```
[PASS] frozen_layers        kb/l0|l1|l2 三层 tree_sha256 与 L5 基线一致=True
[FAIL] l3_append_only       行数 1018 → 1018｜追加 0 行｜前 1018 行逐字节未变=True（哈希 743dc62398311b02，与 L6 存档一致=False）
[FAIL] article_numbers      509/509 条有条款号｜分段 {"W-1": [56, "1~56"], "W-2": [453, "1~453"]}
[PASS] reproducible         重跑追加 0 行｜映射一致=True｜变更文件 无
[PASS] canonical_state      kb/l4/canonical/rules.jsonl 0 字节
[PASS] version_discipline   versions 行 0｜kb_version ['v0']
[FAIL] ledger_coverage      台账 1365 个号码｜各段 next_seq 正确=True
[PASS] article_no_is_not_version  发布/冻结字段命中全 0｜status {'provisional': 509}
```

**4-5 `l4_report.py` → exit 0**（落章引擎；第 3 步已跑过一次，本次为第 2、3 次，用于确认幂等）

```
[dry-run] 预演台账 → kb/l4/runs/RT-20261005-PLAYARD-VIDEO-L4-dryrun.json（顶层 skill=kb-canonical-lookup）；
          **未写** .report.md / .ops.log（那是真档的留痕）
[dry-run] 要真落盘：加 --apply（本轮未加）
run verdict = FAIL
```

幂等实测（第 3 次调用前后对比同一份 dryrun 件）：

```
exit=0
sha_before=a558b7a0b860da20bf894969a34ce0fe23fc1d8253de73c0efe96e502927feb3
sha_after =43fde64ff3b982a7dd51376cc1cf2c468ae031226977be44aa800c138a78280b
mtime: Oct  5 10:41:13 2026 -> Oct  5 10:41:42 2026
diff（忽略 finished_at）→ 无差异 ⇒ IDEMPOTENT：除 finished_at 时间戳外逐字节一致
```

## stamp

`stamp: kb/l4/runs/RT-20261005-PLAYARD-VIDEO-L4-dryrun.json`
（76752 字节｜mtime 2026-10-05 10:41:42｜sha256 `43fde64ff3b982a7…`）

第 5 步要求的顶层字段**原值**（逐字抄自该文件，未改写）：

```
run_id          = "RT-20261005-PLAYARD-VIDEO-L4"
skill           = "kb-canonical-lookup"
skill_source    = "--skill 参数（调用者读 layers.yaml 本层 skill: 后传入；本脚本不硬编码）"
dry_run         = true
applied         = false
pipeline_run_id = null
verdict         = "FAIL"
```

- **`skill == "kb-canonical-lookup"` 已确认**，且三方一致：
  ① 第 1 步用 **skill 工具**实际加载的 `kb-canonical-lookup`；
  ② `kb/l7/registry/layers.yaml` L4 段第 294 行 `skill: [kb-canonical-lookup]`（唯一真源，未从他处手抄）；
  ③ 本落章件顶层 `skill` 字段（由执行本层的进程写入）。
- 同 RUN 另有一份**另一个引擎**的预演件：`kb/l4/runs/RT-20261005-PLAYARD-VIDEO-L4-canonical-dryrun.json`
  （3358 字节｜mtime 10:41:15｜sha256 `895ec07a372341e8…`），来自 `fix_l4_repromote.py`，
  命名与 `l4_report.py` 的那份刻意区分（`layers.yaml` L4 段第 313-314 行写明）。

## gate

闸门那一行 stdout 原文（第 3 步）：

```
[L4] 闸门：过 ｜ exit=0 ｜ 退出码：0
```

同一份输出的另两行原文：

```
[写档闸门] **未带 --write-gate 凭据** → 本次按「各层只许只读档」对待；层引擎不得带 --apply。凭据表见 kb/l7/registry/write-gate.yaml
[L4] --skill 透传：l4_report.py RT-20261005-PLAYARD-VIDEO-L4 --skill kb-canonical-lookup ［预演档：未获本层写档凭据］
```

以及编排器自己的结论行：

```
run verdict = FAIL
[记账] --gate-only：本次**不写** kb/l7/runs/（只过闸门 + 持锁/释放）
结论：L4 全部走完（预演（不带 --apply））
```

**解码结论：闸门过（exit=0）；落章引擎 exit=0；但落章件内部 `verdict = FAIL`—— 两处口径不一致，见下节。**

## 需要如实登记的异常（不影响「闸门过」，但必须可见）

1. **`verdict=FAIL` 是已登记的判据漂移，不是数据坏了，也不是本次执行引入的。**
   `l4_integrity.py` 的三条红（`l3_append_only` / `article_numbers` / `ledger_coverage`）
   来自判据里写死的旧批次常量（`509` / `BASE_SHA16` / 已废止的 `FORM_BLOCK`，且只读 `rules.jsonl`
   首块、看不见 E-2）。依据：`kb/l7/registry/layers.yaml` L4 段 notes（第 316 行，2026-10-03 实测修正）
   与 `kb/l7/registry/l4-known-drift.yaml`。**本次未去「修数据」，也未改判据。**
2. **与登记文件的差异（如实登记）**：`l4-known-drift.yaml` 在 `measured_at: 2026-10-01 16:53:04` 记的是
   **5 项红**（`frozen_layers` / `l3_append_only` / `article_numbers` / `reproducible` / `ledger_coverage`）；
   本次（2026-10-05）实测红的是 **3 项**，`frozen_layers` 与 `reproducible` 均 **PASS**。
   即登记口径晚于实测时点、已部分过期 —— 只登记事实，**不据此改登记文件**。
3. **C9 报的字段与批次6 登记的不同**：批次6（`layers.yaml` L4 段第 371-375 行）记 C9 因
   `owner` / `effective_from` / `half_life_days` / `valid_until` 而不过；本次实测 C9 报的是
   `baseline_date` 与 `never_resets_on_regeneration` **两个键会消失**，5 个形态全中。
   字段集合不一致，按实测登记；**未放开 C9、未改数据**。
4. **`l4_ledger_repair.py` exit 3（逐号对账不通过 → 拒绝落盘）**：归档台账（1242）不含现库 canonical
   已发号的 E-2 那 123 条。这是脚本自身的 fail-closed 拒绝，**非零退出不算失败**（派单原话），
   未加任何开关绕过、未改台账。
5. **`pipeline_run_id = null`**：落章件里该字段确实为空（本次 `--gate-only` 未传 pipeline run id），
   是如实取值，不是读错或字段缺失。
6. **`kb/l7/runs/index.jsonl` 本层未写**：`grep -c "RT-20261005-PLAYARD-VIDEO-L4" kb/l7/runs/index.jsonl` = **0**
   —— `--gate-only` 按设计不记账（stdout 原文：`本次**不写** kb/l7/runs/`）。同文件 10:39 / 10:41 的三行
   其 `source` 为 `daily_health`、`commands` 为 `kb_pipeline.py --check`；本层本次所有命令**均不含 `--check`**。
   （说明：我只能给出「命令列表不含 --check」与「RUN id 0 命中」两项事实，无法从文件本身证明写者身份。）
7. **锁：本次零冲突** —— stdout `锁：已持锁 pid=74995 run_id=RT-20261005-PLAYARD-VIDEO-L4`，
   未出现 `exit 2`、未等待重试、未撬锁、未删 `kb/.work/.kb.lock`。
   （`kb/.work/.kb-loop-claim.json` 显示父会话 `dsh-video-playard-review` 持有 `RT-20261005-PLAYARD-VIDEO`
   的会话级认领，本层未触碰认领文件。）

## blockers

`blockers: 无`

- 无锁冲突、无命令崩溃、无因权限/环境导致的跳过。
- 上面 7 条是**需要父会话知晓的口径差异与归属说明**，不构成阻断：
  闸门过、5 个引擎全部按声明跑过、落章件 `skill` 字段三方一致。

## skill_loaded

`skill_loaded: kb-canonical-lookup`

**用 skill 工具真加载**（不是「知道有这个名字」）：调用返回了该 skill 的完整正文
（`/Users/lute/.dsh/skills/kb-canonical-lookup`，含让位表 §1、数据位置 §2、红线 §3、写档档位 §4）。
skill 名取自 `kb/l7/registry/layers.yaml` L4 段 `skill:` 字段（唯一真源，未从别处手抄）。

按正文行事：本层本次**只走查询档 / 只读**。正文 §4 的写档三条件
（① 由 `kb-pipeline` 以层身份调用 ② 带 `--apply` ③ 人开闸）—— ② 与 ③ 本次均不满足，
故全程未加 `--apply`，也未调用 `kb/.work/l4_article.py` 的写档路径。
（本条为 agent 自述档；「真的加载了」的机器侧证据见上 §stamp 的 `skill` 字段。）

## 本层 engine 清单（取自 `layers.yaml` L4 段，未手抄）

`kb/l7/registry/layers.yaml` 第 300-317 行 `engine:` 共 **5** 个：

1. `kb/.work/l4_ledger_repair.py`
2. `kb/.work/l4_article.py`
3. `kb/.work/fix_l4_repromote.py`
4. `kb/.work/l4_integrity.py`
5. `kb/.work/l4_report.py`

与编排器 stdout 的 `[层表核对] STAMP_SPEC 7 条全部能在 layers.yaml 本层 engine: 里找到 ✅`
以及 `[L4] via-skill：引擎交给 kb-canonical-lookup` 下列出的 5 条逐一对应。

## 边界声明

- 本次**只读 / 预演**：全程未加 `--apply` / `--write-gate` / `--allow-beyond-policy`；
  未改 `kb/l0`–`kb/l7` 任何**数据**文件（未动 canonical、未动 L3 候选、未动 registry、未动各层 runs 台账）。
- `find kb/l0 kb/l1 kb/l2 kb/l3 kb/l5 kb/l6 kb/l7 -newermt "2026-10-05 10:39"` 命中 5 个文件，逐个定性：
  · `kb/l7/runs/index.jsonl`、`kb/l7/runs/20261005-1038/1039/1041.json` —— `source=daily_health` 的定时 `--check` 产物，非本层命令所写（见上 §异常 6）；
  · `kb/l7/_backups/kbpy-perf-S1-20261005-103923/kbpy.before.sha256` —— 名为 kbpy 性能测试的快照，非本层动作。
- `kb/l4` 下本次仅落两个**预演落章件**（`-dryrun.json` / `-canonical-dryrun.json`）——
  这是引擎在预演档**设计内**的输出（任务书第 3、4 步明示），**不是 `--apply` 落盘**。
- `kb/.work/l4_integrity.json`（18383 字节，mtime 10:41:13）是 `l4_integrity.py` 的 scratch，
  按 `layers.yaml` L4 段第 316 行说明**不属库状态**。
- **未手工写 `kb/l7/runs/index.jsonl`**（派单铁律 3）；本次 RUN 在该文件 **0 命中**。
- 本文件由 **write 工具**落盘，未用 python / perl / sed 写 `.md`。
