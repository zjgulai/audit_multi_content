### brand-ai-provenance-rights-review
"Review AI-generation disclosure, deepfakes, child and person privacy, likeness, trademarks, third-party assets, and creator authorization evidence for brand content."

### brand-content-review-agent
Orchestrate local pre-publication review of US-market brand text, image, and video assets for breast pumps, baby monitors, bottle washers, and feeding products. Use when a submission needs versioned PASS, REVIEW, BLOCK, or NEEDS_INPUT decisions, evidence, and human routing.
  【中文入口 · 一批素材的发布前审查全流程】当用户要**一批**素材（文字 + 图片 + 视频混在一起）
  走**发布前审查全流程**、并要一个**统一结论**时使用：
  「送审 / 送审一批素材 / 走一遍发布前审查 / 审查全流程 / 这批素材一起审 /
   给个统一结论 / 这批素材最后到底能不能上 / 文字图片视频一起过一遍发布前审查 /
   统一出个结论并告诉该找谁 / 串起来从收素材到出结论」。
  触发词：送审、送审一批、发布前审查、发布前审查全流程、审查全流程、这批素材一起审、
  统一结论、一起过一遍、pre-publication review、submission review、
  brand-content-review-agent。
  不适用（**已能识别专项就别抢活**，交给对应成员）：
    · 单条文字 / 广告用语 / listing、PDP 文案 → brand-text-compliance-review；
    · 单张图片 / 主图 / 图上文字 → brand-image-safety-review；
    · 单条视频 / 短视频 / 画面时间码 → brand-video-safety-review（视频安全审查）；
    · 产品宣称真伪 / SKU 事实 / 认证范围 → brand-product-claim-verifier；
    · AI 生成披露 / 肖像商标授权 / 儿童出镜隐私 → brand-ai-provenance-rights-review；
    · 美国本地化 / 计量单位 / 文化歧义 → brand-us-locale-cultural-review；
    · 只要某条判定或某条结论的**依据** → kb-content-review；
    · 专项归属不明 / 单条内容该不该拦，且用户没要全流程 → kb-review；
    · 只要送审登记（哈希 / SKU / 渠道采集）→ brand-review-intake-router；
    · 只要最终裁决、不要全流程 → brand-review-decision-engine；
    · 只要报告 / 群发摘要 / 存档 → brand-review-report-memory；
    · 结果同步到飞书群与多维表格 → brand-feishu-review-adapter；
    · 评测审查流程本身的准确率 / 漏放 → brand-review-evaluation。

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
用 Momcozy 内容治理知识库（L0–L6）为**已经给出的判定**产出可核对的**依据**：
  库名 + 版本 + 条款号 + 锚点 + source_sha256 + 逐字摘录。
  【本 skill 是评审链的**链内组件**，不是入口】它只回答"依据是什么"，
  不承接"这段内容该怎么判"。
  当用户已经拿到一条结论、再追问它的来历时使用：
  「为什么判 BLOCK / 依据是哪条规则 / 条款号 / 知识库怎么说 / 三态结论的依据 /
  审查依据 / 逐字摘录 / 锚点在哪 / source_sha256 是多少 / 这条判定的出处在哪 /
  引用契约怎么写的」。
  触发词：为什么判 BLOCK、依据是哪条规则、条款号、知识库怎么说、三态结论的依据、
  审查依据、逐字摘录、锚点在哪、source_sha256、判定出处、引用契约、kb-content-review。
  【不适用，逐个点名去向】
    · 用户刚开始送来待判内容、问它该不该拦 → 走 **kb-review**（评审链入口）；
      一批素材的发布前全流程 → **brand-content-review-agent**；
    · 13 个专项成员（文字 / 图片 / 视频 / 产品宣称 / AI 溯源 / 美国本地化 / 送审登记 /
      汇总裁决 / 报告 / 评测 / 证据源 / 飞书同步）→ 由 **kb-review** 的让位表分派，本 skill 不接；
    · 单独查某条规则的条款号 / 定稿了没有 → **kb-canonical-lookup**；
    · 是不是 P0 / 命中哪些 P0 模式 → **kb-p0-check**；
    · 召回单元 / 查资料 / 检索 → **kb-recall**；
    · 跑知识库链路 / 同步知识库 → **kb-pipeline**；只对账 L0 → **kb-l0-feishu**；
    · 知识库体检 / 跑闸门 → **kb-check**；闸门没过的修复 → **kb-repair**；
    · 这几个 skill 怎么分工 / 注册表 / 路由 → **kb-manage**。
  也不适用：问知识库本身怎么建的（L0–L6、锚点、索引、规则来源等设计讨论）、
  工程操作类问题（文件在哪、索引怎么重建、跑哪个脚本）、没有判定意图的通用写作 / 翻译 / 润色、
  纯业务闲聊（育儿话题讨论、产品咨询）。

