# 红线规则 · 条款号对照表（SOP 可贴版）

> **本文性质**：从**权威分层库**（`kb/l0…l7`）逐字提取的对照表，**不加词、不归纳、不补源里没有的说法**。
> **本次复核**：2026-09-30，只读查询，**未写任何库文件**。核对对象是 **7 条「当前真正会被 P0 判定命中」的红线规则**。
> **能贴进 SOP 的范围**：第 1 节（主表）+ 第 2 节（引用格式）。第 3–5 节是效力信息与**必须一并带上的限制**。

---

## 0. 一句话口径（贴表时建议一起抄）

**P0 = 确定性命中，不做语义推断**：命中即最高优先级，`match_note` 一律 `BLOCK`。

- ① **命中 P0 ≠ 内容违规**，只说明它是**最高优先级**；
- ② **未命中 P0 ≠ 内容合规**，其余风险仍走 `kb-review` 三态判定。

---

## 1. 主表（SOP 正文用 · 7 条）

| # | 规则码 | **条款号** | `rule_id`（唯一连接键） | 主题 | 处理方式 |
|---|---|---|---|---|---|
| 1 | H02 | **W-1.18** | `r-37b49eadb72d7dc2` | 奶量 / 奶阵 / 排空类功效承诺 | BLOCK |
| 2 | H04 | **W-1.13** | `r-3055901e5877f981` | 医生 / 专家 / IBCLC 推荐背书 | BLOCK |
| 3 | H05 | **W-1.33** | `r-7baf7ceb47b2e5bc` | 虚假安全承诺 + 绝对化适配承诺 | BLOCK |
| 4 | H06 | **W-1.8** | `r-15a607c4457c8b55` | FDA 批准 / 认证 | BLOCK |
| 5 | H07 | **W-1.53** | `r-d7290a0ee59c58ef` | 疼痛功效承诺（含法 / 德 / 西语） | BLOCK |
| 6 | H09 | **W-1.1** | `r-006445396c95aa10` | 仿生 / 模仿婴儿吸吮 | BLOCK |
| 7 | U04 | **W-1.55** | `r-e879231d61c9bd08` | 痛点场景 + 消除暗示（需人工判定） | BLOCK |

> **主表可直接贴进 SOP**。多出的 `rule_id` 列不是装饰：`rule_code` 在全库**不唯一**（见 §5.2），
> 只写「H02 = W-1.18」无法唯一定位；带 `rule_id` 才能回源到唯一一条定稿记录。

---

## 2. 引用格式（引自 `kb/l7/registry/l7.json` → `citation_contract`）

**简式（SOP 表格内可用）**：

> 《措辞表达库 v0》第 **W-1.18** 条

**正式文件必须补齐** —— 契约 `format` 原文为：

> `《<库名> <版本>》第 <条款号> 条（链接：<url>）`

且 `must_include` 要求引用必须同时带 **库名 + 版本 + 条款号 + anchor + source_sha256 + 逐字摘录**。
**只写「W-1.18」不满足契约**；进正式文件按 §4 的锚点表补齐。

| 项 | 值（原文） |
|---|---|
| `version_in_citation` | `v0（试用版，未发布）` |
| 库名 | 《措辞表达库》（`kb/l0/registry/kb.json → kb_types`，**不得自造库名**） |
| `forbidden` | 只给锚点不给 `source_sha256`；转述/概括/润色摘录；裸 URL 当依据；引用不存在的库名 |
| `hard_gate` | 引用不到本地锚点（anchor 解析失败 / `source_sha256` 对不上 / 摘录与原文不逐字一致）的结论，**一律不输出** |

---

## 3. 效力与责任（7 条完全相同，只有 owner 分两档）

