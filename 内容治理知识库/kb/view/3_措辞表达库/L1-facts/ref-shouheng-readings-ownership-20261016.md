---
asks:
  - 图片的 OCR 是谁做的（守衡侧还是知识库侧）
  - 知识库侧到底有没有 OCR、它给谁用、什么时候跑
  - 基础视觉识别（画面读数）是模型侧产出的吗
  - 评审链拿不拿得到图片本身，它拿到的到底是什么
  - 模型侧看不看得到原图
  - 为什么画面读数不进知识库那条链、这么做的代价是什么
  - PRD §5.1 有没有规定哪一侧做 OCR 与基础视觉识别
  - 要改这条分工，先看哪几个文件与命令
collection: 3_措辞表达库
corroborated_by:
  - PRD/feishu/内容审查Agent-PRD-v1.0.md#L165-173（§5.1 表格：图片＝OCR＋基础视觉识别；视频＝字幕/旁白＋关键帧＋OCR —— 只定输入/输出，未定实现归属）
  - 守衡实现侧两处独立读法：tools/agent/review_gate.mjs::chainInput（链的素材文本里 scene/画面读数命中 0）与 kb/l8/review_run.sh 用法行（只收 --text/--material-file，--content-type 是标签）
  - 知识库侧覆盖矩阵：kb/l8/daily_digest.py 的 CLASSES 类③图片附件＝store_l0_attachments.py/ocr_attachments.py/apply_ocr_to_l1.py、类④视频素材＝fetch_video_bytes.py/extract_video_keyframes.py/extract_video_asr.mjs
created_at: 2026-10-16
data_level: L2
evidence_group: coordinate
evidence_level: L2
forbidden: 不许据本条判断某条素材能不能发；不许把「知识库侧有 OCR」理解成「评审单上的 OCR 是知识库侧做的」（两套实现、两条路，只是同一台 Apple Vision 引擎）；不许据本条声称画面读数可以当逐字证据或可以进链当素材原文；不许据本条推断库内有画面类规则（本库画面类零覆盖）；不许把「知识库侧拿不到图」说成缺陷 —— 那是设计边界，改它要先解决溯源四段与污染面两条前提。
half_life_days: 90
id: ref-shouheng-readings-ownership-20261016
kb_class: []
kind: fact
not_proves: 不能证明任何一条具体内容能不能发 —— 它讲的是读数归谁产、谁看得到，不是审查结论；不能替代 3_措辞表达库 的任何条款（条款号/命中表达/锚点一律以权威库 kb/l3、kb/l4 为准）；不能证明「画面读数不可信」或反过来「画面读数可信」—— 本件只讲归属，不讲读数质量（质量与保真见 ref-shouheng-image-video-readings-20261016-r2）；不能证明这套分工是 PRD 要求的 —— PRD §5.1 只写「图片＝OCR＋基础视觉识别」这一对输入/输出，**没有规定哪一侧实现**，故本件描述的是 2026-10-16 这一台、这一版代码的实现口径；不能证明「画面读数永不进链」是永久决定 —— 那是一条可被新裁定推翻的现行设计边界；不能证明这条链在别的部署里也这样。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为读数归属与可见性的实现说明（模块名/命令/文件路径），不含姓名、联系方式等个人数据；文中「Owner」为角色指称、不指向可识别自然人；如后续来源变化需重新判定
provenance:
  anchor: PMO/守衡-读数归属与可见性-20261016.md#一/#二/#三/#四
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-16
  fingerprint: 0d46ef37ebf7c435
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-读数归属与可见性-20261016.md
summary: 谁产读数、谁看得到图（2026-10-16 实测）：评审单上的图内文字由守衡侧的 vision.mjs（本机 macOS Vision，二进制 .tools/bin/ocr）产出，画面读数（PRD §5.1 的「基础视觉识别」）由守衡侧的 scene.mjs（吃图模型）产出——两样都发生在守衡 daemon 的 readInboundContent 里、递单之前，与知识库侧无关。知识库侧确实另有一套 OCR（kb/l8/ocr_attachments.py → ocr.jxa.js，同一台 Apple Vision、另一套实现），但它服务的是库内素材入库（供给链类③图片附件/类④视频素材），不是群里这一单。可见性：评审链只吃文字那一半（review_run.sh 只收 --text/--material-file，--content-type image 只是标签），从不下载图片；模型侧两半都吃但看不到原图（model_side.mjs:40）；原图只在守衡取字节那一刻存在于临时目录、用完即删。画面读数不进链是设计边界而非漏做：模型生成物给不出逐字摘录、会被当素材原文用而污染库内依据、且库里画面类规则零覆盖——代价是画面层问题永远不会以「库内条款」的形式出现。
tier: L1
title: "[参考实现] 守衡的读数归属与可见性（2026-10-16）：图上文字与画面读数都是守衡侧产出的、知识库侧只吃文字那一半、模型侧只是读者"
topic: 知识
valid_until: 2027-01-14
---

# 守衡的「谁产读数、谁看得到图」（2026-10-16 现状）

> **本条是「参考实现」的索引入口，不是原文。** 留底件逐字在
> `PMO/守衡-读数归属与可见性-20261016.md`（本仓工作区，6,608 字节，sha256 前 16 位 `0d46ef37ebf7c435`）。
> **引用必须回该文件核对；不得据本条目的转述下结论。**
> 分工：读数**形状与延迟**见 `ref-shouheng-image-video-readings-20261016-r2`；
> 读数**是不是本单的**见 `ref-shouheng-reading-identity-20261016`；本件讲**归属与可见性**。

---

## 〇、起因：一处真实的误解

