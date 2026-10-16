# 依据单：「mimics baby」规则 · 可直接贴进评审记录

> 产出入口：`kb-content-review`（结论 → 库名 / 版本 / 条款号 / 锚点 / `source_sha256` / 逐字摘录）
> 核对时间：2026-09-30 ｜ 本次**全只读**：未写 `kb/`、未发号、未晋升、未改 canonical / 台账 / L5 模式表
> 库根：`…/知识库/内容治理/kb`（含 `kb/KB-ROOT.json` 标记 = 权威分层库）。
> **本文一律引权威分层库，不引派生视图**（`kb/view` 那份 509 条 md 是给宿主镜像吃的派生视图，字段改动不写回权威库）。

---

## 0. 一句话结论

「mimics baby」在库里对应 **`W-1.1`**，规则码 **`H09`**，`rule_id = r-006445396c95aa10`，
`p_level = P0`、`risk_level = 高危·红`、`status = stable`（**已定稿、已发号**）。
**P0 判定在 L5，条款号在 L4 —— 引用时要分层写，不能混成一句。**

---

## 1. 可直接粘贴的引用块（评审记录正文）

> **依据**：《措辞表达库 v0》第 **W-1.1** 条（试用版、未发布）
> **规则码 / rule_id**：`H09` / `r-006445396c95aa10`
> **判定**：`P0`（最高优先级）｜`risk_level` = 高危·红｜条款状态 `status` = `stable`（已定稿，非草案）
> **有效期**：`effective_from = 2026-09-29`，`valid_until = 2027-09-29`（未过期）
> **锚点**：`#广告文案明细/recvuJYdOb61lT/命中片段`
> **`source_sha256`**：`67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e`（本机独立复算一致，见 §5）
> **条款正文逐字**：「规则码 H09：命中「mimics baby；mimics baby,mimics baby’s natural nursing」判定为违规」
> **命中表达逐字**：`mimics baby；mimics baby,mimics baby’s natural nursing`
> **来源**：飞书 Base 广告文案风控库 / 广告文案明细 / 记录 `recvuJYdOb61lT`（风险等级 高危·红，处理状态 待人工复核）
> **出处**：`kb/l4/canonical/wording_entry.jsonl` 第 1 行（条款号）＋ `kb/l5/p0_patterns.jsonl` 第 6 行（P0 判定与指纹）

**照抄用的一句（最小可用）**：

> 判定 BLOCK。依据《措辞表达库 v0》第 W-1.1 条（`rule_code = H09`，`p_level = P0`，`risk_level = 高危·红`，`status = stable`，有效期至 2027-09-29）；
> 锚点 `#广告文案明细/recvuJYdOb61lT/命中片段`；`source_sha256 = 67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e`；
> 条款正文逐字：「规则码 H09：命中「mimics baby；mimics baby,mimics baby’s natural nursing」判定为违规」。

---

## 2. 主干依据 · 逐字段核对表（《措辞表达库 v0》第 W-1.1 条）

| 项 | 值 | 出处（可复算） |
|---|---|---|
| 库名 | 措辞表达库（`wording`，目录 `3_措辞表达库`） | `kb/l0/registry/kb.json → kb_types` |
| 版本 | `v0`（registry 原文：**试用版，未发布**） | `kb/l7/registry/l7.json → citation_contract.version_in_citation` |
| 条款号 | `W-1.1` | `kb/l4/canonical/wording_entry.jsonl` **第 1 行** → `article_no` |
| 发号台账 | `W-1.1`（同号二次确认） | `kb/l4/registry/l4.json → numbering.issued["W-1"].assigned["r-006445396c95aa10"]` |
| 规则码 / rule_id | `H09` / `r-006445396c95aa10` | 同上两处 + L5 第 6 行 |
| 判定层级 | `P0`｜`risk_level = 高危·红`｜`p_level_basis`：「全部支撑记录的风险等级均为高危·红 → P0」 | canonical 行同名字段 |
| 条款状态 | `status = stable`（`promoted_from = provisional`，`promoted_at_run = 20260929-1100`） | canonical 行 |
| 有效期 | `effective_from = 2026-09-29`｜`valid_until = 2027-09-29`｜`half_life_days = 365` | canonical 行 |
| 负责人 | `法务 + 产品负责人` | canonical 行 `owner` |
| 锚点 | `#广告文案明细/recvuJYdOb61lT/命中片段` | canonical 行 `anchor` / `cite_check.anchor` |
| `source_sha256` | `67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e` | canonical 行 `evidence_units[0].source_sha256` ＋ L5 第 6 行顶层同值 |
| 证据规模 | `support_count = 9`｜`risk_evidence_records = 3`｜`scope.records = 3` | canonical 行 |
| 命中模式 | `pattern_id = p-d31dfbc932cb84ac`｜`authority = expert`｜`match_note = BLOCK`｜`type = keyword` | `kb/l5/p0_patterns.jsonl` **第 6 行** |
| 可点链接 | https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdOb61lT | L0 记录 `entry_url` |

