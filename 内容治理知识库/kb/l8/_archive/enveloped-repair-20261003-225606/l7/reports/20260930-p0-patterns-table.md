# P0 模式表（L5 判定层 · 可读导出）

> 本表由 `kb/l5/p0_patterns.jsonl`（运行时权威表）逐行导出，人读版。
> **权威源是 jsonl；两者不一致时以 jsonl 为准。**

| 项 | 值 |
|---|---|
| 库 | Momcozy知识库 · 内容治理 |
| 层 | L5（P0 判定层） |
| 权威表 | `kb/l5/p0_patterns.jsonl` |
| 条数 | 7 |
| sha256 | `470e3fbad21489b9ad3cae7bd5fd5d4273b19262acb297c5b91808b51c570ea8` |
| 选取口径 | p_level=P0 ∧ rule_kind=atomic ∧ authority∈['expert', 'legal']（+ code_allowlist=['H06']） |
| exporter_version | `l5-0.1` |
| kb_version | `v0` |

## 模式清单

| # | pattern_id | 规则码 | authority | match_note | 词条 | 正则 | 证据单元 | 规则 |
|---|---|---|---|---|---|---|---|---|
| 1 | `p-755f9ff377c3052c` | H02 | expert | **BLOCK** | 24 | 3 | 102 | 规则码 H02：命中「augmente la production de lait；boost supply,more milk,trigg… |
| 2 | `p-521d9d1502ee0bfa` | H04 | expert | **BLOCK** | 13 | 2 | 6 | 规则码 H04：命中「ibclc-recommended,recommended by 100+ experts；ob-gyn recomm… |
| 3 | `p-08487282e2d400fe` | H05 | expert | **BLOCK** | 13 | 4 | 36 | 规则码 H05：命中「perfect pump」判定为违规；处理：「perfect pump」→ 删除/替换为：删除 safest/100%… |
| 4 | `p-485c67cc9af960bf` | H06 | inferred | **BLOCK** | 5 | 3 | 4 | 边界：FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified）；触发词：FDA appr… |
| 5 | `p-964b3c2e22b48ade` | H07 | expert | **BLOCK** | 17 | 3 | 153 | 规则码 H07：命中「indolore；indolore,sans douleur；no pain,painless；pain-free；p… |
| 6 | `p-d31dfbc932cb84ac` | H09 | expert | **BLOCK** | 8 | 2 | 9 | 规则码 H09：命中「mimics baby；mimics baby,mimics baby’s natural nursing」判定为违规… |
| 7 | `p-4d1fe41caef6e3b1` | U04 | expert | **BLOCK** | 4 | 2 | 6 | 规则码 U04：命中「painful pumping」判定为违规；处理：删除 pain-free/no pain/without pain/… |

## 逐条明细

### 1. `p-755f9ff377c3052c`

- **规则码 / rule_id**：H02 ｜ `r-37b49eadb72d7dc2`
- **authority / p_level**：expert ｜ P0
- **match_note**：`BLOCK` ｜ **type**：`keyword`
- **anchor**：`#广告文案明细/recvuJYdOb1Rm1/命中片段`
- **source_sha256**：`c77f576dcc392cb3e763e6462d0259e50fb039f924a4af8e100321197e5be577`
- **匹配词条（24）**：`augmente la production de lait`、`boost supply`、`easier let-down`、`easier letdown`、`improve pumping efficiency`、`increase milk supply`、`increases milk production`、`increasing milk supply`、`mehr milch`、`more milk`、`más leche`、`plus de lait`、`producción de leche`、`support faster let-down` …
- **正则（3）**：`\b(more|increase[sd]?|boost[s]?|maximi[sz]e[sd]?)\s+(your\s+)?milk\b` ｜ `\blet[\s-]?down\b` ｜ `增\s*产|催\s*奶|催\s*乳|下\s*奶`
- **白名单豁免表达**：`relaxation`、`relax`、`natural let-down`、`放松`、`自然奶阵`
- **建议替换**：「easier letdown」→ 删除/替换为:删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺;合规替代为放松叙事+限定语,如 relaxation supports your natural let-down, which may help your flow(因为放松,自然奶阵可能更顺畅),只描述自然生理过程、不承诺产品带来结果;faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 静音表述改客观参数(as low as 48 dB),避免 whisper/silent/ultra-quiet 绝对化;「increase milk suppl…
- **证据单元（102）**：`9c313d585ee7d5290c08`、`521753286e8e238938e2`、`7ec15343f347bc92fcc9`、`ab48363a38d4bd7dabb7`、`70089914d416622d611a` …

### 2. `p-521d9d1502ee0bfa`

