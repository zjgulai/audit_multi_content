# 「mimics baby's natural nursing rhythm」是否 P0 · 依据单（2026-09-30）

> 入口：`/kb-p0-check` 查询档（**只读**）。未调 `l5_prep.py` / `l5_export.py`，未改 `kb/l5/p0_patterns.jsonl`，
> 未发号、未晋升 canonical、未动台账。cwd：`…/skills-回归测试/知识库/内容治理`（= `kb/` 的上一级）。
> 待判文本（逐字）：`mimics baby's natural nursing rhythm`

---

## 0. 一句话结论

**是 P0。** 命中 `kb/l5/p0_patterns.jsonl` **第 6 行**的模式
**`p-d31dfbc932cb84ac`**（`rule_code` = **H09**，`rule_id` = `r-006445396c95aa10`，**`authority` = `expert`**，
`p_level` = `P0`，`match_note` = `BLOCK`）。
需引用的证据单元 **9 个** `unit_id`（见 §3），`source_sha256` = `67875346a75bd2f8…`。

---

## 1. 判定（确定性匹配，非语义推断）

命令：`KB_INTERP_OK=1 /usr/bin/python3 kb/l5/matcher.py --text "mimics baby's natural nursing rhythm" --json`

| 项 | 值 |
|---|---|
| 是否 P0 | **是** |
| 命中模式 | `p-d31dfbc932cb84ac`（H09，authority=expert） |
| 命中方式 | **regex**：`\bmimic(s|king)?\b[^.]{0,30}\bbaby\b` |
| 命中 span | `[0, 11]` = 逐字 `mimics baby` |
| `matched_count` | 1（`whitelist_suppressed` = 0 → **豁免未生效**） |
| `match_note` | `BLOCK` |
| 来源 | `kb/l5/p0_patterns.jsonl` **第 6 行** |

**这一点要特别说明**：本条的命中**不是**靠逐字同形，而是靠 `mimics baby` 这个词族形态被正则捞住。
源侧逐字证据是 `mimics baby’s natural nursing`（**带弯引号 ’**）；本次待判文本是直引号 `'`、
且尾部多一个 `rhythm` —— **仍在命中范围内**，因为正则只要求 `mimic(s|king)` 与 `baby` 之间 ≤30 字符。
结论：**换标点、加尾巴都躲不过去**，不要试图靠改写时态/引号规避。

---

## 2. authority 与「条款号」的层归属（两个都要，但不是一个层的）

| 层 | 字段 | 值 |
|---|---|---|
| **L5**（P0 判定层） | `pattern_id` | `p-d31dfbc932cb84ac` |
| | `rule_code` / `rule_id` | `H09` / `r-006445396c95aa10` |
| | **`authority`** | **`expert`**（本层给的权威口径就是它） |
| | `anchor` | `#广告文案明细/recvuJYdOb61lT/命中片段` |
| **L4**（定稿与发布层） | `article_no` | `W-1.1`（`kb/l4/canonical/wording_entry.jsonl` **第 1 行**，`status=stable`） |

**注意**：`authority` 是 **L5 模式**的字段（`expert`），而 `W-1.1` 是 **L4** 的条款号 ——
L5 层**没有** `article_no` 字段。对外引用请写清是哪一层给的：
「P0 判定 → L5 `p0_patterns.jsonl` #6（H09，authority=expert）」；
「条款号 → L4 `wording_entry.jsonl` #1（W-1.1）」。

**本次 authority 复核**（`kb/l5/registry/l5.json → selection`）：
`p_level=P0 ∧ rule_kind=atomic ∧ authority∈{expert,legal}` + `code_allowlist=[H06]`。
H09 走的是**常规门槛**（`expert`），**不是** H06 那条「按码准入」的例外 —— 所以它不依赖 allowlist。

---

## 3. 该引用的证据单元（9 个，全部已回 L2 解析验证）

`source_sha256` 三种取值，按记录分组：

**记录 `recvuJYdOb61lT`（sha `67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e`）**

| unit_id | anchor |
|---|---|
| `74d1ba6b94a5336853dd` | `#广告文案明细/recvuJYdOb61lT/命中片段` |
| `0d3289c8b0363292fff1` | `#广告文案明细/recvuJYdOb61lT/修改建议` |
| `cb3ae64719ed621f4e63` | `#广告文案明细/recvuJYdOb61lT/命中原因` |

**记录 `recvuJYdObDPRw`（sha `c0f86465188e72be494c690c79df75bd563cc59b930cc7588baafa116ed53edb`）**

| unit_id | anchor |
|---|---|
| `5f9f482b4bade3657b3b` | `#广告文案明细/recvuJYdObDPRw/命中片段` |
| `0c2cc17745aa61d72ba5` | `#广告文案明细/recvuJYdObDPRw/修改建议` |
| `6e4f7cd4b290ee3ce3d3` | `#广告文案明细/recvuJYdObDPRw/命中原因` |