### 2.1 逐字摘录（照录，未转述、未润色）

`forbidden_expression`（命中表达，逐字；注意原文用的是**弯引号 `’`**）：

```
mimics baby；mimics baby,mimics baby’s natural nursing
```

`rule_text`（条款正文开头，逐字；**原文到此即被截断于「H07 疼痛功效承」，我没有替它补全**）：

```
规则码 H09：命中「mimics baby；mimics baby,mimics baby’s natural nursing」判定为违规；处理：「mimics baby,mimics baby’s natural nursing」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 删除 pain-free/no pain/without pain/pain relief/less pai；依据：H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H07 疼痛功效承
```

`suggested_replacement`（逐字；**只取与「mimics baby」同源的那一段**，其余段属 H02/H07，混引会串型）：

```
删除自动识别节奏/模拟复制宝宝/饱腹反馈/降低奶量焦虑等智能闭环与仿生宣称；仿生表达只允许 inspired by natural nursing（参考自然哺乳节奏的设计思路）
```

`reason`（逐字，完整——`rule_text` 被截断时以本字段为准）：

```
H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H07 疼痛功效承诺（pain-free/no pain/without pain/pain relief/less pain/缓解疼痛等；吸奶疼痛因人而异，只可讲 comfort/gentle 舒适与缓解胀满不适 discomfort）；H09 智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；W1当前为用户主动调节+保存程序，非闭环生理识别
```

### 2.2 L5 模式表登记的 8 个命中词（逐字）与 2 条正则

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

```
\bmimic(s|king)?\b[^.]{0,30}\bbaby\b
模仿\s*婴儿|模拟\s*婴儿|还原\s*婴儿
```

`variant_sources`（来源可核，**没有凭空加词**）：
`literal_from_source = mimics baby / mimics baby’s natural nursing`（原文里逐字就有）；
`synonym_family = baby-like suckling / imitates baby / mimic baby / mimics a baby / 模仿婴儿 / 模拟婴儿吸吮 / 还原婴儿吮吸`；
`dropped_ungrounded = []`（空）。

### 2.3 白名单（命中这些**不算**违规，逐字）

```
\b(does\s*n[o']?t|do\s+not|does\s+not|not\s+intended\s+to|never|no\s+claim)\b[^.]{0,40}\b(treat|cure|heal|pain|milk)\b
(不能|不可以|无法|并非|不是|不做|严禁|禁止)[^。]{0,20}(治疗|治愈|预防|无痛|增产|催奶|催乳)
^\s*(DO\s+NOT\s+SAY|Do\s+not\s+say|禁用表达|禁用词|禁止表达|禁止使用|禁用|禁止|不允许|不得使用|违规表述|违规词|高危词)\s*[:：][^。！？!?]{0,200}
[「『"“][^」』"”]{0,80}[」』"”]
\b(per|according\s+to|as\s+stated\s+in|cited\s+from)\b[^.]{0,30}
^(依据|来源|原文|条款)[:：]
```

> 实际命中文案时，`whitelist_suppressed = 0`（本机实测，见 §4），即本次命中未被白名单豁免。

---

## 3. 同属 P0 的第二条：《措辞表达库 v0》第 W-1.31 条（管整类「智能闭环 / 仿生虚假宣称」）

