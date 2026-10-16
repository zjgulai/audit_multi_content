# 「mimics baby」的条款号 · 只读核对（20260930）

> 提问入口：`/kb-p0-check` —— 「这条 mimics baby 的规则，条款号是多少？」
> 本次**只读**：未调 `l5_prep.py` / `l5_export.py`，未改 `p0_patterns.jsonl`，未发号、未晋升、未动 canonical / 台账。
> cwd：`…/skills-回归测试/知识库/内容治理`（= `kb/` 的上一级）

---

## 0. 一句话结论

**条款号 = `W-1.1`**（`rule_code` = **H09**，`rule_id` = `r-006445396c95aa10`）。
但**这个号不是 `kb-p0-check` 这一层给的** —— 见 §3 层归属。

---

## 1. L5 本层能给的（确定性匹配，非语义推断）

命令：`KB_INTERP_OK=1 /usr/bin/python3 kb/l5/matcher.py --text "Our pump mimics baby's natural nursing." --json`

```
是否 P0：是
命中模式：H09（pattern_id=p-d31dfbc932cb84ac，authority=expert，match_note=BLOCK）
命中片段：our pump mimics baby's natural nursing.  ← span [9,20]
         命中方式 regex：\bmimic(s|king)?\b[^.]{0,30}\bbaby\b
证据单元：unit_id=74d1ba6b94a5336853dd 等 9 个（另 8 个见下）
         source_sha256=67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e
来源：kb/l5/p0_patterns.jsonl 第 6 行
```

9 个证据单元 `unit_id`：`74d1ba6b94a5336853dd` · `0d3289c8b0363292fff1` · `cb3ae64719ed621f4e63` ·
`5f9f482b4bade3657b3b` · `0c2cc17745aa61d72ba5` · `6e4f7cd4b290ee3ce3d3` ·
`4db6e029b86b84d2bd23` · `ade7467190e6baa76b61` · `1430107f00011461366c`

`anchor`：`#广告文案明细/recvuJYdOb61lT/命中片段`
命中关键词（逐字，共 8 个）：`mimics baby's natural nursing` / `baby-like suckling` / `imitates baby` /
`mimic baby` / `mimics a baby` / `模仿婴儿` / `模拟婴儿吸吮` / `还原婴儿吮吸`

`matcher.py --selftest` 同时复跑：**正例全命中、负例零误报**。

---

## 2. L4 侧（条款号的出处，三处一致）

| 出处 | 内容 |
|---|---|
| `kb/l4/canonical/wording_entry.jsonl` **第 1 行** | `article_no = "W-1.1"`｜`rule_code = "H09"`｜`rule_id = "r-006445396c95aa10"`｜`status = "stable"` |
| `kb/l4/registry/l4.json` → `numbering.issued["W-1"].assigned` | `"r-006445396c95aa10": "W-1.1"` |
| 四个 canonical 形态文件全扫 | `r-006445396c95aa10` **只出现 1 次**（`wording_entry.jsonl`）→ 该号不歧义 |

即：**已定稿、已发号**（`status=stable`），不是 L3 草案。
`kb/l7/scripts/l4_gate.py` 只读复算：定稿 **1242** 条、C1–C6 全过、退出码 0、号段 `E-1.1 … W-3.99`。

---

## 3. 层归属（为什么这一问严格说不在 `kb-p0-check` 里）

- **L5 层没有「条款号」这个字段**：`grep -c article_no kb/l5/p0_patterns.jsonl kb/l5/registry/l5.json kb/l5/matcher.py` → **全 0**。
  L5 只有 `pattern_id` / `rule_code` / `rule_id` / `anchor` / `match_terms`。
- **条款号（`article_no`）是 L4 定稿与发布层的字段**，查询档入口是 **`kb-canonical-lookup`**
  （该 skill 的 B 卷负例口径同此：「批量要条款号做对照表」应触发 `kb-canonical-lookup`，不触发 `kb-p0-check`）。
- 本次是为了把答案给全，**只读跨层核了一次 L4**；上表数字是核对结果，不是 L5 本层的产出。

**所以对外引用时请分开写**：
「P0 判定 → L5 `p0_patterns.jsonl` 第 6 行（H09）」；「条款号 → L4 `wording_entry.jsonl` #1（W-1.1）」。

---

## 4. 引用前要知道的三件事

1. **命中 P0 ≠ 内容违规**：`match_note` 一律 `BLOCK`，只是「最高优先级」口径；未命中也不等于合规，其余风险仍走 `kb-review`。
2. **L4 现行台账与订稿文件口径冲突（既有、已登记）**：现行 `l4.json` 台账 **509** 号（只 W-1 + W-2），
   而四个 canonical 文件与 `l4_gate.py` 复算是 **1242** 号（W-1 56 · W-2 453 · W-3 157 · S-1 201 · E-1 375）。
   **`W-1.1` 落在 509 之内，不受这次冲突影响**；受影响的是 W-3 / S-1 / E-1 那 733 个号。
   详见 `L4条款号-口径冲突-只读-20260930.md`。
3. **`W-1.1` 在 L4 侧缺 `source_sha256`**（顶层与 `cite_check.source_sha256` 均为 `null`；措辞类 509 条全如此）。
   按 `kb/l7/registry/l7.json → citation_contract.hard_gate`，这一份**过不了指纹硬闸门**。
   要带指纹引用，用 L5 这条的 `source_sha256 = 67875346…`；该缺口建议交 `kb-check` / `kb-repair`。

---

## 5. 顺手发现的一个工具问题（建议登记）

手册 `references/layer-playbook.md` §一 写的推荐命令 **`kb/kbpy l5/matcher.py …` 在本机挂住**：
`kbpy` 内部要先跑 `python3 kb/l8/_interp.py` 解析解释器，该步 **>90s 不返回**（`kbpy` 调用整体 >60s 超时被杀）。
绕开办法（本次实测 **2.9s** 出结果）：

```bash
KB_INTERP_OK=1 /usr/bin/python3 kb/l5/matcher.py --text "…" --json
```

`kb/.kb-python` 写的就是 `/usr/bin/python3`，解释器本身没问题 —— 卡在 `_interp.py` 探测那一步。

---

## 6. 边界（本次未做）

未发号、未晋升、未重建 L4/L5、未改任何 canonical / 台账 / 模式表。
重建或导出 P0 层是写操作，走 `kb-pipeline`（层身份 + `--apply` + 人开闸，三条件缺一不可）。

**写入披露（据实）**：本次唯一落进 `kb/` 的字节，是跑 `kb/l7/scripts/l4_gate.py` 时该脚本自己写的
`kb/.work/l4_gate_run.txt`（16:04:20，内容 `exit=0`）—— 闸门自带运行日志，非人工改库。
`kb/l5/p0_patterns.jsonl`（mtime 09-28 18:31）与四个 canonical 文件（09-29 10:32）**mtime 未动**。

**并发提示**：本次查询期间，同一知识库上有**其他会话在并行跑闸门**（`kb_pipeline.py --check` /
`l0_gate.py` / `l5_gate.py` / `workflow_check.py`，见 `ps`）。`kb/l4/registry/l4.json` 的 mtime
在 16:03:27 被动过。**结论已在 16:05:28 复核一次，仍为 `W-1.1`**（`run_id=20260930-1550`、
`assignments=509`、`W-1` 段 56 个号）。若并发批跑改了 L4，请以改动后的台账复算为准。
