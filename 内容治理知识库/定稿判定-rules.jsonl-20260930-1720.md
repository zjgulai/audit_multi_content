# `kb/l3/candidates/rules.jsonl`：哪几条能当定稿用 / 哪几条不能

- **判定时间**：2026-09-30 17:20（CST）
- **被判文件**：`kb/l3/candidates/rules.jsonl` — 1018 行 ｜ 2,778,734 字节
  ｜ `sha256 = aa83d1f98bc86857254bfa4f908ebd6d1a869f868cb04970522d154f776b0dac`
- **逐条标记**：`定稿判定-rules.jsonl-20260930-1720-逐条标记.jsonl`（632 条 + 1 行 summary）
  与 `定稿判定-rules.jsonl-20260930-1720-逐条标记.csv`
- **复算**：`python3 _gen-定稿判定-20260930-1720.py`
- **闸门**：`kb/kbpy l7/scripts/l3_gate.py` → 退出 0；`kb/kbpy l7/scripts/l4_gate.py` → 退出 0（C1–C6 全过）
- 本次**只读判定**：除三个交付文件（都在 `kb/` 之外）外未写任何库内文件

---

## 一、两句话结论

1. **`rules.jsonl` 里的 509 条规则，一条不落，全部已定稿** —— 全部有条款号（`W-1.1…W-1.56` + `W-2.1…W-2.453`），
   全部命中 `kb/l4/canonical/` 的 `status=stable` 记录，双向差集为 0。
2. **"不能当定稿"的规则不在这个文件里** —— 在隔壁 `kb/l3/candidates/external_standard.jsonl`，**123 条**，
   全部无号、无 owner、`verification=待人工复核`，本批没有发号通道。

| | 条数 | 在哪 | 一句话状态 |
|---|---|---|---|
| **能当定稿用** | **509** | `rules.jsonl`（每个 `rule_id` 带号的那一行） | 已编号的定稿快照，可引用 |
| **不能当定稿** | **123** | `kb/l3/candidates/external_standard.jsonl` | 候选件，无号、无 owner、待人工复核 |

> **限定语必须一起说**：这 509 条是**机器晋升（machine-promoted）**。
> 这是 L4 层自己在 `kb/l7/registry/layers.yaml` 的 L4 `notes` 里写死的口径 ——
> 「本批为 machine-promoted —— **只允许当「已编号的定稿快照」用，不允许当「已发布版本」用**」。
> 做引用、做审查依据：可以。说"我们发布了 v1 规则集"：不可以（`kb_version` 仍 `v0`，不产生 `release_id`）。

---

## 二、读这个文件前必须先看穿的坑

**1018 行 ≠ 1018 条规则，是 509 个 `rule_id` × 2 行**：

| 行的来历 | 行数 | `article_no` |
|---|---|---|
| L3 候选行（蒸馏产出） | 509 | **空** |
| L4 追加行（`l4_article.py:168` 以 `'a'` 模式追加，旧行逐字节不动） | 509 | `W-1.x` / `W-2.x` |

**实测 509 组，两行之间差异字段只有 `article_no` 一个，0 组例外。** 所以：

- 只看头 509 行、或只看 `article_no` 为空的那一行 → 会得出"一条都没定稿"的**错误结论**；
- 正确读法：**按 `rule_id` 分组，取带号的那一行**；或**直接以 `kb/l4/canonical/` 为准**；
- **判"定稿了没"永远不要看候选文件里的 `article_no` 字段** —— 那个字段按约定就该是空的。

顺带纠一个更常见的误读：**`kb/l4/canonical/rules.jsonl` 恒 0 字节**（历史迁移留痕，故意保留），
查它取"没定稿"也是错的 —— 定稿在四个形态文件里，不在这个空文件里。

---

## 三、判定依据（四条，全部可复算）

| # | 检查 | 实测 |
|---|---|---|
| 1 | 带号行是否命中 L4 canonical | **509 / 509** 命中 `wording_entry.jsonl`(56) + `wording_revision_pair.jsonl`(453)，全部 `status=stable` |
| 2 | 双向差集 | 候选有定稿没有 **0**；定稿（有 `rule_id` 的 509 条）候选没有 **0** |
| 3 | 条款号唯一性 | canonical 1242 条 `article_no` 唯一 1242 个；`rules.jsonl` 带号行 509 个号互不重复 |
| 4 | 闸门 | `l3_gate.py` 退出 0（证据全可回指）；`l4_gate.py` 退出 0（C1–C6 全过） |

L4 定稿总量 1242 条 = 509 规则（`W-1`56 + `W-2`453）+ 358 `sample_case`（`S-1`201 + `W-3`157）
+ 375 `scoped_clause`（`E-1`375）。

---

## 四、能当定稿的 509 条里，**必须先加限定语才能引用**的 6 类

逐条旗标写在标记文件的 `flags` 字段里。**限定语不是"不能当定稿"，是"引用时要一起说"。**

