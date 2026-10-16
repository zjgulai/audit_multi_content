---
id: cg-r-37b49eadb72d7dc2
title: "[H02] 措辞表达库：命中「augmente la production de lait」等 24 类表达"
collection: 3_措辞表达库
tier: L2-concepts
topic: H02
kind: fact
summary: "[H02] 判为「禁用/必须修改」（P0·高危·红）：命中表达 24 条、证据单元 102 条、覆盖记录 34 条；处理方式是「「easier letdown」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺」。状态 provisional、verification 已归纳。"
owner: 刘华丽
evidence_level: synthesis
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-09-23
valid_until: 2027-03-22
asks:
  - H02 判什么、命中什么算违规
  - H02 应该怎么改（合规替代写法）
  - H02 的证据有几条、证据级是什么
  - H02 是 P 几、风险等级是什么
  - 「augmente la production de lait；boost supply；easier let-down」这类表述能不能用
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「H02」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
related:
source:
  kind: derived
  ref: "kb/l3/candidates/rules.jsonl#r-37b49eadb72d7dc2 ∪ kb/l5/p0_patterns.jsonl#p-755f9ff377c3052c"
  fingerprint: 1bfb6d66b6324a94a77f9e839c8627c8
  captured_at: 2026-09-23
rule_id: r-37b49eadb72d7dc2
article_no: W-1.18
rule_code: H02
p_level: P0
risk_level: 高危·红
rule_status: provisional
verification: 已归纳
support_count: 102
form: entry
kb_type: wording
derived_from: kb/l3/candidates/rules.jsonl
---

# [H02] 措辞表达库：命中「augmente la production de lait」等 24 类表达

**条款号**：W-1.18　|　**规则码**：H02　|　**rule_id**：`r-37b49eadb72d7dc2`　|　**判定**：P0 · 高危·红

## 规则原文（照抄新库，未改写）

规则码 H02：命中「augmente la production de lait；boost supply,more milk,triggers letdown；easier let-down；easier letdown；faster let-down,support faster let-down；improve pumping efficiency；increase milk supply；increase milk supply,more milk」判定为违规；处理：「easier letdown」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 静音表述改客观参数（as low as 48 dB），避免 whisper/silent/ultra-quiet 绝对化；「increase milk suppl；依据：H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；M01 静音程度夸

## 命中表达（24 条；来源：l5 P0 匹配器 p-755f9ff377c3052c）

- `augmente la production de lait`
- `boost supply`
- `easier let-down`
- `easier letdown`
- `improve pumping efficiency`
- `increase milk supply`
- `increases milk production`
- `increasing milk supply`
- `mehr milch`
- `more milk`
- `más leche`
- `plus de lait`
- `producción de leche`
- `support faster let-down`
- `triggers letdown`
- `boost milk`
- `maximize milk`
- `milk supply boost`
- `下奶`
- `催乳`
- `催奶`
- `增产`
- `增加奶量`
- `奶量提升`

### 正则形态

- `\b(more|increase[sd]?|boost[s]?|maximi[sz]e[sd]?)\s+(your\s+)?milk\b`
- `\blet[\s-]?down\b`
- `增\s*产|催\s*奶|催\s*乳|下\s*奶`

### 白名单（命中这些不算违规）

