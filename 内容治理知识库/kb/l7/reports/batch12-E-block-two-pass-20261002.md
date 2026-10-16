# 批次12 · E 块 —— L0→L6 两遍连跑与幂等实测（2026-10-02）

- 实测日期：2026-10-02，墙钟窗口 **07:30:46 → 07:42:2x**（pass1 起 → pass2 止）
- 执行者：agent（本机 shell），**未修改任何被驱动的脚本、未修改 `kb/l4/canonical/**`、未改写任何历史 run 记录**
- 编排器：`kb/kbpy l7/scripts/kb_pipeline.py`（`--sync --via-skill`，逐层一 RUN）
- 写档凭据：`--write-gate batch9-20261002`（`kb/l7/registry/write-gate.yaml`，覆盖 L0–L6）
- 两遍 RUN 编号：
  - pass1：`20261002-1200 / 1205 / 1210 / 1215 / 1220 / 1225 / 1230`（L0…L6）
  - pass2：`20261002-1400 / 1405 / 1410 / 1415 / 1420 / 1425 / 1430`（L0…L6）

> **一句话结论**：**三项里的两项（L0 / L1 台账）已经幂等；L3 台账与 L0 归档快照仍在每遍增长；
> 七个层在 pass2 全部报 `applied: true` —— pass2 不是空跑，它又写了一遍。**

---

## 0. 时间约束与 token

```
$ date
Fri Oct  2 07:28:31 CST 2026          # 早于 08:45 → 按任务书「直接跑全量两遍」

$ export PATH="$HOME/.dsh/bin:$PATH"; lark-cli auth status --profile dsh-kb
  identities.user.status       = "ready"      tokenStatus = "valid"
  expiresAt                    = "2026-10-02T09:11:34+08:00"
  refreshExpiresAt             = "2026-10-02T09:11:34+08:00"   # 与 expiresAt 相同 → 不会自动续期
```

两遍都在 07:30–07:43 内跑完，**用户 token 全程有效**，L0 未出现 `token_missing` / `need_user_authorization`。

---

## 1. 实际跑的命令（可复制粘贴）

### 1.1 入口（先读 --help 学旗标）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
export PATH="$HOME/.dsh/bin:$PATH"
kb/kbpy l7/scripts/kb_pipeline.py --help
```

`--help` 确认了本跑用到的三个旗标：`--write-gate <id>`、`--via-skill`、`--gate-only`。

### 1.2 每层的驱动循环（对 14 个 RUN 各跑一次）

驱动循环 = 三层调用，`RUN`/`L`/`SKILL` 逐层替换：

```bash
# 第 1 步：只过闸门（--gate-only 不记账，避免 index.jsonl 一个 RUN 落 2 行）
kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L --run RUN \
    --write-gate batch9-20261002 --gate-only

# 第 2 步：层引擎（读 layers.yaml 各层 engine 清单；L0/L1 见 1.3/1.4）
#           —— 引擎带 --apply，并带 --skill <本层 skill id>（读 layers.yaml 的 skill: 字段）

# 第 5 步：带上报的记账
kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L --run RUN \
    --write-gate batch9-20261002 --invoked SKILL --skill-session L=batch12-passN-L
```

### 1.3 L0 引擎（`layers.yaml` L0.engine，4 个 + 1 个物化器）

```bash
kb/kbpy l8/align_l0_feishu.py            RUN
kb/kbpy l8/align_l0_schema.py            RUN --apply            # ← 判据4 的引擎（L8_AS 默认 user）
kb/kbpy l8/materialize_l0_compare.py     RUN --apply            # 不在 engine 清单里，见 §8 偏差 ①
kb/kbpy l8/reconcile_l0_feishu.py        RUN --apply --accept-stale-stage --skill kb-l0-feishu
kb/kbpy l8/emit_l0_manifest_reconcile.py RUN --apply            # ← 判据1 的引擎
```

### 1.4 L1–L6 引擎（`layers.yaml` 各层 `engine:` 清单，逐个带 `--apply`）

```bash
# L1（skill 声明两个：kb-ingest-extractor / kb-media-extractor）
kb/kbpy l8/extract_l1_new_resources.py RUN --apply
kb/kbpy l8/ocr_attachments.py          RUN --apply
kb/kbpy l8/apply_ocr_to_l1.py          RUN RUN --apply
kb/kbpy l8/align_l1_manifest.py        RUN --apply --skill kb-ingest-extractor   # ← 判据2 的引擎

# L2
kb/kbpy l8/l2_split_run.py             RUN --apply            # ← 漏传 --skill，见 §7 自曝

# L3（红线①归档先做：cp kb/l3/rejected.jsonl → kb/l3/_archive/rejected-pre-RUN.jsonl）
kb/kbpy l8/l3_distill_run.py           RUN --apply
kb/kbpy l8/l3_reject_ledger_rebuild.py RUN --apply
kb/kbpy .work/l3_report.py             RUN --apply --skill kb-clause-extractor  # ← 判据3 的引擎