| 项 | 值 |
|---|---|
| 条款号 / rule_id | `W-1.31` ／ `r-7489e156a5d2c7b2`（规则码同为 `H09`） |
| 判定 | `P0`｜`risk_level = 高危`｜`status = stable`（已定稿、已发号） |
| 出处 | `kb/l4/canonical/wording_entry.jsonl` **第 31 行** |
| 发号台账 | `kb/l4/registry/l4.json → numbering.issued["W-1"].assigned["r-7489e156a5d2c7b2"] = "W-1.31"` |
| 有效期 | `effective_from = 2026-09-29`｜`valid_until = 2027-09-29` |
| 负责人 | 法务 + 产品负责人 |
| 锚点 | `#品线内容边界规则库/recvuNifmKBXoP/边界内容` |
| `source_sha256` | `a2aca575cf6a2ec78155d31cbabf252fc145844429b89b01923226a720d231aa`（本机独立复算一致） |
| 可点链接 | https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblD1MiUK1v5fdjD&record=recvuNifmKBXoP |

**条款正文（`rule_text`，逐字，本条未被截断）**：

```
边界：智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；只允许“参考自然哺乳节奏的设计思路/inspired by”表达；触发词：auto-detects rhythm, automatically detects your rhythm, automatically finds the best rhythm, detects the best rhythm, smart rhythm detection, mimics your baby, mimics a nursing baby, mimics baby, mimics nursing, copies your baby, simulates your baby, simulates a nursing baby, baby fullness feedback, fullness feedback, reduces milk supply anxiety, ease milk supply anxiety, milk supply anxiety, 自动识别最佳节奏, 自动识别节奏, 自动识别节律, 智能识别节奏, 模拟宝宝, 模拟婴儿, 复制宝宝, 模仿宝宝吃奶, 饱腹反馈, 模拟饱腹, 降低奶量焦虑, 缓解奶量焦虑, 减少奶量焦虑；豁免：inspired by, inspired by natural nursing, 参考自然哺乳, 参考宝宝, 借鉴, 设计思路, 参考思路, 灵感
```

`forbidden_expression`（29 个触发词，逐字）：见上行 `触发词：` 之后至 `；豁免：` 之前的那一串。
`allowed`（豁免词，逐字，**写评审记录时很有用**）：`inspired by, inspired by natural nursing, 参考自然哺乳, 参考宝宝, 借鉴, 设计思路, 参考思路, 灵感`

**来源记录 L0 逐字四个字段**（`recvuNifmKBXoP`，`field_id` 为 L0 原生键）：

- 「边界内容」（`fldZ9ZjOeB`）：`智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；只允许“参考自然哺乳节奏的设计思路/inspired by”表达`
- 「检测关键词」（`fldnuE1F7T`）：29 个词，逐字同 §上 `触发词` 串
- 「豁免词」（`fld5UgtA2v`）：`inspired by, inspired by natural nursing, 参考自然哺乳, 参考宝宝, 借鉴, 设计思路, 参考思路, 灵感`
- 「正则表达式」（`fldGFLQ94w`）——**注意：这 6 段正则只存在于 L0 来源记录，没有进入 L5 模式表，也没有进入 L4 canonical**（本机逐文件核对的事实）：

```
mimic\w* [^.!?|]*(baby|nursing|breastfeed), (cop|copies|copy|simulate\w*|imitates?|replicates?)[^.!?|]*(baby|nursing|infant), (auto|automatic|smart)[^.!?|]*(detect|find|identif|recogniz)\w*[^.!?|]*(rhythm|pattern|let-?down|pace), (fullness|satiety) feedback, (模拟|复制|模仿)[^.!?|]*(宝宝|婴儿), 自动(识别|检测|判断)[^.!?|]*(节奏|节律|模式|奶阵)
```

**`W-1.1` 与 `W-1.31` 怎么分工（照抄原文，不推测）**：

- `W-1.1` 管「mimics baby」这个**具体说法**（词表逐字就是 `mimics baby` / `mimics baby’s natural nursing` 及其等价说法）。
- `W-1.31` 管**整类**「智能闭环 / 仿生虚假宣称」（29 个词，含 `simulates your baby` / `copies your baby` / `饱腹反馈` / `自动识别节奏`）。
- `mimics baby` **同时落在两条里**；但 `simulates your baby`、`copies your baby`、`模拟宝宝`、`饱腹反馈` 这类**只有 `W-1.31` 管**（且当前 matcher 不报，见 §6）。

