# 品牌内容及素材审核 Agent：总体方案（v0.1）

> 来源：美国市场内容治理 PRD v1.2
> 状态：本地核心闭环 v0.1 已实现；范围、路由、裁决语义、输入方式、供应商无关契约、金标准集与 SLA 已确认；离线多模态结果导入和 Momcozy 官网源快照已接入，飞书接入、真实规则固化和具体供应商提取器仍待接入

## 1. 目标与边界

构建一个面向美国市场、吸奶器 / Baby Monitor / Bottle Washer / 喂养品线的发布前内容审核 Agent，覆盖文字、图片、视频、广告二创、达人内容、品牌 AI 素材、独立站、亚马逊和社媒。

第一阶段只做发布前完整内容，不做 brief、脚本、AI 文案等生产中间物，不做历史内容全面倒查，不评价审美和转化效果。输出 PASS / REVIEW / BLOCK，并保留版本、规则、知识库、证据和人工复核记录。

## 2. 当前目录能力盘点

| 现有技能 | 可复用能力 | 不能直接承担的部分 |
|---|---|---|
| `MinMax/skills/vision-analysis` | 图片描述、OCR、对象/人物/活动识别 | 没有母婴安全规则、证据定位和三态决策 |
| `MinMax/skills/minimax-multimodal-toolkit` | 视觉、视频/音频模型调用入口 | 偏生成/通用多模态调用，不提供审核规则和可审计证据 |
| `kimi/skills/compliance-review-planner` | 结构化合规清单、风险等级、整改建议 | 主要面向中国法规，不能直接作为美国规则库 |
| `kimi/skills/legal-risk-analyzer` | 严重性 × 可能性风险矩阵、升级建议 | 通用法律风险框架，不识别广告素材中的具体风险 |
| `kimi/skills/copy-editor` | 清晰度、证据、措辞、风险消除等文案检查 | 不应替代法律、医学或产品事实判断 |
| `kimi/skills/ecom-copy-assistant` | 亚马逊 listing 结构、平台字段和部分禁用表达 | 是生产技能，不是发布前事实/合规审核技能 |
| `kimi/skills/ad-copywriter` | Google/Meta/TikTok 等广告格式、字符限制 | 关注创作与投放规格，不负责风险裁决 |
| `kimi/skills/sop-writer` | SOP、流程图、RACI、异常处理和指标 | 需要绑定本 Agent 的输入/输出契约 |
| `kimi/skills/automation` + `blueprint` | 自动化触发、执行、结果和运行记录 | 是 Daimon Blueprint 运行规范，不是飞书连接器 |
| `kimi/skills/dataset-health-audit` | 批量记录的数据质量检查 | 不评估审核标注质量和模型误报/漏报 |
| `kimi/skills/deep-probe` | 逐题追问、按决策依赖达成共识 | 只负责讨论方法，不负责实际审核流水线 |
| `kimi/skills/locale-guard` | 软件本地化键审计 | 不是美国市场语言、文化和广告语境审查 |
| `kimi/skills/video-compare-tool` | 视频压缩质量和逐帧对比 | 不识别字幕、旁白、动作、安全情节或时序关系 |

## 3. 目标工作流

```text
提交入口（飞书 @Agent / 批量表格 / URL / 文件）
  ↓
素材接收与版本指纹（hash、来源、SKU、渠道、语言、发布版本）
  ↓
多模态标准化
  ├─ 文字：正文、图片文字、字幕、旁白、页面文本
  ├─ 图片：OCR、物体/人物/动作/场景、AI 合成线索
  └─ 视频：ASR、OCR、镜头切分、风险触发帧、前后情节、时间码
  ↓
规则与证据检索（按美国市场、渠道、产品线、有效期过滤）
  ↓
四层审核
  ├─ P0：确定性红线候选检测 + 上下文消歧
  ├─ P1：消费者安全与产品事实核验
  ├─ P2：通识、场景、人物/AI/文化语境
  └─ P3：措辞与表达建议（不改变主结论）
  ↓
证据完整性、模型一致性、版本一致性检查
  ↓
决策引擎：PASS / REVIEW / BLOCK + 置信区间 + 下一责任人
  ↓
飞书群简报 + 多维表记录 + 详细报告
  ↓
人工复核 / sign-off / 修改重提
  ↓
反馈回流、金标准集、规则和知识库版本迭代
```

## 4. 建议的技能组成

### 4.1 编排层

