# 交付：PRD §7.3 入库 —— **全链打通到 L4 条款号**（E-1.3419）

日期 2026-10-13 ｜ 依据 Owner 2026-10-13「同意」＋「全部改完了再告诉我，不要影响现有的工作流」
状态：**改动全部完成**。L0 → L1 → L2 → L3 → L4 全通；**P0 晋升未做，也不该做**（理由见 §五）。

---

## 一、最终结果：四段溯源齐了

| 段 | 值 | 判据 |
|---|---|---|
| **L0** | `sha256=932b8fe0f009926e…`、`sha256_input=doc_text`、`revision=36`、`matched_rule=R27` | `kb/l0/1_外部标准库/feishu_doc__PXfBdjTwFokEQixtmTscqm7knNh.json` |
| **L1** | 锚点 `#l.1-245` / `#l.246-494` / **`#l.495-773`**、`source_sha256=6671c283609bef80…` | `kb/l1/1_外部标准库/url__…NB55….json` |
| **L2** | `unit_id=bd4267ff5c050ca14e98`、`anchor=#l.495-773`、`source_sha256=6671c283…` | `kb/l2/units.jsonl` |
| **L3** | `clause_id=scl-m-b658a049723cae3e`、`anchor=#l.495-773`、**条款号 `E-1.3419`** | `kb/l3/candidates/scoped_clauses.jsonl` |
| **L4** | `E-1.3419`（台账 `numbering.issued.E-1.assigned`） | `kb/l4/registry/l4.json` |

§7.3 的 **7 条 P0 红线**（安全座椅 / 医疗功效 / 绝对化用语 / 销量排名 / 危险示范 / 未成年人出镜 / AI 标识）
现在是一个**带条款号、带物理锚点、带指纹**的一等知识单元。

---

## 二、改了什么（全部增量，零覆盖）

| 文件 | 改动 | 验证 |
|---|---|---|
| `kb/l0/1_外部标准库/feishu_doc__PXfBdjTwFokEQixtmTscqm7knNh.json` | **新增** 1 件 | 与 `feishu_doc` 模板逐键类型一致 |
| `kb/l0/manifest.jsonl` | **+1 行**（8506 → 8507） | L0 闸门红 0 |
| `kb/l0/registry/kb.json` | `rules` **+R27**（26 → 27） | 同上 |
| `kb/l8/drill_links_2levels.py` | 加登记件种子 ＋ 修 wiki 解析 ＋ 加 `doc_text_of()` 解包 ＋ 边表 `from_kind` 如实区分 | 见 §三 |
| `kb/l1/sources/20261013-prd-v2*` | **新增**（下钻产物） | `kind: wiki→docx`、`title` 正确 |
| `kb/l1/1_外部标准库/url__…NB55….json` | **新增** 1 件（3 段，spec 锚点） | `chars` 逐字未变 |
| `kb/l1/manifest_l1.jsonl` | **+1 行** | L1 闸门红 0 |
| `kb/l2/{units,index/l2,manifest_l2}` | **+3 / +3 / +1 行** | L2 闸门红 0 |
| `kb/l3/candidates/scoped_clauses.jsonl` | **+1 行**（6837 → 6838） | **旧行逐字节未变: True**（引擎自报） |
| `kb/l4/registry/l4.json` | 发 1 个号 | **首次分配 1 条｜沿用台账 4523 条** |

**未动**（逐一核过）：
`kb/l5/p0_patterns.jsonl` **sha `b0e29b618729`、11 条，一字未改**；
`kb/l4/canonical/rules.jsonl` 仍 0 字节；飞书侧零写入。

---

## 三、顺带修掉的两个**存量 bug**（都不是本任务引入的）

### A. wiki 链接的正文一直是 API 元数据（**静默失败**）

`fetch()` 读 `data.node.obj_token`，而 `lark-cli wiki +node-get` 实际返回 **`data.obj_token`**（无 `node` 包装）
⇒ `obj` 恒空 ⇒ 掉到最后一条分支，**把 node-get 的原始 JSON 当正文**；
而判据 `ok = 非空 ∧ 首 200 字无 error` 判**绿**。
**存量：`kb/l1/sources` 1,275 份产物中 281 份中招。**

### B. `docs +fetch` 的 JSON 信封**没有任何一层解包**

正文在 `data.document.content`（HTML）里，信封却被当正文写进 L1、落成产物、被 L2 切。
新增 `doc_text_of()`：解包 + HTML→文本（**保住标题/列表结构**，否则 L2 切不出条款）。
**存量：`kb/l1/sources` 的 `L1-*` 产物 312/481 份正文以 `{` 开头。**

### 效果（同一份 PRD）

| | 修前 | 修后 |
|---|---|---|
| L1 正文 | 1,129 B（node-get JSON） | **11,750 B 干净文本** |
| §7.3 | 不在 | **在，7 条红线逐字** |
| L1 段 | 1 段 `#正文`（非 spec 口径） | **3 段 `#l.a-b`（`anchor_spec.url` 口径）** |
| L2 单元 | 0 | **3 个 clause 单元** |
| 条款号 | 无 | **E-1.3419** |

