---
id: cg-r-aee62d35ef8916a8
title: "[W-2.297] 措辞表达库：命中「铁剂补充描述：需要通过血液检查确认存在缺铁后，在医生指导下使用」等 1 类表达"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L1-facts
topic: 未登记规则码
kind: judgment
summary: "[W-2.297] 判为「禁用/必须修改」（P1·unknown）：命中表达 1 条、证据单元 1 条；处理方式是「改为：常规产前复合维生素中含有的低剂量铁，通常可作为孕期常规补充的一部分」。状态 provisional、verification 待验证。"
owner: 刘华丽
evidence_level: observation
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-09-23
valid_until: 2027-03-22
asks:
  - W-2.297 判什么、命中什么算违规
  - W-2.297 应该怎么改（合规替代写法）
  - W-2.297 的证据有几条、证据级是什么
  - W-2.297 是 P 几、风险等级是什么
  - 「铁剂补充描述：需要通过血液检查确认存在缺铁后，在医生指导下使用」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「W-2.297」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
source:
  kind: derived
  ref: "kb/l3/candidates/rules.jsonl#r-aee62d35ef8916a8"
  fingerprint: 47d0b50e064e8da66d9759d9e5da8a44
  captured_at: 2026-09-23
rule_id: r-aee62d35ef8916a8
article_no: W-2.297
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

# [W-2.297] 措辞表达库：命中「铁剂补充描述：需要通过血液检查确认存在缺铁后，在医生指导下使用」等 1 类表达

**条款号**：W-2.297　|　**规则码**：（未登记）　|　**rule_id**：`r-aee62d35ef8916a8`　|　**判定**：P1 · unknown

## 规则原文（照抄新库，未改写）

原表述：铁剂补充描述：需要通过血液检查确认存在缺铁后，在医生指导下使用；修订为：改为：常规产前复合维生素中含有的低剂量铁，通常可作为孕期常规补充的一部分；而额外的治疗性补铁，则建议在血液检查确认缺铁或贫血后，在医生指导下使用，两者不应混淆。；修订原因：表述会让读者理解成所有孕妇都必须先证实缺铁才能补铁，与WHO/ACOG口径不符。WHO明确把每日铁+叶酸补充作为孕期产前保健的一部分；CDC和ACOG均有孕期低剂量常规补铁的口径。正确区分应为：常规产前复合维生素中的低剂量铁可常规使用；额外治疗性补铁才需依据贫血/缺铁评估来决定

## 命中表达（1 条；来源：规则行 forbidden_expression 拆分）

- `铁剂补充描述：需要通过血液检查确认存在缺铁后，在医生指导下使用`

## 判为违规的依据

表述会让读者理解成所有孕妇都必须先证实缺铁才能补铁，与WHO/ACOG口径不符。WHO明确把每日铁+叶酸补充作为孕期产前保健的一部分；CDC和ACOG均有孕期低剂量常规补铁的口径。正确区分应为：常规产前复合维生素中的低剂量铁可常规使用；额外治疗性补铁才需依据贫血/缺铁评估来决定

## 处理方式 / 合规替代

改为：常规产前复合维生素中含有的低剂量铁，通常可作为孕期常规补充的一部分；而额外的治疗性补铁，则建议在血液检查确认缺铁或贫血后，在医生指导下使用，两者不应混淆。

## 禁用表达汇总

铁剂补充描述：需要通过血液检查确认存在缺铁后，在医生指导下使用

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：1（support_count 取新库值 1）
- 证据级（新库取值）：observation
- 验证状态（新库取值）：待验证 · 规则状态：provisional
- 形态：revision_pair　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `a8a86f4079f94c3c6b08`　#专家修订汇总表/recvoyJ6L9taVz/修订位置（原文引用）　→ 【前】铁剂补充描述：需要通过血液检查确认存在缺铁后，在医生指导下使用 【后】改为：常规产前复合维生素中含有的低剂量铁，通常可作为孕期常规补充的一部分；而额外的治疗性补铁，则建议在血液检查确认缺铁或贫血后，在医生指导下使用，两者不应混淆。 【原因】表述会让读者理解成所有孕妇都必须先证实缺铁才能补铁，与WHO/ACO…

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