**`brand-content-review-agent`（总控技能）**

- 识别输入类型、产品线、渠道、语言和送审版本。
- 调用以下子技能并行或串行执行。
- 维护统一 JSON 契约、状态机、超时、重试、幂等和人工升级。
- 不在总控层直接写规则，规则放到版本化 references 中。

### 4.2 输入与证据层

**`brand-review-intake-router`（新建）**

- 接收文字、图片、视频、URL、批量表格。
- 计算内容 hash 和版本 ID，保存原始来源、SKU、渠道、语言、提交人。
- 发现素材缺失、链接失效、权限不足或版本信息不全时，输出 `NEEDS_INPUT`，不做 PASS。

**`brand-policy-source-curator`（新建）**

- 管理美国法规、监管指南、平台政策、内部规则和有效期。
- 每条依据包含 source_id、来源机构、原文 URL、条款/段落、适用范围、生效日、失效日、owner、审核状态。
- 只允许白名单来源进入 P0/P1；抓取内容必须带快照和版本，避免模型凭记忆引用。
- Momcozy 官网候选页由 `core/source_manifest.py` 转为 `knowledge-base/source-manifest.json`，HTML 与可读文本保存到 `snapshots/momcozy/`；抓取状态与审批状态分离，发现证据不会自动升级为已批准规则。

**`brand-product-claim-verifier`（新建）**

- 将文本、字幕、画面和口播中的产品声明抽取成 claim。
- 与 SKU/型号/地区/版本化产品事实库、测试报告、认证和批准措辞逐条比对。
- 区分“事实一致”“证据不足”“型号错配”“暗示性功效”，把证据缺失默认送 REVIEW。

### 4.3 模态审查层

**`brand-text-compliance-review`（新建）**

- 处理 caption、listing、PDP、独立站、社媒文案和图片 OCR 文本。
- 抽取明示和暗示 claim、医疗/功效/安全/销量/排名/比较/背书/免责声明。
- 使用 `copy-editor` 做 P3 表达检查，但不让文案建议改变 P0/P1 结论。

**`brand-image-safety-review`（新建）**

- 调用 `vision-analysis` 的 OCR、对象、人物、活动识别。
- 补充婴儿/儿童、车内、安全座椅、睡眠、喂养、洗护、用电、隐私、AI 合成和产品外观错配规则。
- 每个风险必须回指图像区域、OCR 文本或检测结果；无法定位的判断只能 REVIEW。

**`brand-video-safety-review`（新建）**

- FFmpeg/ASR/OCR/镜头切分/关键帧抽取/音画对齐。
- 先低成本扫描全片，再对风险词、动作和镜头切换附近自适应加密采样。
- 输出时间码、字幕/旁白原文、关键帧、前后情节和音画矛盾。
- 不能证明连续安全的场景不得自动 PASS；复杂情节转 REVIEW。

**`brand-us-locale-cultural-review`（新建）**

- 检查美国英语语义、单位、育儿常识、文化语境、达人表达、歧义、冒犯和本地化误导。
- 不评价“是否更像美国广告”，只识别可能改变消费者理解或引发风险的本地语境问题。

**`brand-ai-provenance-rights-review`（新建）**

- 检查 AI 生成/深度合成标识、虚拟人物、肖像/儿童隐私、授权、商标/第三方素材和证明文件。
- “无法验证授权”默认 REVIEW；明确未经授权或违反硬规则才 BLOCK。

### 4.4 决策与运营层

**`brand-review-decision-engine`（新建）**

- 合并各子技能风险项，按最高优先级和最高严重度裁决。
- 实施 PASS / REVIEW / BLOCK、问题数阈值、责任人路由和消息模板。
- 置信度不采用模型自报值；使用校准模型、规则确定性、证据完整性和多模态一致性计算。

**`brand-review-report-memory`（新建）**

- 生成 PRD 要求的结构化 JSON、短消息、详细报告、引用链接和版本留痕。
- 保存 agent_version、rule_version、knowledge_version、model、输入 hash、输出 hash、人工结论。
- 将人工复核结论转为候选规则、正负样本和争议样本，必须由 owner 审批后才进入生产规则。

**`brand-review-evaluation`（新建）**

- 维护金标准集、回归集、对抗集和跨模态一致性集。
- 计算三态准确率、BLOCK 精确率、PASS 误放率、REVIEW 召回率、P0 漏报率、人工负担和分层命中率。
- 可复用 `dataset-health-audit` 做记录数据质检，不能把数据质检分数当成模型准确率。

