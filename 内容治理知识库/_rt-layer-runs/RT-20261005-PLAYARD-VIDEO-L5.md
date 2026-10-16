# L5 层执行留痕 · RUN=RT-20261005-PLAYARD-VIDEO-L5

- 层：L5（P0 判定层）
- RUN：`RT-20261005-PLAYARD-VIDEO-L5`（未改名）
- 档位：**预演档 / 只读**（全程未加 `--apply`、未加 `--write-gate`、未加 `--allow-beyond-policy`）
- 执行时间：2026-10-05 10:43:07 → 10:44:23（预演落章件最后一次写入 10:43:46；本机时区）
- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（`kb/` 为其下的权威库）

## 第 2 步 · 本层 engine 清单（抄自 `kb/l7/registry/layers.yaml` L5 段，第 416-420 行；未从别处手抄）

`skill:` 字段 = `[kb-p0-check]`（第 406 行，唯一真源）。`engine:` 共 **4** 个：

1. `kb/.work/l5_prep.py` —— RUN：前置 A（追加 rule_kind / authority，精确化 risk_level / p_level）
2. `kb/.work/l5_export.py` —— RUN：P0 可执行导出
3. `kb/.work/l5_bench.py` —— 性能验收（PRD §12 要求 < 1 秒）｜**★ 驱动循环默认跳过**：无预演档，`:121` 无条件写 `kb/l5/benchmark.json`；且它不解析 argv，连 `--help` 都会照常执行并写盘
4. `kb/.work/l5_report.py` —— **L5 落章引擎**：`<RUN> --skill <id> [--apply]`，预演写 `kb/l5/runs/<RUN>-dryrun.json`

**本次照 ★ 标记处理**：清单里**只有** `l5_bench.py` 带 ★ ⇒ **本次未跑它**（它没有预演档，跑＝写 `kb/l5/benchmark.json`）。其余 3 个引擎全部以预演档跑过。

## exit_code 逐条

| # | 命令 | exit_code |
|---|---|---|
| 3 | `sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L5 --gate-only --run RT-20261005-PLAYARD-VIDEO-L5` | **0** |
| 4-1 | `sh kb/kbpy .work/l5_prep.py RT-20261005-PLAYARD-VIDEO-L5` | **0** |
| 4-2 | `sh kb/kbpy .work/l5_export.py RT-20261005-PLAYARD-VIDEO-L5` | **0** |
| 4-3 | `sh kb/kbpy .work/l5_report.py RT-20261005-PLAYARD-VIDEO-L5 --skill kb-p0-check` | **0** |
| 5-1 | `/usr/bin/python3` 只读读 `kb/l5/runs/RT-20261005-PLAYARD-VIDEO-L5-dryrun.json` 顶层字段 | **0** |
| 5-2 | `sh kb/kbpy l5/matcher.py --selftest` | **0** |
| 5-3 | 只读读 `kb/l5/p0_patterns.jsonl`（7 行）+ `kb/l5/registry/l5.json` | **0** |
| — | `kb/.work/l5_bench.py`（★ 标记） | **未跑**（设计内跳过，不加开关绕过） |

## 第 3 步 · 闸门 stdout 原文（全量，逐字）

