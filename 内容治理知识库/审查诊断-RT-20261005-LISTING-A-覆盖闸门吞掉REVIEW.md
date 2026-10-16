# 审查诊断：覆盖信号把已定稿的 REVIEW 覆盖成 NEEDS_INPUT

> **本件不是三态结论**，是**诊断记录**。三态结论只能由评审链引擎产出；
> 本单引擎产出的是 `NEEDS_INPUT`（拒答），`report_path = null`，**未发布飞书**。
> 本件的目的：把「引擎为什么拒答」和「被吞掉的那条命中」留成可核对的证据，并交 `kb-repair`。

| 项 | 值 |
|---|---|
| RUN (BASE) | `RT-20261005-LISTING-A`（L4/L5/L6/L7 各一 RUN） |
| 待审素材 | `吸奶器静音设计，夜里不吵醒宝宝，续航 8 小时`（listing · 美国 · 吸奶器） |
| content_version (sha256) | `3478e21e8c949f71b661b97b7772bcf35eb5a142d632b2e9ea85ceb2be5045ac` |
| content_id | `AUTO-3478e21e8c94` |
| review_id | `rv-20261005-091200`（第 1 跑）/ `rv-20261005-091330`（留证跑） |
| 引擎退出码 | **3**（NEEDS_INPUT / fail-closed） |
| 判定主体 | `文案合规审查`（已用 skill 工具加载并 `--loaded-skill` 申报） |
| 层前置 | `mode=enforced` / `ok=true` / `red_total=0`（四层审计全绿，L4/L5/L6 各带 1 黄 E5 预演） |
| 飞书发布 | **未发**（`publish.reason=no_conclusion`） |

---

## 一、引擎给的结论（唯一有权产出的那一份）

**`NEEDS_INPUT`（拒答）**，`exit=3`，`fails_closed=true`，
`refusal.detail = 依据侧拒答（fail-closed）`。
→ 回答「能不能发」：**本次没有任何一方给出放行依据** —— 既不是 PASS，也不是 REVIEW/BLOCK。

## 二、拒答的真实原因（引擎自己没说的那一半）

用引擎自带的受支持开关 `--findings-out` 取到依据侧原始载荷（**未直调 `review.py`**）：

```
payload.state                  = "REVIEW"          ← 依据侧本来给出的是 REVIEW
payload.findings               = 1 条              ← 且已通过逐字回验
payload.unmet_citation         = 0 条              ← 命中没有被「回验失败」丢掉
payload.trace.coverage.covered = False             ← 唯一原因
payload.trace.units.bm25_max   = 18.3058           （门限 8.0，已过）
payload.trace.coverage.rule_cited_unit_hits = []   ← 无「既被规则引用、又 ≥ 16.0」的单元
payload.trace.coverage.coverage_bm25_min    = 16.0
payload.rendered = 【审查结论：REVIEW】共发现 1 处需人工确认。
```

即：**依据侧已定稿为 REVIEW（1 处，逐字回源成立），
被 `with_kb_evidence.py` 的覆盖短路改写成 NEEDS_INPUT。**

短路点（`kb/l7/review-engine/core/with_kb_evidence.py:239-243`）：

```python
_ev_cov  = ((ev.get("trace") or {}).get("coverage") or {})
_refused = (_ev_state in {"NEEDS_INPUT", "拒答", "REFUSED"}
            or ev.get("refusal") is not None
            or _ev_cov.get("covered") is False)      # ← 本条在「看 findings」之前就短路
if _refused:
    return { ... "issue_count": 0, "risk_items": [],
             "refusal": ev.get("refusal") or {"detail": "依据侧拒答（fail-closed）"} ... }
```

三条越界事实：

