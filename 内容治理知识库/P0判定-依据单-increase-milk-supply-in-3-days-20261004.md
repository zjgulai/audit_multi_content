# P0 判定依据单 —— 「increase milk supply in 3 days」

> 判定层：`kb-p0-check`（L5 P0 判定层 · 查询档，**只读，未写库**）
> 库版本：`kb_version = v0` ｜ 库根：本工作区（`kb/` 的上一级）
> 出具日期：2026-10-04 ｜ 执行方式：本单全部结论由**引擎实跑产出**，不是手写

---

## 0. 一句话结论

**算。** `increase milk supply` **逐字命中** L5 模式 `p-755f9ff377c3052c`（规则码 **H02**、
`p_level = P0`、`match_note = BLOCK`），**关键词 + 正则双命中**，豁免规则一条都没触发
（`whitelist_suppressed = 0`）。

**三件必须一并说清的事：**

1. **「in 3 days」一个字节都没参与这次判定** —— 单独跑零命中（§3），全库没有任何 P0 模式覆盖
   「见效时限承诺」。它不是 P0，但**也不等于合规**，是**覆盖缺口**。
2. **支撑这条 P0 的上游，在活库里已经对不上**：L4 定稿 `W-1.18` 现在写 `p_level = P2` /
   `risk_level = unknown`，而它**自己的** `p_level_basis` 还写着「→ P0」（§4-①）。
3. **这不是三态结论。** 「是 P0」= 最高优先级口径；「能不能发」走 `kb-review` / `文案合规审查`。

---

## 1. 引擎原始输出（可复现）

```bash
cd "<库根>"                      # = kb/ 的上一级
sh kb/kbpy l5/matcher.py --text "increase milk supply in 3 days" --json
# 退出码 1 = 有 P0 命中
```

| 字段 | 值（逐字） |
|---|---|
| `hits[0].pattern_id` | `p-755f9ff377c3052c` |
| `hits[0].rule_id` | `r-37b49eadb72d7dc2` |
| `hits[0].rule_code` | `H02` |
| `hits[0].level` | `P0` |
| `hits[0].match_note` | `BLOCK` |
| `hits[0].matched_count` | `2` |
| 命中 1 | `kind=keyword`，`pattern=increase milk supply`，`span=[0,20]` |
| 命中 2 | `kind=regex`，`pattern=\b(more\|increase[sd]?\|boost[s]?\|maximi[sz]e[sd]?)\s+(your\s+)?milk\b`，`span=[0,13]` |
| `whitelist_suppressed` | `0` |

两个命中区间都落在 **0–20 字符**，全部由 `increase milk supply` 贡献；`in 3 days` 在第 21 字符之后，
**没有任何命中区间覆盖它**。

**为什么「命中」就等于「最高优先级」**：`kb/l5/registry/l5.json` 的 `match_note_enum` 只有一个取值
`["BLOCK"]` —— 该层**不做轻重分级，命中即 BLOCK**。这是「最高优先级」这个说法的技术来源。

**新鲜度不构成拒答理由**：`sh kb/kbpy l7/scripts/freshness.py` 退出码 0，
L5 模式表 16.7 小时前，各层关键产物均不陈旧。

---

## 2. 溯源四段

| 段 | 来源层 | 值 |
|---|---|---|
| ① 条款号 | **L4** | **`W-1.18`**（`kb/l4/canonical/wording_entry.jsonl`；`kb/l4/registry/l4.json → numbering.issued["W-1"].assigned["r-37b49eadb72d7dc2"] = "W-1.18"`，号码永久占用） |
| ② 规则与命中片段 | **L3** | 规则码 `H02`，命中片段逐字 `increase milk supply`；`reason` 逐字：「H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）」 |
| ③ 单元与锚点 | **L2/L1** | `anchor = #广告文案明细/recvuJYdOb1Rm1/命中片段`；`source_sha256 = c77f576dcc392cb3e763e6462d0259e50fb039f924a4af8e100321197e5be577`；`evidence_units[0].unit_id = 9c313d585ee7d5290c08`（该模式共 **102** 个证据单元） |
| ④ 逐字原文 + 直链 | **L0** | `recvuJYdOb1Rm1` 的 `命中片段` **逐字** = `H02:easier letdown / M01:whisper,whisper-quiet` ⚠ **不含 `increase milk supply`** —— 见 §4-③。含该词的 L0 记录：<br>· [recvuJYdOb1fOj](https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdOb1fOj) → `H02:increase milk supply,more milk / M07:better milk flow`<br>· [recvuJYdObLnyQ](https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdObLnyQ) → `H02:increase milk supply,more milk / M07:better milk flow`<br>· [recvuJYdOb61lT](https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdOb61lT) → `H02:increase milk supply / H07:pain-free / H09:mimics baby,…` |