```
[层表核对] STAMP_SPEC 7 条全部能在 layers.yaml 本层 engine: 里找到 ✅
====================================================================================
知识库 L0–L7 执行编排器 · --sync ｜ 预演（不带 --apply） ｜ run_id=RT-20261005-PLAYARD-VIDEO-L5
====================================================================================
锁：已持锁 pid=76563 run_id=RT-20261005-PLAYARD-VIDEO-L5
[写档闸门] **未带 --write-gate 凭据** → 本次按「各层只许只读档」对待；层引擎不得带 --apply。凭据表见 kb/l7/registry/write-gate.yaml
[L5] ⚠️ 写档闸门：**未带 --write-gate 凭据** → 本次按「各层只许只读档」对待；层引擎不得带 --apply。凭据表见 kb/l7/registry/write-gate.yaml
[L5] 闸门：过 ｜ exit=0 ｜ 退出码：0
[L5] via-skill：本层该调的 skill ＝ kb-p0-check
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l5_prep.py
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l5_export.py
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l5_bench.py
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l5_report.py
[L5] via-skill：引擎交给 kb-p0-check（本编排器不跑；它只跑闸门 + 记账 + **--skill 透传**）
[L5] --skill 透传：l5_report.py RT-20261005-PLAYARD-VIDEO-L5 --skill kb-p0-check ［预演档：未获本层写档凭据］
[L5] 落章引擎 exit=0 ｜ 产物变化 0 个
        [dry-run] 台账 → kb/l5/runs/RT-20261005-PLAYARD-VIDEO-L5-dryrun.json（顶层 skill=kb-p0-check）
        run verdict = FAIL
[记账] --gate-only：本次**不写** kb/l7/runs/（只过闸门 + 持锁/释放）—— 最终态由带 --invoked 的那次记账落，一个 RUN 在 index.jsonl 里只留 1 行
[记账] 层侧落章实测：applied 0 ｜ dry 1 ｜ unknown 0 ｜ 读错 0 → human_involved=False ｜ verdict=全走完（预演 · 未落盘 · 非执行证据）
------------------------------------------------------------------------------------
结论：L5 全部走完（预演（不带 --apply））
提示：这是预演。真正落盘要加 --apply，且当前白名单只开 ['L1', 'L2', 'L3', 'L4', 'L5', 'L6']。
```

第 3 步要求记下的三行**原文**：

```
[L5] 闸门：过 ｜ exit=0 ｜ 退出码：0
[L5] --skill 透传：l5_report.py RT-20261005-PLAYARD-VIDEO-L5 --skill kb-p0-check ［预演档：未获本层写档凭据］
run verdict = FAIL
```

**退出码 = 0**。

**解码：闸门过（exit=0）；落章引擎 exit=0；但落章件内部 `verdict = FAIL` —— 两处口径不一致，原因见「需登记的异常 1」。**

## 第 4 步 · 其余引擎（预演档）输出原文

**4-1 `l5_prep.py` → exit 0**（干跑闸门在第一个副作用之前 `sys.exit(0)`，源码第 47-50 行已核）

```
[dry-run] l5_prep.py 未落盘。
[dry-run] 本脚本会写入：L5 前置：**追加写** kb/l3/candidates/rules.jsonl 与 kb/l3/manifest_l3.jsonl（旧行不动）
[dry-run] 加 --apply 才落盘（补档原因：原先运行即写盘，已发生过一次未授权写入）
```

**4-2 `l5_export.py` → exit 0**（同上，源码第 49-52 行）

```
[dry-run] l5_export.py 未落盘。
[dry-run] 本脚本会写入：L5 出表：覆盖写 kb/l5/p0_patterns.jsonl、l5/index/l5.jsonl、l5/registry/l5.json
[dry-run] 加 --apply 才落盘（补档原因：原先运行即写盘，已发生过一次未授权写入）
```

**4-3 `l5_report.py` → exit 0**（落章引擎；第 3 步编排器已跑过第 1 次，本次为第 2 次）

```
[dry-run] 台账 → kb/l5/runs/RT-20261005-PLAYARD-VIDEO-L5-dryrun.json（顶层 skill=kb-p0-check）
run verdict = FAIL
```

非零退出：**本次没有**——4 个 exit_code 全为 0（`l5_bench.py` 按 ★ 未跑，不是「非零退出」）。未为了让任何一项变绿而加开关或改数据。

## 第 5 步 · 落章件核验

`stamp: kb/l5/runs/RT-20261005-PLAYARD-VIDEO-L5-dryrun.json`
（34315 字节｜mtime 2026-10-05 10:43:46｜sha256 `1d8a4a52fc5debf552fdad81e23fb45edbefadf3aae8cbcf98cc36c0ce9325e7`）

顶层字段**原值**（逐字抄自该文件，未改写）：

```
run_id          = "RT-20261005-PLAYARD-VIDEO-L5"
skill           = "kb-p0-check"
dry_run         = true
applied         = false
pipeline_run_id = null
verdict         = "FAIL"
```

