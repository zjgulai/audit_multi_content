# P0 判定申诉依据单（独立复核版）

> 待申诉句：`increase milk supply, guaranteed results`
> 判定层：`kb-p0-check`（L5 P0 判定层，查询档只读，全文未写库）
> 复核人：本单由独立复核跑出，文中每条结论均附**实际执行过的命令与原始输出**
> 库版本：`kb_version = v0` ｜ 库根：本工作区（`kb/` 的上一级）
> 复核日期：2026-09-30

---

## 0. 一句话结论

这句被判**最高优先级（L5 `p_level = P0`，`match_note = BLOCK`）**，触发项**只有一处**：
子串 **`increase milk supply`** —— 关键词命中 + 正则命中，双命中同属一条模式
`p-755f9ff377c3052c`（规则码 **H02**）。

**`guaranteed results` 一个字节都没参与这次判定** —— 单独跑零命中（§3 有原始输出）。

但请注意边界：**「不是 P0」≠「没问题」**。后半句只是**没被 P0 层覆盖**，不构成本句可放行的依据。

---

## 1. 直接原因：命中的是哪一条模式

```bash
cd "<库根>"          # = kb/ 的上一级
python3 kb/l5/matcher.py --text "increase milk supply, guaranteed results" --json
# 退出码 1 = 有 P0 命中（matcher 以 1 表示命中）
```

原始输出（逐字，仅节选判定字段）：

| 字段 | 值 |
|---|---|
| `hits[0].pattern_id` | `p-755f9ff377c3052c` |
| `hits[0].rule_id` | `r-37b49eadb72d7dc2` |
| `hits[0].rule_code` | `H02` |
| `hits[0].level` | `P0` |
| `hits[0].match_note` | `BLOCK` |
| `hits[0].matched_count` | `2` |
| 命中 1 | `kind=keyword`，`pattern=increase milk supply`，`span=[0,20]` |
| 命中 2 | `kind=regex`，`pattern=\b(more\|increase[sd]?\|boost[s]?\|maximi[sz]e[sd]?)\s+(your\s+)?milk\b`，`span=[0,13]` |
| `whitelist_suppressed` | `0`（豁免规则一条都没触发） |

两个命中的**区间都落在句首 0–20 字符**，即全部由 `increase milk supply` 贡献。
`guaranteed results` 位于第 21 字符之后，**没有任何命中区间覆盖它**。

**为什么这一命中就等于「最高优先级」** —— `kb/l5/registry/l5.json` 的 `match_note_enum` 只有
一个取值 `["BLOCK"]`：该层不做轻重分级，命中即 BLOCK。这是「最高优先级」这个说法的技术来源。

---

## 2. 「P0」这个标签是怎么来的（四层依据链）

| 层 | 位置 | 取值 / 逐字 |
|---|---|---|
| L7 判定口径 | `kb/l7/registry/l7.json` → `decision_rules.BLOCK` | 首项 = `P0 命中（kb/l5/matcher.py）` |
| L5 模式表 | `kb/l5/p0_patterns.jsonl` 第 1 行 | `p-755f9ff377c3052c` / H02 / `p_level=P0` / `match_note=BLOCK` / `authority=expert` |
| L5 入选门槛 | `kb/l5/registry/l5.json` → `selection` | `p_level=P0` ∧ `rule_kind=atomic` ∧ `authority∈{expert,legal}` |
| **L4 定稿（P0 的真正理由）** | `kb/l4/canonical/wording_entry.jsonl` → `article_no = W-1.18` | `p_level=P0` ｜ `p_level_basis = "全部支撑记录的风险等级均为高危·红 → P0"` ｜ `risk_level=高危·红` ｜ `risk_evidence_records=34` ｜ `support_count=102` ｜ `owner="法务 + 医学顾问"` ｜ `authority=expert` ｜ `authority_source_table=广告文案明细` ｜ `effective_from=2026-09-29` ｜ `valid_until=2027-09-29`（未过期） |
| L4 发号 | `kb/l4/registry/l4.json` → `numbering.issued["W-1"].assigned["r-37b49eadb72d7dc2"]` | `W-1.18`（号码永久占用、不复用） |
| L3 候选 | `kb/l3/candidates/rules.jsonl` 第 **527** 行 | `article_no=W-1.18` ｜ `rule_code=H02` ｜ `status=provisional` ｜ `p_level=P2` ⚠（见 §4-③） |
| L0 源记录 | `kb/l0/records/广告文案风控库__广告文案明细/recvuJYdOb1fOj.json` | 外部广告ID `GG-39da941fc97a` ｜ Google ｜ 2026-09-09 ｜ **风险等级 高危·红** ｜ 处理状态 待人工复核 ｜ 投放状态 ENABLED |

