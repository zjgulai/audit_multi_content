---
id: cg-r-3b8c946efdf083b5
title: "[W-2.95] 措辞表达库：命中「血压监测就医指征列表（孕晚期）」等 1 类表达"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L1
topic: 未登记规则码
kind: fact
summary: "[W-2.95] 判为「禁用/必须修改」（P1·未定级）：命中表达 1 条、证据单元 1 条；处理方式是「补充就医紧急信号：除血压异常相关症状外，如出现阴道流血/流水、持续剧烈腹痛、呼吸困难、胸痛，或胎动明显减少、改变甚至消失，也应尽快联系医生或立即就医。（参考：C」。状态 provisional、verification 待验证。"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-09-23
valid_until: 2027-03-22
asks:
  - W-2.95 判什么、命中什么算违规
  - W-2.95 应该怎么改（合规替代写法）
  - W-2.95 的证据有几条、证据级是什么
  - W-2.95 是 P 几、风险等级是什么
  - 「血压监测就医指征列表（孕晚期）」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「W-2.95」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
  - cg-r-3b9212dc4072b59b
  - cg-r-3bbba4daed7cba38
  - cg-r-3c36e7a8e76a2206
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/SKkkbdZi9aRuMzs7ob0cpSYHnQg?table=tbl8AI00JZO1iZtp"
  fingerprint: SKkkbdZi9aRuMzs7ob0cpSYHnQg/tbl8AI00JZO1iZtp
  captured_at: 2026-09-23
provenance:
  anchor: "kb/l3/candidates/rules.jsonl#r-3b8c946efdf083b5"
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为广告文案/规则表述与专家修订记录，不含姓名、联系方式等个人数据；如后续来源变化需重新判定
rule_id: r-3b8c946efdf083b5
article_no: W-2.95
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

# [W-2.95] 措辞表达库：命中「血压监测就医指征列表（孕晚期）」等 1 类表达

**条款号**：W-2.95　|　**规则码**：（未登记）　|　**rule_id**：`r-3b8c946efdf083b5`　|　**判定**：P1 · 未定级

## 规则原文（照抄新库，未改写）

原表述：血压监测就医指征列表（孕晚期）；修订为：补充就医紧急信号：除血压异常相关症状外，如出现阴道流血/流水、持续剧烈腹痛、呼吸困难、胸痛，或胎动明显减少、改变甚至消失，也应尽快联系医生或立即就医。（参考：CDC孕期紧急预警信号）；修订原因：就医紧急预警信号不完整，仅列出子痫前期相关症状，未涵盖CDC建议的其他重要孕期紧急信号（如持续剧烈腹痛、呼吸困难、胸痛等），且未提及阴道流血/流水这一重要紧急信号

## 命中表达（1 条；来源：规则行 forbidden_expression 拆分）

- `血压监测就医指征列表（孕晚期）`

## 判为违规的依据

就医紧急预警信号不完整，仅列出子痫前期相关症状，未涵盖CDC建议的其他重要孕期紧急信号（如持续剧烈腹痛、呼吸困难、胸痛等），且未提及阴道流血/流水这一重要紧急信号

## 处理方式 / 合规替代

补充就医紧急信号：除血压异常相关症状外，如出现阴道流血/流水、持续剧烈腹痛、呼吸困难、胸痛，或胎动明显减少、改变甚至消失，也应尽快联系医生或立即就医。（参考：CDC孕期紧急预警信号）

## 禁用表达汇总

血压监测就医指征列表（孕晚期）

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：1（support_count 取新库值 1）
- 证据级（新库取值）：L1
- 验证状态（新库取值）：待验证 · 规则状态：provisional
- 形态：revision_pair　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `b7c3e0700f4dc13d4532`　#专家修订汇总表/recvoyJ6L9ngSN/修订位置（原文引用）　→ 【前】血压监测就医指征列表（孕晚期） 【后】补充就医紧急信号：除血压异常相关症状外，如出现阴道流血/流水、持续剧烈腹痛、呼吸困难、胸痛，或胎动明显减少、改变甚至消失，也应尽快联系医生或立即就医。（参考：CDC孕期紧急预警信号） 【原因】就医紧急预警信号不完整，仅列出子痫前期相关症状，未涵盖CDC建议的其他重要孕期…

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
