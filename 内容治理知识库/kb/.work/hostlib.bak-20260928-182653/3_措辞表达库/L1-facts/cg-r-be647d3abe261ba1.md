---
id: cg-r-be647d3abe261ba1
title: "[W-2.327] 措辞表达库：命中「此外，医生还会全面评估你目前正在服用的处方药、非处方药及日常保健品，以及时停用或替换可能对胎儿有潜在风险的药物」等 1 类表达"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L1
topic: 未登记规则码
kind: fact
summary: "[W-2.327] 判为「禁用/必须修改」（P1·未定级）：命中表达 1 条、证据单元 1 条；处理方式是「修订为：以及时停用或替换可能对妊娠和宝宝发育有潜在风险的药物」。状态 provisional、verification 待验证。"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-09-28
valid_until: 2027-03-27
asks:
  - W-2.327 判什么、命中什么算违规
  - W-2.327 应该怎么改（合规替代写法）
  - W-2.327 的证据有几条、证据级是什么
  - W-2.327 是 P 几、风险等级是什么
  - 「此外，医生还会全面评估你目前正在服用的处方药、非处方药及日常保健品，以及时停用或替换可能对胎儿有潜在风险的药物」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「W-2.327」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
  - cg-r-0f90d588747190c8
  - cg-r-bebb5570bc5bb55c
  - cg-r-bf6ab0d4d6e610dc
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/SKkkbdZi9aRuMzs7ob0cpSYHnQg?table=tbl8AI00JZO1iZtp"
  fingerprint: SKkkbdZi9aRuMzs7ob0cpSYHnQg/tbl8AI00JZO1iZtp
  captured_at: 2026-09-28
provenance:
  anchor: "kb/l3/candidates/rules.jsonl#r-be647d3abe261ba1"
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为广告文案/规则表述与专家修订记录，不含姓名、联系方式等个人数据；如后续来源变化需重新判定
rule_id: r-be647d3abe261ba1
article_no: W-2.327
rule_code: ""
p_level: P1
risk_level: 未定级
risk_level_raw: unknown
risk_level_note: 源库 kb/l3 的 risk_level 为 unknown/空 —— 未做人工定级；本视图不据 P 级反推，故标未定级
evidence_level_note: 源库证据级 observation（单条修订对、单一来源）→ L1
rule_status: provisional
rule_verification: 待验证
support_count: 1
form: revision_pair
kb_type: wording
---

# [W-2.327] 措辞表达库：命中「此外，医生还会全面评估你目前正在服用的处方药、非处方药及日常保健品，以及时停用或替换可能对胎儿有潜在风险的药物」等 1 类表达

**条款号**：W-2.327　|　**规则码**：（未登记）　|　**rule_id**：`r-be647d3abe261ba1`　|　**判定**：P1 · 未定级

## 规则原文（照抄新库，未改写）

原表述：此外，医生还会全面评估你目前正在服用的处方药、非处方药及日常保健品，以及时停用或替换可能对胎儿有潜在风险的药物；修订为：修订为：以及时停用或替换可能对妊娠和宝宝发育有潜在风险的药物；修订原因：孕前检查不涉及胎儿，此处表述有误

## 命中表达（1 条；来源：规则行 forbidden_expression 拆分）

- `此外，医生还会全面评估你目前正在服用的处方药、非处方药及日常保健品，以及时停用或替换可能对胎儿有潜在风险的药物`

## 判为违规的依据

孕前检查不涉及胎儿，此处表述有误

## 处理方式 / 合规替代

修订为：以及时停用或替换可能对妊娠和宝宝发育有潜在风险的药物

## 禁用表达汇总

此外，医生还会全面评估你目前正在服用的处方药、非处方药及日常保健品，以及时停用或替换可能对胎儿有潜在风险的药物

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：1（support_count 取新库值 1）
- 证据级（新库取值）：L1
- 验证状态（新库取值）：待验证 · 规则状态：provisional
- 形态：revision_pair　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `3c04546af4d0796a5e66`　#专家修订汇总表/recvoyJ6L9nqV8/修订位置（原文引用）　→ 【前】此外，医生还会全面评估你目前正在服用的处方药、非处方药及日常保健品，以及时停用或替换可能对胎儿有潜在风险的药物 【后】修订为：以及时停用或替换可能对妊娠和宝宝发育有潜在风险的药物 【原因】孕前检查不涉及胎儿，此处表述有误

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
