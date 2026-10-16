# 依据单：「mimics baby」· 可直贴评审记录（v2 · 已独立复算）

> 口子：`kb-content-review`（链内依据组件 —— 结论 → 库名 / 版本 / 条款号 / 锚点 / `source_sha256` / 逐字摘录）
> 生成：20260930 ｜ 全程**只读**：未写库、未发号、未晋升、未动 canonical / 台账 / L5 模式表
> 库根：`…/知识库/内容治理/kb`（含 `kb/KB-ROOT.json` 标记 = **权威分层库**）
> 与 v1 的关系：v1 = `依据单-mimics-baby-评审记录用-20260930.md`；**v2 每个字段都重新独立复算过**，并补了 v1 没有的三项核验（指纹回算、L4 指纹缺口定性、条款正文截断）

---

## ⚠️ 先读这三条，否则这条依据会被用错

1. **`source_sha256` 不在 L4 层。** `kb/l4/canonical/wording_entry.jsonl` 的 56 条措辞条目**全部**没有 `source_sha256`
   （顶层无该键、`cite_check.source_sha256` 全为 `null`）。本单给的指纹取自 **L0 / L2 / L5 三层**（三层一致，且我按算法回算通过）。
   详见 §4。**别写成「W-1.1 自带指纹」** —— L4 里没有。
2. **`rule_text`（条款正文）是截断的，不能当逐字摘录引。** 实测 498 字，在第 450 字与第 570 字处**两次截断在句子中间**
   （`…pain relief/less pai` / `…H07 疼痛功效承`）。本单的逐字摘录一律取自 **L0 原文**，不取 `rule_text`。详见 §5。
3. **版本 `v0` 是「试用版、未发布」，且 L4 晋升是机器判据、人工抽查未做。** 贴评审记录时这句要一起写，
   否则等于把未验收的库说成已验收。详见 §6。

---

## 1. 主干依据（贴这一段 = BLOCK 的依据）

**《措辞表达库 v0》第 W-1.1 条**

| 字段 | 值 |
|---|---|
| **库名** | 措辞表达库（`3_措辞表达库`，内部标识 `wording`；取自 `kb/l0/registry/kb.json → kb_types`） |
| **版本** | `v0` ｜ registry 原话：`v0（试用版，未发布）` |
| **条款号** | `W-1.1` |
| **规则码 / rule_id** | `H09` ／ `r-006445396c95aa10` |
| **锚点 anchor** | `#广告文案明细/recvuJYdOb61lT/命中片段` |
| **`source_sha256`** | `67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e` ｜ 口径 `sha256_input = record_fields` |
| 判定 | `p_level = P0`（`p_level_basis`：全部支撑记录的风险等级均为高危·红 → P0）｜`risk_level = 高危·红` ｜ `match_note = BLOCK` |
| 条款状态 | `status = stable`（**已定稿、已发号**）｜ `effective_from = 2026-09-29` ｜ `valid_until = 2027-09-29`（**未过期**） |
| 负责人 | 法务 + 产品负责人 |
| 定稿出处 | `kb/l4/canonical/wording_entry.jsonl` **第 1 行**（该文件 sha256 `a1b0cb254be2e2248d034909e137feb56827b37d0d4e9c9b3082b93ccb31de8a`） |
| 发号台账 | `kb/l4/registry/l4.json → numbering.issued["W-1"].assigned["r-006445396c95aa10"] = "W-1.1"` |
| 命中模式出处 | `kb/l5/p0_patterns.jsonl` **第 6 行**（`pattern_id = p-d31dfbc932cb84ac`，该文件 sha256 `470e3fbad21489b9ad3cae7bd5fd5d4273b19262acb297c5b91808b51c570ea8`） |
| 可点链接 | https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdOb61lT |

---

## 2. 逐字摘录（未转述、未润色、未概括）

### 2.1 命中的原文（L0 原件 `命中片段` 字段，`field_id = fldkdgt6Nh`）

```
H02:increase milk supply / H07:pain-free / H09:mimics baby,mimics baby’s natural nursing
```

> 注：`mimics baby’s natural nursing` 里的撇号是 **U+2019（’）**，不是直引号 `'`。逐字引用请照抄。

### 2.2 条款的禁用表达（L4 `forbidden_expression`，逐字）

```
mimics baby；mimics baby,mimics baby’s natural nursing
```

> 该串的两个片段**都能在 2.1 的 L0 原文里逐字找到**（已逐片段比对通过）。