---

## 4. 回原文（L0）：锚点落在哪条记录、那句话在哪

**来源表**：飞书 Base「广告文案风控库 / 广告文案明细」，`table_id = tblcbk4XiW6471YN`，`base_token = Lk3Qb8y2QaVyZns6gprcVNE9nA0`
**记录**：`recvuJYdOb61lT`｜`observed_at = 20260923-1117`｜`timezone = Asia/Shanghai`｜`filter.result = not_in_entry_table_scope`
**本地路径**：`kb/l0/records/广告文案风控库__广告文案明细/recvuJYdOb61lT.json`

字段「命中片段」（`fldkdgt6Nh`）逐字：

```
H02:increase milk supply / H07:pain-free / H09:mimics baby,mimics baby’s natural nursing
```

字段「命中规则」（`fldYvuLtZG`）逐字：`H02,H07,H09`
字段「风险等级」（`fld23zewA0`）逐字：`高危·红`｜字段「处理状态」（`fldjLfDwGf`）逐字：`待人工复核`
字段「文案语种」（`fldzBKSHNY`）逐字：`英语`｜字段「广告账号」（`fldrH3sZQU`）逐字：`Momcozy-外部需求投放`

**投放原文里那句话的逐字位置**（同记录 `Primary Text`，`fldFjwI9JQ`，整串照抄，未改写）：

```
Momcozy® Official | Momcozy W1 vs Air 1 | Find Your Cozy Pump Style | Compare Momcozy Breast Pumps | Find Ideal Pump for Your Needs | Momcozy Wellness 1 | Heated Breast Pump | Breast Pump with Heat | Heated Wearable Breast Pump | Shop Momcozy Wearable Pumps | Pain-Free Breast Pumping | Warm Massage for Better Flow | Effortless Pumping Anywhere | Built-in Heat & Massage Pump | Mimics baby’s natural nursing with heated massage. Increase milk supply comfortably. | Designed for comfort & convenience. Trusted by 4.5M+ moms worldwide | Designed for busy moms. Discreet, wearable, and now with built-in warming technology. | Not sure which pump to choose? Check our guide on Warm Massage vs. App Control features.
```

> ⚠ 原文写的是 **`Mimics baby’s natural nursing`**（首字母大写、弯引号 `’`），不是全小写 `mimics baby`。
> 正则大小写不敏感、`baby` 后允许 0–30 个非句点字符，所以照样命中；
> **但逐字摘录必须照录原样，别顺手改成小写。**

### 4.1 L5 实机复跑（本机，2026-09-30）

命令（`kb-p0-check` 手册推荐的 `kb/kbpy` 通道在本机会卡在 `_interp.py`，用下面的绕开写法，约 0.33s 出结果）：

```bash
KB_INTERP_OK=1 /usr/bin/python3 kb/l5/matcher.py --text "Mimics baby’s natural nursing with heated massage. Increase milk supply comfortably." --json
```

退出码 **1 = 命中**。命中 2 条 P0：

| 命中 | `pattern_id` | 匹配到什么 | 锚点 | `source_sha256` |
|---|---|---|---|---|
| **H09**（`r-006445396c95aa10`） | `p-d31dfbc932cb84ac` | keyword `mimics baby’s natural nursing`（span 0–29）＋ regex `\bmimic(s|king)?\b[^.]{0,30}\bbaby\b`（span 0–11） | `#广告文案明细/recvuJYdOb61lT/命中片段` | `67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e` |
| H02（`r-37b49eadb72d7dc2`） | `p-755f9ff377c3052c` | `increase milk supply` | `#广告文案明细/recvuJYdOb1Rm1/命中片段` | `c77f576dcc392cb3e763e6462d0259e50fb039f924a4af8e100321197e5be577` |

两条 `match_note` 均为 `BLOCK`，`whitelist_suppressed = 0`。

---

## 5. `source_sha256` 独立复算（评审时可重跑，证明不是抄的）

算法取自 `kb/l0/registry/kb.json → fingerprint_policy`（`sha256_input = record_fields`）与生成器 `kb/.work/build2.py` 的 `rec_hash()`：
**按 `field_id` 升序键序列化，剔除 `last_modified_time` / `last_modified_by`，
`json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))` 后取 sha256。**

