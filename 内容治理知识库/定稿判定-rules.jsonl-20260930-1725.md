# 定稿判定 · `kb/l3/candidates/rules.jsonl`（哪些能当定稿用）

> 入口：`kb-canonical-lookup`（**查询档，只读**）+ `kb-clause-extractor`（L3 层身份口径）
> cwd：`…/知识库/内容治理`（= `kb/` 的上一级）｜核查时间：2026-09-30 17:21–17:26
> 逐行标记：`定稿判定-rules.jsonl-20260930-1725-逐条标记.jsonl` / `.csv`（1018 行，一行一条）
> 本次**未写 `kb/` 内任何文件**；候选文件 sha256 核查前后一致（`aa83d1f9…`）

## 一、结论

**这份文件里是 509 条规则，不是 1018 条 —— 每条规则各占 2 行（只差 `article_no`）。**

| 判定 | 行数 | 规则数 |
|---|---|---|
| ✅ 能当定稿用（已编号的定稿快照） | **509** | **509** |
| ❌ 不能当定稿用（无号重复行） | **509** | **0**（与上一行同规则，不新增规则） |

- **能用的那 509 行**：源文件 **第 510–1018 行**，都带条款号 —— `W-1.1–W-1.56`（entry 56 条）+ `W-2.1–W-2.453`（revision_pair 453 条），逐条在 `_定稿判定.verdict = 可当定稿用`。
- **不能用的是哪几行**：源文件 **第 1–509 行** —— 这 509 行 `article_no` 全为空，是同一批规则的**旧副本**，逐条在 `_定稿判定.verdict = 不可当定稿用`，`blockers` 里写明「本行无号」+「它的定稿凭据在第 N 行」。
- 规则级（去掉重复行后）**没有一条「不能当定稿」**：509 个 `rule_id` 全部已进定稿层，号、状态、正文三处一致。

## 二、为什么不能照这份文件的 `status` 读（先说清口径）

| 读法 | 会得出 | 为什么错 |
|---|---|---|
| 看候选文件 `status` | 「一条都没定稿」 | 1018 行的 `status` **全是 `provisional`** —— 发号不改候选状态（`l4.json → promotion_rule`：晋升不是改名，是**新增**定稿记录） |
| 查 `kb/l4/canonical/rules.jsonl` | 「一条都没定稿」 | 该文件**恒 0 字节**，是历史迁移留痕（`kb/l3/CANONICAL_MOVED.md`）；定稿按**形态**分文件，不在这 |
| 数文件行数 | 「1018 条候选」 | 每条规则 2 行，实数 509 条规则 |

**正确口径**：按 `rule_id` 到 `kb/l4/canonical/` 的**四个形态文件**里找 —— 命中且 `status = stable`、号与台账一致 = 已定稿。

## 三、能当定稿用的 509 条：三处一致（可重跑）

| 核对项 | 实测 |
|---|---|
| 定稿本体 | `kb/l4/canonical/wording_entry.jsonl`(56) + `wording_revision_pair.jsonl`(453) = **509 条，`status` 全 `stable`** |
| 候选带号行的号 == 定稿号 | **509 / 509**，冲突 **0** |
| 定稿号 == 现行台账 `l4.json → numbering.issued / assignments` | **509 / 509**（`assignments` 与 `issued` 逐键相同） |
| `rule_text` 候选 ↔ 定稿逐字一致 | **509 / 509** |
| 证据可回指 | `evidence_units[]` 共 **1729 条引用**，`unit_id + source_sha256 + anchor` 全部命中 `kb/l2/units.jsonl`（sha 不符 0、anchor 不符 0、`rule_eligible=false` 0） |
| 台账里有没有多余的号 | 现行台账 509 个 `rule_id` **全部**在本文件里，无「台账有、文件无」 |
| 有效期 | `2027-03-28`(466) · `2026-12-28`(22) · `2027-09-29`(21)，**按今天 2026-09-30 全部未过期** |
| 撤回/失效 | `superseded_by` / `superseded_at` 全空，509 条无撤回 |
| 闸门 | `kb/kbpy l7/scripts/l3_gate.py` 退出 **0**；`kb/kbpy l7/scripts/l4_gate.py` 退出 **0**（C1–C6 全过，复算定稿 1242 条） |
| 定稿记录来源 | 509 条 `promoted_at_run = 20260929-1100`、`promoted_from = provisional`、`promotion_basis = C1…C8` |

