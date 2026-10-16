---
id: cg-r-a5ddf19a11fdb31e
title: "[W-2.282] 措辞表达库：命中「就医指征列表整体（7种危险信号）」等 1 类表达"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L1-facts
topic: 未登记规则码
kind: judgment
summary: "[W-2.282] 判为「禁用/必须修改」（P1·unknown）：命中表达 1 条、证据单元 1 条；处理方式是「参照审核已提供的修订版本，调整就医信号的整体表述格式，采用更严肃规范的语言，例如：出现以下7种情况，请及时寻求医疗帮助」。状态 provisional、verification 待验证。"
owner: 刘华丽
evidence_level: observation
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-09-23
valid_until: 2027-03-22
asks:
  - W-2.282 判什么、命中什么算违规
  - W-2.282 应该怎么改（合规替代写法）
  - W-2.282 的证据有几条、证据级是什么
  - W-2.282 是 P 几、风险等级是什么
  - 「就医指征列表整体（7种危险信号）」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「W-2.282」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
source:
  kind: derived
  ref: "kb/l3/candidates/rules.jsonl#r-a5ddf19a11fdb31e"
  fingerprint: 9c2b674dd9b08c2b8331c455705ae129
  captured_at: 2026-09-23
rule_id: r-a5ddf19a11fdb31e
article_no: W-2.282
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

# [W-2.282] 措辞表达库：命中「就医指征列表整体（7种危险信号）」等 1 类表达

**条款号**：W-2.282　|　**规则码**：（未登记）　|　**rule_id**：`r-a5ddf19a11fdb31e`　|　**判定**：P1 · unknown

## 规则原文（照抄新库，未改写）

原表述：就医指征列表整体（7种危险信号）；修订为：参照审核已提供的修订版本，调整就医信号的整体表述格式，采用更严肃规范的语言，例如：出现以下7种情况，请及时寻求医疗帮助；各条目保持简洁明确；修订原因：就医警示类内容的表述风格过于随意，此类严肃医疗信号应以更正式、清晰的格式呈现

## 命中表达（1 条；来源：规则行 forbidden_expression 拆分）

- `就医指征列表整体（7种危险信号）`

## 判为违规的依据

就医警示类内容的表述风格过于随意，此类严肃医疗信号应以更正式、清晰的格式呈现

## 处理方式 / 合规替代

参照审核已提供的修订版本，调整就医信号的整体表述格式，采用更严肃规范的语言，例如：出现以下7种情况，请及时寻求医疗帮助；各条目保持简洁明确

## 禁用表达汇总

就医指征列表整体（7种危险信号）

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：1（support_count 取新库值 1）
- 证据级（新库取值）：observation
- 验证状态（新库取值）：待验证 · 规则状态：provisional
- 形态：revision_pair　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `2e385dda6cdecc008239`　#专家修订汇总表/recvoyJ6L9SlN4/修订位置（原文引用）　→ 【前】就医指征列表整体（7种危险信号） 【后】参照审核已提供的修订版本，调整就医信号的整体表述格式，采用更严肃规范的语言，例如：出现以下7种情况，请及时寻求医疗帮助；各条目保持简洁明确 【原因】就医警示类内容的表述风格过于随意，此类严肃医疗信号应以更正式、清晰的格式呈现

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
