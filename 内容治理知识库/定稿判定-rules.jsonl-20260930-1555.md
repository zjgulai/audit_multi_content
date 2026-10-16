# `kb/l3/candidates/rules.jsonl` 定稿判定 —— 哪几条能当定稿用

**判定时间**：2026-09-30 15:55（CST）
**被判文件**：`kb/l3/candidates/rules.jsonl`
**判定时快照**：1018 行 ｜ 2,778,734 字节 ｜ `sha256 = aa83d1f98bc86857254bfa4f908ebd6d1a869f868cb04970522d154f776b0dac`
**逐条清单**：`定稿判定-rules.jsonl-20260930-1555.jsonl`（509 行，一个 `rule_id` 一行）

---

## 一、结论

| | 条数 | 说明 |
|---|---|---|
| **已定稿（可当定稿快照用）** | **509** | 全部已发号：W-1.1…W-1.56 + W-2.1…W-2.453 |
| **不能当定稿** | **0** | 本文件里没有一条是"还卡在候选、不能当定稿"的 |

**`rules.jsonl` 里的 509 条规则，一条不落，全部已经进 L4 定稿层并拿到条款号。**
"不能当定稿"的规则不在这个文件里，在隔壁 `kb/l3/candidates/external_standard.jsonl` —— **123 条**（见第四节）。

### 但"能当定稿用"要带一个限定词（必须一起说）

这 509 条是 **机器晋升（machine-promoted）**，**人工抽查未做**。按 L4 层自己的口径：

> 只允许当「**已编号的定稿快照**」用，**不允许当「已发布版本」**用。
> （`kb_version` 仍 `v0`，不产生 `release_id`，`versions.jsonl` 不追加版本行）

---

## 二、依据（三条，都可复算）

1. **定稿文件里逐条命中**
   `kb/l4/canonical/wording_entry.jsonl`(56) + `wording_revision_pair.jsonl`(453) = **509 条**，
   `status=stable`、`promoted_from=provisional`、`effective_from=2026-09-29`、`valid_until ∈ {2026-12-28, 2027-03-28, 2027-09-29}`（**无一条过期**）。
   与候选按 `rule_id` **一一对应**：候选有而定稿没有 0 条，定稿有而候选没有 0 条；
   `rule_text` / `anchor` / `evidence_units` / `evidence_digest` / `support_count` **逐字一致，0 处漂移**。
2. **台账三处全等**
   `kb/l4/registry/l4.json → assignments`(509) == 候选文件里的带号行(509) == canonical 的 `article_no`(509)。
3. **闸门放行**
   `kb/kbpy l7/scripts/l4_gate.py` 退出码 0：**C1–C6 全过**
   （1242 条定稿 ｜ 条款号唯一 ｜ 正文非空 ｜ 证据三件套齐备 ｜ 证据可回指 L2 单元 ｜ 定稿与候选逐字一致 ｜ `canonical/rules.jsonl` 保持 0 字节）。

---

## 三、最容易判错的三个坑（本次实测）

### 坑 1：同一个 `rule_id` 在文件里出现 **两行**

现在文件是 **1018 行 = 509 个 `rule_id` × 2 行**：

| 行的来历 | 行数 | `article_no` | `status` |
|---|---|---|---|
| L3 候选行（`kb/l8/l3_distill_run.py` 产出） | 509 | **`""`（空）** | `provisional` |
| L4 追加行（`kb/.work/l4_article.py` 写 canonical 时对 `kb/l3/...` 追加） | 509 | `W-1.x` / `W-2.x` | `provisional` |

**只看头 509 行、或只看 `article_no` 为空的那一行 → 会得出"一条都没定稿"的错误结论。**
正确读法：按 `rule_id` 分组，取带号的那一行；或以 L4 canonical 为准。

### 坑 2：15:52 之前这个文件只有 509 行、`article_no` 全空

那是 **L3 重建（写模式 `'w'` 覆盖）把 L4 追加的带号行冲掉了**，不是"没定稿"。
证据：`kb/l3/registry/l3.json → appended_fields.old_lines_untouched.sha256`
= `54691908…` = `kb/l4/_pre-rebuild-20260930-1550/rules.candidates.jsonl.bak` 的 sha
（即 L4 备份下来的那份"509 行、无号"原件）。
**判"定稿了没"永远看 L4，不看候选文件里的 `article_no` 字段。**

### 坑 3：不要查 `kb/l4/canonical/rules.jsonl`

该文件**恒 0 字节**（历史迁移留痕，故意保留）。查它必然返回空，**不等于**"这条没定稿"。
定稿在四个形态文件里：`wording_entry` / `wording_revision_pair` / `sample_case` / `scoped_clause`。

---