### kb-l0-feishu
把 Momcozy 内容治理知识库的 **L0（源层）** 与飞书侧源数据做每日同步与核对，飞书侧全程只读。
  **本 skill 只做 L0 这一层**，不往下游 L1–L7 跑（要整条链路走 kb-pipeline）。
  当用户说「只对账 L0 / L0 同步 / L0 对齐一下 / L0 落库 / L0 和飞书对一下 / L0 对账 /
  飞书侧对账 / 飞书侧改了什么 / 库和飞书一致吗 / 飞书侧数据变了吗 / 跑一下每日同步 /
  只跑每日同步这一层 / 源数据同步 / 核对一遍 L0」时使用。
  当用户报「飞书侧改了什么」「库里这条怎么不见了」「图片/视频/链接有没有漏」，也使用。
  触发词：只对账 L0、L0同步、L0 对齐、L0 落库、L0 对账、飞书侧对账、飞书侧改了什么、
  源数据同步、库和飞书一致、每日同步、只跑每日同步、daily sync、reconcile L0、sync L0、
  kb-l0-feishu。
  不适用（各自点名）：
    · 整条链路 / 同步一下知识库 / 跑一遍知识库链路 / 知识库同步到最新 / 全链体检 /
      L0 到 L7 走一遍 / 知识库该更新了 → 走 **kb-pipeline**（本 skill 不跑下游 L1–L7）；
    · 判断内容该不该拦 / 单条内容可用性 → 走 **kb-review**；
    · 问知识库怎么建的、字段与分层定义 → 读 `_meta/GUIDE.md`；
    · 只查条款号 / 是不是 P0 / 召回 → 走 kb-canonical-lookup / kb-p0-check / kb-recall；
    · 知识库体检 / 闸门 → 走 **kb-check**；闸门没过的修复 → 走 **kb-repair**；
    · 没有飞书侧源、纯本地文件的场景 → 不触发本 skill。

### kb-manage
Momcozy 内容治理知识库的**工作流家族管理器**：管注册表、管路由、管生命周期。
  它不干具体的知识库活，只回答「这件事该走哪个成员」和「这个成员现在是什么状态」。
  当用户问「知识库里这几个 skill 怎么分工 / 哪个 skill 负责什么 / 这个说法该走哪个 skill /
  知识库 skill 家族全景 / 成员列表 / skill 注册表 / 路由表 / 家族登记 / 谁负责这条链路 /
  新增一个知识库 skill 要登记到哪 / 停用 / 下线某个成员 / 成员的生命周期与版本」时使用。
  触发词：kb-manage、知识库工作流家族、skill 家族管理、注册表、路由表、家族全景、成员列表、
  家族路由、skill 生命周期、成员启停、登记成员、谁负责、该走哪个 skill、知识库 skill 分工、
  kb family、registry、routing。
  两条链的入口**不在本 skill**：供给链（L0→L7 数据）走 kb-pipeline，评审链（内容能不能用）走 kb-review。
  不适用：创建一个新 skill（走 root-skills-creator）；评测 / 优化 / 诊断 skill 本身
  （走 root-skills-eval / root-skills-opt / root-skills-doctor）；跑知识库链路（走 kb-pipeline）；
  判断一段内容能不能发（走 kb-review）。

