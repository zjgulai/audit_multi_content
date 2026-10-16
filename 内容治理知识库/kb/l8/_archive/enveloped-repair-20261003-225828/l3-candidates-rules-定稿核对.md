# kb/l3/candidates/rules.jsonl · 定稿状态核对

**核对口径**：`kb-canonical-lookup`（L4 定稿与发布层只读查询）§1.3 —— 规则在 `kb/l4/canonical/`
四个形态文件里命中 = 已定稿（已发号）。
⚠️ 不查 `kb/l4/canonical/rules.jsonl`：它恒 0 字节，是迁移留痕；查它返回空**不等于**「没定稿」。

---

## 一句话结论

文件里 **1018 行 = 509 条规则 × 2 行** —— 同一个 `rule_id` 各出现两次，两行**逐字段相同，
只有 `article_no` 一个字段不同**（这 509 对全部核对过）。

**509 条规则全部已经定稿**：都在 `kb/l4/canonical/` 命中，`status="stable"`，
各有唯一条款号（`W-1.1–W-1.56` 词条型 56 条 / `W-2.1–W-2.453` 修订对型 453 条）。

**但没有一条能当「已发布版本」用** —— 晋升档位停在「机器晋升（machine-promoted）· 人工抽查未做」。

**另有 56 条（全部 `W-1.*`）虽已定稿，却被显式排除出判断层。**

---

## 三个档位，别混成一个「定稿了没」

| 档位 | 条数 | 依据 |
|---|---|---|
| ① 已发号 · 已编号的定稿快照 | **509 / 509** | canonical 命中；`status=stable`；`promotion_basis` C1–C8 实测 8/8 通过 |
| ② 已发布版本（可当发布口径引用） | **0 / 509** | `promotion_rule.status = 机器晋升（machine-promoted）· 人工抽查未做`；enum 第三档 `抽查通过（human-verified）` 未达到 |
| ③ 可进判断层 | **453 / 509** | 56 条 `W-1.*` 被 `l3.json → e021_concepts` 标注「未验证、不得进判断层」 |

所以「能当定稿用」的准确答法是：**当①用，509 条全可以用；当②用，一条都不行。**

---

## 不能当定稿用的，逐类标出来

### A. 509 行 `article_no: ""` —— 它们不是「还没定稿的规则」

- **第 1–509 行**：`article_no` 全为空；**第 510–1018 行**：带条款号。
- 这 509 条空号行与第 510–1018 行**是同一批规则**（`rule_id` / `rule_text` / `anchor` 全同），
  不是另外 509 条待定稿候选。
- **陷阱**：按行读、每条 `rule_id` 只取第一次出现，会得到「509 条候选、一条号都没发」的结论，**这是错的**。
- 第 1–509 行与重建前快照 `kb/l4/_pre-rebuild-20260930-1550/rules.candidates.jsonl.bak`
  **逐字节相同**（sha256 `54691908da8e8b59f4ca5e3affd6a565bc760b614258052cc0646a17c70cab1d`）。
- 该次运行自己的 `reproduce` 契约写的是「追加 0 行、`kb/l3/candidates/rules.jsonl` 逐字节不变」，
  而 `inputs` 实记为 `appended_this_run: 509`、`prefix_unchanged: false` —— **运行违反了自身契约**。

### B. 56 条 `W-1.*` —— 已定稿，但**不得进判断层**

`kb/l3/registry/l3.json → e021_concepts`：56 条（= 全部词条型规则）判 `已排除`，
理由原文：「三重验证是人工判断闸门；派生视图无权替人打分，编一个等于把闸门变成自我申报。
故明确标注『未验证、不得进判断层』并从本批产出中排除」。`已补三重验证: 0`。