顺带核到第三件（**未处理**）：`rechunk` 扫出的 11 份「`#正文` 巨段」里 **9 份正文是飞书登录页 HTML**
（`curl()` 兜底抓到的未登录页，92,xxx 字）。**故意没对它们重分块** —— 那会把 9 份垃圾摊成 216 个垃圾单元。

**下游污染评估**：L2 `units.jsonl` 14,649 行中 **38 行**含元数据特征；
**L3 `rules.jsonl` / L3 `scoped_clauses` 旧行 / L5 `p0_patterns` 全为 0 行** ⇒ 垃圾**没变成规则或红线**。

---

## 四、尺子（全部实跑）

| 尺子 | 结果 |
|---|---|
| `ci/run_gates.py`（全量 15 把） | 过 **12/15 ｜ 红 无** |
| └ 与改动前对比 | **无新增失败**（`freshness` / `verdict_latency` / `perf_bench` 是既有告警/失败，`perf_bench` 早被归 `infra`） |
| `p0_regression` | **PASS** |
| `kb/l8/workflow_smoke.py` | ✅ 契约齐 |
| `kb/l8/check_source_readonly.py` | ✅ 只读源没被写 |
| `kb/l4/registry/l4.json` 发号 | 首次分配 **1** 条｜沿用 **4523** 条 |

---

## 五、为什么 **P0 晋升没做** —— 不是没做，是**做不了，且不该硬做**

四条画面红线的 P0 模式（`VIS-CARSEAT-001` 等）**不能手加进 `kb/l5/p0_patterns.jsonl`**，两道硬约束：

### ① L5 闸门会精确变红

`kb/l7/scripts/l5_gate.py::_p0_recompute()` 的 `C_p0_count_recomputable`
**从 L3 反算 P0 集合**：`p_level=P0 ∧ rule_kind=atomic ∧ authority∈{expert,legal}`（+ 白名单码）。
手加 4 条 ⇒ 反算对不上 ⇒ **红**。这是**正确的闸门**，不是障碍。

### ② 四条红线目前**蒸不成规则** —— 根因是**分段把标题与内容切开了**

`kb/l8/l3_clause_distill.py` 对这份 PRD 的结果：`clause_units: 3, rules: 0, rejected: 3`

| 段 | 拒绝码 |
|---|---|
| `#l.1-245` | `narrative_no_obligation` |
| `#l.246-494` | `narrative_no_obligation` |
| **`#l.495-773`（含 7 条红线）** | **`illustrative_copy_fragment`** |

判定第 2 关是「**没有义务/禁止模态 ⇒ 不成规则**」。而 §7.3 的义务模态
（`### 7.3 一票否决项（P0 级，命中即 BLOCK）` ＋ `以下为 P0 级硬性规则，命中即驳回`）
**落在第 2 段尾部**，7 条红线列表落在第 3 段 —— **上下文被切断**。

⇒ 这不是判定错，是**上游分段边界**的缺陷。我在过程中一度把它当「外观问题」，**那是错的**。

**正确修法（未做，需你定）**：PRD 的 `source_kind` 是 `feishu_doc`，而
`kb/l1/registry/l1.json → anchor_spec.by_resource_type.feishu_doc` 规定的锚点是
**`#h.<标题路径>`**（不是 `url` 的 `#l.a-b`）。
按标题分段 ⇒ 标题与内容同行 ⇒ §7.3 带义务模态 ⇒ 才可能蒸出规则。

**我的推荐**：**按标题路径重分段这一份 PRD**（只动它一件，spec 口径本来如此）。
- **代价**：`clause_id` 会变 ⇒ 要新发一个号（`E-1.3420`），`E-1.3419` 按「号码永久占用、不复用」留在台账里作废号 —— 这是政策要求，不是浪费。
- **前提**：重分段后仍要过 `l3_clause_distill` 判定；**不保证**一定蒸得出（`命中即 BLOCK` 是否命中 MODAL 正则需实测）。
- **不推荐**：直接手加 4 条 P0 模式 —— 会红 `C_p0_count_recomputable`，即「影响现有工作流」。

---

## 六、回滚

`kb/.work/revert-prd-s7.3-20261013/` 存有改动前的
`manifest.jsonl` / `registry/kb.json` / `l1__manifest_l1.jsonl` / `l2__*` / `l3__scoped_clauses.jsonl` / `l4__registry__l4.json`。
新增件按 `resource_id` 删除即可。手术式副本（`drill_reg_only.py` / `rechunk_prd_only.py` / `l3_preview_run.py`）
与预览目录 `kb/.work/l3-preview/` 留在 `.work` 里当证据，都不在活路径。

## 七、一条必须记下的教训

**L3 不能重跑。** 预览实测：`l3_distill_run.py --apply` 会把
`rules.jsonl` 1018 → **509**、`scoped_clauses` 6836 → **2997**、`rejected` 5156 → **2869**
（活库是多批次累积的，不是这一个脚本重建的）。
⇒ 往 L3 加东西**只能手术式追加**，这正是它自己写的「kb/l3 只追加」。