### kb-pipeline
Momcozy 内容治理知识库的**供给链入口**：按 `kb/l7/registry/layers.yaml` 把 L0 → L7
  整条链路编排跑一遍（对齐源层 → 抽取 → 切分 → 蒸馏 → 发号 → P0 → 索引 → 报告），
  并在每层过闸门、按幂等键决定跳过还是重跑。
  当用户说「同步一下知识库 / 跑一遍知识库链路 / 知识库同步到最新 / 全链体检 /
  L0 到 L7 走一遍 / 知识库该更新了 / 把知识库更新到最新 / 整条链路走一遍 /
  全链路重建 / pipeline 跑一下」时使用。
  触发词：同步知识库、知识库同步、跑一遍知识库链路、知识库同步到最新、全链体检、
  L0 到 L7、整条链路、全链路重建、知识库该更新了、跑 pipeline、kb-pipeline。
  不适用（三条边界，各自点名）：
    · 只对账 L0、只看飞书侧改了什么、只跑每日同步 → 走 **kb-l0-feishu**（不跑下游）；
    · 单条内容能不能发 / 审一下 / 合规检查 → 走 **kb-review**（评审链，不是供给链）；
    · 查条款号 → 走 **kb-canonical-lookup**；是不是 P0 → 走 **kb-p0-check**；
      召回单元 / 查资料 → 走 **kb-recall**（这三个是只读查询，不重建索引）；
    · 只体检不跑链路 → 走 **kb-check**；闸门没过要修 → 走 **kb-repair**。

### kb-review
Momcozy 内容治理知识库的**评审链入口**：收到一段待判内容，走评审链给三态结论
  （PASS / REVIEW / BLOCK），并把结论分派给对应的专项成员。
  【先让位】只要能看出**专项归属**，就直接走对应专项，本 skill 不接：
    文字 / 广告用语 / listing、PDP 文案 → brand-text-compliance-review；
    图片 / 主图 / 图上文字 / 婴幼儿画面 → brand-image-safety-review；
    视频 / 短视频 / 画面 / 时间码 / 口播 → brand-video-safety-review（视频安全审查）；
    产品宣称真伪 / SKU 事实 / 认证范围 → brand-product-claim-verifier；
    AI 生成披露 / 肖像商标授权 / 儿童出镜隐私 → brand-ai-provenance-rights-review；
    美国本地化 / 计量单位 / 文化歧义 → brand-us-locale-cultural-review；
    一批素材走发布前审查全流程 → brand-content-review-agent。
  本 skill 承接的是**专项归属不明 / 跨模态 / 只问"整体能不能用"**的那一类：
  当用户说「这段内容能不能发 / 审一下 / 帮我审审 / 合规检查 / 合规审查 / 内容审核 /
  会不会违规 / 能过审吗 / 有没有风险 / 踩线 / 禁用 / 敏感 / 这段能不能用 /
  帮我判一下这条内容 / 该不该拦」而不指明是哪一类专项时使用。
  触发词：内容评审入口、能不能发、审一下、帮我审、合规检查、合规审查、内容审核、
  会不会违规、能过审吗、有没有风险、踩线、禁用、敏感、这段能不能用、kb-review。
  不适用：
    · 跑知识库供给链 / 同步知识库 / L0 到 L7 → 走 **kb-pipeline**；
    · 只对账 L0 / 飞书侧改了什么 → 走 **kb-l0-feishu**；
    · 已给出结论、只追问依据 / 条款号 / 逐字摘录 → 走 **kb-content-review**；
    · 单独查某条规则的条款号 → **kb-canonical-lookup**；是不是 P0 → **kb-p0-check**；
      召回单元 / 查资料 → **kb-recall**；
    · 知识库体检 / 闸门 → **kb-check**；闸门没过的修复 → **kb-repair**；
    · 问这几个 skill 怎么分工 / 注册表 / 路由 → **kb-manage**。

