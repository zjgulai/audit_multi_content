# 待并入 `kb/l0/registry/kb.json::open_issues` 的条目（**改名补登记**）

- **生成时间**：2026-10-10（本轮只读核查后）
- **生成者**：DSH agent（会话内），**依据 Owner 指令「按推荐执行、不影响现有工作流」**
- **为什么落在这里而不直接改 `kb.json`**：
  1. `kb/l0/registry/kb.json` 是 **L0 权威登记表**，按库规「真写库要单独报批」；
  2. 库内既有惯例是**批次脚本改它**（`kb/.work/batch16/final.py`、`fix_f11_*.py`），
     人工/会话直改会绕过那个通道；
  3. 本轮 Owner 的约束是「**不影响现有工作流**」⇒ 落成**可审的补丁件**，
     由 `kb-repair` 或 Owner 一键并入，动作可回滚、可留痕。
- **并入方式（二选一，都不需要改代码）**：
  - 走修复入口：把本文件交给 **kb-repair**（它就是「按原因码修 + 修完重跑同一条闸门证明修好了」）；
  - 或人工：按下面的 YAML 逐条 append 进 `kb.json` 的 `open_issues` 数组（**追加，不覆盖**），
    并把 `open_issues_note` 补一句本次来源。

> **纪律（照抄库规）**：`open_issues` 是「**只登记**」的台账 —— 登记 ≠ 已修。
> 每条都必须带 `fix_by`（什么时候前必须处理）与 `status`，否则它下轮又会被重新发现一遍。

---

## 为什么会有这份补丁（三面复查的结论）

任务详情表 G6（10/12–10/16「文字链路首次跑通」行）报了 4 个缺口，
**三面复查（产物面 / 登记面 / 契约面）里，登记面全是空的** ——
也就是说：缺口**只活在 xlsx 的一段话里**，库自己不知道。

| 缺口 | 产物面 | 登记面（改前） | 契约面 |
|---|---|---|---|
| 基线表 | 🟡 三个数散落（无独立产物） | ❌ 无 | — |
| 9 场景覆盖表 | ❌ `find -iname "*场景*"` 为空 | ❌ 无 | `fixed_eval_set: missing` |
| 蒸馏工单 | ❌ 无 | ❌ 无 | — |
| W-4 编号规则 | ❌ 六段无 W-4 实体 | ❌ 无 | — |

**这就是「两周没动」的机制原因**：没有 `open_issues` 行 ⇒ 没有 `fix_by` ⇒ 没人认领 ⇒ 下轮从零重新发现。

---

## 补丁内容（YAML，逐条与现有 `open_issues` 同 schema）