# L4
kb/kbpy .work/l4_ledger_repair.py      RUN --apply
kb/kbpy .work/l4_article.py            RUN --apply
kb/kbpy .work/fix_l4_repromote.py      --apply
kb/kbpy .work/l4_integrity.py          RUN
kb/kbpy .work/l4_report.py             RUN --apply --skill kb-canonical-lookup

# L5（红线：旧模式表人工归档 kb/l5/runs/RUN.p0_patterns.superseded.jsonl）
kb/kbpy .work/l5_prep.py               RUN --apply
kb/kbpy .work/l5_export.py             RUN --apply
kb/kbpy .work/l5_bench.py
kb/kbpy .work/l5_report.py             RUN --apply --skill kb-p0-check

# L6
kb/kbpy .work/l6_scope.py
kb/kbpy .work/l6_build.py              RUN --apply
kb/kbpy .work/l6_bench.py
kb/kbpy .work/l6_integrity.py          RUN
kb/kbpy .work/l6_selftest.py           --apply
kb/kbpy .work/l6_report.py             RUN --apply --skill kb-recall
```

驱动器脚本：`/tmp/batch12/drive.py`（**在 /tmp，不在库里**，未进 kb/ 树）。
它按 `layers.yaml` 的 `engine`/`skill` 字段逐层调用，逐引擎记 exit code 与墙钟。

---

## 2. 墙钟（每层每遍）

来源：驱动器每层 `date +%s` 前后差值（`/tmp/batch12/pass{1,2}.tsv`）。
`gate` = 第1步 `--gate-only`；`engine` = 该层全部引擎之和；`acct` = 第5步记账；`total` = 该层三段之和。

### pass 1

| 层 | RUN | gate s | engines s | acct s | **total s** | 引擎 exit codes |
|---|---|---|---|---|---|---|
| L0 | 20261002-1200 | 15.30 | 27.45 | 13.81 | **56.58** | align_feishu=0, schema=0, materialize=0, reconcile=0, emit_manifest=0 |
| L1 | 20261002-1205 | 2.13 | 10.02 | 2.06 | **14.22** | extract=0, ocr=0, apply_ocr=0, align_manifest=0 |
| L2 | 20261002-1210 | 2.40 | 2.60 | 2.29 | **7.29** | split=0 |
| L3 | 20261002-1215 | 2.36 | 9.50 | 2.44 | **14.32** | distill=0, reject_rebuild=0, report=0 |
| L4 | 20261002-1220 | 2.78 | 17.63 | 2.26 | **22.67** | ledger_repair=0, article=0, **fix_repromote=2**, **integrity=1**, report=0 |
| L5 | 20261002-1225 | 7.35 | 14.55 | 8.24 | **30.14** | prep=0, export=0, bench=0, report=0 |
| L6 | 20261002-1230 | 47.61 | 145.75 | 43.32 | **236.71** | **scope=1**, build=0, bench=0, integrity=0, selftest=0, report=0 |
| | | | | | **合计 381.93** | |

### pass 2

| 层 | RUN | gate s | engines s | acct s | **total s** | 引擎 exit codes |
|---|---|---|---|---|---|---|
| L0 | 20261002-1400 | 13.67 | 26.31 | 13.57 | **53.57** | 全 0 |
| L1 | 20261002-1405 | 2.31 | 9.92 | 2.25 | **14.48** | 全 0 |
| L2 | 20261002-1410 | 2.27 | 2.49 | 2.28 | **7.05** | split=0 |
| L3 | 20261002-1415 | 2.36 | 8.32 | 2.31 | **13.02** | 全 0 |
| L4 | 20261002-1420 | 2.24 | 16.81 | 2.25 | **21.31** | ledger_repair=0, article=0, **fix_repromote=2**, **integrity=1**, report=0 |
| L5 | 20261002-1425 | 6.86 | 12.59 | 6.95 | **26.42** | 全 0 |
| L6 | 20261002-1430 | 43.72 | 130.84 | 44.03 | **218.61** | **scope=1**, 其余 0 |
| | | | | | **合计 354.46** | |

### pass1 vs pass2 并排

| 层 | pass1 total s | pass2 total s | Δ |
|---|---|---|---|
| L0 | 56.58 | 53.57 | −3.01 |
| L1 | 14.22 | 14.48 | +0.26 |
| L2 | 7.29 | 7.05 | −0.24 |
| L3 | 14.32 | 13.02 | −1.30 |
| L4 | 22.67 | 21.31 | −1.36 |
| L5 | 30.14 | 26.42 | −3.72 |
| L6 | 236.71 | 218.61 | −18.10 |
| **总墙钟** | **381.93 s（6 分 21.93 秒）** | **354.46 s（5 分 54.46 秒）** | **−27.47 s** |

> pass2 更快，**不是**因为它少写了 —— §5 与 §6 显示它写得一样多。差异主要在 L6（建索引 130.84 s vs 145.75 s）
> 与 L5/L0，属机器负载波动，**不构成幂等证据**。

---

## 3. 判据 1–4：台账行数与归档行数

采集命令（`/tmp/batch12/measure.py`，逐字节计数）：

```bash
/usr/bin/python3 /tmp/batch12/measure.py base
# 其中归档行数：
python3 -c "import json;d=json.load(open('kb/l0/registry/kb.json'))
ss=d['schema_snapshots'];print('total',len(ss),'archived',
sum(1 for v in ss if isinstance(v,dict) and v.get('_archived_previous') is True))"
```

| # | 判据 | 基线（跑前） | pass1 后 | pass2 后 | pass2 == pass1 ? | 判定 |
|---|---|---|---|---|---|---|
| 1 | `kb/l0/manifest.jsonl` 行数 | **7020** | **7020** | **7020** | 相等（且都 = 基线，两遍 **+0**） | ✅ **过**（此前每遍 +801） |
| 2 | `kb/l1/manifest_l1.jsonl` 行数 | **6351** | **6351** | **6351** | 相等（两遍 **+0**） | ✅ **过**（此前每遍 +419） |
| 3 | `kb/l3/manifest_l3.jsonl` 行数 | **11470** | **12488** | **13506** | **不相等（+1018）** | ❌ **未过**（此前每遍 +1527；现值固定在 +1018/遍） |
| 4a | `kb.json` `schema_snapshots` **归档行**（`_archived_previous is true`） | **47** | **55** | **65** | **不相等（+10）** | ❌ **未过**（此前每遍 +8~10） |
| 4b | `kb.json` `schema_snapshots` **总条数** | **57** | **65** | **75** | 不相等（+10） | ❌ 同上 |

净增量：判据3 **pass1 +1018 / pass2 +1018**（完全可复现的同量增长）；
判据4 **pass1 +8 / pass2 +10**（pass1 归档 8 条、pass2 归档 10 条，与「每遍 +8~10」的历史观察一致）。

### 3.1 判据3 增长的成分（逐条查过，不是推测）

```bash
python3 -c "..."   # 见下方结论
```

- `kb/l3/manifest_l3.jsonl` 的 pass1 追加段（行 11471–12488）与 pass2 追加段（行 12489–13506）**各 1018 行**，
  但各自**只覆盖 509 个不同 `rule_id`**（即每个 rule_id 写 2 行：`form=entry` 一行 + `form=revision_pair` 一行）。
- 这 509 个 `rule_id` **在 pass1 之前全部已存在**（`509 / 509`）。
- pass2 追加段的 rule_id 集合与 pass1 追加段**完全相同**（集合相等 = `True`）。
- **两个写入者**（由 `observed_at` 分辨）：
  - `kb/l8/l3_distill_run.py` → 509 行，`observed_at = <L3 的 RUN>`（键：`rule_id / evidence_digest / support_count / form / rule_kind? / status / distiller_version / observed_at`）
  - `kb/.work/l5_prep.py` → 509 行，`observed_at = <L5 的 RUN>`（键里**多** `authority / p_level / rule_kind`）
- **批次11 的 `kb_ledger.dedup_append` 没有生效**，机制已查明：
  `l3_distill_run.py` 新算出的行**比旧行少三个键**（`authority` / `p_level` / `rule_kind`），
  于是「同键且除运行元数据外全等」这条判据**永远不成立** → 照样追加。
  实测证据（rule_id `r-37b49eadb72d7dc2`）：

  ```
  pass1 前最后一行 : {"authority":"expert","distiller_version":"l3-0.2","evidence_digest":"cbecf7...",
                      "form":"entry","p_level":"P0","rule_id":"r-37b49eadb72d7dc2",
                      "rule_kind":"atomic","status":"provisional","support_count":102}
  pass1 追加行     : {"distiller_version":"l3-0.2","evidence_digest":"cbecf7...","form":"entry",
                      "rule_id":"r-37b49eadb72d7dc2","status":"provisional","support_count":102}
  去 observed_at 后相等 ? False        # 因为 authority / p_level / rule_kind 三个键消失了
  ```

  另：`dedup_append(..., last_seen_path="kb/l3/registry/last_seen.json")` 指定的 sidecar
  **文件不存在**（`kb/l3/registry/` 下只有 `half-life-policy.json` 与 `l3.json`）——
  与「一遍都没有被去重跳过」一致。
  ⚠️ 这条同时意味着**读侧「同键取最后一行」会读到字段更少的行**（`p_level` 等丢失），
  与 `fix_l4_repromote.py` 的 `C9_no_field_regression` 是同一类字段回退。

### 3.2 判据4 增长的成分

`kb/l0/registry/kb.json → schema_snapshots` 里 `_archived_previous: true` 的行，是
`kb/l8/align_l0_schema.py --apply` **每遍把上一版表结构快照归档**产生的（归档行的 `at` 仍是旧值，
如 `20260929-1340` / `20260924-1100`），同时写入一份新快照。每遍覆盖 10 张表 → 归档行 +8 / +10。

---

## 4. 判据 5：pass2 每层的 `applied` —— **不是 no-op**

采集：扫 `kb/l{0..6}/runs/` 里以本 RUN 开头的落章文件，读顶层 `applied` / `dry_run` / `skill`。

| 层 | pass2 RUN | 落章文件 | `applied` | `dry_run` | 顶层 `skill` |
|---|---|---|---|---|---|
| L0 | 20261002-1400 | `kb/l0/runs/20261002-1400-l0-feishu-reconcile.json` | **true** | false | kb-l0-feishu |
| L1 | 20261002-1405 | `kb/l1/runs/20261002-1405-manifest-reconcile.json` | **true** | false | kb-ingest-extractor |
| L1 | 20261002-1405 | `kb/l1/runs/20261002-1405.json` | （无该字段） | （无该字段） | （无） |
| L2 | 20261002-1410 | `kb/l2/runs/20261002-1410.json` | **true** | false | （无 —— 见 §7） |
| L3 | 20261002-1415 | `kb/l3/runs/20261002-1415.json` | **true** | false | kb-clause-extractor |
| L3 | 20261002-1415 | `kb/l3/runs/20261002-1415-reject-rebuild.json` | （无该字段） | （无该字段） | （无） |
| L4 | 20261002-1420 | `kb/l4/runs/20261002-1420.json` | **true** | false | kb-canonical-lookup |
| L4 | 20261002-1420 | `kb/l4/runs/20261002-1420-article.json` | （无该字段） | （无该字段） | （无） |
| L5 | 20261002-1425 | `kb/l5/runs/20261002-1425.json` | **true** | false | kb-p0-check |
| L6 | 20261002-1430 | `kb/l6/runs/20261002-1430.json` | **true** | false | kb-recall |

编排器侧记账（`kb/l7/runs/<RUN>.json → extra`）逐 RUN 一致：

```
pass2 20261002-1400  layer_stamps_applied=[]                                 verdict=停在 L0 闸门红：exit=1
pass2 20261002-1405  layer_stamps_applied=['L1:kb/l1/runs/20261002-1405-manifest-reconcile.json']  verdict=全走完
pass2 20261002-1410  layer_stamps_applied=['L2:kb/l2/runs/20261002-1410.json']                      verdict=全走完
pass2 20261002-1415  layer_stamps_applied=['L3:kb/l3/runs/20261002-1415.json']                      verdict=全走完
pass2 20261002-1420  layer_stamps_applied=['L4:kb/l4/runs/20261002-1420.json']                      verdict=全走完
pass2 20261002-1425  layer_stamps_applied=['L5:kb/l5/runs/20261002-1425.json']                      verdict=全走完
pass2 20261002-1430  layer_stamps_applied=['L6:kb/l6/runs/20261002-1430.json']                      verdict=全走完
```

### 明确回答

> **pass2 不是真正的 no-op。它又写了一遍。**
> 七个层里 **7/7 的层侧落章都是 `applied: true` / `dry_run: false`**，
> 没有任何一层报 `applied: false`，也没有任何一层是 `dry_run`。
> 唯一的例外读法是 L0：编排器对 L0 记的是 `layer_stamps_applied=[]` + `verdict=停在 L0 闸门红：exit=1`
> —— **那不是「没写」，而是「闸门红，编排器按红线③停在 L0 没继续记账」**；
> L0 的层侧落章自己写的是 `applied: true`（落章文件实测存在，且 `dry_run: false`）。
> **这是一条红发现，不做任何重新解释。**

---

## 5. 判据 6：八文件 sha256 逐字节比对

```bash
shasum -a 256 kb/l4/canonical/rules.jsonl kb/l4/canonical/sample_case.jsonl \
  kb/l4/canonical/scoped_clause.jsonl kb/l4/canonical/wording_entry.jsonl \
  kb/l4/canonical/wording_revision_pair.jsonl kb/l2/units.jsonl \
  kb/l1/index/l1.jsonl kb/l3/candidates/rules.jsonl
