---
id: cg-r-252ba6cf5ee92b00
title: "[M02] 措辞表达库：命中「吸力夸大用语（建议改为客观档位描述）」等 1 类表达"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L1
topic: M02
kind: fact
summary: "[M02] 判为「禁用/必须修改」（P0·未定级）：命中表达 1 条、证据单元 3 条。状态 provisional、verification 已归纳。"
owner: 法务 + 产品负责人
half_life_days: 180
valid_until: 2027-03-28
effective_from: 2026-09-29
evidence_level: L1
data_level: L2
sensitivity_level: L2
created_at: 2026-10-22
asks:
  - M02 判什么、命中什么算违规
  - M02 应该怎么改（合规替代写法）
  - M02 的证据有几条、证据级是什么
  - M02 是 P 几、风险等级是什么
  - 「吸力夸大用语（建议改为客观档位描述）」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「M02」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
evidence_group: rule
complements:
  - cg-r-c767bb12e6a8698d
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblD1MiUK1v5fdjD"
  fingerprint: Lk3Qb8y2QaVyZns6gprcVNE9nA0/tblD1MiUK1v5fdjD
  record_ids: [recvuJP1LVe2xP]
  captured_at: 2026-10-22
provenance:
  anchor: "kb/l3/candidates/rules.jsonl#r-252ba6cf5ee92b00 ∪ kb/l5/p0_patterns.jsonl#p-d1cd2f1d1fdba23a"
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为广告文案/规则表述与专家修订记录，不含姓名、联系方式等个人数据；如后续来源变化需重新判定
rule_id: r-252ba6cf5ee92b00
article_no: W-1.12
rule_code: M02
p_level: P0
risk_level: 未定级
risk_level_raw: High
risk_level_note: 源库 kb/l3 的 risk_level 为 unknown/空 —— 未做人工定级；本视图不据 P 级反推，故标未定级
evidence_level_note: 源库证据级 synthesis，但只归属 1 个来源根（需 ≥2）→ 按加载器 E036 的口径降为 L1（单一来源，只能当线索）
rule_status: provisional
rule_verification: 已归纳
support_count: 3
form: entry
kb_type: wording
---

# [M02] 措辞表达库：命中「吸力夸大用语（建议改为客观档位描述）」等 1 类表达

**条款号**：W-1.12　|　**规则码**：M02　|　**rule_id**：`r-252ba6cf5ee92b00`　|　**判定**：P0 · 未定级

## 规则原文（照抄新库，未改写）

边界：吸力夸大用语（建议改为客观档位描述）；触发词：super strong, ultra powerful, max suction, strongest suction, 超强, 极致, 无敌, 超级；豁免：suction level, suction settings, adjustable suction

## 命中表达（1 条；来源：l5 P0 匹配器 p-d1cd2f1d1fdba23a）

- `吸力夸大用语（建议改为客观档位描述）`

### 白名单（命中这些不算违规）

- \b(not|never|no)\s+(better|best|safer|safest|superior|more\s+effective)\b[^.]{0,30}
- \b(did|do|does|will|would|can|could|shall|should|is|are|was|were|has|have|had|wo|ca|sha)\s*n['’]?t\b[^.]{0,20}\b(treat|cure|heal|pain|milk)\b
- \b(did|do|does|will|would|can|could|shall|should|is|are|was|were|has|have|had)\s+not\b[^.]{0,20}\b(treat|cure|heal|pain|milk)\b
- \bcannot\b[^.]{0,20}\b(treat|cure|heal|pain|milk)\b
- \b(does\s*n[o']?t|do\s+not|does\s+not|not\s+intended\s+to|never|no\s+claim)\b[^.]{0,40}\b(treat|cure|heal|pain|milk)\b
- (不能|不可以|无法|并非|不是|不做|不会|不具|未经|尚缺乏|缺乏|没有|严禁|禁止|无需|无须|无证据|无依据|无临床|无科学|无任何|没有任何)[^。]{0,20}(治疗|治愈|预防|无痛|增产|催奶|催乳|堵奶|乳腺炎|临床|证明|科学)
- ^\s*(DO\s+NOT\s+SAY|Do\s+not\s+say|禁用表达|禁用词|禁止表达|禁止使用|禁用|禁止|不允许|不得使用|违规表述|违规词|高危词)\s*[:：][^。！？!?]{0,200}
- [「『\"“][^」』\"”]{0,80}[」』\"”]
- \b(per|according\s+to|as\s+stated\s+in|cited\s+from)\b[^.]{0,30}
- ^(依据|来源|原文|条款)[:：]
- \bbest\s+(regards|wishes|practice|practices|effort|efforts|of\s+luck|before|time|interest|known|case|cases)\b
- \b(at|the)\s+very\s+best\b
- (尽力|努力|尽量|争取|力求)[^。]{0,6}最好
- 最好\s*(在|先|还是|不要|别|能|可以)
- 最高\s*(?:可达|可到|可至|达|到|至)?\s*[-−]?\s*\d+(?:\.\d+)?\s*(?:mmHg|kPa|dB|分贝|档|档位|ml|毫升|oz|盎司|L|升|小时|分钟|秒)

## 判为违规的依据

（新库该行为空）

## 处理方式 / 合规替代

（新库该行为空）

## 禁用表达汇总

super strong, ultra powerful, max suction, strongest suction, 超强, 极致, 无敌, 超级

## 适用范围与证据

- 覆盖记录数：0
- 证据单元数：3（support_count 取新库值 3）
- 证据级（新库取值）：L1
- 验证状态（新库取值）：已归纳 · 规则状态：provisional
- 形态：entry　|　库：措辞表达库（wording）
- P0 匹配器：`p-d1cd2f1d1fdba23a`（authority=None，match_note=BLOCK）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `3324d6641c4630caf9c0`　#品线内容边界规则库/recvuJP1LVe2xP/边界内容　→ 吸力夸大用语（建议改为客观档位描述）
- `71b7540b8885ea5eaf93`　#品线内容边界规则库/recvuJP1LVe2xP/检测关键词　→ super strong, ultra powerful, max suction, strongest suction, 超强, 极致, 无敌, 超级
- `44cdfe90fd35ecc55dde`　#品线内容边界规则库/recvuJP1LVe2xP/豁免词　→ suction level, suction settings, adjustable suction

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