- \b(does\s*n[o']?t|do\s+not|does\s+not|not\s+intended\s+to|never|no\s+claim)\b[^.]{0,40}\b(treat|cure|heal|pain|milk)\b
- (不能|不可以|无法|并非|不是|不做|严禁|禁止)[^。]{0,20}(治疗|治愈|预防|无痛|增产|催奶|催乳)
- ^\s*(DO\s+NOT\s+SAY|Do\s+not\s+say|禁用表达|禁用词|禁止表达|禁止使用|禁用|禁止|不允许|不得使用|违规表述|违规词|高危词)\s*[:：][^。！？!?]{0,200}
- [「『\"“][^」』\"”]{0,80}[」』\"”]
- \b(per|according\s+to|as\s+stated\s+in|cited\s+from)\b[^.]{0,30}
- ^(依据|来源|原文|条款)[:：]

## 判为违规的依据

H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；M01 静音程度夸大（建议改为 low noise / quiet mode）

## 处理方式 / 合规替代

「easier letdown」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 静音表述改客观参数（as low as 48 dB），避免 whisper/silent/ultra-quiet 绝对化；「increase milk supply,more milk」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 奶流/移除量/排空效率/漏奶/短时排乳类claim需W1自身对照数据（样本、对照、统计口径齐全），或改为放松叙事+限定语（may help/natural）；内部测试数值（28.2%/10%/70%）补齐前不得公开传播；「plus de lait」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用；「augmente la production de lait」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 删除 pain-free/no pain/without pain/pain relief/less pain/无痛/缓解疼痛等疼痛功效承诺（含 sans douleur/schmerzfrei/sin dolor），只保留 comfort/gentle 与缓解胀满不适 discomfort 的表述；「increase milk supply」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 删除 pain-free/no pain/without pain/pain relief/less pain/无痛/缓解疼痛等疼痛功效承诺（含 sans douleur/schmerzfrei/sin dolor），只保留 comfort/gentle 与缓解胀满不适 discomfort 的表述 ▸ 删除自动识别节奏/模拟复制宝宝/饱腹反馈/降低奶量焦虑等智能闭环与仿生宣称；仿生表达只允许 inspired by natural nursing（参考自然哺乳节奏的设计思路）；「easier letdown」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 静音表述改客观参数（as low as 48 dB），避免 whisper/silent/ultra-quiet 绝对化；「improve pumping efficiency」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开） ▸ 奶流/移除量/排空效率/漏奶/短时排乳类claim需W1自身对照数据（样本、对照、统计口径齐全），或改为放松叙事+限定语（may help/natural）；内部测试数值（28.2%/10%/70%）补齐前不得公开传播；「improve pumping efficiency」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开） ▸ 奶流/移除量/排空效率/漏奶/短时排乳类claim需W1自身对照数据（样本、对照、统计口径齐全），或改为放松叙事+限定语（may help/natural）；内部测试数值（28.2%/10%/70%）补齐前不得公开传播（另 26 组同码修订建议见证据单元）

## 禁用表达汇总

augmente la production de lait；boost supply,more milk,triggers letdown；easier let-down；easier letdown；faster let-down,support faster let-down；improve pumping efficiency；increase milk supply；increase milk supply,more milk；increases milk production；increasing milk supply；mehr milch；more milk；más leche；plus de lait；producción de leche

## 适用范围与证据

- 覆盖记录数：34
- 证据单元数：102（support_count 取新库值 102）
- 证据级（新库取值）：synthesis
- 验证状态（新库取值）：已归纳 · 规则状态：provisional
- 形态：entry　|　库：措辞表达库（wording）
- P0 匹配器：`p-755f9ff377c3052c`（authority=expert，match_note=BLOCK）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `9c313d585ee7d5290c08`　#广告文案明细/recvuJYdOb1Rm1/命中片段　→ H02:easier letdown / M01:whisper,whisper-quiet
- `521753286e8e238938e2`　#广告文案明细/recvuJYdOb1Rm1/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `7ec15343f347bc92fcc9`　#广告文案明细/recvuJYdOb1Rm1/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；M01 静音程度夸大（建议改为 low noise / quiet mode）
- `ab48363a38d4bd7dabb7`　#广告文案明细/recvuJYdOb1fOj/命中片段　→ H02:increase milk supply,more milk / M07:better milk flow
- `70089914d416622d611a`　#广告文案明细/recvuJYdOb1fOj/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `926ac5ca340c9e242676`　#广告文案明细/recvuJYdOb1fOj/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；M07 效率/漏奶/奶流/移除量/短时排乳类claim需W1自身对照数据（当前仅内部测试或外…
- `efe046efe7b5954b75c6`　#广告文案明细/recvuJYdOb2Qdw/命中片段　→ H02:plus de lait
- `f1ac8ff6e5e08f224451`　#广告文案明细/recvuJYdOb2Qdw/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `589276570ac29dd3dcc3`　#广告文案明细/recvuJYdOb2Qdw/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫
- `0129c68a81f47a8b5c45`　#广告文案明细/recvuJYdOb5q3i/命中片段　→ H02:augmente la production de lait / H07:indolore
- `439ce5acf9525d6813af`　#广告文案明细/recvuJYdOb5q3i/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `2aca7fd69c15fb548e0b`　#广告文案明细/recvuJYdOb5q3i/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H07 疼痛功效承诺（pain-free/no pain/without pain/pain…
- `74d1ba6b94a5336853dd`　#广告文案明细/recvuJYdOb61lT/命中片段　→ H02:increase milk supply / H07:pain-free / H09:mimics baby,mimics baby’s natural nursing
- `0d3289c8b0363292fff1`　#广告文案明细/recvuJYdOb61lT/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `cb3ae64719ed621f4e63`　#广告文案明细/recvuJYdOb61lT/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H07 疼痛功效承诺（pain-free/no pain/without pain/pain…
- `be7ad81966f891ec8336`　#广告文案明细/recvuJYdOb8iq3/命中片段　→ H02:easier letdown / M01:whisper,whisper-quiet
- `f955828017e85c31a4b7`　#广告文案明细/recvuJYdOb8iq3/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `26ac93554908b49c367e`　#广告文案明细/recvuJYdOb8iq3/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；M01 静音程度夸大（建议改为 low noise / quiet mode）
- `b73695e179b65f539484`　#广告文案明细/recvuJYdObCYOh/命中片段　→ H02:improve pumping efficiency / H05:perfect pump / M07:improve milk flow,improve pumping efficiency
- `96f2e6667a2ce7cc44fb`　#广告文案明细/recvuJYdObCYOh/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `8ad0d26e52f4f30fe45c`　#广告文案明细/recvuJYdObCYOh/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09…
- `799d2156d1dac83ba79b`　#广告文案明细/recvuJYdObCu5l/命中片段　→ H02:improve pumping efficiency / H05:perfect pump / M07:improve milk flow,improve pumping efficiency
- `2db4170ee36dfdd000eb`　#广告文案明细/recvuJYdObCu5l/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `1dfe5b28951368980c74`　#广告文案明细/recvuJYdObCu5l/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09…
- `64ac0f3349a250191bc3`　#广告文案明细/recvuJYdObEkcQ/命中片段　→ H02:easier letdown / M01:whisper,whisper-quiet
- `2a8d58e286f0a6103f81`　#广告文案明细/recvuJYdObEkcQ/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `4e9c8a22f04f5d8e2572`　#广告文案明细/recvuJYdObEkcQ/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；M01 静音程度夸大（建议改为 low noise / quiet mode）
- `3c8fce0b57b527aa469c`　#广告文案明细/recvuJYdObEl6L/命中片段　→ H02:more milk / M01:whisper,whisper-quiet / M03:28% faster / M04:don't miss / M02:strong suction
- `59bd46e62ab6f9f60b31`　#广告文案明细/recvuJYdObEl6L/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `e97a11169b087093fbf7`　#广告文案明细/recvuJYdObEl6L/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；M01 静音程度夸大（建议改为 low noise / quiet mode）；M03 未标…
- …另有 72 条，见新库 rules.jsonl 的 evidence_units

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