| 条款号 | p_level | authority | 触发词（截断） |
|---|---|---|---|
| W-1.1 | P0 | expert | mimics baby；mimics baby,mimics baby’s natural  |
| W-1.10 | P0 | inferred | （无触发词，建议表达型） |
| W-1.11 | P1 | expert | hospital grade；hospital grade,hospital-grade；h |
| W-1.12 | P1 | inferred | super strong, ultra powerful, max suction, str |
| W-1.13 | P0 | expert | ibclc-recommended,recommended by 100+ experts； |
| W-1.14 | P0 | inferred | （无触发词，建议表达型） |
| W-1.15 | P3 | inferred | insurance eligible, HSA, FSA, insurance covere |
| W-1.16 | P1 | inferred | last chance, limited time, final hours, don't  |
| W-1.17 | P1 | expert | better milk flow；improve milk flow；improve mil |
| W-1.18 | P0 | expert | augmente la production de lait；boost supply,mo |
| W-1.19 | P1 | inferred | military grade, medical grade silicone, hospit |
| W-1.2 | P0 | inferred | （无触发词，建议表达型） |
| W-1.20 | P1 | expert | 22% slimmer than |
| W-1.21 | P0 | inferred | （无触发词，建议表达型） |
| W-1.22 | P0 | inferred | safest, most safe, 100% safe, 100% painless, z |
| W-1.23 | P2 | inferred | （无触发词，建议表达型） |
| W-1.24 | P0 | inferred | （无触发词，建议表达型） |
| W-1.25 | P1 | expert | 28% faster；28% faster,trusted by 6 million；28% |
| W-1.26 | P3 | inferred | sore nipples, sore breasts, sore breast, painf |
| W-1.27 | P1 | expert | ibclc |
| W-1.28 | P1 | inferred | （无触发词，建议表达型） |
| W-1.29 | P1 | inferred | （无触发词，建议表达型） |
| W-1.3 | P1 | inferred | （无触发词，建议表达型） |
| W-1.30 | P2 | inferred | suction level, suction levels, adjustable suct |
| W-1.31 | P0 | inferred | auto-detects rhythm, automatically detects you |
| W-1.32 | P2 | inferred | （无触发词，建议表达型） |
| W-1.33 | P0 | expert | perfect pump |
| W-1.34 | P2 | inferred | （无触发词，建议表达型） |
| W-1.35 | P1 | expert | hospital；krankenhaus |
| W-1.36 | P1 | inferred | better than, vs competitors, compared to other |
| W-1.37 | P1 | inferred | （无触发词，建议表达型） |
| W-1.38 | P1 | inferred | （无触发词，建议表达型） |
| W-1.39 | P2 | inferred | （无触发词，建议表达型） |
| W-1.4 | P0 | inferred | 10x better, 10x more, better than medela, bett |
| W-1.40 | P3 | inferred | hospital, NICU, nicu grade, 医院, 新生儿 |
| W-1.41 | P0 | inferred | doctor recommended, recommended by doctors, pe |
| W-1.42 | P1 | inferred | （无触发词，建议表达型） |
| W-1.43 | P0 | inferred | treat, cure, heal, remedy, diagnos, 治疗, 治愈, 诊断 |
| W-1.44 | P1 | inferred | reduce milk leakage, reduces milk leakage, red |
| W-1.45 | P2 | inferred | （无触发词，建议表达型） |
| W-1.46 | P2 | inferred | （无触发词，建议表达型） |
| W-1.47 | P0 | inferred | prevent mastitis, mastitis treatment, clogged  |
| W-1.48 | P3 | inferred | lactation consultant, ibclc, 母乳指导, 泌乳顾问, exper |
| W-1.49 | P1 | expert | maximum suction；strong suction；succión potente |
| W-1.5 | P1 | expert | cicha；quiet；silencieux；silenciosa,silencioso；u |
| W-1.50 | P1 | expert | don't miss；limited time |
| W-1.51 | P1 | inferred | 30% more milk, 20% faster, 2x faster, 3x more, |
| W-1.52 | P1 | inferred | （无触发词，建议表达型） |
| W-1.53 | P0 | expert | indolore；indolore,sans douleur；no pain,painles |
| W-1.54 | P1 | inferred | silent, whisper quiet, zero noise, noiseless,  |
| W-1.55 | P0 | expert | painful pumping |
| W-1.56 | P0 | inferred | （无触发词，建议表达型） |
| W-1.6 | P0 | inferred | eliminates pain, pain-free, no pain ever, comp |
| W-1.7 | P1 | inferred | EMPTY:<文案为空/非文本广告> |
| W-1.8 | P0 | inferred | FDA approved, FDA certified, FDA 认证, FDA 批准, F |
| W-1.9 | P0 | inferred | clinically proven, clinically tested, clinical |