### 2.3 判定理由（L0 原件 `命中原因` 字段，`field_id = fldjX36eJ4`，逐字全文）

```
H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H07 疼痛功效承诺（pain-free/no pain/without pain/pain relief/less pain/缓解疼痛等；吸奶疼痛因人而异，只可讲 comfort/gentle 舒适与缓解胀满不适 discomfort）；H09 智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；W1当前为用户主动调节+保存程序，非闭环生理识别
```

**其中与本判定直接相关的 H09 那一句（逐字）**：

```
H09 智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；W1当前为用户主动调节+保存程序，非闭环生理识别
```

### 2.4 处理方式 —— 删除（L4 `suggested_replacement`，逐字，已与 L0 `修改建议` 的 H09 段比对一致）

```
删除自动识别节奏/模拟复制宝宝/饱腹反馈/降低奶量焦虑等智能闭环与仿生宣称；仿生表达只允许 inspired by natural nursing（参考自然哺乳节奏的设计思路）
```

### 2.5 命中词表（L5 第 6 行 `patterns`，逐字，共 8 个）

```
mimics baby’s natural nursing
baby-like suckling
imitates baby
mimic baby
mimics a baby
模仿婴儿
模拟婴儿吸吮
还原婴儿吮吸
```

正则（L5 同一条，逐字，共 2 条）：

```
\bmimic(s|king)?\b[^.]{0,30}\bbaby\b
模仿\s*婴儿|模拟\s*婴儿|还原\s*婴儿
```

可核性：`variant_sources.literal_from_source = ["mimics baby", "mimics baby’s natural nursing"]`（**原文里逐字就有**），
其余 6 个为 `synonym_family`，`dropped_ungrounded = []`（**没有凭空加词**）。

---

## 3. 怎么描述本条的证据链（可直接抄）

- **事实（置信度高）**：`mimics baby` 在 L5 词表的 `literal_from_source` 里，且被正则 `\bmimic(s|king)?\b[^.]{0,30}\bbaby\b` 覆盖 → 含该表述的文案命中 `W-1.1`。
- **事实（置信度高）**：本机实测 `KB_INTERP_OK=1 /usr/bin/python3 kb/l5/matcher.py --text "…" --json`，退出码 **1 = 命中**：
  - `W1 auto-detects your rhythm and mimics a nursing baby for you` → `H09` / `P0` / `BLOCK`，命中 span `[32,53]`；
  - `SoftPulse massage mimics baby's natural rhythm. Relax & let down faster.` → `H09` **且** `H02` 双命中。
- **事实**：本条有 **3 条支撑记录 × 9 个证据单元**（`risk_evidence_records = 3`、`support_count = 9`），
  三条记录 `recvuJYdOb61lT` / `recvuJYdObDPRw` / `recvuJYdObfmhq` 的指纹我逐条回算通过（§4）。

---

## 4. `source_sha256` 的复算与归属（本单最需要留意的一段）

**算法**（不是猜的，出处 `kb/l8/ingest_l0_new_records.py` 第 22 行）：

```
sha256( json.dumps([["field_id", fid, "value", val] …按 fid 升序], sort_keys=True, separators=(",",":")) )
```

**我的独立复算**（对 3 条支撑记录逐条重算，与 L2/L5 声明值比对）：

| record_id | 复算值（前 16 位） | 声明值（前 16 位） | 结果 |
|---|---|---|---|
| `recvuJYdOb61lT` | `67875346a75bd2f8…` | `67875346a75bd2f8…` | ✅ 一致 |
| `recvuJYdObDPRw` | `c0f86465188e72be…` | `c0f86465188e72be…` | ✅ 一致 |
| `recvuJYdObfmhq` | `87c9807847b95860…` | `87c9807847b95860…` | ✅ 一致 |

**三层一致**（同一个值同时出现在）：

| 层 | 文件 | 字段 |
|---|---|---|
| L0 | `kb/l0/3_措辞表达库/feishu_bitable_record__Lk3Qb8y2QaVyZns6gprcVNE9nA0__recvuJYdOb61lT.json` | `sha256`（`sha256_input = record_fields`、`sha256_state = full`） |
| L2 | `kb/l2/units.jsonl` → `unit_id = 74d1ba6b94a5336853dd` | `source_sha256` |
| L5 | `kb/l5/p0_patterns.jsonl` 第 6 行 | `source_sha256` |