```bash
cd "…/知识库/内容治理"
python3 - <<'PY'
import json,hashlib
def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def canon(o): return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(",",":"))
EXCL={"last_modified_time","last_modified_by"}
def rec_hash(fields):
    fv={v["field_id"]:v["raw_verbatim"] for v in fields.values() if v["field_id"] not in EXCL}
    return sha(canon([["field_id",k,"value",v] for k,v in sorted(fv.items())]))
base="kb/l0/records/广告文案风控库__"
for tbl,rid in [("广告文案明细","recvuJYdOb61lT"),("广告文案明细","recvuJYdObDPRw"),
                ("广告文案明细","recvuJYdObfmhq"),("品线内容边界规则库","recvuNifmKBXoP")]:
    print(rid, rec_hash(json.load(open(f"{base}{tbl}/{rid}.json"))["fields"]))
PY
```

2026-09-30 本机实测输出（**4/4 PASS**，与 L0→L4→L5 各侧登记值逐字一致）：

| record_id | 对应条款号 | 复算结果 | 判定 |
|---|---|---|---|
| `recvuJYdOb61lT` | `W-1.1`（主锚点） | `67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e` | PASS |
| `recvuJYdObDPRw` | `W-1.1` 第 2 个支撑记录 | `c0f86465188e72be494c690c79df75bd563cc59b930cc7588baafa116ed53edb` | PASS |
| `recvuJYdObfmhq` | `W-1.1` 第 3 个支撑记录 | `87c9807847b95860c1e4e1c6d30740ed7a00b6f89d677c8b1e28fe7a93984521` | PASS |
| `recvuNifmKBXoP` | `W-1.31` | `a2aca575cf6a2ec78155d31cbabf252fc145844429b89b01923226a720d231aa` | PASS |

`W-1.1` 的 9 个证据单元（`unit_id`，L4 / L5 两侧一致）：
`74d1ba6b94a5336853dd` · `0d3289c8b0363292fff1` · `cb3ae64719ed621f4e63` · `5f9f482b4bade3657b3b` ·
`0c2cc17745aa61d72ba5` · `6e4f7cd4b290ee3ce3d3` · `4db6e029b86b84d2bd23` · `ade7467190e6baa76b61` · `1430107f00011461366c`

`W-1.31` 的 4 个证据单元（同一锚点资源的 4 个字段，`source_sha256` 全为 `a2aca575…`）：
`0d21ce57a193b04e28e5`（边界内容）· `19b2539a4a322b4a2277`（检测关键词）·
`deb98959a4a6dee72f52`（豁免词）· `054ded9d6291ce914535`（正则表达式）

---

## 6. 引用契约硬闸门自查（逐项）

`kb/l7/registry/l7.json → citation_contract`：`must_include = 库名 / 版本 / 条款号 / anchor / source_sha256 / 逐字摘录`；
`hard_gate` = 锚点解析失败、`source_sha256` 对不上、摘录与原文不逐字一致，**三者任一不满足 → 该结论不输出**。

| 闸门项 | 结果 | 证据 |
|---|---|---|
| 锚点可解析到本地 L0 | ✅ | 两个锚点分别落到 `kb/l0/records/广告文案风控库__广告文案明细/recvuJYdOb61lT.json` 与 `…/品线内容边界规则库/recvuNifmKBXoP.json` 的对应字段 |
| `source_sha256` 对得上 | ✅ **本机独立复算 4/4 PASS** | 见 §5 |
| 摘录与原文逐字一致 | ✅ | 本文所有摘录取自 L0 字段与 canonical 行，未转述 |
| 库名在册 | ✅ | 只用 `kb/l0/registry/kb.json → kb_types` 里的《措辞表达库》 |
| 版本可给 | ⚠ **`v0`，且 registry 原文是「试用版，未发布」** | 引用时必须带上这句 |

### 6.1 一个必须一起写进评审记录的缺口：条款号那层**顶层**不带指纹

`wording_entry.jsonl` 第 1 行的 **`cite_check.source_sha256` = `null`**，该行**顶层也没有 `source_sha256` 字段**（措辞类 509 条全如此）。