### kb-check
Momcozy 内容治理知识库的**统一闸门**：把全库各层的 check 一次跑完并汇总成一张体检表——
  登记表自检（应装未装 / 装了没登记 / 副本不一致 / 依赖缺失 / 自测缺失）、层契约自检、
  链路收口核验、信封闸门、投影一致性、路由表对账。
  当用户说「知识库体检 / 检查一下知识库 / 知识库有没有问题 / 跑一遍所有闸门 /
  闸门过没过 / 全库自检 / 知识库健康检查 / 各层 check 跑一下 / 信封闸门过一遍 /
  登记表对不对 / skills_check 跑一下 / workflow_check 跑一下」时使用。
  触发词：知识库体检、全库自检、统一闸门、跑一遍所有闸门、闸门过没过、知识库健康检查、
  信封闸门、登记表自检、层契约自检、路由对账、skills_check、layers_check、workflow_check、
  envelope gate、kb-check。
  不适用（各自点名）：
    · 闸门没过、要**修** → 走 **kb-repair**（本 skill 只报不改，默认全只读）；
    · 要跑 L0→L7 供给链本身 → 走 **kb-pipeline**；
    · 只对账 L0 / 飞书侧 → 走 **kb-l0-feishu**；
    · 判断一段内容能不能发 → 走 **kb-review**；
    · 评测 / 优化某个 skill 的质量 → 走 root-skills-eval / root-skills-opt（质量评测不属本家族）。

### kb-repair
Momcozy 内容治理知识库的**修复入口**：闸门红了之后，按原因码定位并修，
  修完重跑同一条闸门证明修好了。
  当用户说「闸门没过帮我修 / 知识库哪里坏了修一下 / 修一下知识库 / 不过就修 /
  把这些失败项修掉 / 副本不一致帮我同步 / 登记表补登记 / 依赖缺失补上 /
  自测缺失补上 / 把信封态修掉 / 路由表和实际对不上帮我改」时使用。
  触发词：不过就修、修知识库、闸门没过、修复失败项、按原因码修、副本同步、
  补登记、补依赖、补自测、修信封、路由对不上、kb-repair。
  不适用（各自点名）：
    · 只体检不修 → 走 **kb-check**（本 skill 必须以一条已红闸门为输入）；
    · 跑 L0→L7 供给链本身 → 走 **kb-pipeline**；
    · 判断一段内容能不能发 → 走 **kb-review**；
    · 造 skill / agent、改 skill 质量 → 走 root-skills-creator / root-skills-opt；
    · 新增或停用家族成员 → 走 **kb-manage**（生命周期动作不在这里）。

### kb-canonical-lookup
Momcozy 内容治理知识库 **L4（定稿与发布层）** 的**只读查询**入口：
  查一条规则的**条款号**、查一个条款号对应哪条规则、查这条规则**定稿了没有**
  （canonical 状态 / 是否已发号 / 是否 stable）。
  当用户问「这条规则的条款号是多少 / 这个条款号对应哪条规则 / 这条规则定稿了吗 /
  进 canonical 了吗 / 发号了吗 / 条款号怎么分配的 / 这条还是草案吗 /
  L4 里有没有这条 / canonical 里有多少条」时使用。
  触发词：条款号是多少、条款号对应哪条规则、article_no、规则定稿了吗、进 canonical 了吗、
  发号了吗、canonical 状态、L4 查询、定稿与发布、kb-canonical-lookup。
  本 skill **只读**：不写库、不发号、不晋升。发号 / 晋升 canonical 是写操作，
  由 **kb-pipeline** 在 `--apply` 下编排 `kb/.work/l4_article.py` 执行。
  不适用（各自点名）：
    · 已经给出三态结论、要追问**结论的依据** → 走 **kb-content-review**；
    · 判断一段内容能不能发 → 走 **kb-review**；
    · 这个是不是 P0 → 走 **kb-p0-check**；召回单元 / 查资料 → 走 **kb-recall**；
    · 跑 L0 到 L7 / 同步知识库 → 走 **kb-pipeline**；
    · 知识库体检 / 闸门 → 走 **kb-check**。

