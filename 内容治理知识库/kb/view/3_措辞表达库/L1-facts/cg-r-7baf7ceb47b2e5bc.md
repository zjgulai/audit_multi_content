---
id: cg-r-7baf7ceb47b2e5bc
title: "[H05] 措辞表达库：命中「perfect pump」等 13 类表达"
collection: 3_措辞表达库
kb_class: [措辞表达库]
tier: L1
topic: H05
kind: fact
summary: "[H05] 判为「禁用/必须修改」（P0·未定级）：命中表达 13 条、证据单元 36 条、覆盖记录 12 条；处理方式是「「perfect pump」→ 删除/替换为：删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all」。状态 provisional、verification 已归纳。"
owner: 法务 + 产品负责人
half_life_days: 365
valid_until: 2027-09-29
effective_from: 2026-09-29
evidence_level: L1
data_level: L2
sensitivity_level: L2
created_at: 2026-10-10
asks:
  - H05 判什么、命中什么算违规
  - H05 应该怎么改（合规替代写法）
  - H05 的证据有几条、证据级是什么
  - H05 是 P 几、风险等级是什么
  - "「perfect pump；100% safe；100%safe」这类表述能不能用"
not_proves: 不能证明该条已过新库的正式验收（新库 l3 全部为 provisional，l4 canonical 尚未写入）；不能证明该条可替代合规/法务意见；不能证明「H05」以外的规则码（未命中 ≠ 合规）
forbidden: 不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；不许把派生视图的字段改动当成新库改动（视图不写回）
evidence_group: rule
complements:
  - cg-r-3b6c3c82dc667295
source:
  kind: feishu-base
  ref: "https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN"
  fingerprint: Lk3Qb8y2QaVyZns6gprcVNE9nA0/tblcbk4XiW6471YN
  record_ids: [recvuJYdOb1B8v, recvuJYdObCYOh, recvuJYdObCu5l, recvuJYdObE80Z, recvuJYdObFeLc, recvuJYdObGB9q, recvuJYdObGM2P, recvuJYdObJwyY, recvuJYdObKvVy, recvuJYdObNa32, recvuJYdOblbCM, recvuJYdObroBd]
  captured_at: 2026-10-10
provenance:
  anchor: "kb/l3/candidates/rules.jsonl#r-7baf7ceb47b2e5bc ∪ kb/l5/p0_patterns.jsonl#p-08487282e2d400fe"
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为广告文案/规则表述与专家修订记录，不含姓名、联系方式等个人数据；如后续来源变化需重新判定
rule_id: r-7baf7ceb47b2e5bc
article_no: W-1.33
rule_code: H05
p_level: P0
risk_level: 未定级
risk_level_raw: unknown
risk_level_note: 源库 kb/l3 的 risk_level 为 unknown/空 —— 未做人工定级；本视图不据 P 级反推，故标未定级
evidence_level_note: 源库证据级 synthesis，但只归属 1 个来源根（需 ≥2）→ 按加载器 E036 的口径降为 L1（单一来源，只能当线索）
rule_status: provisional
rule_verification: 已归纳
support_count: 36
form: entry
kb_type: wording
---

# [H05] 措辞表达库：命中「perfect pump」等 13 类表达

**条款号**：W-1.33　|　**规则码**：H05　|　**rule_id**：`r-7baf7ceb47b2e5bc`　|　**判定**：P0 · 未定级

## 规则原文（照抄新库，未改写）

规则码 H05：命中「perfect pump」判定为违规；处理：「perfect pump」→ 删除/替换为：删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）；「perfect pump」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因；依据：H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）

## 命中表达（13 条；来源：l5 P0 匹配器 p-08487282e2d400fe）

- `perfect pump`
- `100% safe`
- `100%safe`
- `fits all breast shapes`
- `one size fits all`
- `risk-free`
- `safest`
- `zero risk`
- `一定不损伤`
- `完全安全`
- `绝对安全`
- `适合所有胸型`
- `零风险`

### 正则形态

- `\b(safest|perfect|zero[\s-]?risk|risk[\s-]?free)\b`
- `\b100\s*%\s*(safe|safety)\b`
- `one[\s-]size[\s-]fits[\s-]all`
- `适合\s*所有\s*胸型|完全\s*安全|零\s*风险|绝对\s*安全|一定\s*不\s*损伤`
- `最\s*(好|佳|优|强|安全|低价|便宜|有效|快|大|高|省|舒适)`
- `(排名|销量|全网|行业|品类|国内|全球|世界|亚洲)\s*第一`
- `第一\s*(品牌|选择|名|款|位)`
- `最佳`
- `纯\s*天然`
- `100\s*%\s*(安全|有效|无痛|无副作用|纯|天然|放心|保障|满意)`
- `(?:\bno\.?\s*1|#\s*1)\b`
- `\bbest\b`

### 白名单（命中这些不算违规）

- \b(not|never|no)\s+(better|best|safer|safest|superior|more\s+effective)\b[^.]{0,30}
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

H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）

## 处理方式 / 合规替代

