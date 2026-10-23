---
id: cg-sc-a9aa90b4ee6029ac
title: "[S-1.131] 内部正负样本库：反例·unknown·图片"
collection: 2_内部正负样本库
kb_class: [内部正负样本库]
tier: L1
topic: S-1.131
kind: fact
summary: "[S-1.131] 反例案例（图片/展会）：原因归类「unknown」；案例作参照、不构成规则。状态 stable。"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - S-1.131 是正例还是反例
  - S-1.131 的问题要点与原因归类是什么
  - S-1.131 应该怎么做（合规做法 / 修改建议）
not_proves: 案例是参照，不构成规则 —— 不能证明「和它像」就违规、也不能证明「和它像」就合规；不能证明该条已过正式验收；不能证明该条可替代合规/法务意见
forbidden: 不许把案例当规则用（案例只作参照）；不许据本条直接判 BLOCK；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
  - cg-sc-c93511828529e3c0
  - cg-sc-a8046e5cf045c74f
  - cg-sc-f6752c31c0ccee6d
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN"
  fingerprint: Lk3Qb8y2QaVyZns6gprcVNE9nA0/tblcbk4XiW6471YN
  captured_at: 2026-10-22
provenance:
  anchor: "kb/l4/canonical/sample_case.jsonl#sc-a9aa90b4ee6029ac"
  confidence: 确定
pii:
  detected: true
  masked: true
  strategy: "案例正文与原因分析里的 @人名 不可逆脱敏（mask-at-name）；已检出并脱敏"
article_no: S-1.131
form: sample_case
kb_type: internal_sample
kb_version: v0
case_id: sc-a9aa90b4ee6029ac
status: stable
polarity: 反例
material_type: 图片
channel: 展会
reason_category: unknown
evidence_strength: 禁区可复现：有完整样本本体 + 原因分析
promoted_from: provisional
anchor: "#负面样本/recvw7XJiSNTFQ/具体原因/分析"
source_sha256: 59ade0b6c242472631e69d11169e8d228e9dacf476b805526845ba5a3db8a7ed
resource_id: bitable__tbld8qE92YaY38Yz__recvw7XJiSNTFQ
sample_body: "【审核 · 2026-08-15 02:51 · 韦化】【终审-@[已脱敏]】麻烦看看呀:YouAreTheBest: **项目名：中东吸奶器易拉宝修改** **设计要求：**修改一：产品替换 修改二：每个吸奶器的下边放上名称 **设计稿件：** ![Image](img_v3_0214i_15e00052-dfc1-4f50-8e95-6b1ebb28bbfg)"
reason_analysis: "【审核问题】图片 设计要求：修改一：产品替换。 【问题要点】 1. 设计要求：修改一：产品替换 2. 【终审-@[已脱敏]】麻烦看看呀 3. 修改二：每个吸奶器的下边放上名称"
advice: ""
---

# [S-1.131] 内部正负样本库：反例·unknown·图片

**条款号**：S-1.131　|　**形态**：`sample_case`　|　**正/反例**：反例　|　**状态**：stable

## 样本本体（照抄新库，未改写）

【审核 · 2026-08-15 02:51 · 韦化】【终审-@[已脱敏]】麻烦看看呀:YouAreTheBest:
**项目名：中东吸奶器易拉宝修改**
**设计要求：**修改一：产品替换
修改二：每个吸奶器的下边放上名称
**设计稿件：**
![Image](img_v3_0214i_15e00052-dfc1-4f50-8e95-6b1ebb28bbfg)

## 原因分析

【审核问题】图片 设计要求：修改一：产品替换。
【问题要点】
1. 设计要求：修改一：产品替换
2. 【终审-@[已脱敏]】麻烦看看呀
3. 修改二：每个吸奶器的下边放上名称

## 引用依据

- 锚点：`#负面样本/recvw7XJiSNTFQ/具体原因/分析`
- 指纹：`59ade0b6c242472631e69d11169e8d228e9dacf476b805526845ba5a3db8a7ed`
- 原因归类：unknown　|　素材类型：图片

> 案例只作参照，不构成规则。