| 条款号 | 规则码 | owner | 生效 | 有效期至 | 半衰期 | `p_level` | `risk_level` | `status` | `superseded_by` |
|---|---|---|---|---|---|---|---|---|---|
| W-1.18 | H02 | 法务 + 医学顾问 | 2026-09-29 | 2027-09-29 | 365 天 | P0 | 高危·红 | stable | 空 |
| W-1.13 | H04 | 法务 + 产品负责人 | 2026-09-29 | 2027-09-29 | 365 天 | P0 | 高危·红 | stable | 空 |
| W-1.33 | H05 | 法务 + 产品负责人 | 2026-09-29 | 2027-09-29 | 365 天 | P0 | 高危·红 | stable | 空 |
| W-1.8 | H06 | 法务 + 产品负责人 | 2026-09-29 | 2027-09-29 | 365 天 | P0 | 高危 | stable | 空 |
| W-1.53 | H07 | 法务 + 医学顾问 | 2026-09-29 | 2027-09-29 | 365 天 | P0 | 高危·红 | stable | 空 |
| W-1.1 | H09 | 法务 + 产品负责人 | 2026-09-29 | 2027-09-29 | 365 天 | P0 | 高危·红 | stable | 空 |
| W-1.55 | U04 | 法务 + 医学顾问 | 2026-09-29 | 2027-09-29 | 365 天 | P0 | 高危·红 | stable | 空 |

**7 条均在有效期内**（截至 2026-09-30 剩余 **364 天**）。
W-1.8 是唯一一条 `authority = inferred`（其余 6 条为 `expert`）、`risk_level` 为「高危」（无「·红」）的条目。

---

## 4. 命中范围、触发表达与回源锚点

### 4.1 规模与锚点

| 条款号 | 字面触发词 | 正则 | 证据单元 | 指纹（`evidence_units[].source_sha256`） | anchor | authority |
|---|---|---|---|---|---|---|
| W-1.18 | 24 | 3 | 102 | 34 个不同源（非单一值） | `#广告文案明细/recvuJYdOb1Rm1/命中片段` | expert |
| W-1.13 | 13 | 2 | 6 | 2 个 | `#广告文案明细/recvuJYdObV6eR/命中片段` | expert |
| W-1.33 | 13 | 4 | 36 | 12 个 | `#广告文案明细/recvuJYdOb1B8v/命中片段` | expert |
| W-1.8 | 5 | 3 | 4 | 1 个：`2e8bb36d6edf7c4971132b69ff6d39819a5a0e0e8043e9001e096be1bc2a02d6` | `#品线内容边界规则库/recvuJP1LVW6E0/边界内容` | inferred |
| W-1.53 | 17 | 3 | 153 | 51 个 | `#广告文案明细/recvuJYdOb1u94/命中片段` | expert |
| W-1.1 | 8 | 2 | 9 | 3 个 | `#广告文案明细/recvuJYdOb61lT/命中片段` | expert |
| W-1.55 | 4 | 2 | 6 | 2 个 | `#广告文案明细/recvuMGgT9p2zx/命中片段` | expert |

**合计**：字面触发词 **84** ｜ 正则 **19** ｜ 证据单元 **316**（本次逐条相加，与分列加总一致）。
7 条**完全不共享触发词**（各条 `match_terms` 两两交集为空）；共享的是**同一组 6 条误报豁免正则**（`whitelist` 签名一致，共 6 条）。

### 4.2 触发表达（逐字，源字段顺序）

| 条款号 | 触发表达（`match_terms[].term` 原文） |
|---|---|
| W-1.18 | `augmente la production de lait`、`boost supply`、`easier let-down`、`easier letdown`、`improve pumping efficiency`、`increase milk supply`、`increases milk production`、`increasing milk supply`、`mehr milch`、`more milk`、`más leche`、`plus de lait`、`producción de leche`、`support faster let-down`、`triggers letdown`、`boost milk`、`maximize milk`、`milk supply boost`、`下奶`、`催乳`、`催奶`、`增产`、`增加奶量`、`奶量提升` |
| W-1.13 | `ibclc-recommended`、`ob-gyn recommended`、`recommended by 100+ experts`、`doctor recommended`、`doctor-recommended`、`expert recommended`、`expert-recommended`、`expert-tuned`、`pediatrician recommended`、`专家推荐`、`专家认证推荐`、`专家调校`、`医生推荐` |
| W-1.33 | `perfect pump`、`100% safe`、`100%safe`、`fits all breast shapes`、`one size fits all`、`risk-free`、`safest`、`zero risk`、`一定不损伤`、`完全安全`、`绝对安全`、`适合所有胸型`、`零风险` |
| W-1.8 | `FDA approved`、`FDA certified`、`FDA 批准`、`FDA 认证`、`FDA 通过` |
| W-1.53 | `indolore`、`no pain`、`pain-free`、`painlessly`、`sans douleur`、`say goodbye to cold, painful`、`schmerzfrei`、`sin dolor`、`zero pain`、`free of pain`、`pain relief`、`relieve pain`、`without pain`、`不痛`、`告别疼痛`、`无痛`、`缓解疼痛` |
| W-1.1 | `mimics baby’s natural nursing`、`baby-like suckling`、`imitates baby`、`mimic baby`、`mimics a baby`、`模仿婴儿`、`模拟婴儿吸吮`、`还原婴儿吮吸` |
| W-1.55 | `painful pumping`、`clogged ducts`、`sore breasts`、`sore nipples` |