这 56 条里 **41 条 `authority=inferred`**（模型归纳、无外部权威背书），只有 15 条 `expert`。

### C. 全部 509 条 —— 都不能当「已发布版本」

`kb/l4/_pre-rebuild-20260930-1550/l4.registry.json.bak → promotion_rule.what_it_means` 原文：
「canonical 的 1242 条定稿记录是由下列可复算判据**机器**晋升的，不是人工抽查通过的。
因此**只允许当「已编号的定稿快照」用；不允许当「已发布版本」用**。」
`human_spotcheck.done = false`；`kb_version` 仍 `v0`，未冻结版本、未产生 `release_id`。

---

## D. 必须先修的不一致：登记表说「0 条定稿」，canonical 说「509 条」

同一层两个真源现在互相打脸，**这决定了你按哪边答会得到相反结论**：

| | 重建前 `l4.registry.json.bak`（run `20260929-1100`） | 现在 `kb/l4/registry/l4.json`（run `20260930-1550`） |
|---|---|---|
| `canonical.state` | 「已填：四个形态文件，共 **1242** 条定稿记录；status=stable」 | 「**空**（本批不写…）」（指向 0 字节的 `canonical/rules.jsonl`） |
| `promotion_rule.status` | 「机器晋升（machine-promoted）· 人工抽查未做」 | 「**待抽查（本批不做）**」 |
| `numbering.issued` 段 | `W-1` `W-2` `W-3` `S-1` `E-1` = **1242** 个号 | 只剩 `W-1` `W-2` = **509** 个号 |
| `assignments` | **1242** 条 | **509** 条 |
| 键 | 另有 `totals_20260924-1320`、`repromotions` | **两个键都没了** |

- 登记表被重建时**回退**了：丢掉 `W-3` / `S-1` / `E-1` 共 **733 个已发条款号**
  （即 `sample_cases.jsonl` / `scoped_clauses.jsonl` 那 733 条定稿的登记），
  `canonical` 与 `promotion_rule` 也被写回成「空 / 待抽查」。
- **对本次问题的影响**：`rules.jsonl` 这 509 个号在新登记表里**仍在册**（`W-1` 56 + `W-2` 453），
  与 canonical 文件逐条比对 **0 处不一致**，所以 509 条已定稿这个结论不受影响。
  但**谁只读 `l4.json` 判「定稿了没」，会对这 509 条全答「没定稿」**。
- 按 `kb-canonical-lookup` 红线：此项**只报告、不代为修复** → 交 `kb-check`（体检）/ `kb-repair`（修复）。

### 附：一处次要缺口
候选文件里 `owner` / `effective_from` **全为空**，且**没有 `half_life_days` / `valid_until` 两个键**；
而 canonical 记录里这 4 个字段都有值（`owner` 角色位、`effective_from=2026-09-29`、
`half_life_days ∈ {365,90,180}`、`valid_until ∈ {2026-12-28,2027-03-28,2027-09-29}`）。
`l3.json → changes` 记着 run `20260929-1040` 对这 509 条做过这 4 个字段的 backfill —— 候选文件与自己的变更记录对不上。

---

## 逐条明细

- `l3-candidates-rules-定稿明细.tsv` —— 509 行，列含
  `article_no` / `rule_id` / `form` / `status` / `verification` / `support_count` /
  `authority` / `p_level` / `judgment_layer` / `l3_lines`（两行行号）/ `canon_file` / `canon_line` / `text`。

分布：`stable` 509 · `W-1` 56 / `W-2` 453 · `P0` 21 / `P1` 477 / `P2` 7 / `P3` 4 ·
`authority` expert 416 / inferred 93 · `verification` 已归纳 62 / 待验证 447 ·
判断层显式排除 56。