| 旗标 | 条数 | 引用时必须一起说 |
|---|---|---|
| `support_count=1·verification=待验证` | **447** | 单条修订支撑，L4 自己标 `verification=待验证`。别把它当"多来源互证过的规则" |
| `risk_level=unknown·源表无风险等级字段` | **454** | 源表（专家修订汇总表）没有风险等级字段，L4 按 P1 兜底。不是缺数据，是源头没有 |
| `authority=inferred·模型归纳无外部权威背书` | **93** | **模型归纳，不是外部标准**。引用这类要说清"这是归纳推断" |
| `E021·未过三重验证·不得进判断层` | **56** | **见下方专门一节** |
| `半衰期90天·valid_until=2026-12-28` | **22** | 这批最先到期，是最近一个复核窗口 |
| `候选副本与定稿漂移` | **49** | 见下方"以谁为准" |

### 4.1 那 56 条要单独说一句（唯一一类"有使用禁区"的）

`kb/l3/registry/l3.json → e021_concepts` 把这 **56 条 `form=entry`（全部是 `W-1.*`）判为"未过三重验证、
不得进判断层"**（`verdicts: 已排除 × 56`，`concepts=56`，`mapped_rule_ids=56`），原话是：

> 三重验证是人工判断闸门；派生视图无权替人打分，编一个等于把闸门变成自我申报。
> 故明确标注「未验证、不得进判断层」并从本批产出中排除

**这不是"它们不算定稿"** —— 它们在 canonical 里是 `status=stable`、有号、有 owner。
但它给出了一个**使用禁区**：

| | |
|---|---|
| ✅ 可以 | 当**引用材料**用（原文摘录、条款号回溯、证据锚点） |
| ❌ 不可以 | 进**判断层**当判据（"这条命中 W-1.x，所以判 BLOCK"）—— 那是三重验证没过的东西 |

**完整列表**：`W-1.1 … W-1.56`（即 `W-1` 整段 56 个号，一个不多一个不少）。

### 4.2 那 49 条的"以谁为准"

候选副本与 L4 定稿在三个关键字段上不一致，**方向两边都有**，不是"L4 一律升级"：

| 字段 | 条数 | 方向（候选 → 定稿） |
|---|---|---|
| `p_level` | 42 | P1→P0 ／ P2→P1 ／ P1→P2 ／ P2→P0 ／ P1→P3 五个方向都出现 |
| `rule_code` | 21 | 候选为空 → 定稿补出 `H06/H07/H08/M01…` |
| `suggested_replacement` | 12 | 候选值 12/12 都是多规则字符串拼接，定稿换成了属于本条那条规则的替换建议 |

**一个反直觉的例子**：`r-006445396c95aa10`（`W-1.1`）候选副本写 `p_level=P2`，
L4 定稿写 **`P0`**，理由在 canonical 的 `p_level_basis`：「全部支撑记录的风险等级均为高危·红 → P0」。

**结论：候选文件不是定稿正文的可信来源；引用一律回 `kb/l4/canonical/`。**
（另：`owner` 字段候选全空，定稿才有 —— `法务`474 ／ `法务 + 产品负责人`14 ／ `法务 + 渠道负责人`13 ／ `法务 + 医学顾问`8。）

### 4.3 把限定语叠起来之后，真正"无保留可用"的只有 6 条

同时满足 **① `authority=expert`（有外部权威背书，不是归纳）② `support_count ≥ 2`（多来源支撑）
③ 未被 E021 排除（可进判断层）** 的，只有 **6 条**：

| 条款号 | `rule_id` | `support_count` | owner |
|---|---|---|---|
| `W-2.36` | `r-14056187c2923e38` | 57 | 法务 |
| `W-2.73` | `r-30c3d9dbd0f5f2a0` | 18 | 法务 |
| `W-2.116` | `r-49a58aca87e2b71d` | 47 | 法务 |
| `W-2.130` | `r-5129868cac83a174` | 74 | 法务 |
| `W-2.228` | `r-8380b74f7d98d063` | 246 | 法务 |
| `W-2.277` | `r-a1a9c278662bcad2` | 4 | 法务 |

**这不是说另外 503 条不能用** —— 它们照样是定稿快照。这只是说：
**能不加任何限定语直接当"硬规则"用的，就这 6 条。**
注意这 6 条**全部落在 `W-2` 段**：`W-1` 整段 56 条一条都没进（它们是 `form=entry`、被 E021 排除、49/56 还带着字段漂移）。
**`W-1` 段是这批数据里最需要人看一眼的一段。**

---

## 五、"不能当定稿"的 123 条：不在这个文件里，而且现在也发不了号

`kb/l3/candidates/external_standard.jsonl`（123 行，`sha256 = 7e3ac8ae…`）实测：