### 4.5 流转适配层

**`brand-feishu-review-adapter`（新建，平台适配器）**

- 处理飞书群 @Agent、飞书多维表、飞书云文档、@责任人、状态回写和报告链接。
- 与审核核心解耦；没有飞书 API/机器人权限时，支持 webhook 或结构化文件适配。
- 这是当前目录和推荐插件列表中的明确集成缺口，不能假设已有连接器。

## 5. 关键设计决策

### 5.1 P0 不做“裸关键词即 BLOCK”

保留 P0 快速扫描，但分成三步：命中候选 → 规范化/否定/引用/免责声明消歧 → 证据定位。只有明确表达且适用范围匹配的命中才自动 BLOCK；语境不确定、引用他人说法、比较语句或“禁止这样做”的反例进入 REVIEW。这样可以避免 P0 误伤，同时保留红线低延迟。

### 5.2 PASS 必须满足“覆盖完整”

只有在所有请求模态都成功抽取、产品/SKU/渠道已确认、P0-P2 无高风险项、证据引用完整、版本 hash 未变时才允许 PASS。任何权限失败、视频抽取不完整、来源过期或模型分歧都进入 REVIEW/NEEDS_INPUT。

### 5.3 置信度必须校准

将模型自报 confidence 视为原始信号，不直接分流。用历史金标准校准分数，并加入：规则是否确定、证据是否可定位、模态是否覆盖、模型是否一致、知识来源是否有效。P0 的确定性命中仍由规则裁决，不能被置信度覆盖。

### 5.4 视频采用“全片粗扫 + 风险附近加密”

固定每 5 秒取帧会漏掉短时危险动作。先做音频/字幕/镜头边界扫描，再对风险词、人物/儿童/车内/睡眠/喂养/用电场景附近提高帧率；每条问题保存开始时间、结束时间、代表帧和证据文本。

### 5.5 产品事实库是 PASS 的前置依赖

没有 SKU 级功能边界、型号差异、认证、测试报告和允许/禁止表达时，只能做通用风险预审，不能承诺“产品准确性”或自动 PASS。产品事实库需要 owner、版本、生效期和证据链接。

### 5.6 规则和知识库分离

规则决定如何判断，知识库决定依据是什么。法规/平台政策、产品事实、措辞库、正负样本分别版本化；每条风险只引用一个可追溯的 evidence_id，避免“模型生成链接”。

## 6. 统一数据契约

保留 PRD 的 JSON 主结构，新增以下字段：

- `input_manifest`: 文件/URL、mime、sha256、版本、语言、SKU、渠道、抓取时间、抽取状态。
- `coverage`: text/image/audio/video/ocr/asr/keyframes 的完成状态和缺口。
- `claim_items`: 明示/暗示 claim、claim 类型、证据需求、产品事实匹配结果。
- `evidence_refs`: source_id、快照版本、段落、适用地区、有效期。
- `decision_trace`: 每层规则、命中、消歧、模型、阈值和升级原因。
- `calibration`: 原始分数、校准分数、校准集版本。
- `version_gate`: reviewed_hash、release_hash、是否一致。
- `status`: `NEEDS_INPUT | PRECHECK | PASS | REVIEW | BLOCK | HUMAN_SIGNOFF | RELEASED`。

## 7. 分流规则

1. `NEEDS_INPUT`：缺素材、权限、SKU、版本或证据，不进入发布。
2. P0 确定性红线：BLOCK；P0 语境不确定：REVIEW。
3. P1 高风险且证据充分：BLOCK；证据不足/模型分歧：REVIEW。
4. P2 明确危险示范：BLOCK 或 REVIEW，按规则的可验证性决定；通识疑点默认 REVIEW。
5. P3 只生成建议，不改变主结论。
6. 多条命中按“最高优先级 → 最高严重度 → 版本门禁”汇总。
7. PASS 必须交 sign-off；BLOCK 修改后以新 hash 重新送审。

## 8. 第一阶段交付顺序

### W0：方案与权限冻结

- 确定飞书接入方式、角色、责任人、数据保留和素材权限。
- 冻结产品线、渠道、规则 owner、法务/医学/北美复核人。
- 建立最小金标准集和争议样本集。

### W1：文字审核 MVP

- Intake、P0-P3 文字规则、产品 claim 抽取、证据检索、JSON、短消息和报告。
- 先覆盖广告二创、吸奶器、独立站结构化文本。