## 四、"不能当定稿"的到底在哪

不在 `rules.jsonl`，在 **`kb/l3/candidates/external_standard.jsonl`（123 条）**：

| 字段 | 值 |
|---|---|
| `status` | 全部 `candidate` |
| `rule_status` | 全部 `provisional` |
| `article_no` | **全部为空（未发号）** |
| `verification` | 全部 `待人工复核` |
| `evidence_level` | 全部 `cited` |
| `form` | recommendation 36 / substantiation 24 / disclosure 18 / prohibition 16 / scope 15 / mandate 14 |
| `applicable_jurisdiction` | 全部 `US` ｜ `owner` 全部为空 |
| 产出 | run `20260930-1400`，distiller `l3-clause-0.1`，源 8 个资源（Amazon Ads 政策等） |

L4 台账也明确说这几类库是空的：`numbering.totals.libraries_empty = ["external_standard", "internal_sample", "product_desc", "unknown"]`。
**这 123 条才是"还不能当定稿用"的** —— 它们只是候选，条款号要由 L4 发。

---

## 五、509 条的构成（便于按需取用）

| 维度 | 分布 |
|---|---|
| 形态 | `entry` 56（W-1.1…W-1.56） ｜ `revision_pair` 453（W-2.1…W-2.453） |
| 条款号段 | 全部 `W-*`（`3_措辞表达库`） |
| `authority` | `expert` 416 ｜ `inferred` **93**（模型归纳，无外部权威背书） |
| `rule_kind` | `atomic` 483 ｜ `inductive` 26 |
| `verification` | `已支持`（`support_count ≥ 2`） 62 ｜ `待验证`（`support_count = 1`） 447 |
| `evidence_level` | `synthesis` 62 ｜ `observation` 447 |
| `p_level` | P0 21 ｜ P1 477 ｜ P2 7 ｜ P3 4 |
| `valid_until` | 2027-03-28 466 ｜ 2026-12-28 22 ｜ 2027-09-29 21 —— **均未过期** |

可注明但不影响定稿成立的两点：
- `support_count = 1 → 待验证` 是 L3 的既定口径；对 `atomic`（一对修订天然只有一条支撑）**是正常的**，只有 `inductive` 才算证据不足 —— 而 26 条 `inductive` **全部** `support_count ≥ 2`，不存在证据不足的归纳型规则。
- L3 台账 `e021_concepts` 里，56 条 `form=entry` 被判「未过三重验证、不得进判断层」，那是**派生视图**（`kb/.work/gen-host-library*.py` 出 L1-facts/L2-concepts）的分层口径，不是 L4 定稿口径 —— 拿它们进评审链做判断依据时需另核，别把它读成"这 56 条不算定稿"。

---

## 六、判完之后需要人看的一件事（留痕，不自动修）

15:50–15:53 有一次 **kb-pipeline `--via-skill` 重建**（备份目录 `kb/l7/_backups/via-skill-20260930-152329`），它：

1. 把 L4 前置状态备份到 `kb/l4/_pre-rebuild-20260930-1550/`（含 `l4.registry.json.bak`，sha `7d53459a…`）；
2. 重跑 `l4_article.py` → `rules.jsonl` 509 → 1018 行（幂等：沿用原号，`newly_assigned=0`）；
3. **把 `kb/l4/registry/l4.json` 换成了精简版**：
   - `canonical.state` 从「已填（20260929-1100）：四个形态文件，共 1242 条定稿记录；status=stable」→「**空（本批不写…）**」；
   - `promotion_rule` 从带 C1–C8 判据/`human_spotcheck`/抽样方案的整块 → 缩成 5 行；
   - `repromotions` 与 `totals_20260924-1320` 两个字段**消失**；
   - 逐形态文件的 `lines/bytes/sha256` 记录消失。

**定稿文件本身没被动**（`kb/l4/canonical/*.jsonl` mtime 仍是 2026-09-29 10:32，行数 1242 不变，闸门仍过），
但**台账里"这 509 条是定稿、status=stable"的那句话，现在只存在于备份里**。
要不要把 `canonical.state` 与 `promotion_rule` 回写回去（或补一条 run 记录说明），是人的决定 —— 本次只报告，不改库。

---

## 七、复算方法

```bash
cd ~/.dsh/Momcozy知识库          # = kb/ 的上一级
kb/kbpy l7/scripts/l4_gate.py    # 退出 0 = C1–C6 全过
# 逐条判定（本文件同款逻辑）：按 rule_id 分组取带号行，
# 再与 kb/l4/canonical/{wording_entry,wording_revision_pair,sample_case,scoped_clause}.jsonl 比对
#   —— 跳过恒 0 字节的 kb/l4/canonical/rules.jsonl
```