抽样：`r-006445396c95aa10` → `W-1.1`（`wording_entry.jsonl` 第 1 行，规则码 H09「mimics baby」）。

## 四、不能当定稿的 509 行，长什么样

| 项 | 实测 |
|---|---|
| 位置 | 第 1–509 行 |
| `article_no` | 全为空 |
| 与带号行的差异 | **仅 `article_no` 一个字段**（509 对逐字段比对，差异字段集合 = `{article_no}`） |
| 与备份的关系 | 前 509 行与 `kb/l4/_pre-rebuild-20260930-1550/rules.candidates.jsonl.bak` **逐字节相同**（sha256 `54691908…`，1,387,672 字节）—— 即发号前的旧快照 |
| 为什么不能用 | ① 没号：给不出「第几条」，引用不了；② **没有 `valid_until`**（有效期是四条硬规则第一条，候选行连字段都没有）；③ `owner` 全空、`risk_level` 全 `unknown`、`status` 全 `provisional` |

> 处理建议（不在本次权限内，只报不改）：这 509 行是同 `rule_id` 的旧副本，留着只会让人按行数误判条数；
> 但 L3 是**覆盖式写入层且无 `_archive` 兜底**，任何去重/清行都得先归档再动，不要就地删。

## 五、还有三条边界 —— 不是「没定稿」，是「不能这么用」

### 1. 509 条**都不能当「已发布 / 已验收定稿」**用

| 证据 | 值 |
|---|---|
| `l4.json → promotion_rule.status` | `待抽查（本批不做）`（旧台账写作「机器晋升（machine-promoted）· 人工抽查未做」） |
| `l4.json → canonical.state` | `空（本批不写；定稿要过抽查闸门，抽查是人工环节，不在本批）` |
| `l4_gate.py` | 明说 **C7/C8（晋升后抽查、撤回纪律）不复算** —— 「闸门过」≠「已验收」 |
| `version_rule` | `kb_version` 仍 `v0`、不产生 `release_id`、`versions.jsonl` 不追加版本行 |

→ 它们只是**已编号的定稿快照**，可当「这条规则的性质与正文」的依据，**不可**当「已发布版本 / 已验收」的依据。

### 2. 候选文件的带号行**不能替代定稿记录**（字段差得比想象多）

拿带号候选行与同 `rule_id` 的定稿记录逐字段比，**509 条全部有差异**：

| 字段 | 值不同的条数 | 其中方向 |
|---|---|---|
| `status` | 509 | `provisional` → `stable` |
| `owner` | 509 | 空 → `法务` / `法务 + 产品负责人` 等 |
| `effective_from` | 509 | 空 → `2026-09-29` |
| `verification` | 62 | 全是 `已归纳` → `已支持`（其余 447 条两边都是 `待验证`） |
| `risk_level` | 55 | `unknown` → `高危·红` / `审慎·黄` / `绿色-可用` … |
| **`p_level`** | **42** | 例：`W-1.1` 候选 P2 → 定稿 **P0** |
| `rule_code` | 21 | 候选常为空、定稿回填规则码 |
| `suggested_replacement` | 12 | 定稿改写 |

另外候选行**根本没有**这些字段：`valid_until`、`half_life_days`、`cite_check`、`promotion_basis`、`promoted_at_run`、`promoted_from`、`p_level_basis`、`authority`、`authority_source_table`、`rule_kind`、`risk_evidence_records`。

**最要命的一条**：候选文件里 `p_level` 只有 P1/P2，**P0 条数 = 0**；定稿记录里有 **21 条 P0**（W-1.1、W-1.2、W-1.4、W-1.6、W-1.8、W-1.9、W-1.10、W-1.13、W-1.14、W-1.18、W-1.21、W-1.22、W-1.24、W-1.31、W-1.33、W-1.41、W-1.43、W-1.47、W-1.53、W-1.55、W-1.56）。
→ **谁拿候选行当定稿用，就会漏掉全部 21 条 P0。** 定稿判定可以看候选，**取字段必须回 `kb/l4/canonical/`**。

