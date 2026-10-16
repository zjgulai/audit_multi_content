# P0 判定依据单（申诉用）：`increase milk supply, guaranteed results`

- 判定时间：2026-09-30 17:20
- 判定层：L5 P0 判定层（只读查询档）
- 判定器：`kb/l5/matcher.py`（exporter_version `l5-0.1`）
- 待判文本：`increase milk supply, guaranteed results`（40 字符）
- 复算命令：`cd ~/.dsh/Momcozy知识库 && kb/kbpy l5/matcher.py --text "increase milk supply, guaranteed results" --json`（退出码 1 = 有 P0 命中）

---

## 一、结论（L5 输出契约）

```
是否 P0：是
命中模式：H02（rule_code=H02；pattern_id=p-755f9ff377c3052c）
          authority=expert ｜ anchor=#广告文案明细/recvuJYdOb1Rm1/命中片段
          match_note=BLOCK ｜ level=P0
命中片段：increase milk supply        ← keyword 命中，span [0,20]
          increase milk               ← regex 命中，span [0,13]
证据单元：unit_id=74d1ba6b94a5336853dd ｜ source_sha256=67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e
          （锚点 #广告文案明细/recvuJYdOb61lT/命中片段）
来源：kb/l5/p0_patterns.jsonl #1
```

同一条规则下的另外两条等价证据单元：

| unit_id | 锚点 | source_sha256 |
|---|---|---|
| `ab48363a38d4bd7dabb7` | `#广告文案明细/recvuJYdOb1fOj/命中片段` | `3f80e285066d73f0cc01ea59869fe5ee086091c4fa013ff887f772d69fdcfc4c` |
| `ff2411eaf09d2459c5bb` | `#广告文案明细/recvuJYdObLnyQ/命中片段` | `3c47b7b1e3df4737f0d55cad46ffac67088245de3662279ec5121363fa211741` |

**两路独立命中落在同一处文本上**：
- keyword 表里 `increase milk supply` 逐字在列（`patterns[5]`，basis=`verbatim_source`）；
- 正则 `\b(more|increase[sd]?|boost[s]?|maximi[sz]e[sd]?)\s+(your\s+)?milk\b` 同时命中 `increase milk`。

`whitelist_suppressed = 0` —— 这句话是裸用宣称，没有落进任何豁免语境。

---

## 二、「为什么是最高优先级」的直接依据

**P0 不是匹配器自己拔高的，是规则本身带的。** 引用级真源在 L4 定稿层：

`kb/l4/canonical/wording_entry.jsonl` **第 18 行**：

| 字段 | 值 |
|---|---|
| `article_no` | **W-1.18** |
| `p_level` | **P0** |
| `p_level_basis` | **「全部支撑记录的风险等级均为高危·红 → P0」** |
| `risk_level` | 高危·红 |
| `risk_evidence_records` | 34 |
| `authority` | expert（`authority_source_table`=广告文案明细） |
| `rule_kind` | atomic |
| `status` | **stable**（已定稿） |
| `owner` | 法务 + 医学顾问 |
| `effective_from` / `valid_until` | 2026-09-29 / **2027-09-29（未过期）** |
| `half_life_days` | 365 |
| `scope` | `{records: 34, rule_code: H02}` |
| `support_count` | 102 个证据单元 |
| `forbidden_expression` | …；**increase milk supply**；increase milk supply,more milk；… |
| `promotion_basis` | C1 唯一条款号 / C2 引用三件套齐全 / C3 正文非空 / C4 与候选逐字一致 / C5 证据单元可在 L2 解析 / C6 证据单元 rule_eligible / C7 kb_version=v0 / C8 发号幂等 |

**独立复算 `p_level_basis`**：拿 W-1.18 的 34 条支撑记录逐条回 L0 查 `风险等级` 字段 ——
**34/34 全部 = `["高危·红"]`**（32 条在 `kb/l0/records/广告文案风控库__广告文案明细/`，2 条 `recvuJYeGR6F4W`、`recvuJYeGRdUud` 在 `kb/l0/records/广告文案明细/`，`entry_url` 指向同一张飞书表 `Lk3Qb8y2QaVyZns6gprcVNE9nA0` / `tblcbk4XiW6471YN`）。
「全支撑记录都是高危·红 ⇒ P0」这条判据**成立**。