> 触发表达分两类：`verbatim_source`（源里原话）/ `verbatim_rule_text`（规则正文原话）/ `equivalent_of:<锚点>`（等价变体）。
> SOP 若要给一线「照着搜」的词表，建议**只用上表**，不要自行扩写同义词。

### 4.3 误报豁免（7 条共用同一组 6 条正则 · 命中即**不判 P0**）

| # | 正则 | 作用 |
|---|---|---|
| 1 | `\b(does\s*n[o']?t\|do\s+not\|does\s+not\|not\s+intended\s+to\|never\|no\s+claim)\b[^.]{0,40}\b(treat\|cure\|heal\|pain\|milk)\b` | 英文否定式（"does not treat…"） |
| 2 | `(不能\|不可以\|无法\|并非\|不是\|不做\|严禁\|禁止)[^。]{0,20}(治疗\|治愈\|预防\|无痛\|增产\|催奶\|催乳)` | 中文否定式 |
| 3 | `^\s*(DO\s+NOT\s+SAY\|Do\s+not\s+say\|禁用表达\|禁用词\|禁止表达\|禁止使用\|禁用\|禁止\|不允许\|不得使用\|违规表述\|违规词\|高危词)\s*[:：][^。！？!?]{0,200}` | 培训/清单语境（"禁用词：…"） |
| 4 | `[「『"“][^」』"”]{0,80}[」』"”]` | 引号包裹的**被引用**表达 |
| 5 | `\b(per\|according\s+to\|as\s+stated\s+in\|cited\s+from)\b[^.]{0,30}` | 出处引述 |
| 6 | `^(依据\|来源\|原文\|条款)[:：]` | 中文出处引述 |

### 4.4 建议替代（`suggested_replacement` 原文）

- **W-1.18**（H02）：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用
- **W-1.13**（H04）：删除医生/专家/IBCLC/OB-GYN 推荐背书；免费 IBCLC 服务可单独陈述但不得与“推荐”绑定 ▸ 效果百分比/销量/评分声称需附测试来源与口径，否则删除（折扣百分比不在此列） ▸ 核验 IBCLC/专家身份、参与方式、程序设计依据与 COI 披露后再保留（含 expert-tuned/专家调校/专家程序）
- **W-1.33**（H05）：删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）
- **W-1.8**（H06）：**该字段为空**（`suggested_replacement = ""`）；规则正文即「FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified）」，豁免 `FDA cleared / FDA-cleared / FDA registered / FDA 注册`
- **W-1.53**（H07）：删除 pain-free/no pain/without pain/pain relief/less pain/无痛/缓解疼痛等疼痛功效承诺（含 sans douleur/schmerzfrei/sin dolor），只保留 comfort/gentle 与缓解胀满不适 discomfort 的表述
- **W-1.1**（H09）：删除自动识别节奏/模拟复制宝宝/饱腹反馈/降低奶量焦虑等智能闭环与仿生宣称；仿生表达**只允许** inspired by natural nursing（参考自然哺乳节奏的设计思路）
- **W-1.55**（U04）：删除 pain-free/no pain/without pain/pain relief/less pain/无痛/缓解疼痛等疼痛功效承诺（含 sans douleur/schmerzfrei/sin dolor），只保留 comfort/gentle 与缓解胀满不适 discomfort 的表述 ▸ 人工判定 sore/painful/clogged ducts 是痛点场景描述还是功效承诺；若与 goodbye/no more/not anymore/relieve 连用暗示消除疼痛或堵奶，升级为红并改写为 comfort/discomfort 表述