**所以「为什么是最高优先级」的完整回答是两条：**

1. **机制上**：`increase milk supply` 逐字命中 L5 的 H02 模式，该层命中即 BLOCK。
2. **实体上**：H02 被判 P0 的依据写在 L4 定稿里 —— **它背后的 34 条源记录，在飞书《广告文案风控库 · 广告文案明细》里全部被人工标成「高危·红」**；规则内容是「催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效 claim，无 FDA/临床证据）」，署名 owner 为「法务 + 医学顾问」。

规则判据逐字（`kb/l3/candidates/rules.jsonl` 第 527 行 → `reason`）：

> H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；M01 静音程度夸大（建议改为 low noise / quiet mode）

---

## 3. `guaranteed results` 不是触发项（对应「不服气」的那一点）

```bash
python3 kb/l5/matcher.py --text "guaranteed results" --json
# → {"elapsed_ms": …, "hits": []}   退出码 0
```

```bash
python3 kb/l5/matcher.py --text "increase milk supply" --json
# → 命中 p-755f9ff377c3052c / H02 / P0，与整句结果完全一致
```

**结论成立**：全库 P0 模式表里检索 `guarantee` → **0 处**。
没有任何 P0 模式覆盖「结果保证 / guaranteed results」本身。
若运营的申辩点是「`guaranteed results` 凭什么判 P0」——**这一条成立，它不是 P0**。

但要如实说明：`guaranteed` 在规则层的其他码里出现过（`guaranteed safe` 走 W-1.22 虚假安全、
`Guaranteed No Pain` 走 W-2.369 疼痛功效），**全部是 P1，且没有一条覆盖 `guaranteed results` 这个组合**。
这属于**覆盖缺口**（库没写这一条），**不等于合规**。

---

## 4. 申诉可用的技术点（每条都独立复现过）

### ① 锚点错位：被引用的那条记录里根本没有这句话 —— 可要求对方补正

模式行顶层 `anchor` = `#广告文案明细/recvuJYdOb1Rm1/命中片段`，
但其指向的源记录 `recvuJYdOb1Rm1` 的「命中片段」**逐字是**：

> `H02:easier letdown / M01:whisper,whisper-quiet`

**不含 `increase milk supply`**。也就是说，**支撑本条判定的锚点与本词条不同源**。

该词条真正的逐字落点在另外三条记录（均在模式的 102 个证据单元内，均 `<source_sha256>` 复算通过）：

| 源记录 | 命中片段（逐字） | `source_sha256`（完整，已复算） | 外部广告ID |
|---|---|---|---|
| `recvuJYdOb1fOj` | `H02:increase milk supply,more milk / M07:better milk flow` | `3f80e285066d73f0cc01ea59869fe5ee086091c4fa013ff887f772d69fdcfc4c` | `GG-39da941fc97a` |
| `recvuJYdObLnyQ` | `H02:increase milk supply,more milk / M07:better milk flow` | `3c47b7b1e3df4737f0d55cad46ffac67088245de3662279ec5121363fa211741` | `GG-8aef74bb0f52` |
| `recvuJYdOb61lT` | `H02:increase milk supply / H07:pain-free / H09:mimics baby,mimics baby's natural nursing` | `67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e` | — |

**指纹本身是真的**：`c77f576dcc392cb3e763e6462d0259e50fb039f924a4af8e100321197e5be577`
经复算 = 对 `recvuJYdOb1Rm1` 的 **27 个字段**按 `field_id` 升序规范化后取 sha256
（`sha256_input = "record_fields"`，剔除 `last_modified_time` / `last_modified_by`）。
**指纹对得上，问题只在「锚点指向了哪条记录」** —— 这条可以要求补正，但**不足以推翻判定**。

### ② 规则自己推荐的「合规替代」，会被自家匹配器判 BLOCK —— 最硬的一条

H02 源记录的「修改建议」逐字推荐了这句合规替代：

> relaxation supports your natural let-down, which may help your flow

把它丢回匹配器：

```bash
python3 kb/l5/matcher.py --text "relaxation supports your natural let-down, which may help your flow" --json
```