1. **超出声明语义**。覆盖信号在 registry 里的声明是**服务于 PASS 判定**：
   `registry.gate.coverage_reasoning`＝「**PASS 必须建立在「知识库认识这个主题」之上**」；
   `review.py:721-728` 也只在 **`else`（findings 为空）分支**用它：
   `state = "PASS" if covered else "拒答"`。引擎把它提成了**无条件短路**。
2. **拒答分支把 findings 写死为 0**（`"findings": 0`、`"issue_count": 0`）⇒
   **真实命中在用户可见层整个消失**，`refusal.detail` 还是**默认文案**，
   看不出真因是「覆盖率不足」。
3. **真实风险进不了下游**：`NEEDS_INPUT` 按设计**不发布飞书** ⇒
   该命中的风险项**在「内容处理问题描述」表里没有任何落点**。

**影响面（推断，未实测，须标清）**：该短路在检查 `findings` 之前，
故 `covered=False` 时**连 BLOCK 也会被改写成 NEEDS_INPUT** —— 这是**代码路径推断**。
对照实测（本次跑的探针，`--no-publish-to-feishu`）：
`"这款吸奶器帮助催奶增产，无痛设计"` → `state=BLOCK`、3 条 findings、
`rule_cited_unit_hits` 非空（coverage 达标）→ **正常返回 BLOCK**。
⇒ 闸门**不是普遍失效**，只在覆盖信号缺失时咬人。**未构造出「P0 命中且 covered=False」的活样本**。

## 三、被吞掉的那条命中（四段溯源齐备）

| 段 | 值 |
|---|---|
| ④ 条款号（L4） | **W-1.54** ｜ rule_id `r-ddf0f8360c7b53a7` ｜ rule_code **M01** ｜ p_level **P1** ｜ library 措辞表达库 |
| ③ 规则与命中片段（L3） | 逐字命中「**静音**」；判定类别 `平台与促销 / 静音绝对化表述`；severity **REVIEW** ｜ confidence 中 |
| ② 单元与锚点（L2/L1） | anchor `#品线内容边界规则库/recvuJP1LV2uxa/边界内容` ｜ source_sha256 `1bf6ceb91a0d404e52dadd28aa2aa63585b57e03f3ac51a55f58635772e903d2` ｜ L6 单元 `6820619bf4bc83a64fff`（检测关键词）/ `e433b2b5d1233d2798be`（豁免词） |
| ① 逐字原文（L0） | 记录 `kb/l0/records/广告文案风控库__品线内容边界规则库/recvuJP1LV2uxa.json`（source_table `品线内容边界规则库`），字段「边界内容」＝**`静音程度夸大（建议改为 low noise / quiet mode）`** |

同记录的另两个字段（同为 L0 逐字值）：

- 「检测关键词」＝ `silent, whisper quiet, zero noise, noiseless, 几乎静音, 完全静音, 零噪音, 静音`
- 「豁免词」＝ `low noise, quiet mode, low-decibel, silent mode, 静音模式`

⇒ 待审句的「**静音设计**」落在**检测关键词**里；**豁免词只有「静音模式」，不含裸用「静音」**。

**sha 措辞**：上列 `source_sha256` 是**与 L0 记录值比对一致**，**不是「重算通过」**
（L0 的 sha 输入是 `record_fields` blob，本地 L0 件不含该 blob，重算在本地结构上不可能）。

## 四、本次四层只读档的其余读数（供交叉核对）

- **L5 P0：0 命中**（`matcher.py --selftest` 通过 → 排除「匹配器坏了」；对照串可命中 → 真阴性）。
  生效 P0 模式 **7 条**（6 条过阈值 + `H06` 走白名单），**无一条覆盖「静音/睡眠/续航」**。
  ⚠️ `H02`/`H07` 的 `suggested_replacement` 里逐字写着「静音表述改客观参数(as low as 48 dB)，
  避免 whisper/silent/ultra-quiet 绝对化」—— **该治理口径躺在自由文本字段里，不在任何参与匹配的字段中**，
  故 matcher 结构上永远不会因「静音」命中。**0 命中 ≠ 合规**。
