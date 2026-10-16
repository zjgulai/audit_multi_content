### brand-ai-provenance-rights-review
"Review AI-generation disclosure, deepfakes, child and person privacy, likeness, trademarks, third-party assets, and creator authorization evidence for brand content."

### brand-content-review-agent
"Orchestrate local pre-publication review of US-market brand text, image, and video assets for breast pumps, baby monitors, bottle washers, and feeding products. Use when a submission needs versioned PASS, REVIEW, BLOCK, or NEEDS_INPUT decisions, evidence, and human routing."

### brand-feishu-review-adapter
"Adapt the local brand review contract to Feishu group mentions, files, multidimensional tables, cloud documents, status updates, and owner routing without coupling Feishu into the review core."

### brand-image-safety-review
"Review US-market brand images for OCR text, product and scene accuracy, infant and child safety, privacy, AI provenance, endorsement, and other locatable content risks."

### brand-policy-source-curator
"Maintain versioned, jurisdiction-aware evidence sources for US-market brand content review, including regulator guidance, platform policies, internal rules, product documents, effective dates, owners, and applicability."

### brand-product-claim-verifier
"Extract and verify product claims in US-market brand content against SKU-level product facts, approved wording, tests, certifications, and model/version scope."

### brand-review-decision-engine
"Aggregate multimodal brand review findings into calibrated PASS, REVIEW, BLOCK, or NEEDS_INPUT decisions with priority handling, version gates, evidence requirements, and owner routing."

### brand-review-evaluation
"Evaluate the local brand content review workflow against gold and regression sets, measuring three-state accuracy, BLOCK precision, PASS leakage, REVIEW recall, P0 misses, coverage, and human workload."

### brand-review-intake-router
"Normalize and validate pre-publication brand content submissions, including text, image, video, URLs, and batch rows, while capturing hashes, versions, SKU, channel, language, and permission status."

### brand-review-report-memory
"Generate the brand review JSON, concise Feishu-ready summaries, detailed evidence reports, version traceability, and approved human-feedback candidates for knowledge-base updates."

### brand-text-compliance-review
"Review US-market captions, listings, PDP copy, social copy, OCR text, subtitles, and voice transcripts for advertising, safety, product-claim, endorsement, and wording risks."

### brand-us-locale-cultural-review
"Review US English, units, parenting context, creator language, ambiguity, and cultural or local-market issues that could change consumer understanding or create brand risk."

### 视频安全审查
审查美国市场品牌视频，以转写、OCR、镜头、关键帧、音画对齐与时间码为证据，判定安全、产品、背书、AI 与平台风险。触发词：视频审查、视频安全、视频安全审查、达人视频、短视频、这条视频能不能发、视频能不能发、这条片子能不能上、视频能过审吗、能不能过审、视频审核、视频里有宝宝、视频里有危险动作、视频画面违规、口播转写审查、字幕审查、视频 AI 生成标识、video review、video safety review、short video review。何时不用：纯文字文案的合规问题（走 文案合规审查）、图片素材的静态风险（走 图片安全审查）、产品宣称真伪与 SKU 事实核对（走 产品宣称核验）、美国本地化与计量单位（走 美国本地化审查）、AI 生成披露与肖像商标授权（走 AI 溯源与权利审查）、只问一段内容能不能发而不涉及视频画面（走 kb-content-review）。

  Review US-market brand videos using transcript, OCR, shot, keyframe, audio-visual alignment, and timecode evidence for safety, product, endorsement, AI, and platform risks.

### kb-content-review
用 Momcozy 内容治理知识库（L0–L6）审查一段待审内容，按 PASS / REVIEW / BLOCK 三态给结论，
  并逐条给出可核对的依据（库名 + 版本 + 条款号 + 锚点 + source_sha256 + 逐字摘录）。
  当用户提交文案/脚本/字幕/详情页/广告创意/图片/视频并要求判断能不能用时使用；
  当出现"审查、审一下、合规检查、合规审查、内容审核、能不能发、会不会违规、能过审吗、有没有风险、踩线、禁用、敏感"
  或 "review / compliance check / is this compliant / will this pass / any risk" 等意图时使用；
  当用户追问某条结论的依据（"为什么判 BLOCK""依据是哪条规则"）时也使用。
  当专项归属不明确（问的是"用知识库能不能过""依据是什么"）时，作为保底入口承接。
  【专项审查请交给对应专项 skill —— 本 skill 只负责"用知识库依据给三态结论"，不做专项审查】
    · 文字 / 广告用语合规 → brand-text-compliance-review
    · 图片安全、婴幼儿安全场景 → brand-image-safety-review
    · 视频安全、画面与时间码 → brand-video-safety-review
    · AI 生成标识、肖像与商标授权、儿童出镜隐私 → brand-ai-provenance-rights-review
    · 产品宣称与 SKU 事实 / 认证范围比对 → brand-product-claim-verifier
    · 证据源（法规 / 平台政策）维护与登记 → brand-policy-source-curator
    · 多条发现汇总成最终裁决与责任人 → brand-review-decision-engine
    · 出审查报告 / 群发摘要 / 存档留痕 → brand-review-report-memory
    · 发布前全流程送审（文字 + 图片 + 视频一起走）→ brand-content-review-agent
    · 送审登记、哈希 / SKU / 渠道采集 → brand-review-intake-router
    · 美国本地化与计量单位 / 文化歧义 → brand-us-locale-cultural-review
    · 结果同步到飞书群与多维表格 → brand-feishu-review-adapter
    · 审查流程本身的准确率 / 漏放评测 → brand-review-evaluation
  也不适用：问知识库本身怎么建的（L0–L6、锚点、索引、规则来源等设计讨论）、工程操作类问题
  （文件在哪、索引怎么重建、跑哪个脚本）、没有审查意图的通用写作/翻译/润色、纯业务闲聊
  （育儿话题讨论、产品咨询）。这些不触发本 skill。

### kb-l0-feishu
把 Momcozy 内容治理知识库的 L0（源层）与飞书侧源数据做每日同步与核对，飞书侧全程只读。
  当用户说「L0 同步 / L0 对齐 / L0 和飞书对一下 / 库和飞书一致吗 / 飞书侧数据变了吗 /
  跑一下每日同步 / 知识库该同步了 / 对账一下 / 核对一遍」时使用；
  当用户报「飞书侧改了什么」「库里这条怎么不见了」「图片/视频/链接有没有漏」，也使用。
  触发词：L0同步、L0 对齐、L0 落库、L0 对账、飞书侧对账、源数据同步、库和飞书一致、
  每日同步、daily sync、reconcile L0、sync L0、kb-l0-feishu。
  不适用：判断一段内容能不能发（走 kb-content-review）；问知识库怎么建的、字段与分层定义
  （读 _meta/GUIDE.md）；只改 L1–L7 的下游优化；没有飞书侧源、纯本地文件的场景。

### kb-retriever
面向本地知识库目录的检索和问答助手。核心流程：(1)分层索引导航 (2)遇到PDF/Excel时必须先读取references学习处理方法 (3)处理文件后再检索。按文件类型组合使用 grep、Read、pdfplumber、pandas 进行渐进式检索，避免整文件加载。用户问题涉及"从知识库目录回答问题/检索信息/查资料"时使用。