但**指纹并非完全拿不到** —— 同一行的 `evidence_units[]` 里带着 9 个单元级 `source_sha256`，
`evidence_units[0]` 就是 `67875346…`（本文 §2 引的就是这一处，与 L5 第 6 行顶层同值）。

**正确写法是分层成对引用**，不要合成一句：

- 「**P0 判定** → L5 `p0_patterns.jsonl` 第 6 行（H09），`source_sha256 = 67875346…`（顶层字段）」
- 「**条款号** → L4 `wording_entry.jsonl` 第 1 行（`W-1.1`），该行顶层/`cite_check.source_sha256` = `null`；
  指纹取同行 `evidence_units[0].source_sha256` = `67875346…`」

按 `hard_gate` 的严格读法，**单看 L4 那一行的 `cite_check` 字段是过不了指纹闸门的**；
本单的写法是把 L5 顶层与 L4 单元级这一对**同值指纹**并引。该缺口已登记，建议交 `kb-check` / `kb-repair`，
**不要在评审记录里假装它不存在**。

---

## 7. 已知冲突与未决项（写评审记录时如实带上，别抹平）

1. **L4 条款号口径冲突（既有、已登记）**：现行 `l4.json` 台账共 **509** 号（仅 `W-1` 56 个 + `W-2` 453 个，`totals.assigned = 509`，`run_id = 20260930-1550`），
   而四个 canonical 形态文件实文件行数是 **1242** 行（`wording_entry` 56 ▪ `wording_revision_pair` 453 ▪ `sample_case` 358 ▪ `scoped_clause` 375）。
   **`W-1.1` 与 `W-1.31` 都落在台账的 509 之内，不受这次冲突影响**；受影响的是台账里还没有的号段。
   详见 `L4条款号-口径冲突-只读-20260930.md`。
2. **人工抽查未做、无发布版本**：L4 晋升依据是机器判据 `C1–C8` 实测全过（`promotion_basis` 逐条列在 canonical 行里），
   **人工抽查未做**。本库因此**不能声称已过正式验收**，`v0` 只能按「试用版、未发布」引用。
3. **`rule_text` 被截断**（`W-1.1`）：原文在「H07 疼痛功效承」处断掉（入库时截断，非本文删减）。
   要完整依据用 `reason` 字段（本文 §2.1 已逐字给出，是完整的）。
4. **`W-1.31` 的宽正则没进 L5 也没进 L4**（§3 已逐字摘录 L0 的 6 段正则）：
   L5 该行 `regex_patterns` 只有 2 条（不含 `simulate\w*` / `cop|copies|copy` / `replicates?` / `(fullness|satiety) feedback` / `自动(识别|检测|判断)…`），
   L4 canonical 行只保留了 29 个关键词文本。**属 L5 模式表与来源词表口径不一致**，建议交 `kb-check` / `kb-repair`。
5. **未做**：未发号、未晋升、未重建 L4/L5、未改 canonical / 台账 / L5 模式表。

---

## 8. 引用前的三条边界（库自己写的口径）

1. **命中 P0 ≠ 内容违规定性**：`match_note` 一律 `BLOCK`，是「最高优先级」分流口径；
   **未命中也不等于合规**（`no_hit_semantics` 原文：**字面未匹配，不代表合规**）。
2. **改写建议 ≠ 放行依据**：`suggested_replacement` 只解决「怎么写更稳」，不构成「这条能发」的结论；
   该字段**是多段拼接的**（`W-1.1` 那行里混进了 H02/H07 的建议），**只引与命中片段同源的那一段**。
3. **⚠ 部署的 L5 matcher 只覆盖 `W-1.31` 词表的 4/29**（2026-09-30 逐词实测）：
   ✅ 命中 4 个：`mimics your baby` · `mimics a nursing baby` · `mimics baby` · `模拟婴儿`（最后一个走的是 `W-1.1` 的等价词表）；
   ❌ 未命中 26 个，含 `simulates your baby` · `copies your baby` · `copies your baby` · `饱腹反馈` · `模拟宝宝` · `自动识别节奏` · `降低奶量焦虑` 等。
   **审计口径必须写：「matcher 未命中」≠ 该表述合规** —— 它们在 `W-1.31` 的条款定义里明确是违规。
   **不要**在评审记录里把 `W-1.31` 的 29 个词写成「均已由 P0 拦截」，实测只有 4 个。