### W2：图片审核

- OCR、场景/动作/人物、安全座椅/睡眠/喂养/用电/AI 线索。
- 建立区域级证据和人工复核界面/链接。

### W3：视频基础版

- ASR、OCR、镜头切分、风险附近关键帧、时间码报告。
- 复杂连续动作全部 REVIEW，先保证召回和可解释性。

### W4：批量与回流

- 多维表批量扫描、报告链接、状态回写、抽检、指标看板、规则/样本回流。
- 以金标准评估是否达到 PRD 的 90%/95%/5% 目标；未达到时调整阈值和范围，不直接扩大自动 PASS。

## 9. 验收门槛

- 所有结论绑定输入 hash、模型/规则/知识库版本。
- 每个风险都有位置、原文/画面证据、原因、依据、建议和 owner。
- 任何抽取失败或版本不一致都不能 PASS。
- P0 规则有逐条法务确认和回归测试；P0 漏报率目标为 0。
- BLOCK 精确率、PASS 误放率、REVIEW 召回率用人工金标准计算。
- 飞书消息、表格记录、报告和人工结论可通过 `review_id` 串联。

## 10. 当前缺口清单

1. 美国法规、监管指南和平台政策的权威来源库与更新机制。
2. SKU/型号级产品事实、测试、认证和允许/禁止 claim 库。
3. 适用于母婴场景的视觉/视频风险 taxonomy 和标注规范。
4. 视频 ASR/OCR/镜头切分/时间码/自适应采样组件。
5. AI 合成、肖像、儿童隐私、达人披露和素材授权规则。
6. 版本 hash、发布版本门禁和内容—审核绑定。
7. 置信度校准、金标准集、回归集和对抗集。
8. 飞书连接器、权限、@路由、云文档报告和多维表写回。
9. 审核日志、脱敏、保留期限、访问控制和审计。
10. 人工复核回流的审批流程，避免未经审核的样本直接改规则。

## 11. 待逐题确认顺序

按依赖关系依次确认：

1. 飞书接入方式和素材权限边界。
2. 第一阶段的真实产品 SKU/型号范围及产品事实库负责人。
3. P0 规则的法务确认机制和“关键词候选 vs 自动 BLOCK”边界。
4. 美国法规/平台政策来源白名单和更新频率。
5. 医学、安全、专家、北美复核人的路由与 SLA。
6. 允许自动 PASS 的内容类型与必须 REVIEW 的例外。
7. 视频长度、语言、音轨、字幕和可接受处理延迟。
8. 报告访问权限、数据保留和儿童/达人素材脱敏要求。
9. 金标准集规模、人工复核抽样比例和准确率验收口径。
10. 是否先实现飞书轻量版，还是先做本地可运行的核心审核包。

## 12. 本轮已落地的本地骨架

- `core/review_engine.py`：确定性三态决策、证据门槛、覆盖门禁、版本 hash 门禁和摘要渲染。
- `contracts/review-contract.json`：统一审核输入契约。
- `contracts/source-record.json`：规则与证据来源契约。
- `knowledge-base/product-fact-template.json`：SKU 级产品事实模板。
- `knowledge-base/rule-template.json`：P0-P3 规则模板。
- `samples/*.json`：PASS、REVIEW、BLOCK、NEEDS_INPUT 样例。
- `tests/test_review_engine.py`：5 个核心回归用例。
- `skills/`：13 个可发现的子技能入口，飞书 adapter 与审核核心解耦。

本地核心的置信度标记为 `heuristic_not_calibrated`，在金标准集完成前不得当作统计概率或自动放行依据。

## 13. 官网种子产品事实（待 owner 审批）

已从 Momcozy 官网和官方支持中心建立第一版种子条目：

- M5 Wearable Breast Pump：官网给出 SKU `BP078-GR00BA-A`，3 modes、9 suction levels、8 oz 等规格。
- BM03 Black：官网给出 5.5-inch Full HD、1080p、FHSS local connection、360° pan、140° tilt、4x zoom 等信息；当前 SKU 为内部临时键，待产品负责人确认。
- DeepClean Baby Bottle Washer D8：官方支持页给出 `BW05/D8`、8 bottles、96 oz water tank、560W/120V/60Hz、72-hour storage 等规格。