### kb-p0-check
Momcozy 内容治理知识库 **L5（P0 判定层）** 的**只读查询**入口：
  回答「**这个是 P0 吗**」「这段命中哪些 P0 模式」「这条为什么被判最高优先级」。
  当用户问「这个是 P0 吗 / 算不算 P0 / 命中哪些 P0 模式 / P0 模式有哪些 /
  这段文字命中 P0 了吗 / 优先级是不是 P0 / 为什么是 P0 / L5 里有没有这条 /
  P0 清单给我看一下 / 这条触碰红线了吗（红线口径 = P0）」时使用。
  触发词：是不是 P0、这个是 P0 吗、命中 P0、P0 模式、P0 清单、P0 判定、最高优先级、
  p0_patterns、L5 查询、kb-p0-check。
  本 skill **只读**：只做确定性匹配与清单查询，不写库、不改 P0 模式表。
  重建 / 导出 P0 层是写操作，由 **kb-pipeline** 在 `--apply` 下编排
  `kb/.work/l5_prep.py RUN` → `kb/.work/l5_export.py RUN` 执行。
  不适用（各自点名）：
    · 查条款号 / 定稿了没有 → 走 **kb-canonical-lookup**；
    · 召回相关单元 / 查资料 → 走 **kb-recall**；
    · 判断一段内容能不能发（要三态结论）→ 走 **kb-review**；
    · 已经给出结论、要追问依据 → 走 **kb-content-review**；
    · 跑 L0 到 L7 / 同步知识库 → 走 **kb-pipeline**；体检 / 闸门 → 走 **kb-check**。

### kb-recall
Momcozy 内容治理知识库 **L6（召回层）** 的**只读检索**入口，并已并入原 `kb-retriever`：
  按 **BM25 + 向量**双索引召回知识单元，也支持面向本地知识库目录的分层索引导航式检索
  （遇 PDF / Excel 必须先读 references 学处理方法再检索，避免整文件加载）。
  当用户说「召回一下 / 检索单元 / 按语义召回 / BM25 召回 / 向量召回 / 召回 top-k /
  知识库里有哪些相关单元 / 帮我查一下知识库 / 查资料 / 检索信息 /
  从知识库目录回答问题 / 知识库检索 / 分层索引导航 / 查一下有没有相关规则 /
  这句话在库里能找到什么」时使用。
  触发词：召回、检索、查资料、知识库检索、检索信息、语义召回、BM25、向量召回、top-k、
  相关知识单元、查一下库里、从知识库目录回答问题、分层索引导航、PDF 读取、Excel 读取、
  渐进式检索、L6 召回、kb-recall（原 kb-retriever 已并入本 skill）。
  本 skill **只读**：不改索引、不写库。重建 BM25 + 向量索引是写操作，
  由 **kb-pipeline** 在 `--apply` 下编排 `kb/.work/l6_build.py RUN` 执行。
  不适用（各自点名）：
    · 查条款号 / 定稿了没有 → 走 **kb-canonical-lookup**；
    · 这个是 P0 吗 / 命中哪些 P0 模式 → 走 **kb-p0-check**；
    · 判断一段内容能不能发（要三态结论）→ 走 **kb-review**；
    · 已经给出结论、要追问依据 / 逐字摘录 → 走 **kb-content-review**；
    · 跑 L0 到 L7 / 同步知识库 / 重建索引 → 走 **kb-pipeline**；
    · 知识库体检 / 闸门 → 走 **kb-check**；问 skill 怎么分工 → 走 **kb-manage**。
