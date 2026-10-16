# P0 判定依据单：`increase milk supply, guaranteed results`

> 用途：申诉留痕 ｜ 判定层：`kb-p0-check`（L5 P0 判定层，查询档只读）｜ 生成：2026-09-30 16:03 ｜ 库版本 `kb_version = v0`
> 复现根目录：`~/.dsh/Momcozy知识库`（= `kb/` 的上一级）

---

## 0. 结论（一句话）

这句被判最高优先级（L5 P0 / `match_note=BLOCK`），触发项**只有一处**：子串 **`increase milk supply`**，
命中 L5 模式 `p-755f9ff377c3052c`（规则码 **H02**，`authority=expert`，`p_level=P0`）。

**`guaranteed results` 不触发 P0** —— 单独跑零命中，库里没有覆盖「结果保证」的 P0 模式。
但「未命中 ≠ 合规」：这一半只是**没被 P0 层覆盖**，不等于可以发。

---

## 1. 判定怎么做的（可复现）

```bash
cd ~/.dsh/Momcozy知识库
kb/kbpy l5/matcher.py --text "increase milk supply, guaranteed results" --json
# 退出码 1 = 有 P0 命中（matcher.py 第 208 行：sys.exit(1 if hits else 0)）
```

原始输出（逐字，节选）：

| 字段 | 值 |
|---|---|
| `hits[0].pattern_id` | `p-755f9ff377c3052c` |
| `hits[0].rule_id` | `r-37b49eadb72d7dc2` |
| `hits[0].rule_code` | `H02` |
| `hits[0].level` | `P0` |
| `hits[0].match_note` | `BLOCK` |
| 命中 1 | `kind=keyword`，`pattern=increase milk supply`，`span=[0,20]` |
| 命中 2 | `kind=regex`，`pattern=\b(more\|increase[sd]?\|boost[s]?\|maximi[sz]e[sd]?)\s+(your\s+)?milk\b`，`span=[0,13]` |
| `anchor` | `#广告文案明细/recvuJYdOb1Rm1/命中片段` |
| `source_sha256` | `c77f576dcc392cb3e763e6462d0259e50fb039f924a4af8e100321197e5be577` |
| `evidence_units[0].unit_id` | `9c313d585ee7d5290c08` |

来源：**`kb/l5/p0_patterns.jsonl` 第 1 行**。
模式行属性：`authority=expert`｜`p_level=P0`｜`match_note=BLOCK`｜24 关键词 + 3 正则 + 6 豁免｜**102 个证据单元 / 34 条源记录**。

---

## 2. 依据链（四层，每层可点回）

判定口径（`kb/l7/registry/l7.json` → `decision_rules.BLOCK`）：
`P0 命中（kb/l5/matcher.py）` / `规则层命中且 rule.p_level = P0` / `规则层命中且 rule.risk_level = 高危·红` —— 三者任一即 BLOCK。本句走第一条。

| 层 | 依据位置 | 取值 / 逐字 |
|---|---|---|
| L7 口径 | `kb/l7/registry/l7.json` → `decision_rules` | `BLOCK` 首项 = 「P0 命中（`kb/l5/matcher.py`）」 |
| L5 模式表 | `kb/l5/p0_patterns.jsonl` #1 | `p-755f9ff377c3052c` / H02 / P0 / BLOCK / authority=expert |
| L5 入选口径 | `kb/l5/registry/l5.json` → `selection` | `p_level=P0` ∧ `rule_kind=atomic` ∧ `authority∈{expert,legal}`；21 条 P0 → 入选 6 条 |
| L5 导出记录 | `kb/l5/runs/20260923-1430.json`、`20260923-1430.report.md`（2026-09-23 13:27，verdict=PASS） | H02 `r-37b49eadb72d7dc2`：support 102｜`risk_level=高危·红`｜`authority_source_table=广告文案明细` |
| L3 规则 | `kb/l3/candidates/rules.jsonl` **第 527 行** | `rule_code=H02`｜`article_no=W-1.18`｜`status=provisional`｜`p_level=P2`（⚠ 见 §4-③） |
| L4 发号 | `kb/l4/registry/l4.json` → `numbering.issued["W-1"].assigned["r-37b49eadb72d7dc2"]="W-1.18"` | 号码已发、永不复用；`promotion_rule.status=待抽查（本批不做）`；`kb/l4/canonical/rules.jsonl` = **0 字节（空）** |
| L2 单元（逐字） | `unit_id=9c313d585ee7d5290c08`｜anchor `#广告文案明细/recvuJYdOb1Rm1/命中片段` | 正文逐字：`H02:easier letdown / M01:whisper,whisper-quiet` |
| L1 登记 | `kb/l1/manifest_l1.jsonl`（resource `bitable__Lk3Qb8y2QaVyZns6gprcVNE9nA0__recvuJYdOb1Rm1`） | `source_sha256=c77f576d…`（与 L2/L5 三处一致）｜`source_kind=feishu_bitable_record` |
| L0 源记录 | `kb/l0/records/广告文案风控库__广告文案明细/recvuJYdOb1Rm1.json` | 外部广告ID `GG-12d45aa812b7`｜平台 Google｜语种 英语｜**风险等级 高危·红**｜处理状态 待人工复核｜投放状态 ENABLED |