**L4 层缺口（如实登记，未修）**：`kb/l4/canonical/wording_entry.jsonl` 56 条**全部**无 `source_sha256`；
`wording_revision_pair.jsonl` 453 条**同样全部为空**。对照：`sample_case.jsonl` 358/358 与
`scoped_clause.jsonl` 375/375 **都带指纹**。即 **509 条措辞类条目整体缺指纹**，353 条非措辞类不缺氧。
按 `kb/l7/registry/l7.json → citation_contract.hard_gate`（「只给锚点不给 `source_sha256`」属 forbidden），
**W-1.1 这一份在 L4 层过不了指纹硬闸门**；本单因此把指纹来自 L0/L2/L5 这件事写明，而不是假装 L4 有。
> 该缺口建议交 `kb-check` / `kb-repair` 处置；本单**不改库**。

**附带更正**：`evidence_digest = 980f20fdd6998fdb55558d7bfb8c0d5af320c8c9` 只有 40 位 → 是 **SHA-1**、不是 SHA-256，
不能当 `source_sha256` 用。

**别拿文件哈希当 `source_sha256`**：`source_sha256` 是 `record_fields` 内容指纹，**不等于**文件字节哈希。
实测 L0 落盘文件哈希是别的值（原件 JSON 文件 `bf0c3b3514dd17f3…`，登记副本文件 `74184e70cd69d818…`），
两者与 `source_sha256` 都不同 —— 这是设计如此，不是对不上。

---

## 5. 条款正文的截断（引用时避开）

`kb/l4/canonical/wording_entry.jsonl` 第 1 行 `rule_text` 共 498 字，**两处截断在句子中间**：

```
… faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 删除 pain-free/no pain/without pain/pain relief/less pai   ← 截断
… 依据：H02 催乳/增产/奶量产出承诺（…无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H07 疼痛功效承   ← 截断
```

因此：

- **不要**把 `rule_text` 当逐字摘录，也不要用它去证明 L0 `命中原因` 的完整性（`命中原因` 全文在 `rule_text` 里**不逐字成立**，实测 `in` 判定为 False）。
- 要引条款正文，用 **§2.3 的 L0 `命中原因` 全文** + **§2.2 的 `forbidden_expression`**，这两处是完整的。
- `rule_text` 是 L3 蒸馏器（`distiller_version = l3-0.2`）拼接生成的摘要字段，本身不是源文本。

---

## 6. 引用时必须一并写出的边界

1. **命中 P0 ≠ 内容违规**：`match_note` 一律 `BLOCK`，只是「最高优先级」口径；**未命中也不等于合规**（`kb_guide` 与 `l7.json` 的 `no_hit_semantics` 均明写「字面未匹配，不代表合规」）。
2. **版本是试用版**：`v0（试用版，未发布）`；全库无 `release_id`、`kb/versions/versions.jsonl` 无版本行。
3. **晋升是机器判据、人工抽查未做**：L4 晋升依据 `promotion_basis` C1–C8（C1 唯一条款号 / C2 引用三件套齐全 / C3 正文非空 / C4 与候选逐字一致 / C5 证据单元可在 L2 解析 / C6 `rule_eligible` / C7 `kb_version=v0` / C8 发号幂等），**人工抽查未做** → 本库仍**不能声称已过正式验收**。
4. **锚点只锚「命中片段」这一个字段，不锚整条广告文案**：`#广告文案明细/recvuJYdOb61lT/命中片段` 的逐字内容就是 §2.1。
   我在 L0 里**找不到**任何字段逐字存着「our pump mimics baby's natural nursing.」这整句 —— 那句只出现在实测与报告里。
   评审记录里若要引整句，须**另行取证**，不要挂在 W-1.1 的锚点上。
5. **责任人角色未配置**：`kb/l7/registry/l7.json → approvers.configured = false`，三个角色位（sign-off / 复核 / 内容方修改）`handle` 均为 `null` → 本单**不写死人名**，评审记录里请写角色并标注「未配置」。
6. **本单不覆盖**：不构成「这条能发 / 不能发」的结论，也不替代法务意见；替换建议只解决「怎么写更稳」。

---

## 7. 相关但**不相等**的条款号（别混引）