实测结果：

| 字段 | 值 |
|---|---|
| 命中 | `p-755f9ff377c3052c` / **H02 / P0 / BLOCK** |
| 命中方式 | `kind=regex`，`pattern=\blet[\s-]?down\b`，`span=[33,41]`（即 `let-down`） |
| `whitelist_suppressed` | `0` |

**即：规则说「这样写可以」，运行时说「这样写也 BLOCK」。**

根因是**接线缺口**（已核实到代码行）：

- `kb/l5/registry/l5.json` → `whitelist_policy.rule_specific_allowed.H02 = ["relaxation","relax","natural let-down","放松","自然奶阵"]` —— 例外清单**登记在册**；
- 但 `kb/l5/matcher.py` 第 51 行编译豁免时**只读模式行自带的 `whitelist` 字段**
  （6 条否定/引用语境），**从不读 `rule_specific_allowed`**。

这直接说明 H02 的匹配面**过宽**：`\blet[\s-]?down\b` 把「自然奶阵」这个**规则明确允许的**表达一并吃掉。
本句虽由**关键词**命中（不走这条正则），但同一模式的正则是过宽的 ——
可用于主张「该模式的精确率存疑、判定口径需要收窄后重判」。

### ③ 上游规则是草案：无责任人、无生效日、无风险等级

`kb/l3/candidates/rules.jsonl` 第 1 行与第 527 行（同一 `rule_id` 出现两次）：

| 字段 | 值 |
|---|---|
| `status` | `provisional`（草案） |
| `owner` | `""`（空 —— 无具名责任人） |
| `effective_from` | `""`（空 —— 无生效日） |
| `risk_level` | `"unknown"` |
| `p_level` | `P2` ⚠ 与 L4 定稿的 `P0` **不一致** |
| `evidence_level` | `synthesis`（综合归纳，非逐字引用） |
| `verification` | `已归纳` |

全库实测（1018 行）：**带 `authority` 键的行 = 0；带 `rule_kind` 键的行 = 0；
`owner` 非空的行 = 0；`effective_from` 非空的行 = 0。**

→ 可主张：**P0 所依赖的上游规则尚未定稿、无人署名、无生效日**。

### ④ 当前活库已无法复核「H02 是 P0 / atomic / expert」这一入选前提

- L5 **入选门槛**（`kb/l5/registry/l5.json` → `selection`）：`p_level=P0 ∧ rule_kind=atomic ∧ authority∈{expert,legal}`；
- L5 **导出当时的实况**（`kb/l5/runs/20260923-1430.json`，`verdict=PASS`）：
  `precondition_a.组合分布["atomic|expert|P0"] = 6`，全库 `p_level` 分布 `P0=21 / P1=477 / P2=7 / P3=4` —— H02 在入选集合内；
- **当前**活库（`kb/l3/candidates/rules.jsonl`，1018 行，mtime 2026-09-30 15:52）：
  `p_level` 分布 **`P1=986 / P2=32`，`P0 = 0`**；且**没有任何一行带 `authority` / `rule_kind` 键**；
  H02 那两行（第 1、527 行）都是 **`P2`**。

→ **P0 所依赖的入选前提，在今天的活库里已经无法重新推导出来。**
本条**据实报告、不替它定性**（是追加行丢失还是后续重建覆盖，需交 `kb-check` 的条目基线比对去核）。

### ⑤ 同一条规则的候选行重复

`rule_id = r-37b49eadb72d7dc2` 在 `kb/l3/candidates/rules.jsonl` 里出现 **2 次**：
第 **1** 行（`article_no` 为空）与第 **527** 行（`article_no = W-1.18`），其余字段一致。
可要求一并清理，避免申诉时被反问「你引的是哪一行」。

---

## 5. 不能拿去申诉的三点（写清楚，免得被一句话驳回）

1. **未命中 ≠ 合规。** `guaranteed results` 零命中只说明它**不在 P0 层覆盖面内**，是**覆盖缺口**，
   不构成放行依据。别把它当免死金牌用。
2. **两套「优先级」不是同一个字段。** 运营说的「最高优先级」是 **L5 层的 P0**（命中即 BLOCK）；
   而 L3 规则候选行自己的 `p_level` 现在是 **P2**。申诉文里必须写明 **「L5 P0」**，
   混用口径会被直接驳回。
