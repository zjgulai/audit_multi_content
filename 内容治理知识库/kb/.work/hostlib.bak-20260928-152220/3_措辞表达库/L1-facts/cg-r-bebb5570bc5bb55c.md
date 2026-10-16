---
id: cg-r-bebb5570bc5bb55c
title: "[W-2.329] 措辞表达库：命中「孕期Hb＜110g/L即可诊断贫血」等 1 类表达"
collection: 3_措辞表达库
tier: L1-facts
topic: 未登记规则码
kind: judgment
summary: "[W-2.329] 判为「禁用/必须修改」（P1·unknown）：命中表达 1 条、证据单元 1 条；处理方式是「修订为：孕早期和孕晚期Hb＜110g/L可诊断贫血」。状态 provisional、verification 待验证。"
owner: 刘华丽
evidence_level: observation
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-09-23
valid_until: 2027-03-22
asks:
  - W-2.329 判什么、命中什么算违规
  - W-2.329 应该怎么改（合规替代写法）
  - W-2.329 的证据有几条、证据级是什么
  - W-2.329 是 P 几、风险等级是什么
  - 「孕期Hb＜110g/L即可诊断贫血」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「W-2.329」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
source:
  kind: derived
  ref: "kb/l3/candidates/rules.jsonl#r-bebb5570bc5bb55c"
  fingerprint: 66788814880c83a33906e9ef391600b4
  captured_at: 2026-09-23
rule_id: r-bebb5570bc5bb55c
article_no: W-2.329
rule_code: ""
p_level: P1
risk_level: unknown
rule_status: provisional
verification: 待验证
support_count: 1
form: revision_pair
kb_type: wording
derived_from: kb/l3/candidates/rules.jsonl
---

# [W-2.329] 措辞表达库：命中「孕期Hb＜110g/L即可诊断贫血」等 1 类表达

**条款号**：W-2.329　|　**规则码**：（未登记）　|　**rule_id**：`r-bebb5570bc5bb55c`　|　**判定**：P1 · unknown

## 规则原文（照抄新库，未改写）

原表述：孕期Hb＜110g/L即可诊断贫血；修订为：修订为：孕早期和孕晚期Hb＜110g/L可诊断贫血；孕中期由于血液稀释，诊断标准通常为Hb＜105g/L（参考WHO及ACOG标准）；修订原因：孕中期由于血液稀释达到高峰，诊断标准通常放宽至Hb＜105g/L，原文未区分孕期阶段

## 命中表达（1 条；来源：规则行 forbidden_expression 拆分）

- `孕期Hb＜110g/L即可诊断贫血`

## 判为违规的依据

孕中期由于血液稀释达到高峰，诊断标准通常放宽至Hb＜105g/L，原文未区分孕期阶段

## 处理方式 / 合规替代

修订为：孕早期和孕晚期Hb＜110g/L可诊断贫血；孕中期由于血液稀释，诊断标准通常为Hb＜105g/L（参考WHO及ACOG标准）

## 禁用表达汇总

孕期Hb＜110g/L即可诊断贫血

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：1（support_count 取新库值 1）
- 证据级（新库取值）：observation
- 验证状态（新库取值）：待验证 · 规则状态：provisional
- 形态：revision_pair　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `12323dd4cc73668a88a7`　#专家修订汇总表/recvoyJ6L9Co0v/修订位置（原文引用）　→ 【前】孕期Hb＜110g/L即可诊断贫血 【后】修订为：孕早期和孕晚期Hb＜110g/L可诊断贫血；孕中期由于血液稀释，诊断标准通常为Hb＜105g/L（参考WHO及ACOG标准） 【原因】孕中期由于血液稀释达到高峰，诊断标准通常放宽至Hb＜105g/L，原文未区分孕期阶段

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