- **`skill == "kb-p0-check"` 已确认**（比较结果为 `True`），且三方一致：
  ① 第 1 步用 **skill 工具**实际加载的 `kb-p0-check`；
  ② `kb/l7/registry/layers.yaml` L5 段第 406 行 `skill: [kb-p0-check]`（唯一真源）；
  ③ 本落章件顶层 `skill` 字段（由执行本层的进程写入）。
- 该文件顶层键共 24 个：`run_id / stage / finished_at / exporter_version / kb_version / inputs_read_only / precondition_a / precondition_b / selection / patterns / term_grounding / benchmark / selftest / integrity / artifacts / decisions / not_done / verdict / dry_run / applied / skill / skill_source / pipeline_run_id`。

### P0 模式清单（只读事实，供父会话写报告用）

`kb/l5/p0_patterns.jsonl`：**7 条**（`grep -c .` = 7；非空 JSONL 行数一致）
93848 字节｜sha256 `470e3fbad21489b9ad3cae7bd5fd5d4273b19262acb297c5b91808b51c570ea8`｜mtime 2026-10-05 10:15:11（**本次执行未改动**）
全部 7 条 `p_level` 均为 `P0`（集合 = `{P0}`），`match_note` 均为 `BLOCK`，`type` 均为 `keyword`。

| # | pattern_id | 规则码 | authority | P0 模式（anchor） | 规则摘要（match_terms + 边界） | evidence_units |
|---|---|---|---|---|---|---|
| 1 | `p-755f9ff377c3052c` | H02 | expert | `#广告文案明细/recvuJYdOb1Rm1/命中片段` | 增产催奶 / more milk 类：`more milk` `increase milk supply` `boost supply` `easier letdown` `下奶` `催乳` `催奶` `增产` `增加奶量` `奶量提升` 等 **24** 词；白名单放行 `relaxation` `natural let-down` `放松` `自然奶阵` | 102（`source_sha256=c77f576dcc39…`） |
| 2 | `p-521d9d1502ee0bfa` | H04 | expert | `#广告文案明细/recvuJYdObV6eR/命中片段` | 专家/医生推荐背书：`ob-gyn recommended` `recommended by 100+ experts` `doctor recommended` `ibclc-recommended` `专家推荐` `医生推荐` `专家调校` 等 **13** 词；白名单仅 `free ibclc service` `免费 IBCLC 服务` | 6（`6059659ad3f6…`） |
| 3 | `p-08487282e2d400fe` | H05 | expert | `#广告文案明细/recvuJYdOb1B8v/命中片段` | 虚假安全 / 绝对化：`safest` `100% safe` `zero risk` `risk-free` `perfect pump` `one size fits all` `绝对安全` `零风险` `适合所有胸型` 等 **13** 词；白名单 `best` `#1` `no.1` `第一` | 36（`e7aabf747875…`） |
| 4 | `p-485c67cc9af960bf` | H06 | **inferred** | `#品线内容边界规则库/recvuJP1LVW6E0/边界内容` | FDA 背书类：`FDA approved` `FDA certified` `FDA 批准` `FDA 认证` `FDA 通过` **5** 词；白名单 `FDA cleared` `FDA-cleared` `FDA registered` `FDA 注册` | 4（`2e8bb36d6edf…`） |
| 5 | `p-964b3c2e22b48ade` | H07 | expert | `#广告文案明细/recvuJYdOb1u94/命中片段` | 无痛 / 缓解疼痛承诺：`pain-free` `no pain` `without pain` `pain relief` `zero pain` `无痛` `缓解疼痛` `不痛` `告别疼痛`（含 `sans douleur` `schmerzfrei` `sin dolor` `indolore`）等 **17** 词；白名单 `comfort` `gentle` `discomfort` `舒适` `温和` | 153（`1e3bd4c1ca09…`） |
| 6 | `p-d31dfbc932cb84ac` | H09 | expert | `#广告文案明细/recvuJYdOb61lT/命中片段` | 拟真婴儿吮吸：`mimics baby’s natural nursing` `mimic baby` `imitates baby` `baby-like suckling` `模仿婴儿` `模拟婴儿吸吮` `还原婴儿吮吸` **8** 词；白名单**空** | 9（`67875346a75b…`） |
| 7 | `p-4d1fe41caef6e3b1` | U04 | expert | `#广告文案明细/recvuMGgT9p2zx/命中片段` | 疼痛功效承诺：`painful pumping` `clogged ducts` `sore breasts` `sore nipples` **4** 词；白名单**空** | 6（`b5de79a05b4f…`） |