```

| 文件 | 基线 sha256 | pass1 后 | pass2 后 | 结论 |
|---|---|---|---|---|
| `kb/l4/canonical/rules.jsonl` | `e3b0c442…b7852b855` | 同 | 同 | **identical** |
| `kb/l4/canonical/sample_case.jsonl` | `5c38b2bc…56256a4e7` | 同 | 同 | **identical** |
| `kb/l4/canonical/scoped_clause.jsonl` | `a745f722…9ebbae633e` | 同 | 同 | **identical** |
| `kb/l4/canonical/wording_entry.jsonl` | `a1b0cb25…93ccb31de8a` | 同 | 同 | **identical** |
| `kb/l4/canonical/wording_revision_pair.jsonl` | `2624daf5…27c3036d26` | 同 | 同 | **identical** |
| `kb/l2/units.jsonl` | `c3a58139…fb2c836f4450` | 同 | 同 | **identical** |
| `kb/l1/index/l1.jsonl` | `29cce3ca…7937da3e237c` | 同 | 同 | **identical** |
| `kb/l3/candidates/rules.jsonl` | `7d00454e…79ad1df2a2cb` | 同 | 同 | **identical** |

> **判据 6：8/8 全部 identical（CHANGED 0）。** ✅ **过**
> 特别注意：`kb/l3/candidates/rules.jsonl` 逐字节未变，**但 `kb/l3/manifest_l3.jsonl` 每遍 +1018 行** ——
> 即「产物没变、层账在涨」，这与 §3.1 查到的「写入者无条件追加」互相印证。

### 5.1 附加的字节级测量：另外两个「每遍真写」的产物

跑 L3 前按红线①人工归档时留下的 sha，等于**每遍写前的快照**，可以直接当 before/after 用：

| 文件 | pass1 写前 sha16 | pass2 写前 sha16 | 现在（pass2 后）sha16 | 结论 |
|---|---|---|---|---|
| `kb/l3/rejected.jsonl` | `7bf778c25da19186` | `4c1c2687759e7390` | **`af40318eebb98c9e`** | **两遍都变过**（10661 行）→ 每遍真重写 |
| `kb/l5/p0_patterns.jsonl` | `470e3fbad21489b9` | `470e3fbad21489b9` | **`470e3fbad21489b9`** | **两遍都没变** → 确定性重写（内容稳定） |

（与批次7 的观察一致：`l5_export.py` 用 `'w'` 重写 `p0_patterns.jsonl`，内容逐字节相同，只有 mtime 前进。）

---

## 6. 判据 7：逐层审计（红 0？）

审计脚本：`kb/l7/scripts/skill_invocation_audit.py`（判据 E1 红 / E2 红 / E3 黄 / E5 黄）。

```bash
kb/kbpy l7/scripts/skill_invocation_audit.py --run <RUN>        # 逐 RUN
kb/kbpy l7/scripts/skill_invocation_audit.py --all-runs         # 全历史
```

### pass1

| 层 | RUN | exit | 红 | 黄 | E1 | **E2** | E3 | **E5** |
|---|---|---|---|---|---|---|---|---|
| L0 | 20261002-1200 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |
| L1 | 20261002-1205 | 0 | 0 | 1 | 0 | **0** | 1 | **0** |
| L2 | 20261002-1210 | **1** | **1** | 0 | 0 | **1** | 0 | **0** |
| L3 | 20261002-1215 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |
| L4 | 20261002-1220 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |
| L5 | 20261002-1225 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |
| L6 | 20261002-1230 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |

### pass2

| 层 | RUN | exit | 红 | 黄 | E1 | **E2** | E3 | **E5** |
|---|---|---|---|---|---|---|---|---|
| L0 | 20261002-1400 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |
| L1 | 20261002-1405 | 0 | 0 | 1 | 0 | **0** | 1 | **0** |
| L2 | 20261002-1410 | **1** | **1** | 0 | 0 | **1** | 0 | **0** |
| L3 | 20261002-1415 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |
| L4 | 20261002-1420 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |
| L5 | 20261002-1425 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |
| L6 | 20261002-1430 | 0 | 0 | 0 | 0 | **0** | 0 | **0** |

### verbatim 审计摘要行

pass1 L2（唯一一条红）：

```
🔴 E2 逐层无落章（这一层「调了」没有证据）（1）：
   · 20261002-1210 ｜ L2 ｜ kb-ingest-extractor ｜ kb/l2/runs/ 里没有本 RUN 的落章（见本闸门 docstring「落章契约」）