**记录 `recvuJYdObfmhq`（sha `87c9807847b95860c1e4e1c6d30740ed7a00b6f89d677c8b1e28fe7a93984521`）**

| unit_id | anchor |
|---|---|
| `4db6e029b86b84d2bd23` | `#广告文案明细/recvuJYdObfmhq/命中片段` |
| `ade7467190e6baa76b61` | `#广告文案明细/recvuJYdObfmhq/修改建议` |
| `1430107f00011461366c` | `#广告文案明细/recvuJYdObfmhq/命中原因` |

**回验**：9/9 全部在 `kb/l2/units.jsonl` 解析到，`source_sha256` 逐条与模式表一致（缺失 0 / 不一致 0）。
覆盖记录 **3** 条（`recvuJYdOb61lT` / `recvuJYdObDPRw` / `recvuJYdObfmhq`）。

**引用时建议只带这 3 个**（最省、且每个记录都有「命中片段 + 处理方式 + 命中原因」三件套）：
`74d1ba6b94a5336853dd`（0 号记录的命中片段，逐字含 `H09:mimics baby,mimics baby’s natural nursing`）、
`5f9f482b4bade3657b3b`、`4db6e029b86b84d2bd23`。

---

## 4. 处理方式（源侧给的口径，**不许直接外发**）

- H09 怎么改：**删除**「自动识别节奏 / 模拟复制宝宝 / 饱腹反馈 / 降低奶量焦虑」等**智能闭环与仿生宣称**；
  仿生表达**只允许** `inspired by natural nursing`（参考自然哺乳节奏的设计思路）。
- 命中原因（`cb3ae64719ed621f4e63` 逐字）：H09 智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；
  **W1 当前为用户主动调节 + 保存程序，非闭环生理识别** —— 即产品不具备该能力，「mimics baby's natural nursing rhythm」构成**能力夸大**。
- ⚠️ 同一条命中片段（`74d1ba6b94a5336853dd`）**同时挂着 H02 与 H07**：
  `H02:increase milk supply / H07:pain-free / H09:mimics baby,mimics baby’s natural nursing`。
  所以这句所在的那段文案若还带 `more milk` / `pain-free` 一类表述，是**三码并发**，别只按 H09 处理。

---

## 5. 引用前必须知道的四条边界

1. **命中 P0 ≠ 内容合规判决**：`match_note=BLOCK` 只是「最高优先级」口径。**未命中也不等于合规**，
   其余风险仍走 `kb-review`。
2. **`suggested_replacement` 不许直接外发**，外发前仍需人工复核。
3. **本条证据级为 `L1`**（派生视图 `cg-r-006445396c95aa10` 明写：源库证据级 synthesis，但只归属 **1 个来源根**，
   按加载器 E036 口径降为 L1，**只能当线索**）。`rule_status=provisional`（未过正式验收）。
4. **`W-1.1` 在 L4 侧缺 `source_sha256`**（顶层与 `cite_check` 均为 `null`）。
   要带指纹引用条款号，**用 L5 这条的 `source_sha256 = 67875346…`**。

---

## 6. 顺手核到的两个口径坑（别按错的说法宣导）

1. **「P0 共 6 条」是错的**。手册 `references/layer-playbook.md` §写档写「实测 21 条 P0 → 入选 6 条」，
   那是 **`authority` 门槛内**的数；`l5.json → excluded.P0_admitted_by_allowlist = 1` 说明 H06 另按码准入。
   **模式表实测 7 条**（`kb/l5/p0_patterns.jsonl` 非空行 7，与 `kb/l5/index/l5.jsonl` 7 行一致）。
   宣导口径：**7 条**，或「6 条 expert 门槛内 + 1 条 H06 按码准入」。
2. **闸门状态**：`kb/l7/scripts/l5_gate.py` 退出码 **0** ——实质 4 项（`pattern_traceability` /
   `no_fabricated_words` / `version_discipline` / `offline`）全 **PASS**；
   基线 2 项（`frozen_layers` / `l3_append_only`）**FAIL 但已登记为判据过期**，不判红。

---

## 7. 边界（本次未做）

未发号、未晋升、未重建 L4/L5，未改任何 canonical / 台账 / 模式表。
重建或导出 P0 层是**写操作**，走 `kb-pipeline`（层身份 + `--apply` + 人开闸，三条件缺一不可）。

**写入披露（据实）**：本次在 `kb/` 内唯一落盘的字节是 `kb/l7/scripts/l5_gate.py` 自检器写的
`kb/.work/l5_integrity.json`（闸门自带证据文件，非人工改库）；
`kb/l5/p0_patterns.jsonl` **mtime 09-28 18:31 未动**。本依据单落在工作区根目录，不落 `kb/view/` 装载位。