3. **`increase milk supply` 的命中是确定性的，不是语义推断。**
   该词条在 `kb/l5/registry/l5.json` → `term_grounding` 标为 **`verbatim_source`**（逐字取自源侧「命中片段」，非归纳），
   正则另覆盖 `more / increase / boost / maximize + (your) milk` 的词形变化。
   **要推翻只能攻「这条规则是否该管这一句」与「依据链是否有效」，攻「没命中」必败。**

---

## 6. 复现清单（逐条可跑，结果可对账）

```bash
cd "<库根>"    # kb/ 的上一级

# 1) 待申诉句 → 命中 H02 / P0 / BLOCK，退出码 1
python3 kb/l5/matcher.py --text "increase milk supply, guaranteed results" --json

# 2) 只留后半句 → 零命中（证明触发项是前半句）
python3 kb/l5/matcher.py --text "guaranteed results" --json

# 3) 只留前半句 → 与整句同结果
python3 kb/l5/matcher.py --text "increase milk supply" --json

# 4) H02 自己推荐的合规替代 → 仍被判 H02 / P0 / BLOCK（接线缺口）
python3 kb/l5/matcher.py --text "relaxation supports your natural let-down, which may help your flow" --json

# 5) 锚点错位：被引记录里没有这个词条
python3 -c "import json;d=json.load(open('kb/l0/records/广告文案风控库__广告文案明细/recvuJYdOb1Rm1.json',encoding='utf-8'));print(d['fields']['命中片段']['raw_verbatim'])"
# → H02:easier letdown / M01:whisper,whisper-quiet

# 6) 重复行
grep -n -o "r-37b49eadb72d7dc2" kb/l3/candidates/rules.jsonl   # → 1 行与 527 行

# 7) L4 定稿带的 P0 依据
python3 -c "import json;[print(json.dumps({k:v for k,v in json.loads(l).items() if k in ('article_no','p_level','p_level_basis','risk_level','owner','effective_from','valid_until')},ensure_ascii=False)) for l in open('kb/l4/canonical/wording_entry.jsonl',encoding='utf-8') if l.strip() and json.loads(l).get('article_no')=='W-1.18']"

# 8) 匹配器自测（正例全命中 / 负例零误报）
python3 kb/l5/matcher.py --selftest
```

---

## 7. 引用契约

- 库名：**《措辞表达库》**（`kb_type = wording`；四类库中当前只有这类有规则，其余库名不许拿来引用）
- 版本：`kb_version = v0`（**试用版，未发布**）
- 条款号：**W-1.18**（L4 已发号；但 `kb/l4/canonical/rules.jsonl` 为 **0 字节空文件**，
  `l4.json` → `promotion_rule.status = "待抽查（本批不做）"`，**抽查是人工环节、本批未做**）
- `anchor`：`#广告文案明细/recvuJYdOb1Rm1/命中片段`（**已知错位**，真锚点见 §4-①）
- `source_sha256`：`c77f576dcc392cb3e763e6462d0259e50fb039f924a4af8e100321197e5be577`（**已复算通过**）
- 逐字摘录：`H02:easier letdown / M01:whisper,whisper-quiet`（该被引记录的命中片段）
- 性质：**事实**（matcher 确定性输出、文件行号、`source_sha256` 均已复算）｜ 置信度：**高**

---

## 8. 送审建议（申诉怎么打）

| 主张 | 强度 | 说明 |
|---|---|---|
| ① `guaranteed results` 不是 P0 触发项 | **成立** | 但**不能**据此要求放行整句 |
| ② H02 匹配面过宽（正则吃掉自家允许的 `natural let-down`） | **强** | 有代码级根因，可要求收窄口径后重判 |
| ③ 上游草案：无 owner、无生效日、`p_level` 与定稿冲突 | **中强** | 指向治理流程未闭环 |
| ④ 活库已无法复核 P0/atomic/expert 前提 | **中** | 结论是「存疑待核」，不是「已证伪」 |
| ⑤ 锚点错位 | **中** | 可要求补正；**不能**推翻判定 |
| ⑥ 要求整句放行 | **不成立** | 命中是确定性的，且库层面 `increase milk supply` 仍为 `高危·红` |

**结论**：可以打的是**程序与口径**（②③④⑤），**不是**「没命中」（⑥）。
申诉的正确落点是「**请按收窄后的口径重判，并补正依据链**」，
而不是「**这句话没有触发 P0，所以应当放行**」。