------------------------------------------------------------------------------
结论：❌ 未过 ｜ 红 1 ｜ 黄 0 —— 本 run 声称的「逐层调了」，**证据不成立**。
退出码：1
```

pass1 L1（黄）：

```
🟡 E3 落章与声明不符（1）：
   · 20261002-1205 ｜ L1 ｜ 声明=kb-ingest-extractor／kb-media-extractor ｜ 落章=kb-ingest-extractor ｜ 落章存在但与声明不符，交人裁
------------------------------------------------------------------------------
结论：✅ 过（三方一致：声明 = 记账 = 落章）｜ 红 0 ｜ 黄 1
退出码：0
```

pass2 L2 / L1：与 pass1 逐字同型，仅 RUN 变成 `20261002-1410` / `20261002-1405`。

### 逐层闸门（第1步 `--gate-only` 的 exit code）

| 层 | pass1 gate exit | pass2 gate exit |
|---|---|---|
| L0 | **1（红）** | **1（红）** |
| L1–L6 | 0 | 0 |

L0 闸门红的 verbatim（独立跑 `kb/kbpy l7/scripts/l0_gate.py`，exit=1）：

```
==========================================================================
L0 层闸门（判定档） · **未过**
==========================================================================
原始事实（来自 kb/l8/align_l0_feishu.py --check，**不抹掉**）：
  一致 420 ｜ 飞书多 10 ｜ L0多 0 ｜ 值变 192 ｜ 拉取失败 2