- **规则码 / rule_id**：H04 ｜ `r-3055901e5877f981`
- **authority / p_level**：expert ｜ P0
- **match_note**：`BLOCK` ｜ **type**：`keyword`
- **anchor**：`#广告文案明细/recvuJYdObV6eR/命中片段`
- **source_sha256**：`6059659ad3f649c3ac1ff6ca602fdcd0368094a9d9490fa5dca0319872677af0`
- **匹配词条（13）**：`ibclc-recommended`、`ob-gyn recommended`、`recommended by 100+ experts`、`doctor recommended`、`doctor-recommended`、`expert recommended`、`expert-recommended`、`expert-tuned`、`pediatrician recommended`、`专家推荐`、`专家认证推荐`、`专家调校`、`医生推荐`
- **正则（2）**：`\b(doctor|physician|pediatrician|expert|ibclc|ob[\s-]?gyn)[\s-]*(recommended|approved|endorsed|backed)\b` ｜ `医生\s*推荐|专家\s*推荐|专家\s*调校`
- **白名单豁免表达**：`free ibclc service`、`免费 ibclc 服务`
- **建议替换**：「ob-gyn recommended」→ 删除/替换为:删除医生/专家/IBCLC/OB-GYN 推荐背书;免费 IBCLC 服务可单独陈述但不得与“推荐”绑定 ▸ 效果百分比/销量/评分声称需附测试来源与口径,否则删除(折扣百分比不在此列) ▸ 核验 IBCLC/专家身份、参与方式、程序设计依据与 COI 披露后再保留(含 expert-tuned/专家调校/专家程序);「ibclc-recommended,recommended by 100+ experts」→ 删除/替换为:删除医生/专家/IBCLC/OB-GYN 推荐背书;免费 IBCLC 服务可单独陈述但不得与“推荐”绑定 ▸ …
- **证据单元（6）**：`640b623aca25775f9843`、`dcbe0ffa1f84d60a41fe`、`ad83f2317442eda2c56d`、`99520c3966e0dff95381`、`b46fc211f15f844dd6e2` …

### 3. `p-08487282e2d400fe`