**sha 措辞纪律**：模式行与 L2 单元登记的 `source_sha256` **一致**；但 L0 本地件**不含**
`record_fields` 这个字段 blob（`sha256_input` 只记了字面量），**重算在本地结构上不可能** ——
只能写「**与 L2 登记值比对一致**」，要真核对须点上面三条飞书直链。**本单不写「重算通过」。**

---

## 3. 「in 3 days」不是触发项（覆盖缺口）

```bash
sh kb/kbpy l5/matcher.py --text "in 3 days"      # → 结论: PASS，退出码 0
```

全库 `kb/l5/p0_patterns.jsonl` 仅 **7 条**模式，逐条读过，覆盖面为：
H02 催乳/增产/奶量产出 · H04 专家/医生背书 · H05 虚假安全与绝对化适配 · H06 FDA 措辞 ·
H07 疼痛功效 · H09 仿生（mimics baby）· U04 疼痛症状词。
**没有任何一条覆盖「N 天见效 / 时限承诺」**。

`kb/l4/canonical/*.jsonl` 全库检索「`in N days` / 见效 / 时限 / 24 小时」→ **0 行**；
`kb/l3/candidates/rules.jsonl` 命中 18 行，但全是**医学/操作准确性**类（如「每 24 小时不少于 8 次」
「发热超过 24 小时仍未缓解」），**没有一条是广告见效时限**。

⇒ 判定：**这是覆盖缺口，不是「没问题」。** 按 `kb-p0-check` 红线「**不自己造模式**」，
不把「in 3 days」顺手归纳成新 P0；要加必须走 `kb-pipeline` 走链路。

---

## 4. 四条必须一并报告的边界（本单的重点）

### ① L4 定稿与 L5 模式表，对**同一个 `rule_id`** 给出不同的 `p_level` —— 且 L4 那条自相矛盾

| 层 | 位置 | `p_level` | `risk_level` |
|---|---|---|---|
| **L5**（运行时命中处） | `kb/l5/p0_patterns.jsonl` | **P0** | — |
| **L4**（条款号定稿） | `kb/l4/canonical/wording_entry.jsonl` → `W-1.18` | **P2** | **unknown** |
| L3 候选（生行） | `kb/l3/candidates/rules.jsonl`（第 1、527 行） | **P2** | unknown |
| L3 manifest（富化行） | `kb/l3/manifest_l3.jsonl` | **P0**（`authority=expert`、`rule_kind=atomic`） | — |

**L4 那条记录自己跟自己打架**（同一行内，逐字）：

- `p_level` = `"P2"`
- `p_level_basis` = **`"全部支撑记录的风险等级均为高危·红 → P0"`**
- `risk_level` = `"unknown"`，而 `risk_evidence_records` = **34**、`support_count` = **102**

**这是被一次重建改写的，不是原状。** 与 `kb/l4/_pre-rebuild-20260930-1550/wording_entry.jsonl`
（2026-09-29 10:32 的快照）逐条比对：

| | 旧 build | 当前 canonical |
|---|---|---|
| `p_level` | `P0` | `P2` |
| `risk_level` | `高危·红` | `unknown` |
| `valid_until` | `2027-09-29` | `2026-12-28` |
| `p_level_basis` | （同上，未变） | 「…→ P0」**未随之更新** |

范围（同一备份全量比对 56 条 `wording_entry`）：

- **`p_level` 被改写 42/56**（`P0→P1` 15 条、`P1→P2` 10 条、`P2→P1` 7 条、**`P0→P2` 6 条**、`P3→P1` 4 条）；
- **`risk_level` 被改写 55/56**（**全部**变成 `unknown`）；
- `valid_until` 被改写 21 条；
- **当前 canonical 中，`p_level_basis` 写「→ P0」但 `p_level` 不是 P0 的共 15 条**
  （`W-1.18`、`W-1.13`、`W-1.33`、`W-1.53`、`W-1.1` …）。

