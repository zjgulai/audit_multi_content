---
id: cg-sc-0db1c3ae8cfd53d1
title: "[S-1.210] 内部正负样本库：反例·审核问题·图片"
collection: 2_内部正负样本库
kb_class: [内部正负样本库]
tier: L1
topic: S-1.210
kind: fact
summary: "[S-1.210] 反例案例（图片/其他）：原因归类「审核问题」；案例作参照、不构成规则。状态 stable。"
owner: 董希
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - S-1.210 是正例还是反例
  - S-1.210 的问题要点与原因归类是什么
  - S-1.210 应该怎么做（合规做法 / 修改建议）
not_proves: 案例是参照，不构成规则 —— 不能证明「和它像」就违规、也不能证明「和它像」就合规；不能证明该条已过正式验收；不能证明该条可替代合规/法务意见
forbidden: 不许把案例当规则用（案例只作参照）；不许据本条直接判 BLOCK；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
  - cg-sc-97b3655b8e87f697
  - cg-sc-950bf7e40c6b6ca7
  - cg-sc-727a61971e3cd9c6
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN"
  fingerprint: Lk3Qb8y2QaVyZns6gprcVNE9nA0/tblcbk4XiW6471YN
  captured_at: 2026-10-22
provenance:
  anchor: "kb/l4/canonical/sample_case.jsonl#sc-0db1c3ae8cfd53d1"
  confidence: 确定
pii:
  detected: true
  masked: true
  strategy: "案例正文与原因分析里的 @人名 不可逆脱敏（mask-at-name）；已检出并脱敏"
article_no: S-1.210
form: sample_case
kb_type: internal_sample
kb_version: v0
case_id: sc-0db1c3ae8cfd53d1
status: stable
polarity: 反例
material_type: 图片
channel: 其他
reason_category: 审核问题
evidence_strength: 禁区可复现：有完整样本本体 + 原因分析
promoted_from: provisional
anchor: "#负面样本/recvw7XJiSyehR/具体原因/分析"
source_sha256: e9bf74063c0eb063bb189e80a238b0966b8edb534ed57d5699dd75b1d9b582e1
resource_id: bitable__tbld8qE92YaY38Yz__recvw7XJiSyehR
sample_body: "【审核 · 2026-09-04 00:20 · 董希】初审@[已脱敏] ，再看看呀 项目需求：paruu老品优化-银质因为存在差评问题，在原图片增加提醒&补充对比说明情况  设计稿件 ![Image](img_v3_02156_58e6c835-ab59-4f77-bee4-c29d2086667g) ![Image](img_v3_02156_1cd664e5-ac73-42a8-8755-0573ddd1ebcg) ![Image](img_v3_02156_cf77cf71-a308-4811-9d5f-eb45f5c49cag) ![Image](img_v3_02156_cf91247d-82c8-450f-9c86-ad2267910ccg)  ![Image](img_v3_02156_7efc85bd-bbe8-4d09-84bf-ec8accb2dd1g)  ![Image](img_v3_02156_f32c3a30-9fa1-4459-b61e-a1b6bb96161g)"
reason_analysis: "【审核问题】文案 项目需求：paruu老品优化-银质因为存在差评问题，在原图片。 原因：项目需求：paruu老品优化-银质因为存在差评问题，在原图片增加提醒&补充对比说明情况 【问题要点】 1. 项目需求：paruu老品优化-银质因为存在差评问题，在原图片增加提醒&补充对比说明情况 2. 初审@[已脱敏] ，再看看呀"
advice: "优化-银质因为存在差评问题，在原图片增加提醒&补充对比说明情况"
---

# [S-1.210] 内部正负样本库：反例·审核问题·图片

**条款号**：S-1.210　|　**形态**：`sample_case`　|　**正/反例**：反例　|　**状态**：stable

## 样本本体（照抄新库，未改写）

【审核 · 2026-09-04 00:20 · 董希】初审@[已脱敏] ，再看看呀
项目需求：paruu老品优化-银质因为存在差评问题，在原图片增加提醒&补充对比说明情况

设计稿件
![Image](img_v3_02156_58e6c835-ab59-4f77-bee4-c29d2086667g)
![Image](img_v3_02156_1cd664e5-ac73-42a8-8755-0573ddd1ebcg)
![Image](img_v3_02156_cf77cf71-a308-4811-9d5f-eb45f5c49cag)
![Image](img_v3_02156_cf91247d-82c8-450f-9c86-ad2267910ccg)

![Image](img_v3_02156_7efc85bd-bbe8-4d09-84bf-ec8accb2dd1g)

![Image](img_v3_02156_f32c3a30-9fa1-4459-b61e-a1b6bb96161g)

## 原因分析

【审核问题】文案 项目需求：paruu老品优化-银质因为存在差评问题，在原图片。
原因：项目需求：paruu老品优化-银质因为存在差评问题，在原图片增加提醒&补充对比说明情况
【问题要点】
1. 项目需求：paruu老品优化-银质因为存在差评问题，在原图片增加提醒&补充对比说明情况
2. 初审@[已脱敏] ，再看看呀

## 建议

优化-银质因为存在差评问题，在原图片增加提醒&补充对比说明情况

## 引用依据

- 锚点：`#负面样本/recvw7XJiSyehR/具体原因/分析`
- 指纹：`e9bf74063c0eb063bb189e80a238b0966b8edb534ed57d5699dd75b1d9b582e1`
- 原因归类：审核问题　|　素材类型：图片

> 案例只作参照，不构成规则。
