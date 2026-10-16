---
id: cg-r-ddf0f8360c7b53a7
title: "[M01] 措辞表达库：命中「silent」等 8 类表达"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L2
topic: M01
kind: judgment
summary: "[M01] 判为「禁用/必须修改」（P1·黄）：命中表达 8 条、证据单元 4 条。状态 provisional、verification 已支持。"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-09-28
valid_until: 2027-03-27
asks:
  - M01 判什么、命中什么算违规
  - M01 应该怎么改（合规替代写法）
  - M01 的证据有几条、证据级是什么
  - M01 是 P 几、风险等级是什么
  - 「silent；whisper quiet；zero noise」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「M01」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
  - cg-r-0ffc53715dfa4e43
  - cg-r-106e4c5b6475d0e3
  - cg-r-15a607c4457c8b55
  - cg-r-16cac1c85580f8f7
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblD1MiUK1v5fdjD"
  fingerprint: Lk3Qb8y2QaVyZns6gprcVNE9nA0/tblD1MiUK1v5fdjD
  captured_at: 2026-09-28
provenance:
  anchor: "kb/l3/candidates/rules.jsonl#r-ddf0f8360c7b53a7"
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为广告文案/规则表述与专家修订记录，不含姓名、联系方式等个人数据；如后续来源变化需重新判定
rule_id: r-ddf0f8360c7b53a7
article_no: W-1.54
rule_code: M01
p_level: P1
risk_level: 黄
risk_level_raw: 审慎
evidence_level_note: 源库证据级 synthesis，但只归属 1 个来源根（需 ≥2）→ 按加载器 E036 的口径降为 L1（单一来源，只能当线索）
rule_status: provisional
rule_verification: 已支持
support_count: 4
form: entry
kb_type: wording
---

# [M01] 措辞表达库：命中「silent」等 8 类表达

**条款号**：W-1.54　|　**规则码**：M01　|　**rule_id**：`r-ddf0f8360c7b53a7`　|　**判定**：P1 · 黄

## 规则原文（照抄新库，未改写）

边界：静音程度夸大（建议改为 low noise / quiet mode）；触发词：silent, whisper quiet, zero noise, noiseless, 几乎静音, 完全静音, 零噪音, 静音；豁免：low noise, quiet mode, low-decibel, silent mode, 静音模式

## 命中表达（8 条；来源：规则行 forbidden_expression 拆分）

- `silent`
- `whisper quiet`
- `zero noise`
- `noiseless`
- `几乎静音`
- `完全静音`
- `零噪音`
- `静音`

### 白名单（命中这些不算违规）

- low noise
- quiet mode
- low-decibel
- silent mode
- 静音模式

## 判为违规的依据

（新库该行为空）

## 处理方式 / 合规替代

（新库该行为空）

## 禁用表达汇总

silent, whisper quiet, zero noise, noiseless, 几乎静音, 完全静音, 零噪音, 静音

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：4（support_count 取新库值 4）
- 证据级（新库取值）：L1
- 验证状态（新库取值）：已支持 · 规则状态：provisional
- 形态：entry　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `268dfb116baeec22337b`　#品线内容边界规则库/recvuJP1LV2uxa/边界内容　→ 静音程度夸大（建议改为 low noise / quiet mode）
- `6820619bf4bc83a64fff`　#品线内容边界规则库/recvuJP1LV2uxa/检测关键词　→ silent, whisper quiet, zero noise, noiseless, 几乎静音, 完全静音, 零噪音, 静音
- `e433b2b5d1233d2798be`　#品线内容边界规则库/recvuJP1LV2uxa/豁免词　→ low noise, quiet mode, low-decibel, silent mode, 静音模式
- `2963dd4d8d27ee7b5025`　#品线内容边界规则库/recvuJP1LV2uxa/正则表达式　→ \b(silent|noiseless|whisper.?quiet)\b

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
