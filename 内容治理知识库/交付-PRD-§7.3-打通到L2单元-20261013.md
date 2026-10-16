# 交付：PRD §7.3 —— 已打通到 **L2 可召回单元**（含两个存量 bug 的修复）

日期 2026-10-13 ｜ 依据 Owner 2026-10-13「同意」（继续做 L1 台账那一步）
状态：**L0 → L1 → L2 全通**；L3 蒸馏 → L4 发号未做。

---

## 一、最终结果（一句话）

PRD §7.3 的 **7 条 P0 红线**现在是 L2 的**一等 clause 单元**，带物理锚点与来源指纹：

```
unit_id = bd4267ff5c050ca14e98
unit_type = clause
anchor = #l.495-773              ← anchor_spec.url.line_range 口径
source_sha256 = 6671c283609bef80
红线命中 7/7
```

⇒ 四段溯源的前三段（L0 记录 + L1 anchor/sha + L2 单元）**已齐**。

---

## 二、这一轮做的五件事（每件都有 before/after）

| # | 动作 | 结果 |
|---|---|---|
| ① | L0 登记件投影（记录件 + 台账行 + R27） | L0 闸门 **红 0**（加之前后同值） |
| ② | 下钻加「登记件」种子 | `待处理记录 1 条 {('已登记来源','feishu_wiki_docx'):1}` |
| ③ | **修** wiki 解析（`data.node.obj_token` → `data.obj_token`） | `kind: wiki` → **`wiki→docx`**；`title` 空 → **内容审查 Agent PRD** |
| ④ | **修** JSON 信封未解包（新增 `doc_text_of()`） | 正文 `{"ok":true…}` → **干净文本**，§7.3 可读 |
| ⑤ | L1 落地 + 重分块 + L2 切分 | 3 个 clause 单元，§7.3 那一个 **7/7** |

### 关键 before / after

| | 修前 | 修后 |
|---|---|---|
| L1 正文 | 1,129 B（node-get JSON） | **11,750 B（干净文本）** |
| §7.3 | 不在 | **在，7 条红线逐字** |
| L1 产物段 | 1 段 `#正文`（非 anchor_spec 口径） | **3 段 `#l.1-245` / `#l.246-494` / `#l.495-773`** |
| L2 单元 | 0 | **3 个 clause 单元** |

---

## 三、顺带发现的两个**存量缺陷**（都不是本任务引入的）

### 缺陷 A：wiki 链接的正文一直是 API 元数据

`fetch()` 的 wiki 分支读 `data.node.obj_token`，实际返回 **`data.obj_token`**（无 `node` 包装）
⇒ `obj` 恒空 ⇒ 掉到最后一条 `return "wiki"`，**把 node-get 原始 JSON 当正文**，
而 `ok = 非空 ∧ 首 200 字无 error` 判**绿** —— **静默失败**。

实测存量：`kb/l1/sources` 1,275 份产物中 **281 份**正文是 node-get JSON。

### 缺陷 B：`docs +fetch` 的 JSON 信封**没有任何一层解包**

`docs +fetch` 返回 `{"data":{"document":{"content":"<h3>…</h3>…"}}}` —— 正文在 `content`（HTML）里。
在此之前信封被当正文一路写进 L1、落成产物、被 L2 切。

实测存量：`kb/l1/sources` 的 `L1-*` 产物 **312 / 481 份**正文以 `{` 开头；
`kb/l1/1_外部标准库/url__*.json` 亦然。

### 缺陷 C（顺带核到）：10 份 L1 产物是**飞书登录页 HTML**

`rechunk` 扫描命中 11 份「`#正文` 巨段」，其中 **9 份正文是 `<!doctype html>…`**
（`curl()` 兜底分支抓到的未登录页面，92,xxx 字 ×9）。
**⇒ 没有对它们重分块** —— 那会把 9 份垃圾摊成 **216 个垃圾单元**。
只对 PRD 做了手术式重分块（`kb/.work/rechunk_prd_only.py`，加资源过滤）。

**下游污染评估**：L2 `units.jsonl` 14,649 行中 **38 行**含元数据特征；
**L3 `scoped_clauses` / `rules.jsonl` / L5 `p0_patterns` 全为 0 行** ⇒ 垃圾**没变成规则或红线**。
⚠️ 281 份坏产物与 9 份登录页**未重跑**（重跑会重下钻全部来源），要单独开一次。

---

## 四、验证汇总（本会话实跑）

| 尺子 | 结果 |
|---|---|
| `ci/run_gates.py --only l0 l1 l2` | **3/3 PASS ｜ 红 0** |
| `kb/l8/workflow_smoke.py` | ✅ 契约齐 |
| `kb/l8/check_source_readonly.py` | ✅ 只读源没被写、规则在位 |
| L2 覆盖率 | 1313/1341 → **1314/1341** |
| `units.jsonl` | 14,649 → **14,652**（+3） |

---

## 五、改动清单

| 文件 | 改了什么 |
|---|---|
| `kb/l0/1_外部标准库/feishu_doc__PXfBdjTwFokEQixtmTscqm7knNh.json` | **新增**（L0 记录件） |
| `kb/l0/manifest.jsonl` | +1 行（8506 → 8507） |
| `kb/l0/registry/kb.json` | `rules` 加 R27（26 → 27） |
| `kb/l8/drill_links_2levels.py` | ① 加登记件种子 ② 修 wiki 解析 ③ 加 `doc_text_of()` 解包 ④ 边表 `from_kind` 如实区分 |
| `kb/l1/sources/20261013-prd-v2*` | **新增**（下钻产物） |
| `kb/l1/1_外部标准库/url__momcozy_in.feishu.cn_wiki_NB55….json` | **新增**（L1 产物，3 段） |
| `kb/l1/manifest_l1.jsonl` | +1 行 |
| `kb/l2/units.jsonl` / `index/l2.jsonl` / `manifest_l2.jsonl` | +3 / +3 / +1 行 |
| `kb/.work/drill_reg_only.py` / `rechunk_prd_only.py` | 手术式验证/落地副本（只跑 PRD 那一份） |

## 六、回滚

`kb/.work/revert-prd-s7.3-20261013/` 存有改动前的
`manifest.jsonl` / `registry/kb.json` / `l1__manifest_l1.jsonl` / `l2__*`。
L1/L2 的新增件按 `resource_id` 删除即可（台账是 append-only，删末行）。

## 七、剩余（未做）

1. **L3 蒸馏**：从 `bd4267ff5c050ca14e98` 这个单元蒸出四条画面红线规则候选。
2. **L4 发号**：拿 `article_no`（**写操作，要单独报批**）。
3. **P0 替换**：`p0_fastpath` ⑩d 写死 `len(_rows)==11`，四条进来后是 15 → 建议改按 `enabled` 计数。
4. **281 份坏产物 + 9 份登录页**是否重跑。
