---
id: cg-r-8dfbcdca24e18a60
title: "[W-1.37] 措辞表达库规则（3 条证据）"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L1
topic: 未登记规则码
kind: fact
summary: "[W-1.37] 判为「禁用/必须修改」（P1·黄）：命中表达 0 条、证据单元 3 条；处理方式是「可能帮助前几分钟排乳更顺，建议作为待验证产品终点。」。状态 provisional、verification 已支持。"
owner: 法务
half_life_days: 90
valid_until: 2026-12-28
evidence_level: L1
data_level: L2
sensitivity_level: L2
created_at: 2026-09-29
asks:
  - W-1.37 判什么、命中什么算违规
  - W-1.37 应该怎么改（合规替代写法）
  - W-1.37 的证据有几条、证据级是什么
  - W-1.37 是 P 几、风险等级是什么
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「W-1.37」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
  - cg-r-8e049d8b38a8ac31
  - cg-r-97044c3283e41aea
  - cg-r-9e252d15425a4179
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblqUTAKFkWheU49"
  fingerprint: Lk3Qb8y2QaVyZns6gprcVNE9nA0/tblqUTAKFkWheU49
  captured_at: 2026-09-29
provenance:
  anchor: "kb/l3/candidates/rules.jsonl#r-8dfbcdca24e18a60"
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为广告文案/规则表述与专家修订记录，不含姓名、联系方式等个人数据；如后续来源变化需重新判定
rule_id: r-8dfbcdca24e18a60
article_no: W-1.37
rule_code: ""
p_level: P1
risk_level: 黄
risk_level_raw: 黄色-需限定
evidence_level_note: 源库证据级 synthesis，但只归属 1 个来源根（需 ≥2）→ 按加载器 E036 的口径降为 L1（单一来源，只能当线索）
rule_status: provisional
rule_verification: 已支持
support_count: 3
form: entry
kb_type: wording
---

# [W-1.37] 措辞表达库规则（3 条证据）

**条款号**：W-1.37　|　**规则码**：（未登记）　|　**rule_id**：`r-8dfbcdca24e18a60`　|　**判定**：P1 · 黄

## 规则原文（照抄新库，未改写）

建议表达：可能帮助前几分钟排乳更顺，建议作为待验证产品终点。；限定要求：需说明不是W1直接研究，不能承诺个人结果。；判定理由：相关研究支持短时方向，但不能外推到长期奶量。

## 判为违规的依据

相关研究支持短时方向，但不能外推到长期奶量。

## 处理方式 / 合规替代

可能帮助前几分钟排乳更顺，建议作为待验证产品终点。

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：3（support_count 取新库值 3）
- 证据级（新库取值）：L1
- 验证状态（新库取值）：已支持 · 规则状态：provisional
- 形态：entry　|　库：措辞表达库（wording）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `cddc22a85f2d08893fc1`　#W1卖点表达边界（品线反馈0910）/recvuNf8jlo1pD/建议表达（合规话术）　→ 可能帮助前几分钟排乳更顺，建议作为待验证产品终点。
- `a273691c68d7f04f50a1`　#W1卖点表达边界（品线反馈0910）/recvuNf8jlo1pD/判定理由　→ 相关研究支持短时方向，但不能外推到长期奶量。
- `a96cda9448e780f43560`　#W1卖点表达边界（品线反馈0910）/recvuNf8jlo1pD/避免条件/限定要求　→ 需说明不是W1直接研究，不能承诺个人结果。

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