---

## 三、逐字源证据（L0 原始记录）

`increase milk supply` 在源侧就是被运营/法务判过红的**真实投放文案**，不是关键词表的凭空归纳。

**① `recvuJYdOb61lT`（最能打的一条）** —— `kb/l0/records/广告文案风控库__广告文案明细/recvuJYdOb61lT.json`

- 平台 Google ｜ 广告组 `wearable-pump-warm-massage-vs-app-4.10` ｜ 语种 英语 ｜ 投放状态 ENABLED ｜ 风险等级 高危·红 ｜ 处理状态 待人工复核
- `Primary Text` 逐字含：`… | Mimics baby's natural nursing with heated massage. **Increase milk supply comfortably.** | Designed for comfort & convenience…`
- `命中片段`：`H02:increase milk supply / H07:pain-free / H09:mimics baby,mimics baby's natural nursing`
- `命中原因`：`H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）…`
- `修改建议`：`删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语…`

**② `recvuJYdOb1fOj`** —— 该记录的**广告组名就叫 `Increase Milk Supply`**；`Primary Text` 含 `{KeyWord:increase milk supply}`、`Discover 8 best breast pumps to help increase milk supply`；落地页 `…/8-best-pumps-to-increase-milk-supply`。风险等级 高危·红。

**③ `recvuJYdObLnyQ`** —— 同款文案第二例，`命中片段` 同为 `H02:increase milk supply,more milk / M07:better milk flow`。风险等级 高危·红。

---

## 四、申诉要点（哪块站得住、哪块可争）

### 站得住 —— 别在这上面浪费申诉额度

1. **`increase milk supply` 是逐字命中，不是语义外推。**
   `kb/l5/registry/l5.json` 的 `variant_policy.word_level_grounding` 规定每个词必须带 basis；`increase milk supply` 的 basis 是 **`verbatim_source`**（逐字来自该规则的「命中片段」字段），不是 `synonym_family` 也不是 `equivalent_of`。想争「你们自己归纳出来的词」，不成立。
2. **两路独立命中**（关键字 + 正则）落在同一处，改一处拼写躲不过去。
3. **规则是 stable 且未过期**（W-1.18，2026-09-29 生效，2027-09-29 到期），条款号唯一、引用三件套齐、8 项晋升条件逐条留痕。
4. **源侧不是孤证**：同码（H02）支撑记录 34 条，证据单元 102 个，横跨多个广告账号/广告组。

### 可以争 —— 这才是申诉该打的三点

1. **`guaranteed results` 不是判 P0 的原因。**
   实测：`kb/kbpy l5/matcher.py --text "guaranteed results" --json` → **0 命中**。
   整句命中的两处 span 全部落在 `increase milk supply` 上（[0,20] 与 [0,13]）。
   ⇒ 如果运营的说法是「整句都因为 guaranteed results 被判最高优先级」，这个说法**不准确**；能争的只有第一句。
2. **白名单豁免是真实存在的，可用来界定适用范围。**
   实测：`--text "禁用表达：increase milk supply"` → **0 命中**（命中器先跑白名单，`^禁用表达[:：]`、`[「『"“]…[」』"”]`、"DO NOT SAY:"、"依据/来源/原文/条款:" 等元语境整行豁免）。
   ⇒ 引用、转述、禁用词清单、培训材料里的这句话不算 P0；只有**把它当卖点用**才算。
3. **源侧记录自身还停在「待人工复核」。**
   34 条支撑记录的 `处理状态` 字段**全部 = `["待人工复核"]`**（实测分布：32 条 + 2 条，无一例外）。
   ⇒ 「P0 依据的是 34 条尚待人工复核的机审记录」是可以要求人重新过一遍的合理请求。

### 不在本 skill 职责内

本 skill 只答「**是不是 P0**」。**「能不能发」的三态结论（PASS / REVIEW / BLOCK）走 `kb-review`** —— 申诉时要的是「改判成什么」，那一步不在这里出。

---

## 五、两处需要人裁的不一致（按 skill §3 报冲突，建议交 `kb-check`）