**L5 的 P0 从哪来**（读代码到行）：`kb/.work/l5_export.py:272` `P0 = [r for r in latest.values() if r["p_level"] == "P0"]`，
而设 `latest` 的 `kb/l3/candidates/rules.jsonl` 生行**缺 `rule_kind`/`authority`**，
由「富化兜底」从 `kb/l3/manifest_l3.jsonl` 补齐（`l5_export.py:77-100`，只补缺失键、不覆盖已有值）。
⇒ **L5 的 P0 标签来自 L3 manifest 的富化行，与 L4 定稿之间没有任何对账。**

**库自己的体检看不见这件事**：实跑 `kb_check` → 「条目基线…**治理字段被原地改 0**」。
原因是基线比对的对象是**派生视图 `kb/view`**，而视图里不带 L4 的 `p_level`。
grep 全部 checker，**没有任何一处把 L4 的 `p_level` 与 L5 的 `p_level` 并排核对**。

**另记两处小口子**（据实报告，不定性）：`W-1.18` 的 `promoted_at_run = "20261002-1620"`，
但 `kb/l4/runs/` 下**没有** `20261002-1620.json`（`wording_entry.jsonl` mtime 为 10-02 22:23）。

⇒ **建议**：这属于「哪一层的 `p_level` 才是准的」的**待裁事项**，交 `kb-check` / 人工裁决。
本单**只据实并排，不替它定性** —— 因为「`P2` 是对的、`P0` 是旧的」与「`P0` 是对的、
重建时被覆盖坏了」**两种解释都与现有证据相容**，证据不足以推翻任一侧。

### ② 把这句话加引号，匹配器就判 PASS —— 豁免面过宽

```bash
sh kb/kbpy l5/matcher.py --text '"increase milk supply in 3 days"'      # → PASS（退出码 0）
sh kb/kbpy l5/matcher.py --text '「increase milk supply in 3 days」'    # → PASS（退出码 0）
sh kb/kbpy l5/matcher.py --text 'She said "it increased my milk supply"' # → PASS（退出码 0）
```

根因是豁免清单里的**引用式豁免** `[「『"“][^」』"”]{0,80}[」』"”]`
（`kb/l5/registry/l5.json → whitelist_policy.quotation`）：本意是放行「禁用词清单 / 依据原文」，
但它**整段吃掉任何被引号包起来的文本** —— 达人证言、转述、字幕引号都会静默 PASS。
配套证据：`matcher.py` 编译豁免时**只读模式行自带的 `whitelist` 字段**，从不读
`rule_specific_allowed`（`grep -n rule_specific_allowed kb/l5/matcher.py` → **0 命中**）。
⇒ **这是录入侧的坑：送文本时不要带引号/角括号，否则判定结果会假 PASS。**

### ③ 锚点错位：顶层 `anchor` 指向的那条 L0 记录里，没有这句话

模式行顶层 `anchor = #广告文案明细/recvuJYdOb1Rm1/命中片段`，
而该字段在 L0 里**逐字**是 `H02:easier letdown / M01:whisper,whisper-quiet`（见 §2-④ 表）。
它指向的是**同码的另一个词条**，**不是** `increase milk supply` 的落点。
⇒ 引用时**别照抄顶层 `anchor`**，要引 §2-④ 表中那三条真落点记录。

### ④ 两条口径纪律

- **「不是 P0」≠「没问题」**：`in 3 days` 零命中只说明 P0 层没覆盖它。
- **「是 P0」≠「三态结论」**：本单不出 PASS/REVIEW/BLOCK 的发布结论。
  「这句口播能不能发」是另一个问题，走 `kb-review`（按让位表：文字/口播转写 → `文案合规审查`；
  若整条片子要判 → `视频安全审查`），且那条路要跑 L4→L5→L6→L7 层前置后由引擎出结论。

---

## 5. 复现命令（逐条）

```bash
cd "<库根>"
sh kb/kbpy l7/scripts/freshness.py                                   # ① 新鲜度（退出码 0）
sh kb/kbpy l5/matcher.py --text "increase milk supply in 3 days" --json   # ② 命中（退出码 1）
sh kb/kbpy l5/matcher.py --text "in 3 days"                          # ③ 覆盖缺口（PASS）
sh kb/kbpy l5/matcher.py --text '"increase milk supply in 3 days"'   # ④ 引号豁免（PASS）
sh kb/kbpy l5/matcher.py --selftest                                  # ⑤ 匹配器自测：正例全命中、负例零误报
```

本单**未调用任何写档引擎**，未改 `kb/l0…l7` 任何一个文件。

---

**出具**：`kb-p0-check`（L5 查询档）｜ 结论只覆盖「是不是 P0」，不覆盖「能不能发」。