**pattern_id 列表（7 条）**：
`p-755f9ff377c3052c`（H02）· `p-521d9d1502ee0bfa`（H04）· `p-08487282e2d400fe`（H05）· `p-485c67cc9af960bf`（H06）· `p-964b3c2e22b48ade`（H07）· `p-d31dfbc932cb84ac`（H09）· `p-4d1fe41caef6e3b1`（U04）

### `matcher.py --selftest` → exit 0（只读器，不写盘）

```
载入 P0 模式 7 条
--- positives
  ✅ HIT  [H07] Experience pain-free pumping with our hospital grade pum
  ✅ HIT  [H02] This pump helps you get more milk in less time.
  ✅ HIT  [H04] Recommended by 100+ experts and trusted worldwide.
  ✅ HIT  [H05] The safest, most perfect pump — 100% safe.
  ✅ HIT  [H09] Designed to mimic baby's natural nursing rhythm.
  ✅ HIT  [U04] Say goodbye to painful pumping forever.
  ✅ HIT  [H02,H07] 采用无痛设计，缓解疼痛，帮助催奶增产。
  ✅ HIT  [H04] 医生推荐的专业选择，专家推荐品牌。
  ✅ HIT  [H02,H07] 禁用表达：pain-free。但我们这款提供无痛体验，还能帮助催奶。
--- negatives_should_be_empty
  ✅ MISS [ ] Our device is not intended to treat, cure or prevent any
  ✅ MISS [ ] 本产品不能治疗乳腺炎，也不可以预防疾病。
  ✅ MISS [ ] 禁用表达：pain-free、more milk。
  ✅ MISS [ ] DO NOT SAY: pain-free; SAY THIS INSTEAD: comfortable.
  ✅ MISS [ ] 依据原文：「more milk」属于禁用表述。

自测结论：✅ 正例全命中、负例零误报
```

（7 条模式全部载入；正例 9 条全命中、负例 5 条零误报。）

## `l5_gate.py` 6 项自检实测（第 3 步闸门的底层证据，读自 `kb/.work/l5_integrity.json`，`checked_at=2026-10-05 10:43:09`）

| 项 | 类别 | 本次实测 | 说明 |
|---|---|---|---|
| `frozen_layers` | 基线 | **FAIL** | l0 4059 文件/max_mtime 09:59:46、l1 3162/10:14:49、l2 893/10:14:54，均晚于 `l5_first_write=2026-09-23 13:22:33` ⇒ 活库上必然 FAIL |
| `l3_append_only` | 基线 | **FAIL** | lines=1018｜baseline_lines=509｜`appended_covers_baseline=true`｜`byte_identical_to_pre_append=false`（prefix `acf77a6a0b05937d` ≠ prep 基线 `743dc62398311b02`） |
| `pattern_traceability` | 实质 | PASS | 7 条模式逐条可回指（`bad=[]`）|
| `no_fabricated_words` | 实质 | PASS | 84 词全有 basis｜`dropped_ungrounded=0`｜`bad=[]` |
| `version_discipline` | 实质 | PASS | `kb_version=['v0']`｜canonical 0 字节｜versions 0 行 |
| `offline` | 实质 | PASS | `network_symbols_found=[]` |

⇒ **实质 4 项全 PASS；基线 2 项 FAIL 且已在 `kb/l7/registry/l5-known-drift.yaml` 逐项登记** ⇒ `l5_gate.py` 判「过」（未被判红），与第 3 步 `[L5] 闸门：过 ｜ exit=0` 一致。落章件的 `verdict=FAIL` 是**未分类的原始自检结论**（`l5_integrity.json` 顶层 `verdict=FAIL`），不是闸门口径。

## 需登记的异常（不影响「闸门过」，但必须可见）