| 条款号 | rule_id | 形态 | 与本单关系 | 引用时的性质 |
|---|---|---|---|---|
| **`W-1.1`** | `r-006445396c95aa10` | `entry` | **就是本单这条**（`H09`，`P0`，`高危·红`） | **BLOCK 的依据** |
| `W-1.31` | `r-7489e156a5d2c7b2` | `entry` | 同一 `H09` 规则码的**更宽边界条目**，管整类「智能闭环/仿生虚假宣称」；锚点不同：`#品线内容边界规则库/recvuNifmKBXoP/边界内容` | 也是 `P0`；`risk_level = 高危`（**无「·红」后缀**，与 W-1.1 不同）；`forbidden_expression` 按分隔符数 **30 项**（v1 写的 29 项，按不同切法；请以文件为准） |
| `W-2.176` / `W-2.217` / `W-2.342` / `W-2.370` | `r-6449be54796427f3` / `r-790e26c27102e241` / `r-c515e503185d5234` / `r-d827cc631a0cd70a` | `revision_pair` | 「原文 → 建议文案」的**改写建议**，`rule_code` 为空串 | **不是主干依据**；贴它会把 BLOCK 降格成 REVIEW。要给改写方案时才引 |

**覆盖面差异（重要）**：`simulates your baby` / `copies your baby` / `饱腹反馈` 这类**只有 `W-1.31` 管**；
`mimics baby` 同时落在 `W-1.1` 与 `W-1.31` 两条里。只引 `W-1.1` 会漏掉这一类。

---

## 8. 为什么不用 `kb_search` / `kb_read` 出这份依据

宿主侧 `kb_*` 工具指向的是**派生视图** `kb/view/`（509 条 md），实测：

- `kb_search "mimics baby"` → 命中 6 条（`cg-r-006445396c95aa10` 及 `W-2.176/217/342/370`、`W-2.94`），
  **只给能力声明与边界，不给 `anchor` / `source_sha256` / 逐字原文** → 结构上出不了评审记录要的三件套。
- 该视图自己的 `_meta/GUIDE.md` 已声明「**不能声称已过正式验收**」，且其元字段仍是旧口径
  （「l4 canonical 尚未写入」）—— 而 `kb/l4/canonical/` **实际已写入 1242 条**。**该字段已过期，别据它判断 L4 状态。**
- 更关键：视图条目本身的 `not_proves` 写着「不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，**l4 canonical 尚未写入**）」——**这句已与库的实际状态不符**。

**结论**：评审记录要的库名/版本/条款号/锚点/指纹/逐字摘录，必须落到**权威分层库** `kb/l0…l5`（本单即如此）。

---

## 9. 复算留痕（谁想复核，跑这些）

```bash
cd …/知识库/内容治理/kb

# ① P0 确定性匹配（退出码 1 = 命中）
KB_INTERP_OK=1 /usr/bin/python3 l5/matcher.py \
  --text "W1 auto-detects your rhythm and mimics a nursing baby for you" --json

# ② 条款号三处一致（canonical 第 1 行 / 台账 / 全扫唯一）
KB_INTERP_OK=1 /usr/bin/python3 -c "
import json;r=json.loads(open('l4/canonical/wording_entry.jsonl').readline())
print(r['article_no'],r['rule_code'],r['rule_id'],r['status'])"

# ③ 指纹回算（本单 §4 表）
#    算法见 l8/ingest_l0_new_records.py:22；对 l0/records/广告文案风控库__广告文案明细/<rec>.json 的 fields 重算

# ④ 台账 vs canonical 差额（W-1.1 不受影响）
#    台账 509 号（仅 W-1 56 + W-2 453）；canonical 1242 号；差 733 号全在 W-3/S-1/E-1
```

**本次核验的事实（供留痕）**：

- `W-1.1` 在四个 canonical 形态文件里**只出现 1 次**（`wording_entry.jsonl`）→ 号不歧义、无跨形态重复号（全库重复号 = 0）。
- **台账与 canonical 的口径冲突不影响本单**：台账只有 `W-1`(56) + `W-2`(453) = **509** 号；
  canonical 实际 **1242** 号；差 **733** 号全部落在 `W-3`(157) / `S-1`(201) / `E-1`(375)；
  「在台账但不在 canonical」= **0**。`W-1.1` 属 509 之内，**不受该冲突影响**。
- L0 与 L2 文件**均无信封字节**（`node` 读回首字节为 `{`，权威判定按 `kb/_meta/GUIDE.md` §八）。

## 10. 本次写入披露（据实）

本单**未改知识库任何文件**。唯一落进工作区的字节 = 本文件 `依据单-mimics-baby-评审记录用-20260930-v2.md`（经 `node fs.writeFileSync` 写入并读回校验）。
`kb/l4/**`、`kb/l5/p0_patterns.jsonl`、`kb/l0/**`、`kb/l2/**` **mtime 未动**。
§8 提到的派生视图过期字段**已登记、未修**（属写操作，走 `kb-pipeline` / `kb-repair`）。