| 字段 | 值 |
|---|---|
| `status` / `rule_status` | 全部 `candidate` / 全部 `provisional` |
| `article_no` | **全部为空（123/123 未发号）** |
| `verification` / `evidence_level` | 全部 `待人工复核` / 全部 `cited` |
| `owner` | **全部为空** |
| `kb_type` | 全部 `external_standard` |
| `form` | recommendation 36 ｜ substantiation 24 ｜ disclosure 18 ｜ prohibition 16 ｜ scope 15 ｜ mandate 14 |
| `applicable_jurisdiction` | 全部 `US` |

**发号通道的现状**（只报实测到的边界，不替它下因果结论）：
按 `kb/l7/registry/layers.yaml` 的 L4 `outputs` 登记，本层引擎 `l4_article.py` 的产出**只有四个形态文件**
（`wording_entry` / `wording_revision_pair` / `sample_case` / `scoped_clause`），**不含 `external_standard`**；
而这 123 条的六个 `form` 值与编号方案的 `form_block`（`entry/revision_pair/boundary/saythis`）**零交集**（实测 `set ∩ = ∅`）。
→ **本批没有它的发号通道**。要发号得先动编号方案，那是另一件事，不是顺手能做的。

> ⚠️ 一处不能照抄的推论：`scoped_clause` 的 `form` 值 `scoped_clause` **同样不在 `form_block` 里，但它拿到了 `E-1.1…E-1.375`**。
> 所以"form 不在 form_block 里 → 发不了号"**作为一般规则是错的**。
> 这 123 条当下发不了号是**实测事实**（无号、无 owner、无引擎通道），原因待确认，**不要当成已证因果**。

---

## 六、判完之后，三件"别被台账带偏"的事（只报告，不改库）

1. **L4 台账 `l4.json` 里写着"canonical 是空的"**
   `canonical.state = "空（本批不写；定稿要过抽查闸门，抽查是人工环节，不在本批）"`，
   而 canonical 四个文件里躺着 **1242 条 `stable`** —— **台账与事实自相矛盾**。
   → **判"定稿了没"不要读这个字段**，要读 canonical 文件本身。
2. **同一次重建还写丢了 733 个已发号码的台账登记**
   现台账 `numbering.issued` 只有 `W-1`(56) + `W-2`(453) = **509**；
   canonical 里另有 `S-1`201 + `W-3`157 + `E-1`375 = **733 个号**没进台账，
   `next_seq` 也只有 `W-1=57 / W-2=454`，没有 `S-1 / W-3 / E-1` 三个续号游标。
   **这不影响 509 条的定稿成立**（canonical 文件本身没被动，两个闸门仍过），
   但意味着：**谁现在拿这份台账跑一次 `l4_article.py --apply`，`S-1 / W-3 / E-1` 三段可能被当成从没发过号 → 撞号。**
   修它要走 `kb-repair` 或人决定用备份（`kb/l4/_pre-rebuild-20260930-1550/`）回灌还是重发。
3. **`promotion_rule.status = "待抽查（本批不做）"`**
   台账明写晋升路径是「候选 → **抽查（人工）** → 定稿」，而 C7/C8（晋升后抽查、撤回纪律）
   **`l4_gate.py` 明说不复算 —— "它们要人抽检，不是机器判据"**。
   → 这 509 条的"定稿"是**机器晋升意义上的定稿**；**人工抽查闸门至今没有跑过的证据**。

---

## 七、复算方法

```bash
cd /Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理   # = kb/ 的上一级
kb/kbpy l7/scripts/l3_gate.py          # 退出 0
kb/kbpy l7/scripts/l4_gate.py          # 退出 0（C1–C6 全过；C7/C8 明说不复算）
python3 _gen-定稿判定-20260930-1720.py  # 重生成逐条标记
```

核心三行：

```python
import json
rows = [json.loads(l) for l in open('kb/l3/candidates/rules.jsonl') if l.strip()]
print('总行', len(rows), '｜唯一 rule_id', len({r['rule_id'] for r in rows}),
      '｜带号行', sum(1 for r in rows if r['article_no']))   # 1018 ｜ 509 ｜ 509
```

---

## 八、交付物

| 文件 | 是什么 |
|---|---|
| `定稿判定-rules.jsonl-20260930-1720-逐条标记.jsonl` | **主交付**：632 条（509 能 + 123 不能）＋ 1 行 summary。每条给 `verdict` / `blocking` / `allowed_use` / `canonical_ref` / `owner` / `valid_until` / `in_judgment_layer` / `flags` / `candidate_vs_canonical_drift` |
| `定稿判定-rules.jsonl-20260930-1720-逐条标记.csv` | 同上，给人眼看的表（18 列，带 BOM，Excel 直接开） |
| `定稿判定-rules.jsonl-20260930-1720.md` | 本文件 |
| `_gen-定稿判定-20260930-1720.py` | 生成器（只读 `kb/`，只写出上面三个文件） |

`verdict` 只有两个值：`能当定稿用`（509）／`不能当定稿`（123）。
"能当定稿"里带使用禁区的（56 条 `in_judgment_layer=false`）**不降级成"不能当定稿"** ——
它们确实已定稿，只是**不得进判断层**，这在 `in_judgment_layer` 字段里单独标。