- **L4 关联条款**（`kb-canonical-lookup` 只读档命中）：`W-1.5`（M01 判违规）、`W-2.165`（静音形容词→按型号实测分贝）、
  `W-2.177`（"静音绝对化 + night feeds"→给实测区间、承认非绝对静音）、`W-2.312`、
  `W-2.138`（续航→`240 minutes of battery`）、`W-2.107`（→`6 sessions per charge`）、
  `E-2.28`（FTC：客观宣称须有实证）。
  ⇒ **续航的口径是「给实测分钟/次数」，不是「8 小时」**；「不吵醒宝宝」在 L4 **逐字 0 条**。
- **L4 结构缺陷（既有）**：`source_sha256` 在 `wording_entry` **0/56**、`wording_revision_pair` **0/453**、
  `clause` **0/123** 整列为空；`clause` 连 `anchor` 也 **0/123** ⇒ **四段溯源在这三个形态上取不全**。
- **L6 召回**：四组查询（静音/睡眠/续航/绝对化）均 `--mode bm25_only`、exit 0；
  唯一直接管「静音」的一对单元只排到 rank 9/10；**续航/电池、"不吵醒宝宝"召回为空**（如实报"没有候选"）。
- **L7**：`l7_gate.py` C1–C4 全过 / 红 0；六要素可物化 1365/1365＝100.0%；E-2 段覆盖无缺号。
- **落章与审计**：四层 RUN 记账 `skill_evidence=agent_reported`；
  `skill_invocation_audit` 四道**红 0**（L4/L5/L6 各 1 黄 **E5＝预演台账**，L7 豁免）
  ⇒ **本单是「机制证据」，不是「这些层真落盘过」**。全程**未加 `--apply`**，未改任何库数据。

## 五、交 `kb-repair` 的三条（本件不修，只报）

1. **覆盖短路越界（本次主缺陷）**：`with_kb_evidence.py:239-243` 的
   `or _ev_cov.get("covered") is False` 应**只在 findings 为空时生效**（对齐 `review.py:721-728` 与
   registry `coverage_reasoning` 的声明）；并让拒答分支**透出真因**（覆盖不足）
   与 `unmet_citation` / `trace.coverage`，不要 `findings: 0` 一刀切。
   **代码注释引用的 `PMO/守衡-全链验收与两处缺陷-20261005.md` 在本工作区不存在（引用悬空）。**
2. **`freshness.py` 不是只读**（既有）：它经 `daily_health.py:649-651` → `run_record.py:145-147`
   写 `kb/l7/runs/<id>.json` 并 append `index.jsonl`，且 `commands` 字段硬编码为
   `kb/kbpy l7/scripts/kb_pipeline.py --check`（**台账记录与实际命令不符**）。
   本次 ①/②c 各跑一次 ⇒ 该副作用由**机制**造成，非写库动作。
3. **L4 三形态 `source_sha256` 整列为空**（既有）⇒ 引用契约第四段在这三个形态上无法物化；
   而 `l7_gate.py` C3 仍报「六要素齐备 1365/1365＝100%」，**判据与实际不符**，需一并复核。

## 六、本件的边界

- **不是三态结论**，也不得当作放行/拦截依据；放行依据只能来自评审链引擎且为 PASS/REVIEW/BLOCK。
- **渠道未指定**（未传 `--channel`）⇒ 渠道特有条款未叠加；目标渠道确认后应重跑。
- **素材为中文**；若实际投放为美区英文（`silent design` / `won't wake your baby` / `8-hour battery`），
  须按英文口径重跑，并另过 `美国本地化审查`。
- L4 落章自报 `verdict=FAIL`、L5 `frozen_layers`/`l3_append_only` 红、L6 `vector_traceability` 红，
  **均为已登记的既有状态**（同日同类历史 run 读数相同），非本次造成，本次未修。