1. **`verdict=FAIL` 是已知判据漂移，不是数据坏了、也不是本次执行引入的。**
   落章件 `verdict` 抄的是 `l5_integrity.py` 的**未分类**结论（6 项里 2 项基线 FAIL ⇒ 顶层 FAIL）；
   闸门 `l5_gate.py` 的价值恰好在于把这 2 项**分类为已登记漂移**、只看实质 4 项 —— 所以闸门过、落章件 FAIL。
   依据：`kb/l7/registry/l5-known-drift.yaml` + `layers.yaml` L5 段第 414-415 行。**本次未改数据、未改判据。**
2. **`l3_append_only` 登记里的「证据」与本次实测已不一致（只登记事实，不据此改登记文件）。**
   `l5-known-drift.yaml` 第 50 行写的过期理由是「实测当前文件**正好 509 行**（2026-09-29 14:46）…`new_rows = raw[509:] = []` → `new_ids = ∅ ≠ base_ids`」；
   本次（2026-10-05）实测该文件已 **1018 行**，且自检器已报 `appended_covers_baseline=true`
   —— 即登记时那条「追加段为空」的理由**已不成立**，本次 FAIL 的真实原因是
   `byte_identical_to_pre_append=false`（前 509 行前缀哈希 `acf77a6a0b05937d…` ≠ prep 基线 `743dc62398311b02…`）。
   登记项本身存在（故闸门判过、未判红），但**登记口径晚于实测时点、已部分过期**，如实登记。
3. **`layers.yaml` notes 的「21 条 P0 → 入选 6 条」与实表 7 条不一致（如实登记，未改）。**
   第 446-447 行写「21 条 P0 → 入选 6 条」；实测 `kb/l5/p0_patterns.jsonl` = **7** 条。
   `kb/l5/registry/l5.json` 的 `excluded` = `{non_P0: 488, P0_but_authority_insufficient: 8, P0_admitted_by_allowlist: 1, P0_but_inductive: 6}`（合计 503），
   其中 `P0_admitted_by_allowlist: 1` 正是 H06（码准入，非放宽 authority）⇒ **6 + 1 = 7** 与实表自洽，
   即「6 条」是**加 H06 码准入之前**的旧数。两个数都能复算出来，差异在口径时点，**不是本次跑出来的**。
4. **★ 本次未做 superseded 归档（铁律 5，本层多出的那条红线）**：本次是**预演档**，无覆盖式写入 ⇒
   `kb/l5/runs/RT-20261005-PLAYARD-VIDEO-L5.p0_patterns.superseded.jsonl` **不存在**（已显式核验：ABSENT）。
   预演档**不做**这个归档动作；真档（`--apply`）跑前必须由**人工**先归档旧模式表，这个缺口仍在。
5. **`l5_bench.py` 本次未跑**：清单里带 ★「驱动循环默认跳过（无预演档）」，且它不解析 argv（连 `--help` 都写盘）。
   为了让 `kb/l5/benchmark.json` 保持不动（mtime 仍为 2026-10-03 06:56:54），**按标记跳过**，未加任何开关绕过。
   后果：落章件里 `benchmark` 一节读的是**旧基准件**，不代表本轮性能验收 —— 父会话写报告时不要把它当本轮实测。
6. **`pipeline_run_id = null`**：落章件里该字段确实为空（本次 `--gate-only` 未传 pipeline run id），是如实取值。
7. **`kb/l7/runs/index.jsonl` 本层未写**：`grep -c "RT-20261005-PLAYARD-VIDEO-L5"` = **0**（grep exit=1）。
   该文件 mtime `10:42:30` 的那一行 `commands` 是 `kb_pipeline.py --sync --via-skill --only L4 --run RT-20261005-PLAYARD-VIDEO-L4 --invoked kb-canonical-lookup`（**父会话的 L4 记账**），
   与本层无关；另两行是 `kb_pipeline.py --check` 的 `daily_health` / `freshness` 定时产物。本层命令列表**不含 `--check`**、也不含记账动作。
8. **锁：本次零冲突** —— stdout `锁：已持锁 pid=76563 run_id=RT-20261005-PLAYARD-VIDEO-L5`，
   未出现 `exit 2`、未等待重试、未撬锁、未删 `kb/.work/.kb.lock`。会话级认领 `kb/.work/.kb-loop-claim.json`
   显示父会话 `dsh-video-playard-review`（base `RT-20261005-PLAYARD-VIDEO`）持有，本层未触碰认领文件。