---

## 5. ⚠️ 贴进 SOP 前必须先看的限制

### 5.1 这 7 条的条款号**不在 P0 清单里** —— 本表是新做的映射

`kb/l5/p0_patterns.jsonl`（7 行）**没有 `article_no` 字段**（实测：该字段不存在，非空值）。
本表的条款号来自 **L4 定稿层** `kb/l4/canonical/wording_entry.jsonl`，映射键是 **`rule_id`**。

### 5.2 **不许用 `rule_code` 当连接键**（会串号）

`rule_code` **在全库里不唯一**：本次实测 L4 `wording_entry` 56 条里只有 23 个不同 `rule_code`，其中 **16 个是多义码**。
同一个码对应**多条不同规则、甚至不同等级**：

| rule_code | L4 定稿条数 | 条款号（等级） |
|---|---|---|
| H02 | 2 | W-1.18（P0）、**W-1.47（P0）** |
| H04 | 2 | W-1.13（P0）、**W-1.41（P0）** |
| H05 | 2 | W-1.33（P0）、**W-1.22（P0）** |
| H06 | 1 | W-1.8（P0） |
| H07 | 2 | W-1.53（P0）、**W-1.6（P0）** |
| H09 | 2 | W-1.1（P0）、**W-1.31（P0）** |
| U04 | 2 | W-1.55（P0）、**W-1.26（P3，不是 P0）** |

→ SOP 里写「H02 → W-1.18」是对的（这是**该码在 P0 命中表里的那一条**），
但**不能写成「H02 就是这个号」**：同码还有 W-1.47。`rule_code` 只是**人读的码**，不是主键。

### 5.3 与 L3 候选层的等级不一致（现状，**未裁决**）

- **L4 定稿**：这 7 条 `p_level = P0`（`p_level_basis`：除 W-1.8 为「来源记录风险等级=高危」外，其余 6 条为「全部支撑记录的风险等级均为高危·红 → P0」）；
- **L3 候选**：同 `rule_id` 的行标 `P2`（6 条）/ `P1`（1 条，W-1.8），且 `risk_level = unknown`、`status = provisional`。
- **另注**：L3 候选里 **W-1.8 的 `rule_code` 是空串**（同一记录两条副本 L3#20 / L3#517 实测均为 `""`），
  `H06` 这个码只出现在 L4 定稿与 L5 匹配表 —— 即**跨层的 `rule_code` 本身对不上**。
  故本表的规则码一律取 **L4 定稿**口径，不取 L3。

L4 闸门 `l4_gate.py` 的 C5「定稿不改写」**只逐字核正文**（`rule_text` 等文本字段），**不核 `p_level`**，所以两处并存不会被判红。

> **贴 SOP 时的安全写法**：等级一律引 **L4 定稿的 P0**（本表口径），并注明「L3 候选同码行为 P1/P2，两者差异未裁决」。

### 5.4 生效范围是 7 条，但 `p_level = P0` 的标记有 21 条

L4 `wording_entry` 里 `p_level = P0` 的记录共 **21 条**，但 L5 匹配表（真正会命中的那套）只有 **7 条**，
另 **14 条没有可执行 pattern**：

`W-1.2`、`W-1.4`、`W-1.6`、`W-1.9`、`W-1.10`、`W-1.14`、`W-1.21`、`W-1.22`、`W-1.24`、`W-1.31`、`W-1.41`、`W-1.43`、`W-1.47`、`W-1.56`

→ 这 14 条**当前不会被 P0 判定命中**。SOP 若要用它们，必须先补 pattern（走 `kb-pipeline` 链路），
**不要在 SOP 里把它们写成「已生效的红线」**。