- **规则码 / rule_id**：H05 ｜ `r-7baf7ceb47b2e5bc`
- **authority / p_level**：expert ｜ P0
- **match_note**：`BLOCK` ｜ **type**：`keyword`
- **anchor**：`#广告文案明细/recvuJYdOb1B8v/命中片段`
- **source_sha256**：`e7aabf7478753887ea85470fa114b4d0b22d74d21cb901b3a02e7672dff4f4c5`
- **匹配词条（13）**：`perfect pump`、`100% safe`、`100%safe`、`fits all breast shapes`、`one size fits all`、`risk-free`、`safest`、`zero risk`、`一定不损伤`、`完全安全`、`绝对安全`、`适合所有胸型`、`零风险`
- **正则（4）**：`\b(safest|perfect|zero[\s-]?risk|risk[\s-]?free)\b` ｜ `\b100\s*%\s*(safe|safety)\b` ｜ `one[\s-]size[\s-]fits[\s-]all` ｜ `适合\s*所有\s*胸型|完全\s*安全|零\s*风险|绝对\s*安全|一定\s*不\s*损伤`
- **白名单豁免表达**：`best`、`#1`、`no.1`、`no. 1`、`排名第一`、`第一`
- **建议替换**：「perfect pump」→ 删除/替换为:删除 safest/100% safe/zero risk/perfect 等虚假安全承诺,以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺(best/#1/No.1 排名最高级已放开);「perfect pump」→ 删除/替换为:删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺;合规替代为放松叙事+限定语,如 relaxation supports your natural let-down, which may help your flow(因…
- **证据单元（36）**：`6778ea95201740e84dab`、`013407bfc66962d3c7a5`、`0d2031cb39d411b8ce19`、`b73695e179b65f539484`、`96f2e6667a2ce7cc44fb` …

### 4. `p-485c67cc9af960bf`

- **规则码 / rule_id**：H06 ｜ `r-15a607c4457c8b55`
- **authority / p_level**：inferred ｜ P0
- **match_note**：`BLOCK` ｜ **type**：`keyword`
- **anchor**：`#品线内容边界规则库/recvuJP1LVW6E0/边界内容`
- **source_sha256**：`2e8bb36d6edf7c4971132b69ff6d39819a5a0e0e8043e9001e096be1bc2a02d6`
- **匹配词条（5）**：`FDA approved`、`FDA certified`、`FDA 批准`、`FDA 认证`、`FDA 通过`
- **正则（3）**：`\bFDA\s+(approved|certified)\b` ｜ `\bFDA[\s-]*(approved|certified)\b` ｜ `FDA\s*(认证|批准|通过)`
- **白名单豁免表达**：`FDA cleared`、`FDA-cleared`、`FDA registered`、`FDA 注册`
- **证据单元（4）**：`a4424c8206b8e8a6bcc8`、`3cb8d721d7d71f434e42`、`af2b9b5f556eb911640e`、`85d8ac10e115ac92800c`

### 5. `p-964b3c2e22b48ade`

- **规则码 / rule_id**：H07 ｜ `r-d7290a0ee59c58ef`
- **authority / p_level**：expert ｜ P0
- **match_note**：`BLOCK` ｜ **type**：`keyword`
- **anchor**：`#广告文案明细/recvuJYdOb1u94/命中片段`
- **source_sha256**：`1e3bd4c1ca097ee1b7f0011014ff91c1012b258c1e691525e0df454790b4c011`
- **匹配词条（17）**：`indolore`、`no pain`、`pain-free`、`painlessly`、`sans douleur`、`say goodbye to cold, painful`、`schmerzfrei`、`sin dolor`、`zero pain`、`free of pain`、`pain relief`、`relieve pain`、`without pain`、`不痛` …
- **正则（3）**：`(no|without|free\s+of|zero)\s+(more\s+)?pain\b` ｜ `\bpain[\s-]*(free|less)\b` ｜ `无\s*痛|缓解\s*疼痛|不\s*会\s*痛`
- **白名单豁免表达**：`comfort`、`gentle`、`discomfort`、`缓解胀满不适`、`舒适`、`温和`
- **建议替换**：「schmerzfrei」→ 删除/替换为:效果百分比/销量/评分声称需附测试来源与口径,否则删除(折扣百分比不在此列) ▸ 删除 pain-free/no pain/without pain/pain relief/less pain/无痛/缓解疼痛等疼痛功效承诺(含 sans douleur/schmerzfrei/sin dolor),只保留 comfort/gentle 与缓解胀满不适 discomfort 的表述;「sans douleur」→ 删除/替换为:删除 pain-free/no pain/without pain/pain relief/less pain/无痛/缓解疼痛…
- **证据单元（153）**：`4c8dbd916a46eb348a5c`、`ae2fa01a0a9b318ade35`、`406eee8b9c28b1bded00`、`215941b02763d9850df6`、`367a39e272206d930157` …

### 6. `p-d31dfbc932cb84ac`

- **规则码 / rule_id**：H09 ｜ `r-006445396c95aa10`
- **authority / p_level**：expert ｜ P0
- **match_note**：`BLOCK` ｜ **type**：`keyword`
- **anchor**：`#广告文案明细/recvuJYdOb61lT/命中片段`
- **source_sha256**：`67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e`
- **匹配词条（8）**：`mimics baby’s natural nursing`、`baby-like suckling`、`imitates baby`、`mimic baby`、`mimics a baby`、`模仿婴儿`、`模拟婴儿吸吮`、`还原婴儿吮吸`
- **正则（2）**：`\bmimic(s|king)?\b[^.]{0,30}\bbaby\b` ｜ `模仿\s*婴儿|模拟\s*婴儿|还原\s*婴儿`
- **建议替换**：「mimics baby,mimics baby’s natural nursing」→ 删除/替换为:删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺;合规替代为放松叙事+限定语,如 relaxation supports your natural let-down, which may help your flow(因为放松,自然奶阵可能更顺畅),只描述自然生理过程、不承诺产品带来结果;faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 删除 pain-free/no pain/without pain/pain relief/less pai…
- **证据单元（9）**：`74d1ba6b94a5336853dd`、`0d3289c8b0363292fff1`、`cb3ae64719ed621f4e63`、`5f9f482b4bade3657b3b`、`0c2cc17745aa61d72ba5` …

### 7. `p-4d1fe41caef6e3b1`

- **规则码 / rule_id**：U04 ｜ `r-e879231d61c9bd08`
- **authority / p_level**：expert ｜ P0
- **match_note**：`BLOCK` ｜ **type**：`keyword`
- **anchor**：`#广告文案明细/recvuMGgT9p2zx/命中片段`
- **source_sha256**：`b5de79a05b4fe03cdd256ebc39f9d58183ebfc0e7cdbc7c1fba4770dfd4ef88b`
- **匹配词条（4）**：`painful pumping`、`clogged ducts`、`sore breasts`、`sore nipples`
- **正则（2）**：`\b(goodbye|no more|not anymore|relieve[sd]?)\b[^.]{0,40}\b(sore|painful|clogged)\b` ｜ `(告别|不再|摆脱)[^。]{0,20}(疼痛|堵奶|胀痛)`
- **建议替换**：删除 pain-free/no pain/without pain/pain relief/less pain/无痛/缓解疼痛等疼痛功效承诺(含 sans douleur/schmerzfrei/sin dolor),只保留 comfort/gentle 与缓解胀满不适 discomfort 的表述 ▸ 人工判定 sore/painful/clogged ducts 是痛点场景描述还是功效承诺;若与 goodbye/no more/not anymore/relieve 连用暗示消除疼痛或堵奶,升级为红并改写为 comfort/discomfort 表述
- **证据单元（6）**：`7e311fb13db463edc98b`、`48b59e6989011473ad0f`、`ccdb44ea5d38076e07b6`、`58db70ede9f718f8c8b7`、`dece606b4045e058b531` …

## 排除项（同一次导出）

| 排除原因 | 条数 |
|---|---|
| non_P0 | 488 |
| P0_but_authority_insufficient | 8 |
| P0_admitted_by_allowlist | 1 |
| P0_but_inductive | 6 |

> 「未命中」= 不是最高优先级，**不等于**内容合规；其余风险仍走 `kb-review`。