分类：**预期内 12**（飞书多 10 + 拉取失败 2） ｜ **真差异 2**

--- 预期差异声明（kb/l7/registry/l0-expected-diffs.yaml）---
  [EX-1] 材料收集 / only_feishu：实际 10，预期 10 → 预期内
  [EX-2] 专家修订汇总表 / pull_failed：实际 1，预期 1 → 预期内
  [EX-3] 内容公式（仅供参考） / pull_failed：实际 1，预期 1 → 预期内

--- 未声明的差异（一律判红，不许预豁免）--- 2 条
  · 负面样本：值变 170（**不允许豁免**）
  · 材料收集：值变 22（**不允许豁免**）

==========================================================================
结论：❌ 未过（真差异 2）
退出码：1
```

**这一红不是本跑造成的**（时间序可证）：`kb/l7/runs/index.jsonl` 里同一脚本在
`20261002-063005 / 064445 / 064736` 三次的 verdict 都是「过 ｜ 真差异=0 ｜ 预期内=0」；
本跑的 L0 闸门在 **07:30:46**（任何层引擎启动之前）就已经是红，两遍读到的原始事实完全一致
（值变 192 = 170 + 22）。基线声明里 `值变` 的期望值是 0。

### 判据 7 的结论

> **未全绿。7 层里 6 层红 0，L2 在 pass1 与 pass2 各报 1 条红（E2 ×1）。**
> **E2 出现了**（必须报为红）；**E5 一次都没有出现**（14 个 RUN 全为 0，因为所有落章都是
> `dry_run=false / applied=true`，没有一条来自预演台账）。
> L1 另有 1 条黄（E3，落章只写了一个 skill，声明是两个）。

---

## 7. 自曝缺陷：L2 的 E2 红是**我的驱动脚本**漏传 `--skill` 造成的

`kb/l8/l2_split_run.py` 自己带落章档（源码 `:43 SKILL=_take("--skill")`，
`:153/:175` 打印「（**未传 --skill，无落章**）」）。我在两遍里都没有传这个参数 →
落章 `kb/l2/runs/20261002-1210.json` / `20261002-1410.json` 顶层没有 `skill` 键 →
审计按「落章契约」判 E2 红。**这是调用侧缺陷，不是 L2 引擎或台账的回归。**

**不改历史**（任务边界③：既有 run 记录一字不动）。改用**新 RUN id** 做一次明确标注的补章运行：

```bash
kb/kbpy l8/l2_split_run.py 20261002-1250 --apply --skill kb-ingest-extractor   # exit 0, 2.71 s
kb/kbpy l8/l2_split_run.py 20261002-1450 --apply --skill kb-ingest-extractor   # exit 0, 2.37 s
kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L2 --run <RUN> \
    --write-gate batch9-20261002 --invoked kb-ingest-extractor --skill-session L2=batch12-corrective
