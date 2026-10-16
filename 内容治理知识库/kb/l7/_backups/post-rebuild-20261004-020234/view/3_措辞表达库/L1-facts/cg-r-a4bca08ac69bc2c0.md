---
id: cg-r-a4bca08ac69bc2c0
title: "[W-2.281] 措辞表达库：命中「NT检查将无法补做」等 1 类表达"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L1
topic: 未登记规则码
kind: fact
summary: "[W-2.281] 判为「禁用/必须修改」（P1·未定级）：命中表达 1 条、证据单元 1 条；处理方式是「已在正文标注建议修改，修订为：NT测量本身有明确的孕周窗口，错过后通常不能再补做同类测量」。状态 provisional、verification 待验证。"
owner: 法务
half_life_days: 180
valid_until: 2027-04-02
effective_from: 2026-10-04
evidence_level: L1
data_level: L2
sensitivity_level: L2
created_at: 2026-10-04
asks:
  - W-2.281 判什么、命中什么算违规
  - W-2.281 应该怎么改（合规替代写法）
  - W-2.281 的证据有几条、证据级是什么
  - W-2.281 是 P 几、风险等级是什么
  - 「NT检查将无法补做」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「W-2.281」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
evidence_group: rule
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/SKkkbdZi9aRuMzs7ob0cpSYHnQg?table=tbl8AI00JZO1iZtp"
  fingerprint: SKkkbdZi9aRuMzs7ob0cpSYHnQg/tbl8AI00JZO1iZtp
  record_ids: [recvoyJ6L9DZ31]
  captured_at: 2026-10-04
provenance:
  anchor: "kb/l3/candidates/rules.jsonl#r-a4bca08ac69bc2c0"
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为广告文案/规则表述与专家修订记录，不含姓名、联系方式等个人数据；如后续来源变化需重新判定
rule_id: r-a4bca08ac69bc2c0
article_no: W-2.281
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

# [W-2.281] 措辞表达库：命中「NT检查将无法补做」等 1 类表达

**条款号**：W-2.281　|　**规则码**：（未登记）　|　**rule_id**：`r-a4bca08ac69bc2c0`　|　**判定**：P1 · 未定级

## 规则原文（照抄新库，未改写）

原表述：NT检查将无法补做；修订为：已在正文标注建议修改，修订为：NT测量本身有明确的孕周窗口，错过后通常不能再补做同类测量；但这并不代表后续没有其他筛查或评估选项，具体可与医生讨论适合自己的后续方案。；修订原因：表述过于绝对，错过NT测量窗口后，仍可能有其他筛查或评估路径（如二孕期筛查、cfDNA/NIPT、系统超声等），不应让读者误以为完全无后续选择

## 命中表达（1 条；来源：规则行 forbidden_expression 拆分）

- `NT检查将无法补做`

## 判为违规的依据

表述过于绝对，错过NT测量窗口后，仍可能有其他筛查或评估路径（如二孕期筛查、cfDNA/NIPT、系统超声等），不应让读者误以为完全无后续选择

## 处理方式 / 合规替代

已在正文标注建议修改，修订为：NT测量本身有明确的孕周窗口，错过后通常不能再补做同类测量；但这并不代表后续没有其他筛查或评估选项，具体可与医生讨论适合自己的后续方案。

## 禁用表达汇总

NT检查将无法补做

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：1（support_count 取新库值 1）
- 证据级（新库取值）：L1
- 验证状态（新库取值）：待验证 · 规则状态：provisional
- 形态：revision_pair　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `e02db97c7d0b0d439fb6`　#专家修订汇总表/recvoyJ6L9DZ31/修订位置（原文引用）　→ 【前】NT检查将无法补做 【后】已在正文标注建议修改，修订为：NT测量本身有明确的孕周窗口，错过后通常不能再补做同类测量；但这并不代表后续没有其他筛查或评估选项，具体可与医生讨论适合自己的后续方案。 【原因】表述过于绝对，错过NT测量窗口后，仍可能有其他筛查或评估路径（如二孕期筛查、cfDNA/NIPT、系统超声…

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