规则判据逐字（`kb/l3/candidates/rules.jsonl` #527 的 `reason` 字段）：

> H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）

---

## 3. 「increase milk supply」这个词条的逐字落点

`kb/l5/registry/l5.json` → `term_grounding["increase milk supply"] = "verbatim_source"`（逐字来自规则的「命中片段」，不是归纳）。
逐字含它的源记录有三条，均在该模式的 102 个证据单元内：

| 源记录 | 命中片段（逐字） | unit_id | source_sha256（前 16） |
|---|---|---|---|
| `recvuJYdOb1fOj` | `H02:increase milk supply,more milk / M07:better milk flow` | `ab48363a38d4bd7dabb7` | `3f80e285066d73f0` |
| `recvuJYdObLnyQ` | `H02:increase milk supply,more milk / M07:better milk flow` | `ff2411eaf09d2459c5bb` | `3c47b7b1e3df4737` |
| `recvuJYdOb61lT` | `H02:increase milk supply / H07:pain-free / H09:mimics baby,mimics baby’s natural nursing` | `74d1ba6b94a5336853dd` | `67875346a75bd2f8` |

`recvuJYdOb1fOj`（外部广告ID `GG-39da941fc97a`，2026-09-09，Google）的 Primary Text 里逐字含
`{KeyWord:increase milk supply}` 与 `{KeyWord:increase breast milk supply}` —— 同一批广告的真人判定先例。

⚠️ **锚点错位（可要求对方补正）**：模式行顶层 `anchor` 指向 `recvuJYdOb1Rm1/命中片段`，
但**那条记录的命中片段里并没有 `increase milk supply`**（它写的是 `H02:easier letdown / M01:whisper,whisper-quiet`）。
该词条的真锚点在另外三条记录上。`anchor` 与本词条不同源。

---

## 4. 申诉可用的四个技术点（各附复现命令）

**① `guaranteed results` 不是触发项**（对应运营的不服气点）

```bash
kb/kbpy l5/matcher.py --text "guaranteed results" --json       # → {"hits": []}，退出码 0
```

全库 `guaranteed` 只出现在两类源记录：
H07 疼痛功效（`guaranteed no pain` / `guaranteed painless`，见 `recvuNn4RsP5aR`、`recvuNn4RsFeU9`）
与 H05 虚假安全（`guaranteed safe` / `guaranteed no damage`，见 `recvuJP1dDumuM`）。
**没有任何 P0 模式覆盖「结果保证 / guaranteed results」本身。**
若申辩点是「guaranteed results 凭什么判 P0」，这一条成立：它不是 P0。

**② 规则自己写的「合规替代」，会被自家 matcher 判 BLOCK**（自相矛盾，最硬的一条）

```bash
kb/kbpy l5/matcher.py --text "relaxation supports your natural let-down, which may help your flow" --json
# → 命中 H02（正则 \blet[\s-]?down\b），whitelist_suppressed = 0
```

这句正是 H02 源记录「修改建议」里**逐字推荐**的合规替代。根因是接线缺口：

- `kb/l5/registry/l5.json` → `whitelist_policy.rule_specific_allowed.H02 = ["relaxation","relax","natural let-down","放松","自然奶阵"]`；
- 但 `kb/l5/matcher.py` 第 51 行编译时只读模式行的 `whitelist` 字段（6 条否定/引用语境），**从不读 `rule_specific_allowed`**。

即：**规则说「这样可以」，运行时说「这样也 BLOCK」。**

**③ 上游规则是草案、无人署名、无生效日**