「perfect pump」→ 删除/替换为：删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）；「perfect pump」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开） ▸ 奶流/移除量/排空效率/漏奶/短时排乳类claim需W1自身对照数据（样本、对照、统计口径齐全），或改为放松叙事+限定语（may help/natural）；内部测试数值（28.2%/10%/70%）补齐前不得公开传播；「perfect pump」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开） ▸ 奶流/移除量/排空效率/漏奶/短时排乳类claim需W1自身对照数据（样本、对照、统计口径齐全），或改为放松叙事+限定语（may help/natural）；内部测试数值（28.2%/10%/70%）补齐前不得公开传播；「perfect pump」→ 删除/替换为：删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）；「perfect pump」→ 删除/替换为：删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开） ▸ hospital/NICU 场景表述需事实依据，否则删除；「perfect pump」→ 删除/替换为：删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）；「perfect pump」→ 删除/替换为：删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）；「perfect pump」→ 删除/替换为：删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开） ▸ 删除 pain-free/no pain/without pain/pain relief/less pain/无痛/缓解疼痛等疼痛功效承诺（含 sans douleur/schmerzfrei/sin dolor），只保留 comfort/gentle 与缓解胀满不适 discomfort 的表述（另 4 组同码修订建议见证据单元）

## 禁用表达汇总

perfect pump

## 适用范围与证据

- 覆盖记录数：12
- 证据单元数：36（support_count 取新库值 36）
- 证据级（新库取值）：L1
- 验证状态（新库取值）：已归纳 · 规则状态：provisional
- 形态：entry　|　库：措辞表达库（wording）
- P0 匹配器：`p-08487282e2d400fe`（authority=expert，match_note=BLOCK）

## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）

- `6778ea95201740e84dab`　#广告文案明细/recvuJYdOb1B8v/命中片段　→ H05:perfect pump
- `013407bfc66962d3c7a5`　#广告文案明细/recvuJYdOb1B8v/修改建议　→ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）
- `0d2031cb39d411b8ce19`　#广告文案明细/recvuJYdOb1B8v/命中原因　→ H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）
- `b73695e179b65f539484`　#广告文案明细/recvuJYdObCYOh/命中片段　→ H02:improve pumping efficiency / H05:perfect pump / M07:improve milk flow,improve pumping efficiency
- `96f2e6667a2ce7cc44fb`　#广告文案明细/recvuJYdObCYOh/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `8ad0d26e52f4f30fe45c`　#广告文案明细/recvuJYdObCYOh/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09…
- `799d2156d1dac83ba79b`　#广告文案明细/recvuJYdObCu5l/命中片段　→ H02:improve pumping efficiency / H05:perfect pump / M07:improve milk flow,improve pumping efficiency
- `2db4170ee36dfdd000eb`　#广告文案明细/recvuJYdObCu5l/修改建议　→ 删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；fa…
- `1dfe5b28951368980c74`　#广告文案明细/recvuJYdObCu5l/命中原因　→ H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫；H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09…
- `ddc8b8b615d199fee027`　#广告文案明细/recvuJYdObE80Z/命中片段　→ H05:perfect pump
- `784b39bfc2ccdc57aa2f`　#广告文案明细/recvuJYdObE80Z/修改建议　→ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）
- `a474b925e84d72226774`　#广告文案明细/recvuJYdObE80Z/命中原因　→ H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）
- `9f37bfde3a67139feecb`　#广告文案明细/recvuJYdObFeLc/命中片段　→ H05:perfect pump / U03:hospital
- `22f0f7639e474d4f483a`　#广告文案明细/recvuJYdObFeLc/修改建议　→ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开） ▸ hospital/NICU 场景表述需事实…
- `f6bd9821c740f24d09a1`　#广告文案明细/recvuJYdObFeLc/命中原因　→ H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）；U03 涉及医院/NICU 场景，需核实临床适用性声明
- `554739313ff065877de1`　#广告文案明细/recvuJYdObGB9q/命中片段　→ H05:perfect pump
- `72dfdb599c759f2a0680`　#广告文案明细/recvuJYdObGB9q/修改建议　→ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）
- `d83f86f5e0711951168e`　#广告文案明细/recvuJYdObGB9q/命中原因　→ H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）
- `a197a27b044e10ccf923`　#广告文案明细/recvuJYdObGM2P/命中片段　→ H05:perfect pump
- `da51cace6dac60fd2e4c`　#广告文案明细/recvuJYdObGM2P/修改建议　→ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）
- `1326c2ce7ee828300995`　#广告文案明细/recvuJYdObGM2P/命中原因　→ H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）
- `8943d27265ed005ce726`　#广告文案明细/recvuJYdObJwyY/命中片段　→ H05:perfect pump / H07:pain-free
- `f2b7e9a1bf41de84a9d9`　#广告文案明细/recvuJYdObJwyY/修改建议　→ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开） ▸ 删除 pain-free/no pain/…
- `57e446bcb15cd7f592a7`　#广告文案明细/recvuJYdObJwyY/命中原因　→ H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）；H07 疼痛功效承诺（pain-free/no pain/without pain/pain relief/less pain/缓解疼痛等；吸奶疼痛因人而异，只可讲 comfort/ge…
- `7ebdb69835908336054f`　#广告文案明细/recvuJYdObKvVy/命中片段　→ H05:perfect pump
- `cfbd1de0a3d12efb97f7`　#广告文案明细/recvuJYdObKvVy/修改建议　→ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）
- `0a3112cb85a0d190e5cc`　#广告文案明细/recvuJYdObKvVy/命中原因　→ H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）
- `6e92be2b84522e3f9160`　#广告文案明细/recvuJYdObNa32/命中片段　→ H05:perfect pump
- `de793128c20c2232fc9f`　#广告文案明细/recvuJYdObNa32/修改建议　→ 删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺（best/#1/No.1 排名最高级已放开）
- `b399e8a207cb44bc60af`　#广告文案明细/recvuJYdObNa32/命中原因　→ H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险）
- …另有 6 条，见新库 rules.jsonl 的 evidence_units

---

> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。