官网营销表达（如 painless、hospital-grade、99.99% germs、safe/private 等）已经单独标记为“需证据或 owner 审批”，不会直接进入自动 PASS 事实库。详见 `knowledge-base/seed-products.json`。当前已生成 33 条审批队列记录（18 条规格事实、15 条需证据/措辞审批的 claim），见 `knowledge-base/product-fact-approval-queue.json`；已确认的审批矩阵版本为 `product-fact-approval-2026-09-24`：规格事实由产品 owner 审批，客观/比较表达由产品+法务审批，健康/安全/功效表达由产品+法务+医学审批。队列使用角色占位并映射到显示名称，`product_fact_gate` 已接入文字、OCR、ASR 和文本化视觉观察入口，会把未审批事实分流为 REVIEW，把证据缺口分流为 NEEDS_INPUT。`core/product_fact_approval.py` 以幂等事件写回审批结果并重建活动事实库；活动事实库在 owner 审批前保持为空，见 `knowledge-base/product-fact-library.json`。

已基于上述事实建立 `knowledge-base/seed-rules.json`。其中健康/安全声明、达人背书、产品事实冲突、无证据客观主张和平台排名/绝对化主张均先按 REVIEW 或产品事实冲突 BLOCK 处理。美国市场不应直接套用“出现最/第一/最佳即 BLOCK”的中国广告法式规则；这类表达需要结合平台、时间窗口、方法和证据，由法务与渠道 owner 确认后再升级为硬规则。

该裁决语义已由用户确认，并已落成 `core/rule_engine.py` 与 `core/review_text.py`。规则扫描器只产生 `uncertain` 候选，产品事实核验或人工证据确认后才允许升级为 confirmed BLOCK。

角色级人工路由已确认并写入 `knowledge-base/routing-policy.json`，决策引擎会在没有指定个人时自动输出产品、法务、医学、北美和渠道角色。

第一阶段渠道已确认并写入 `knowledge-base/channel-scope.json`：TikTok 广告二创、Amazon Listing/主图/A+、Momcozy 独立站 PDP/落地页。每个渠道单独定义必需输入、渠道规则和默认复核角色。

输入方式已确认采用 URL + 本地文件 + 粘贴文本，并支持 JSON/CSV/TSV 批量入口。配置见 `knowledge-base/input-scope.json`，实现见 `core/intake_router.py`。URL 在真正抓取前保持 `url_pending_fetch`，不会伪造已读取或已完成的覆盖状态。

多模态执行方式已确认采用供应商无关接口。契约见 `knowledge-base/multimodal-provider-contract.json` 和 `contracts/offline-extraction-result.json`，实现见 `core/media_adapter.py` 与 `core/offline_review.py`。离线 JSON 结果可直接导入 OCR、ASR、关键帧和观察证据；任何结果必须回传素材 hash、provider/version、覆盖状态和定位证据；未完成提取时自动保留 `incomplete`，决策引擎不允许 PASS。

报告生成已本地化到 `core/report_memory.py`：输出可移植的 Markdown + JSON；`core/feishu_adapter.py` 已提供 Feishu 轻量映射和 JSON fallback，输出群消息、报告链接、角色占位 @、多维表 patch，并以 `review_id + content_version` 做幂等。真实 Feishu 凭证接入后只替换 transport。问题数量达到 3 时，短消息仍只返回分类汇总，完整问题清单保存在报告文件中。

验收指标已落到 `core/evaluator.py`，每个指标同时输出分母。金标准集需要由人工复核生成，不能用模型自评替代。

首轮金标准集已确认目标为 100 条（文字 40、图片 30、视频 30），采样、双人复核和争议裁决规则写入 `evaluation/gold-set-plan.json`，单条记录模板写入 `evaluation/gold-item-template.json`。

Momcozy 官网与官方支持页已整理为候选来源，见 `evaluation/source-candidates.json`；已通过 `core/source_manifest.py` 抓取 9 个 HTML 页面并保存哈希快照，见 `knowledge-base/source-manifest.json` 与 `snapshots/momcozy/`。这些来源仍标记为 `discovery_only`，不会自动赋予 PASS 或合规标签。

真实来源与内部对抗样本的 provenance 规则见 `evaluation/provenance-policy.json`，对抗样本构造模板见 `evaluation/adversarial-template.json`。每个对抗样本必须记录父样本和变换方式。

人工复核 SLA 已由用户确认并写入 `knowledge-base/sla-policy.json`；本地决策引擎已输出目标时限、升级角色、时区和计时规则，后续飞书适配器只需将这些字段映射到提醒与升级事件。