`kb/l3/candidates/rules.jsonl` #527：`status = provisional`｜`owner = ""`（空）｜`effective_from = ""`（空）｜`effective_to = ""`｜`evidence_level = synthesis`｜`risk_level = "unknown"`。
L4 层也只做到「发号」：`kb/l4/canonical/rules.jsonl` 是 **0 字节空文件**，`promotion_rule.status = "待抽查（本批不做）"`，晋升路径写明「抽查未过不得晋升」。
→ 可主张：P0 所依赖的规则**尚未定稿、无责任人、无生效日**。

**④ 依据漂移：L5 依赖的上游属性行，在当前活库里查不到**

- L5 入选前提（`kb/l5/registry/l5.json`）：`p_level=P0 ∧ rule_kind=atomic ∧ authority=expert`；
- L5 导出时的实况（`kb/l5/runs/20260923-1430.json` → `precondition_a`）：`atomic|expert|P0 = 6`，H02 在列，`authority_source_table=广告文案明细`；
- **当前**（`kb/l3/candidates/rules.jsonl`，1018 行，mtime 2026-09-30 15:52）：509 条规则各两行、`status` 全为 `provisional`、**没有任何一行带 `authority` / `rule_kind` 键**，`p_level` 分布 `P1 986 / P2 32`（**P0 = 0**）；H02 那两行（#1、#527）都是 `P2`。

→ **当前活库已无法复核「H02 是 P0 / atomic / expert」这一前提。**
本条据实报告、不替它定性（是 L5 前置 A 的追加行丢失，还是后续 L3 重建覆盖，需交 `kb-check` 的条目基线比对去核）。

---

## 5. 不能拿来申诉的三点（边界，写清楚免得被一句话驳回）

1. **未命中 ≠ 合规。** `guaranteed results` 零命中只说明它不在 P0 层的覆盖面内，属**覆盖缺口**，
   不构成放行依据；其余风险仍须走 `kb-review`。别把它当免死金牌用。
2. **两套「优先级」不是同一个字段。** 运营说的「最高优先级」是 **L5 层的 P0**（命中即 P0/BLOCK，
   该层 `match_note_enum` 只有 `BLOCK`）；而 L3 规则行自己的 `p_level` 现在是 **P2**。
   申诉文里必须写明「L5 P0」，混用口径会被驳回。
3. **`increase milk supply` 的命中是确定性的，不是语义推断。** 词条 `basis = verbatim_source`
   （逐字来自源侧「命中片段」），正则另覆盖 `more/increase/boost/maximize + (your) milk` 的词形变化。
   要推翻只能攻「这条规则是否该管这一句」与「依据链是否有效」，攻「没命中」必败。

---

## 6. 复现清单（一条条跑，结果可对账）

```bash
cd ~/.dsh/Momcozy知识库

# 1) 待申诉句：命中 H02 → P0 / BLOCK，退出码 1
kb/kbpy l5/matcher.py --text "increase milk supply, guaranteed results" --json

# 2) 只留后半句：零命中（证明触发项是前半句）
kb/kbpy l5/matcher.py --text "guaranteed results" --json

# 3) 匹配器自测：正例全命中、负例零误报
kb/kbpy l5/matcher.py --selftest

# 4) 规则自己推荐的合规替代：仍被判 H02 BLOCK（接线缺口）
kb/kbpy l5/matcher.py --text "relaxation supports your natural let-down, which may help your flow" --json

# 5) 清单与逐字落点
grep -c . kb/l5/p0_patterns.jsonl                    # → 7 行（其中 H02 = 第 1 行）
sed -n '527p' kb/l3/candidates/rules.jsonl | head -c 400   # → article_no W-1.18 那行
```

---

## 7. 引用契约（按 `kb/l7/registry/l7.json` → `citation_contract` 填写）

- 库名：**《措辞表达库》**（`kb_type=wording`，当前 509 条规则全在此库）
- 版本：`kb_version = v0`
- 条款号：**W-1.18**（L4 已发号；`kb/l4/canonical/rules.jsonl` 为空，**未定稿**）
- `anchor`：`#广告文案明细/recvuJYdOb1Rm1/命中片段`（词条真锚点另见 §3 三行）
- `source_sha256`：`c77f576dcc392cb3e763e6462d0259e50fb039f924a4af8e100321197e5be577`
- 逐字摘录：`H02:easier letdown / M01:whisper,whisper-quiet`（该记录命中片段）
- 性质：**事实**（matcher 确定性输出、文件行号与 sha256 均可复算）；置信度：**高**
