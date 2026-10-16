---
id: cg-r-335f00d14cefe7f9
title: "[U02] 措辞表达库：命中「insurance eligible」等 6 类表达"
collection: 3_措辞表达库
tier: L2-concepts
topic: U02
kind: fact
summary: "[U02] 判为「禁用/必须修改」（P1·待复核）：命中表达 6 条、证据单元 2 条。状态 provisional、verification 已归纳。"
owner: 刘华丽
evidence_level: synthesis
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-09-23
valid_until: 2027-03-22
asks:
  - U02 判什么、命中什么算违规
  - U02 应该怎么改（合规替代写法）
  - U02 的证据有几条、证据级是什么
  - U02 是 P 几、风险等级是什么
  - 「insurance eligible；HSA；FSA」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「U02」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
source:
  kind: derived
  ref: "kb/l3/candidates/rules.jsonl#r-335f00d14cefe7f9"
  fingerprint: aa379cbecb967d7d6724ae4ef8655aac
  captured_at: 2026-09-23
rule_id: r-335f00d14cefe7f9
article_no: W-1.15
rule_code: U02
p_level: P1
risk_level: 待复核
rule_status: provisional
verification: 已归纳
support_count: 2
form: entry
kb_type: wording
derived_from: kb/l3/candidates/rules.jsonl
---

# [U02] 措辞表达库：命中「insurance eligible」等 6 类表达

**条款号**：W-1.15　|　**规则码**：U02　|　**rule_id**：`r-335f00d14cefe7f9`　|　**判定**：P1 · 待复核

## 规则原文（照抄新库，未改写）

边界：保险/HSA/FSA报销声明：站点报销资质已具备（2026-09-09用户确认），规则停用、不再判险；触发词：insurance eligible, HSA, FSA, insurance covered, 保险, 医保

## 命中表达（6 条；来源：规则行 forbidden_expression 拆分）

- `insurance eligible`
- `HSA`
- `FSA`
- `insurance covered`
- `保险`
- `医保`

## 判为违规的依据

（新库该行为空）

## 处理方式 / 合规替代

（新库该行为空）

## 禁用表达汇总

insurance eligible, HSA, FSA, insurance covered, 保险, 医保

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：2（support_count 取新库值 2）
- 证据级（新库取值）：synthesis
- 验证状态（新库取值）：已归纳 · 规则状态：provisional
- 形态：entry　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `c93f27800398ac4b52da`　#品线内容边界规则库/recvuJP2Ot3owA/边界内容　→ 保险/HSA/FSA报销声明：站点报销资质已具备（2026-09-09用户确认），规则停用、不再判险
- `85c8f7b284302f5f4395`　#品线内容边界规则库/recvuJP2Ot3owA/检测关键词　→ insurance eligible, HSA, FSA, insurance covered, 保险, 医保

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