> 另有一处不算硬伤、但机器取字段会取空的：**19 条 `entry` 的 `forbidden_expression` 为空**
> （`W-1.2/1.3/1.10/1.14/1.21/1.23/1.24/1.28/1.29/1.32/1.34/1.37/1.38/1.39/1.42/1.45/1.46/1.52/1.56`）——
> 它们的「禁用/建议表达」写在 `rule_text` 与 `suggested_replacement` 里（19 条均非空），语义自足。
> 按结构化字段取「禁用表达」的下游会取到空串，属字段回填缺口。

### 3. 引用契约缺一个字段（要修，不是「不能用」）

`kb/l7/registry/l7.json → citation_contract.must_include` 要 `source_sha256`（`forbidden` 明确禁止「只给锚点不给 source_sha256」）。实测：

- 509 条定稿的**顶层 `source_sha256` = 空**，`cite_check.source_sha256` **也为 null**；
- 但 **`evidence_units[]` 里逐条指纹齐全**（1729/1729，且 sha256/anchor 与 L2 单元逐字一致、`cite_check.unresolvable` 全空）。

→ 结论只到「**便利字段为空、指纹要从 `evidence_units[]` 取**」这一层。我**没有**验证引用方是否接受从 `evidence_units[]` 取指纹，因此**不主张**「这批引用不出去」；补齐顶层字段属注册表/契约层面的修复，交 `kb-check` / `kb-repair`。

## 六、顺手记两条台账口径（会影响「怎么判已发号」）

1. **现行台账只登记了 509 条，定稿文件里是 1242 条**。
   - `kb/l4/registry/l4.json`（run `20260930-1550`）：`libraries_used = ["wording"]`，`issued` 只有 `W-1`(56) + `W-2`(453)。
   - `kb/l4/canonical/` 实际：1242 条（`sample_case` 358 + `scoped_clause` 375 + entry 56 + revision_pair 453），`l4_gate` 也按 1242 复算。
   - 旧备份 `kb/l4/_pre-rebuild-20260930-1550/l4.registry.json.bak` 里有 **1242** 个号（多出 `W-3` 157 / `S-1` 201 / `E-1` 375 = **733 个**）。
   → 判「已发号」别只看现行台账；本次这 509 条不受影响（三处一致）。
2. **现行台账 `inputs` 块自相矛盾**：`base_lines = 1018`、`lines_after = 1018`、`appended_this_run = 509`（追加 509 却行数不变）；`prefix_unchanged = false` 也与实测（前 509 行逐字节未变）不符。另：`base_sha256 = aa83d1f9…` 实测等于**追加后**的现行文件哈希，不等于发号前的 `.bak` 哈希（`54691908…`）。这是自述字段写错，**不是数据损坏**。

## 七、逐条标记怎么看

`定稿判定-rules.jsonl-20260930-1725-逐条标记.jsonl` —— 1018 行，每行 = 源文件一行 + 一个 `_定稿判定` 块：

```json
{"src_line": 510, "rule_id": "r-006445396c95aa10", "article_no": "W-1.1", "form": "entry",
 "p_level_candidate": "P2", "p_level_canonical": "P0", "twin_lines": [5],
 "_定稿判定": {"verdict": "可当定稿用",
              "口径": "已编号的定稿快照（machine-promoted）",
              "blockers": [],
              "notes": ["定稿本体在 kb/l4/canonical/wording_entry.jsonl 第 1 行", "…"],
              "不能当什么用": ["已发布定稿 —— kb_version=v0 未发布；人工抽查未做（machine-promoted）"]}}
```

`verdict` 只有两个取值：`可当定稿用`（509 行，第 510–1018 行）/ `不可当定稿用`（509 行，第 1–509 行，`blockers` 写明原因）。`.csv` 是同样内容的表格版（含「阻断原因」一列，可直接筛）。

## 八、边界（没做的事）

- **没写 `kb/` 内任何文件**：候选、canonical、台账、索引全程只读；产物只落在工作区根目录。
- 没发号、没晋升、没改 `canonical`、没去重那 509 行（去重属 L3 写操作，须先归档，交 L3 owner / `kb-repair`）。
- 没核 `source_sha256` 顶层字段的补齐方案（只报「为空」＋「指纹在 `evidence_units[]` 里齐全」）。
- `l4_gate.py` 的 C7/C8 不复算，本报告**不主张**这 509 条已通过人工抽查。
- 本次核查前后 `kb/l3/candidates/rules.jsonl` sha256 均为 `aa83d1f9…`（未变）；另两个只读闸门脚本经源码确认只 `open(..., encoding="utf-8")` 读文件、无写盘调用。