9. **`.work/l5_integrity.json` 是自检器 scratch**（4361 字节，mtime 10:43，由第 3 步闸门内的 `l5_integrity.py` 写出），
   按 `l5_gate.py` 头部注释「**不是层产物**」口径，不属库状态；本层未额外写它。

## blockers

`blockers: 无`

- 无锁冲突、无命令崩溃、无非零退出、无因权限/环境导致的跳过。
- 上面 9 条是**需要父会话知晓的口径差异与归属说明**，不构成本层阻断。

## skill_loaded

`skill_loaded: kb-p0-check`

**用 skill 工具真加载**（不是「知道有这个名字」）：调用返回了该 skill 的完整正文
（`/Users/lute/.dsh/skills/kb-p0-check` → 软链到 `kb/l7/skills/kb-p0-check`，含 §1 数据在哪、§2 红线、§3 何时停下来问人、§4 写档档位），
并按需读了它的详情页 `references/layer-playbook.md`（查询档判法 / 输出契约 / 写档三条件与红线）。
skill 名取自 `kb/l7/registry/layers.yaml` L5 段 `skill:` 字段（唯一真源，未从别处手抄）。

按正文行事：本层本次**只走查询档 / 只读**。正文 §4 的写档三条件
（① 由 `kb-pipeline` 以层身份调用 ② 带 `--apply` ③ 人开闸）—— ② 与 ③ 本次均**不满足**（①虽满足，但不满足②③仍只许停查询档），
故全程未加 `--apply`，未跑 `l5_prep.py` / `l5_export.py` 的落盘路径，也未做 §3.3 的 superseded 归档。
（本条为 agent 自述档；「真的加载了」的机器侧证据见上 §第 5 步 的 `skill` 字段。）

## 边界声明

- 本次**只读 / 预演**：全程未加 `--apply` / `--write-gate` / `--allow-beyond-policy`；
  未改 `kb/l0`–`kb/l7` 任何**数据**文件。
- **零写实证（执行前后逐字节比对，sha 与 mtime 全部一致）**：

| 文件 | 执行前 sha256(16) / mtime | 执行后 sha256(16) / mtime | 判定 |
|---|---|---|---|
| `kb/l5/p0_patterns.jsonl` | `470e3fbad21489b9` / 10-05 10:15:11 | `470e3fbad21489b9` / 10-05 10:15:11 | 未变 |
| `kb/l5/index/l5.jsonl` | `2bbf831ce7621a7a` / 10-05 10:15:11 | `2bbf831ce7621a7a` / 10-05 10:15:11 | 未变 |
| `kb/l5/registry/l5.json` | `f475013735d113fc` / 10-05 10:15:11 | `f475013735d113fc` / 10-05 10:15:11 | 未变 |
| `kb/l5/benchmark.json` | `071e365908168e25` / 10-03 06:56:54 | `071e365908168e25` / 10-03 06:56:54 | 未变 |
| `kb/l3/candidates/rules.jsonl` | `743dc62398311b02` / 10-02 22:45:07 | `743dc62398311b02` / 10-02 22:45:07 | 未变 |
| `kb/l7/runs/index.jsonl` | `069ad5b61370cd74` / 10-05 10:42:30 | `069ad5b61370cd74` / 10-05 10:42:30 | 未变 |

- `find kb/l0 … kb/l7 -newermt "2026-10-05 10:42:30"` 命中 **1 个文件**：
  `kb/l5/runs/RT-20261005-PLAYARD-VIDEO-L5-dryrun.json` —— 这是**落章引擎在预演档设计内**的输出
  （任务书第 3、4 步明示「预演写 `runs/<RUN>-dryrun.json`」），**不是 `--apply` 落盘**。
- **未做 superseded 归档**（铁律 5）：本 RUN 的 `.p0_patterns.superseded.jsonl` 不存在。
- **未手工写 `kb/l7/runs/index.jsonl`**（铁律 3）；本次 RUN 在该文件 **0 命中**。
- **未撬锁、未删 `kb/.work/.kb.lock`**（铁律 2）；未触碰 `kb/.work/.kb-loop-claim.json`。
- 本文件由 **write 工具**落盘，未用 python / perl / sed 写 `.md`（铁律 7）。