### 5.5 引用纪律（原文口径）

> `promotion_rule.status = 机器晋升（machine-promoted）· 人工抽查未做` —— 1242 条**只许当「已编号的定稿快照」用，不许当「已发布版本」用**；`kb_version` 仍 `v0`，不产生 `release_id`。

另有 **123 个已发号（全在 `E-` 段）在 canonical 里没有对应记录**（台账 1365 vs 在用 1242），
属**已知缺口**，与本表 7 条无关（本次复算：7 条均能对上 canonical 记录，缺口 123 条**全落 `E-` 段**）。

---

## 6. 复核依据（可逐条重跑）

| 项 | 值（2026-09-30 本次复核实测） |
|---|---|
| 条款号来源 | `kb/l4/canonical/wording_entry.jsonl` ｜ **56 条** ｜ 第 1/8/13/18/33/53/55 行 |
| P0 模式表 | `kb/l5/p0_patterns.jsonl` ｜ **7 行** ｜ 第 1–7 行 |
| 号台账 | `kb/l4/registry/l4.json` → `numbering.issued`（**段 → `assigned{rule_id: 条款号}`** 结构，非平铺列表）；6 个段：`W-1/W-2/W-3/S-1/E-1/E-2` |
| 双路径交叉核验 | 7 条的 `rule_id → article_no` 分别用**台账**与 **canonical 文件**两条独立路径重算：**7/7 两路一致** |
| L4 定稿合计 | 1242 条（wording_entry 56 / wording_revision_pair 453 / sample_case 358 / scoped_clause 375）；`rule_id` **509 个全部唯一、零重复**；733 条样本/条款记录**无 `rule_id` 字段** |
| 7 条定稿属性 | 7 条**全在 `wording_entry` 形态**；`status` 全 `stable`；`superseded_by` 全空；`form = entry`；`rule_kind = atomic`；`verification = 已支持`；`promoted_at_run = 20260929-1100` |
| 明文校验 | 本次读取走 node 读回，权威文件与本表首字节均为明文 JSON/Markdown，**无信封前缀** |
| 库名 / 版本 | 《措辞表达库》`v0`（`kb/l0/registry/kb.json → kb_types`，不得自造库名） |

> `kb/l4/canonical/rules.jsonl` 为 **0 字节**，是迁移留痕 ——
> **查它一定返回空，不代表「没定稿」**。

---

## 7. 可直接贴进 SOP 的最小版（只抄这一块）

```markdown
### 红线规则条款号对照（P0 · 7 条）

| 规则码 | 条款号 | 主题 | 处理方式 |
|---|---|---|---|
| H02 | 《措辞表达库 v0》第 W-1.18 条 | 奶量 / 奶阵 / 排空类功效承诺 | BLOCK |
| H04 | 《措辞表达库 v0》第 W-1.13 条 | 医生 / 专家 / IBCLC 推荐背书 | BLOCK |
| H05 | 《措辞表达库 v0》第 W-1.33 条 | 虚假安全承诺 + 绝对化适配承诺 | BLOCK |
| H06 | 《措辞表达库 v0》第 W-1.8 条 | FDA 批准 / 认证 | BLOCK |
| H07 | 《措辞表达库 v0》第 W-1.53 条 | 疼痛功效承诺（含法 / 德 / 西语） | BLOCK |
| H09 | 《措辞表达库 v0》第 W-1.1 条 | 仿生 / 模仿婴儿吸吮 | BLOCK |
| U04 | 《措辞表达库 v0》第 W-1.55 条 | 痛点场景 + 消除暗示（需人工判定） | BLOCK |

注 1：命中 P0 ≠ 内容违规，只说明是最高优先级；未命中 P0 ≠ 合规。
注 2：`rule_code` 不唯一（如 H02 还对应 W-1.47），引用一律以条款号为准。
注 3：等级取自 L4 定稿（P0）；L3 候选同码行为 P1/P2，差异未裁决。
注 4：库为 v0 试用版、未发布，人工抽查未做；引用须带库名+版本+条款号+anchor+source_sha256+逐字摘录。
```