Owner 问：「图片OCR+基础视觉识别，这两个是谁在做？知识库侧OCR，基础视觉识别是模型侧吗」
—— 这句里两个前提都站不住：「知识库侧 OCR」把**两套 OCR 混成了一套**；
「基础视觉识别是模型侧」把**产出方**与**消费方**当成了一件事。

留档的理由不是这个问句，而是**现有两条参考实现挡不住它**：r1/r2 表格里写的是
「谁产的 = 本机 macOS Vision（`vision.mjs`）」「谁产的 = 吃图的视觉模型（`scene.mjs`）」
—— 那是**进程内的模块名**，没回答「守衡侧还是知识库侧」「链拿不拿得到图」。
⇒ **归属与可见性是一层独立的知识**，不是读数形状的附属句。

## 一、四个动作，四个位置

| # | 动作 | 谁在做 | 对什么做 | 何时 | 结果去哪 |
|---|---|---|---|---|---|
| ① | **图内文字（评审单）** | **守衡** `tools/agent/vision.mjs` → `.tools/bin/ocr`（源码 `base/ocr_vision.m`，Apple Vision `VNRecognizeTextRequest`） | 群里这一单发来的**那张图** | 每次送审，`readInboundContent` 取到字节之后 | 链的素材文本／模型侧／内核图块／报告附录 |
| ② | **图内文字（库内素材）** | **知识库侧** `kb/l8/ocr_attachments.py` → `osascript -l JavaScript kb/.work/ocr.jxa.js`（**同一台 Apple Vision，另一套实现**） | **库里的素材附件**（L0 记录挂的图片；视频走关键帧同一通道） | **供给链（日更/周更）**，与守衡这一单无关 | `kb/l1/media/` ＋ OCR 缓存 → L1/L2 单元 → **这才是「库内依据」** |
| ③ | **基础视觉识别**（画面读数） | **守衡** `tools/agent/scene.mjs`（吃图模型，走项目已在用的那一个端点） | 同一张图／视频抽出并选中的 ≤3 帧 | 每次送审，与 ① **并排**跑 | 模型侧＋内核图块＋报告附录；**不进链** |
| ④ | **判定（模型侧）** | 守衡 `tools/agent/model_side.mjs` | 读 ①③ 两节的**文本** | 与链**同时起跑** | 结论卡 |

⇒ ①③ 都在守衡侧；② 在知识库侧，且**与评审单无关**。

## 二、可见性矩阵

| 观察者 | 图上文字 | 画面读数 | 图片字节 |
|---|---|---|---|
| **知识库侧**（评审链 `kb/l8/review_run.sh`） | ✅ 作为 `--text`／`--material-file` 的**素材原文** | ❌ **完全拿不到** | ❌ 从不下载 |
| **模型侧**（`model_side.mjs`） | ✅ | ✅ | ❌ **看不到原图**（`:40` 注释即此句） |
| **内核 agent**（写回复的那一个） | ✅ | ✅ | 只在取字节那一刻、临时目录、用完即删 |
| **库内素材**（L1 media） | ✅ 但来自 ②，与评审单无关 | ❌ | 附件字节在 L0/L1，按供给链规矩 |

### 硬证据（都能自己跑一遍）

1. `grep -c "scene\|画面读数" tools/agent/review_gate.mjs` = **0**；`chainInput` 只拼
   `【图片 N 的图内文字（本机 OCR）】`／`画面上的字（按时间码）`／`音轨转写（本机识别）`。
2. 实物对得上：`kb/l7/reports/20261015-175333.json` 的 `input_manifest.text` =
   `【图片 1 的图内文字（本机 OCR）】\nmomcozY`，`content_type: text`、`modality: ["text"]`。
3. 链入口只收文字：`kb/l8/review_run.sh` 用法行 `--text "<素材原文，逐字>" [--content-type text|image|video]`
   —— `image`／`video` 是**标签**（决定判定主体让位），**不是字节**。
4. 知识库侧那套 OCR 挂在供给链上：`kb/l8/daily_digest.py` 的覆盖矩阵类③「图片附件」＝
   `store_l0_attachments.py / ocr_attachments.py / apply_ocr_to_l1.py`，类④「视频素材」＝
   `fetch_video_bytes.py / extract_video_keyframes.py / extract_video_asr.mjs`。

## 三、为什么画面读数**不**进链（设计边界，不是漏做）

1. **溯源四段要求「逐字原文与 sha 核对」**，画面读数是**模型生成物** ⇒ 给不出逐字摘录、回不到 L0；
2. 递进去它会被当**素材原文**用 ⇒ 「模型说的话」可能被引成**库内条款命中的依据**
   —— 与 2026-10-15 串单**同一种形状**（把「别的东西说的」当「本单素材里有的」）；
3. 库里**画面类规则零覆盖**（建设方案 §9.2）⇒ 递进去检索不到东西，只增加污染面。

⇒ 代价照实说：**画面层问题永远不会以「库内条款」的形式出现在结论里**，
只能以「模型侧观察／无库内依据」的身份出现。要让它也能引条款，得先把画面类规则建进 L3/L4（另一件事）。

## 四、一句话

**图上文字与画面读数，两样都是守衡侧产出的读数；知识库侧（链）只吃文字那一半、拿不到图；
模型侧两半都吃，但它只是读者 —— 原图两边都看不到。**
知识库侧自己那套 OCR 是给**库内素材入库**用的，与群里这一单是两回事
（只是碰巧用同一台引擎，所以最容易混）。

## 五、出处

守衡侧 `tools/agent/{vision,scene,agent,review_gate,model_side,tools}.mjs`｜
知识库侧 `kb/l8/{ocr_attachments.py,daily_digest.py,review_run.sh}` 与 `kb/.work/ocr.jxa.js`｜
实物读数 `kb/l7/reports/20261015-175333.json`｜PRD §5.1／§12。
