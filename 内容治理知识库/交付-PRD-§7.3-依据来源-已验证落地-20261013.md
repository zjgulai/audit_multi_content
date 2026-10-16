# 交付：PRD §7.3 作为依据来源 —— **已验证并落地**（三处改动）

日期 2026-10-13 ｜ 依据 Owner 2026-10-13「同意你的推荐，把 PRD §7.3 作为依据来源入库」
状态：**① ② 已落地并验证；③ 是顺带修掉的存量缺陷**。剩余 L2→L3→L4 发号未做。

---

## 一、结论：方案不是「开新投影轴」，是**给已验证过的下钻通道加一类种子**

PRD 今天在链里**只有一个身份：减法**（§2.2 非目标 → `rule_eligible=false`）。
**§7.3 一票否决项 —— 真正的红线清单 —— 原先零表示**：L0 无记录、L1 无正文、L3 无规则、无条款号。
现已打通到 **L1 正文**，§7.3 逐字原文在库内可锚定。

---

## 二、三处改动（每处都有 before/after 实测）

### ① L0 加登记件投影 —— `kb.json` R27 + 记录件 + 台账行

| 项 | 内容 |
|---|---|
| 记录件 | `kb/l0/1_外部标准库/feishu_doc__PXfBdjTwFokEQixtmTscqm7knNh.json`（由 `feishu_doc` 模板 `update()` 派生 ⇒ 键集/类型必然一致） |
| 台账行 | `kb/l0/manifest.jsonl` +1 行（8506 → 8507），键集严格按 manifest 的 24 键 |
| 规则 | `kb/l0/registry/kb.json` → `rules` 加 **R27**（`match_type=registered_source`），26 → 27 条 |

**关键验证（控制实验）**：加之前 / 之后，L0 闸门

| 指标 | 加之前 | 加之后 |
|---|---|---|
| L0多 | 0 | **0** |
| manifest 未登记 | 0 | **0**（根本没出现） |
| 真差异 | 0 | **0** |
| `ci/run_gates.py --only l0` | PASS | **PASS / 红 0** |

**为什么为零**（读码确证，不是运气）：
`l0_gate.py:153` 的差异循环只遍历**对账器返回的飞书受控表**；
`align_l0_feishu.py:245-252` 的「manifest 未登记」只遍历 **`l0_by_table`**，
而 `l0_by_table` 只 walk **`kb/l0/records`**（:99-113）。
登记件不在受控表里、也不在 `records/` 下 ⇒ **两条检查都不覆盖它**。
⇒ **不需要改闸门、不需要 `l0-expected-diffs` 声明。**

⚠️ **一处自我更正**：`sha256_input` 我原先写 `docx_content_utf8`，
`layers.yaml` 的 L0 notes 明写枚举为 `{doc_text, record_files, record_fields, file_bytes, url_text, structure}`
⇒ 已改成 **`doc_text`**（记录件与台账行同步改）。

**落地的安全性**：`kb/l8/reconcile_l0_feishu.py:411-425` 是 read-modify-write
（`json.load` → 只追加 `l0_feishu_reconcile` → 整体回写）⇒ 手加的 R27 **不会被日更冲掉**。

### ② 下钻通道加「登记件」种子 —— `kb/l8/drill_links_2levels.py`

原种子的形状是 `(L0 记录目录名, [字段名])`，读 `kb/l0/records/<目录>/*.json` 的 `fields` blob。
登记件**不在任何受控表里、没有 `fields`** ⇒ 这个形状**盖不到它**。
新增一类种子：读 `kb/l0/manifest.jsonl` 里 `rule_eligible_source == "registered_source"` 的行。
**精确自限** —— 既有 10 条 `feishu_doc` 是 `material_collection_child_inherited`，**一条都没碰**。

实测：`[下钻] 待处理记录 1 条｜按源：{('已登记来源','feishu_wiki_docx'): 1}` ✅

### ③ ★ 顺带修掉一个**存量缺陷**：wiki 链接的正文一直是 API 元数据

`fetch()` 的 wiki 分支读 `data.node.obj_token`，而 `lark-cli wiki +node-get` 实际返回
**`data.obj_token`（无 `node` 包装）** ⇒ `obj` 恒为空 ⇒ 掉到最后一个分支，
**把 node-get 的原始 JSON 当正文写进产物**，而 `ok = 非空 ∧ 首 200 字无 error` 判**绿**。

| | 修前 | 修后 |
|---|---|---|
| `kind` | `wiki` | **`wiki→docx`** |
| `title` | 空 | **内容审查 Agent PRD** |
| 产物字节 | 1,129（JSON） | **33,926**（正文） |
| §7.3 | 不在 | **在**（逐字原文） |
| 产物文件名 | `L1-docx:PXfBdjTwFokEQixtmTscqm7knNh.md` | `L1-prd-content-review-agent.md` |

**存量影响（实测）**：`kb/l1/sources` 共 1,275 份产物，其中
**281 份 `kind: wiki` 的正文是 node-get 原始 JSON**（只有我刚落的 1 份是 `wiki→*`）。
**下游污染评估**：L2 `units.jsonl` 14,649 行中 **38 行**含元数据特征；
**L3 `scoped_clauses` / `rules.jsonl` / L5 `p0_patterns` 全为 0 行** ⇒ 垃圾**没有变成规则或红线**。
⚠️ 这 281 份**未重跑**（重跑会重下钻全部来源）—— 需要的话单独开一次。

---

## 三、验证汇总（本会话实跑）

| 尺子 | 结果 |
|---|---|
| `ci/run_gates.py --only l0` | PASS ｜ 红 0 |
| `ci/run_gates.py --only l1` | PASS ｜ 红 0 |
| `kb/l8/workflow_smoke.py` | ✅ 契约齐（链上约定没被改坏） |
| `kb/l8/check_source_readonly.py` | ✅ 只读源没被写、规则在位 |
| `extract_l1_new_resources.py`（预演） | `L0 活跃 ⊖ L1 = 1 {'feishu_doc': 1}` ⇒ PRD 已被识别 |

---

## 四、剩余（未做）

1. **L1 → L2**：把 `kb/l1/sources/20261013-prd-reg__L1-prd-content-review-agent.md` 按条款切单元。
   ⚠️ 已知断点：`extract_l1_new_resources.py` 的 dispatch 只处理
   `feishu_bitable_record` / `feishu_attachment`，**其余 `[跳过]`** ⇒
   `source_kind=feishu_doc` 目前在 L1 台账那一步会被跳过（下钻那条路已通，但**L1 台账行**未生成）。
2. **L3 → L4 发号**：四条画面红线成规则候选 + 拿 `article_no`（**写操作，要单独报批**）。
3. **⑤ P0 替换**：`p0_fastpath` ⑩d 写死 `len(_rows)==11`，四条进来后是 15 —— 须同步改。

## 五、回滚

`kb/.work/revert-prd-s7.3-20261013/` 存有改动前的
`manifest.jsonl` 与 `registry/kb.json` 原件；记录件删除即可。
（L1 下钻产物是新增文件，不影响既有行。）