> 这两条是**独立于本案**的库内问题，写在这里是因为申诉方一定会问「你们的依据自洽吗」。

### 冲突 1：L3 现行候选已不再标 P0，与 L4/L5 不一致

同一条 `rule_id = r-37b49eadb72d7dc2`：

| 文件 | mtime | p_level | authority | rule_kind |
|---|---|---|---|---|
| `kb/l3/candidates/rules.jsonl`（**现行**，第 527 行 = latest 视图） | 2026-09-30 15:52 | **P2** | **null** | **null** |
| `kb/l3/history/rules-pre-converge-20260924-1230.jsonl` | — | P0 | expert | atomic |
| `kb/l3/history/rules-superseded-20260924-1230.jsonl` | — | P0 | expert | atomic |
| `kb/l4/canonical/wording_entry.jsonl` #18（定稿） | — | **P0** | expert | atomic |
| `kb/l5/p0_patterns.jsonl` #1 | 2026-09-28 18:31 | **P0** | expert | — |

- 全库 1018 行现行 L3 的 `p_level` 分布 = `{P1: 986, P2: 32}` —— **现行 L3 里一条 P0 都没有**。
- 但 `kb/.work/l5_export.py` 的选取口径是 `r["p_level"] == "P0"` ∧ `rule_kind == "atomic"` ∧ `authority ∈ {expert, legal}`（`kb/l5/registry/l5.json` 同款）。
  ⇒ **拿现行 L3 重跑 L5，本条不会入选**；现存的 7 条 P0 表（2026-09-28 18:31）建在一个已被 2026-09-30 重跑覆盖的 L3 快照上。
- 影响面：源不变则 `pattern_id = sha1(EXPORTER_VERSION|rule_id)[:16]` 不变，所以匹配结果暂时不受影响；但**「这个库现在还说它是 P0 吗」这个问题，L3 和 L4 给了不同答案**。

### 冲突 2：匹配器把这条规则自己建议的「合规替代句」也判了 BLOCK

- 规则 W-1.18 的 `suggested_replacement` / `命中原因` 明写：合规替代为放松叙事 + 限定语，例如
  `relaxation supports your natural let-down, which may help your flow`，
  且「自然奶阵 / may help」**走 M07 语境守卫**（即允许但受守卫），`whitelist_allowed_expressions` 里也有 `relaxation` / `natural let-down` / `放松` / `自然奶阵`。
- 实测：`--text "relaxation supports your natural let-down, which may help your flow" --json` → **命中同一条 P0 模式**（regex `\blet[\s-]?down\b`，span [33,41]），`whitelist_suppressed = 0`。
- `kb/l5/matcher.py` 只把 `whitelist`（否定/引用/清单类正则）当豁免源；**`whitelist_allowed_expressions` 这个字段在匹配器里从未被读取**（matcher.py 全文只读 `patterns` / `regex_patterns` / `whitelist`）。
  ⇒ 「照规则建议改完反而还是 P0」是一处真实的自相矛盾，需人裁。

### 附带（不影响本案）

- `kb/l4/canonical/wording_entry.jsonl` #18 的 `cite_check.source_sha256 = null`，而同一条在 L5 里有 `c77f576dcc39…`；L4 的引用三件套缺 sha 一项。
- 同一张飞书表在 L0 下有两个记录目录（`广告文案风控库__广告文案明细/` 200 条 + `广告文案明细/` 91 条），W-1.18 的 34 条支撑记录跨这两个目录。

---

## 六、复算清单（申诉现场可当场跑）

```bash
cd ~/.dsh/Momcozy知识库

# ① 本句判定（退出码 1 = 有 P0 命中）
kb/kbpy l5/matcher.py --text "increase milk supply, guaranteed results" --json

# ② 归因对照：后半句单独跑，应为 0 命中
kb/kbpy l5/matcher.py --text "guaranteed results" --json

# ③ 白名单边界：引用语境应豁免，0 命中
kb/kbpy l5/matcher.py --text "禁用表达：increase milk supply" --json

# ④ 匹配器自测：正例全命中、负例零误报
kb/kbpy l5/matcher.py --selftest
```

以上四步实测结果：① 1 条命中（H02，2 处 span）｜② 0 命中｜③ 0 命中｜④ 通过。