```yaml
- id: OI-BL-001
  severity: medium
  title: 基线表三个数散落无独立产物；且历史值口径不可复现（健康分同日出现 76.7 与 79.3）
  evidence:
    product_face: "无独立基线表产物；数字只散在任务详情 xlsx G6 的文字里"
    reproduced_20261010: "健康分 79.3 / 规则孤岛率 0.9412 / 检索命中 433-557（77.7%）/ 评审单 562（source=review_machine）"
    unreproducible: "xlsx 里出现过的 112 / 472 / 183 / 155 四个值：按任何日期切法都不等于 112（≤10/1=45｜≤10/2=142｜10/3 起=205）"
    same_engine_two_scores: "同一台引擎（dsh-kb/lib/kb.js::check()）12:04 采样 76.7、12:15 采样 79.3 —— 两次都真，差在 kb/view 是持续重建的派生视图"
    artifact_now: "kb/l7/reports/baseline-20261010-121825.md / .json / .json.sha256（生成器 kb/l8/baseline_table.mjs，只读）"
  impact: >
    任何引用这个数的表、报告、周报都可能引到不可复现的值；
    「对不上账」会在下一个人那里重复发生一次。
  root_cause: >
    数字在生成时就没绑「采样时点 + 生成命令 + 指纹」；而 kb/view 是持续重建的派生视图
    ⇒ 同一台引擎在不同分钟给出不同分（76.7 / 79.3 都为真）。
  fix_by: "2026-10-17（下一轮周报前）"
  suggested_fix: >
    ① 数字引用改走 baseline 产物（连 baseline_id 一起引）；
    ② 裁「一单」判据（见 OI-BL-004）。产物已就位：kb/l8/baseline_table.mjs。
  status: open
  recorded_at: "20261010-1218"

- id: OI-COV-001
  severity: medium
  title: 9 场景覆盖表（PRD §7.2）三面皆空，两周未动
  evidence:
    product_face: "find . -iname '*场景*'（排除 _archive）零命中"
    registry_face: "本文件——kb/l0/registry/kb.json 的 open_issues 此前无此项"
    contract_face: "_meta/acceptance.yaml conditions.fixed_eval_set = missing；负面阻断码 DATASET_NOT_BUSINESS_AUTHORIZED"
    domains_defined_at: "kb/l7/registry/l7.json::vocabulary.prd_7_2_domains（九域齐全）"
    field_gap: "kb/l3/candidates/rules.jsonl 1018 行**没有**场景域字段（0 行含 prd_7_2/scenario/场景域）⇒ 覆盖表需要先补一次映射"
    why_blocked: "难看的真实结果（多数场景域大概率 0 条规则）；且要先定「一域算不算覆盖」的判据"
  impact: >
    「规则体系覆盖 9 大场景域」这条 PRD 承诺**没有可核对的产物**；
    对外说「已覆盖」时拿不出表。
  root_cause: >
    PRD §7.2 的九域只在 l7.json 的词表里，L3 规则行**没有**场景域字段
    ⇒ 「覆盖表」需要先补一次映射，且结果大概率难看（多数域 0 条）⇒ 没人愿意第一个交。
  fix_by: "2026-10-23"
  suggested_fix: >
    按 PRD §7.2 九域逐域统计证据单元数（0 条就写 0），落 kb/l7/reports/ 并回填本 open_issues；
    不许为了消灭 ❌ 而凑数。
  status: open
  recorded_at: "20261010-1218"

- id: OI-DIST-001
  severity: low
  title: 蒸馏工单无产物；上游处于 🟡（语料/裁决未齐），本条更可能是「阻塞」而非「欠做」
  evidence:
    product_face: "无工单产物"
    upstream_state: "任务详情表同期多条为 🟡：S-1 316 条已发号 / 视频字幕与旁白抽取仍未落 / canonical 定稿 1480 条"
    dependency: "蒸馏吃「已裁决素材」；未裁决素材进 L3 = 把噪声固化成条款（库内已有先例与警告）"
  impact: >
    🟡 挂在交付物里既不推进也不关闭，占用「完成度」的注意力。
  root_cause: >
    上游没货：蒸馏吃「已裁决素材」，而同期多条素材仍停在 🟡（未裁决 / 未抽全）。
    在没货时补工单 = 凑数，反而会把「噪声固化成条款」的风险引进来。
  fix_by: "2026-10-23"
  suggested_fix: >
    二选一并写进表：① 改记「**阻塞**」＋写明阻塞条件（等哪批素材裁决完成）；
    ② 承认它不属本期交付物、从 D 列移出。**不建议现在凑一份工单。**
  status: open
  recorded_at: "20261010-1218"

- id: OI-L4-004
  severity: medium
  title: W-4 段位已声明但零实体（错在「账」不在「规则」）；且 reserved_unused_segments 列出已用段
  evidence:
    w4_registered: "kb/l4/registry/l4.json 两处写着 \"W-4\": {block:4, form:wording_boundary, label:'boundary（边界内容型）', state:'reserved_unused'}"
    w4_has_no_rule: "kb/l4/canonical/*.jsonl 五个形态文件共 1480 行，段位只有 E-1/E-2/S-1/W-1/W-2/W-3 六段，**无 W-4 实体规则**"
    ledger_self_contradiction: "同一份 l4.json 的 reserved_unused_segments = [W-4, W-5, W-6, S-2, E-2, P-1]，但 **E-2 已在用**（clause.jsonl 123 条），且 segments_used 里也列了 E-2 —— 同一份注册表自相矛盾"
    deliverable_wording: "任务详情 D6 写「W-4 编号规则 ≥1 条」，xlsx G6 写「❌ L4 发号台账仍只有六段」—— 两者说的不是同一件事"
  impact: >
    「W-4 编号规则 ❌」会被读成「编号规则没建」，
    实际是「段位规则已建、没有内容进来」⇒ 派活方向会错（去写规则 vs 去等内容）。
  root_cause: >
    台账把「段位已声明」与「已有实体规则」混成了一件事；且 reserved_unused_segments 没随 E-2 发号同步维护。
  fix_by: "2026-10-17"
  suggested_fix: >
    ① 修 l4.json：把 E-2 从 reserved_unused_segments 移除（纯记账修正，不改发号）；
    ② 表里改写为「W-4 段位规则已在 l4.json；**尚无 ≥1 条实体规则入段**」；
    ③ 若确需实体规则，先产出边界型内容再发号 —— 不许为凑数硬造。
  status: open
  recorded_at: "20261010-1218"
```

---

## 两条**不属于** open_issues、但仍需 Owner 一句话的（口径裁决，不是缺陷）

1. **「一单」判据** —— 建议定为「一次评审运行」（现基线读数 562）。另两个可选口径：一素材 = 一单 / 飞书登记表一行 = 一单。
2. **两个健康分口径进表时分开写** —— 口径 A（视图内容质量，79.3「不通过」）与口径 C（流水线，GREEN 红 0）。
   建议**分开写、不合并**；合并 = 用好看的那个盖住难看的那个。

（这两条已同时登记在 `kb/l7/registry/report-output-contract.yaml::decision_20261010_baseline_table.pending_owner`。）

---

*本文件是**补丁件**，不是台账本体。合并之前 `open_issues` 里仍然没有这几条 —— 别把它当已登记。*
