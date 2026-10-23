---
id: cg-r-953aea516fc7ae54
title: "[BR-01] 措辞表达库：命中「M0m222」等 7 类表达"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L1
topic: BR-01
kind: fact
summary: "[BR-01] 判为「需按建议改写」（P2·未定级）：命中表达 7 条、证据单元 3 条；处理方式是「momcozy（登记写法：全小写、一个词、无空格）」。状态 provisional、verification 待验证。"
owner: 法务
half_life_days: 180
valid_until: 2027-04-18
effective_from: 2026-10-20
evidence_level: L1
data_level: L2
sensitivity_level: L2
created_at: 2026-10-22
asks:
  - BR-01 判什么、命中什么算违规
  - BR-01 应该怎么改（合规替代写法）
  - BR-01 的证据有几条、证据级是什么
  - BR-01 是 P 几、风险等级是什么
  - 「M0m222；momc0zy；m0mcozy」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「BR-01」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
evidence_group: rule
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN"
  fingerprint: Lk3Qb8y2QaVyZns6gprcVNE9nA0/tblcbk4XiW6471YN
  record_ids: []
  captured_at: 2026-10-22
provenance:
  anchor: "kb/l3/candidates/rules.jsonl#r-953aea516fc7ae54"
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为广告文案/规则表述与专家修订记录，不含姓名、联系方式等个人数据；如后续来源变化需重新判定
rule_id: r-953aea516fc7ae54
article_no: W-1.57
rule_code: BR-01
p_level: P2
risk_level: 未定级
risk_level_raw: Medium
risk_level_note: 源库 kb/l3 的 risk_level 为 unknown/空 —— 未做人工定级；本视图不据 P 级反推，故标未定级
evidence_level_note: 源库证据级 observation（单条修订对、单一来源）→ L1
rule_status: provisional
rule_verification: 待验证
support_count: 1
form: entry
kb_type: wording
---

# [BR-01] 措辞表达库：命中「M0m222」等 7 类表达

**条款号**：W-1.57　|　**规则码**：BR-01　|　**rule_id**：`r-953aea516fc7ae54`　|　**判定**：P2 · 未定级

## 规则原文（照抄新库，未改写）

规则码 BR-01：命中**品牌名字标的字符级错误写法**（以数字替换字母，或在品牌名中插入空格，如 M0m222／momc0zy／mom cozy）判定为「品牌写法不一致」；处理：改为登记写法 momcozy（全小写、品牌名是一个词、不留空格），并核对原图实物字标；**大小写不一致不在本规则范围内**（引擎归一化会把大小写抹平，判不了，见 brand-wording-policy.yaml）。

## 命中表达（7 条；来源：规则行 forbidden_expression 拆分）

- `M0m222`
- `momc0zy`
- `m0mcozy`
- `momco2y`
- `m0mco2y`
- `mom cozy`
- `Mom Cozy`

## 判为违规的依据

品牌名字标写法与品牌侧规范不一致（数字替换字母 / 品牌名里插空格），美国消费者会把它读成乱码，或误认成非官方账号，品牌识别被稀释

## 处理方式 / 合规替代

momcozy（登记写法：全小写、一个词、无空格）

## 禁用表达汇总

M0m222,momc0zy,m0mcozy,momco2y,m0mco2y,mom cozy,Mom Cozy

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：3（support_count 取新库值 1）
- 证据级（新库取值）：L1
- 验证状态（新库取值）：待验证 · 规则状态：provisional
- 形态：entry　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `3f79c2707e10dbbb231e`　#l.3-19　→ <callout emoji="📝"> **Brand Copy & Typography Guidelines** 本规范用于统一 Momcozy 品牌传播中**文案层级、大小写、字体搭配及信息强调方式**，建立清晰、一致且可延展的品牌文案视觉体系。 工具：https://capitalizemytitle.c…
- `47bcbc6f8f461942e40e`　#h.品牌与渠道的责任边界 / Brand / VI 负责　→ - Copy Hierarchy 文案层级 - Headline 大小写原则 - Body Copy 原则 - Typography Hierarchy 字体层级 - Serif Emphasis 强调逻辑 - Brand Keyword 品牌关键词原则 - Number / Data 数据视觉原则 - Loca…
- `81c65cde06bd28ebb610`　#h.多语言与本地化原则　→ - Capitalization 大小写 - Headline Structure 标题结构 - Serif Emphasis 关键词强调 - Keyword Selection 关键词选择 - Punctuation 标点 - Number Formatting 数字格式 - Currency Formatti…

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