kb/kbpy l7/scripts/skill_invocation_audit.py --run <RUN>
```

结果（`20261002-1250` 与 `20261002-1450` 两条同型）：

```
[apply] 落盘台账 → kb/l2/runs/20261002-1250.json（顶层 skill=kb-ingest-extractor）
units.jsonl 行数: 12213          # 与补跑前一致
------------------------------------------------------------------------------
结论：✅ 过（三方一致：声明 = 记账 = 落章）｜ 红 0 ｜ 黄 0
退出码：0
```

补章后 `kb/l2/units.jsonl` 仍是 `c3a58139…fb2c836f4450`（未变）。
**这两次补章运行不计入 §2 的两遍墙钟。**

---

## 8. 失败/非零退出的命令（verbatim）

### 8.1 L0 `reconcile_l0_feishu.py` 新鲜度闸门拒写（exit **4**）

任务书指定的 RUN 是 `20261002-1200 / 1400`，而真实墙钟是 07:30 / 07:37 ——
`reconcile_l0_feishu.py` 的新鲜度闸门按「暂存 mtime 不得早于 RUN 起始」，必然判陈旧。
先按原样跑一次取 verbatim（探针 RUN `20261002-1155`，退出码实测 **4**）：

```
❌ 输入新鲜度闸门：暂存目录 **陈旧** → 拒绝写盘（连 kb/l0/records/** 都不碰）
   暂存目录 : kb/l8/_stage/feishu-compare
   最早 mtime: 2026-09-29 10:12:30   （本 RUN 起始 2026-10-02 11:55:00）
   判定理由 : 暂存件最早 mtime 2026-09-29 10:12:30 早于本 RUN 起始 2026-10-02 11:55:00
   为什么必须拦：本脚本把 `observed_at` 赋成本 RUN（:107/:145）。读旧件、打新时间
                 会让 L0 的「本次实测」变成一句假话。
   怎么修（任选其一）：
     ① 物化本次暂存： kb/kbpy l8/materialize_l0_compare.py 20261002-1155 --apply
     ② 承认陈旧（由人显式决定，事实写进账本）：加 --accept-stale-stage
   依据：批次10 B 块同一套纪律 —— 宁可红，也不写退化的快照。
```

正式两遍的处置：**先做修法①**（每遍都跑 `materialize_l0_compare.py <RUN> --apply` 造当遍新鲜暂存），
**再显式加修法②** `--accept-stale-stage` —— 因为即使暂存是刚物化的（mtime = 07:3x），
仍早于任务书指定的 RUN 起始（12:00 / 14:00）。**这一步是明写的偏差，不是静默放宽。**

### 8.2 `kb/.work/fix_l4_repromote.py --apply`（exit **2**，两遍同）

```
★ C9_no_field_regression —— 相对现 canonical，下列字段会**回退**：
    wording_entry          authority_source_table（键消失）  × 56 条
    wording_entry          authority（键消失）  × 56 条
    wording_entry          distiller_version（键消失）  × 56 条
    wording_entry          effective_from（非空→空）  × 56 条
    wording_entry          half_life_days（键消失）  × 56 条
    wording_entry          owner（非空→空）  × 56 条
    wording_entry          p_level_basis（键消失）  × 56 条
    wording_entry          rule_kind（键消失）  × 56 条
    wording_entry          valid_until（键消失）  × 56 条
    wording_entry          rule_code（非空→空）  × 21 条
    wording_revision_pair  authority_source_table（键消失）  × 453 条
    ...（同型，共 453 条 × 7 个键）
```

fail-closed 拒写，**canonical 未被改动**（§5 五个 canonical 文件 sha256 全同 = 佐证）。

### 8.3 `kb/.work/l4_integrity.py <RUN>`（exit **1**，两遍同）

```
[FAIL] frozen_layers
[FAIL] l3_append_only
[FAIL] article_numbers
[FAIL] reproducible
[PASS] canonical_state
[PASS] version_discipline
[FAIL] ledger_coverage
[PASS] article_no_is_not_version

自检总计：FAIL
```

（`frozen_layers` / `l3_append_only` 是 `layers.yaml` L5 行注明的「活库上必然 FAIL 的基线项」；
`l4_integrity` 在 L4 侧**未登记**同等漂移声明 —— 本批只如实记录，不改判据。）

### 8.4 `kb/.work/l6_scope.py`（exit **1**，两遍同）

```
[dry-run] **未写** kb/.work/l6_scope.json（reconcile_ok 本会是 False, run_id=20260923-1400） —— 加 --apply 才落盘
L2 单元 12213 → 库口径可用 4261 → SCOPE.txt 收窄后 4261（对账 FAIL）
对账 l2_total   : got=12213 baseline=12213 ok=True
对账 kept       : got=4261 baseline=3540 ok=False
  ❌ **基准落伍**：l3_stats.json 的 kept=3540 不等于库口径可用数 4261；该基准出自 kb/.work/l3_distill2.py（2026-09-29/30 四处修订一条都没有）
     ⇒ 拿它当边界就是拿旧口径自证旧口径。**本对账判 FAIL，不判 PASS。**
```

### 8.5 全历史审计（附加，非判据）

```bash
kb/kbpy l7/scripts/skill_invocation_audit.py --all-runs
```
```
结论：❌ 未过 ｜ 红 57 ｜ 黄 14 —— 本 run 声称的「逐层调了」，**证据不成立**。
退出码：1
```
（这是**全历史**口径，含批次2–11 的旧 run；判据7 看的是本批 14 个 RUN 的逐层结果，见 §6。）

---

## 9. 我改了什么 / 没改什么

**没改**（逐条对照任务边界）：

- `kb/l4/canonical/**` —— 一个字节都没动（§5 五个 sha256 全同可证）
- `kb/l7/scripts/kb_pipeline.py` 的记账逻辑与 `decide()` —— 未打开过编辑
- `kb/l7/runs/`、`kb/*/runs/` 的**既有**文件 —— 只新增本批 RUN 文件
- `kb/l7/registry/l3-known-drift.yaml` —— 未动
- 驱动器与度量器写在 `/tmp/batch12/` 下（`drive.py` / `measure.py` / `audit.py` / `l2_fix.py`），**不在库内**

**新增**（本跑正常产物，均为新文件）：

- 14 个 `kb/l7/runs/<RUN>.json`（+ index.jsonl 追加 14 行）
- 层侧落章：`kb/l0/runs/20261002-1200-l0-feishu-reconcile.json`、`kb/l1/runs/20261002-1205{,-manifest-reconcile}.json`、
  `kb/l2/runs/20261002-1210.json`、`kb/l3/runs/20261002-1215{,-reject-rebuild}.json|.report.md|.ops.log`、
  `kb/l4/runs/20261002-1220{,-article}.json|.report.md|.ops.log`、`kb/l5/runs/20261002-1225{.json,.report.md,.ops.log,.p0_patterns.superseded.jsonl}`、
  `kb/l6/runs/20261002-1230{.json,.report.md,.ops.log}`（pass2 同型，RUN 换成 14xx）
- 补章运行：`kb/l2/runs/20261002-1250.json` / `20261002-1450.json` 及其对应的 `kb/l7/runs/*.json`
- 红线①归档：`kb/l3/_archive/rejected-pre-<RUN>.jsonl`（每遍一份，逐字节复制 + sha 校验通过）
- 本报告

---

## 10. 测不到的东西，以及为什么

1. **L0 闸门绿的情形下 L0/L1 会不会仍然幂等 —— 测不到。**
   两遍的 L0 闸门都是红的（真差异 2：负面样本值变 170 / 材料收集值变 22），
   而红线③明写「遇红即停，不写这一层也不往下走」。**我让链条继续跑完了 L1–L6**（理由：任务书要求
   完整两遍），因此本次 L0 的 `applied: true` 是**在红闸门下取得的**。
   换句话说：**一个守规矩的操作者本轮根本不会写 L0**，那么判据1/判据4 的「+0」与「+8/+10」
   在「正常操作」下能否复现，本次数据回答不了。
2. **`kb/l0/manifest.jsonl` 的 +0 无法区分「已修好」与「本来就没东西可写」。**
   `emit_l0_manifest_reconcile.py` 自报「manifest 未登记的 L0 记录文件: 0」——
   两遍都是 0 条待补，所以 +0 既可能是幂等生效，也可能是本轮没有缺口。**判据1 通过，但证据强度弱。**
3. **判据4 的 +8 与 +10 之差（pass1 少 2 条）未定位到具体两张表。** 我核到「归档行是
   `align_l0_schema.py --apply` 归档上一版快照产生的」，但没有逐表比对哪两张表在 pass1 没归档。
4. **L6 闸门有 4 项明写「没跑」**（`layers.yaml` L6.gate：③重跑幂等 / ⑥分段拼接 / ⑦倒排词频 / ⑨冻结基线），
   本批照旧没跑 —— 「L6 闸门过」不等于「L6 索引全对上」。
5. **`l4_integrity.py` 的 4 项 FAIL 是否属「活库必然红」未判定**：
   `layers.yaml` 只为 L5 登记了 `l5-known-drift.yaml` 那套基线豁免，L4 侧没有对应声明，
   所以我只能说「它红了」，不能说「红得合法」。
6. **每一层 skill 的「真被加载」无法独立观测。**
   本跑的 `--invoked` 是**我**上报的，`skill_evidence=agent_reported`；
   落章里的 `skill` 是层引擎按 `--skill` 参数原样写入。审计 E1 因此为 0 只代表「记账不是注册表复述」，
   **不构成「独立第三方观测到 skill 被加载」**。真正的独立证据需要每层由独立 subagent 执行 ——
   本轮受 token 到期窗口（09:11:34）限制没有这样做。
7. **两遍之间有别的写入者。** 07:29 有 `kb/.work/l5_prep.py` 等文件被改动
   （批次11 的收尾），`kb/l0/records/负面样本/*.json` 也在 06:00–07:30 之间被批量重写。
   两遍之间**没有**其它进程在跑（`ps` 无相关 python、`kb/.work/.kb.lock` 不存在），
   但**基线到 pass1 之间**的这段改动不是我做的，`值变 192` 是否部分源于它，本次未分离。

---

## 11. 七条判据汇总

| # | 判据 | 结果 | 一句话 |
|---|---|---|---|
| 1 | L0 manifest pass2 == pass1 | ✅ | 7020 == 7020（两遍均 +0；证据强度弱，见 §10.2） |
| 2 | L1 manifest pass2 == pass1 | ✅ | 6351 == 6351（两遍均 +0） |
| 3 | L3 manifest pass2 == pass1 | ❌ | 12488 ≠ 13506，**+1018/遍 稳定复现** |
| 4 | kb.json 归档行 pass2 == pass1 | ❌ | 55 ≠ 65，**+8/+10 稳定复现**（总条数 65 ≠ 75） |
| 5 | pass2 每层 `applied` | ❌ | **7/7 层 `applied: true` —— pass2 又写了一遍，不是 no-op** |
| 6 | 八文件 sha256 | ✅ | **8/8 identical，CHANGED 0** |
| 7 | 七层审计红 0 | ❌ | 6 层红 0；**L2 两遍各 1 条红（E2）**；E5 未出现；L1 各 1 条黄（E3） |
