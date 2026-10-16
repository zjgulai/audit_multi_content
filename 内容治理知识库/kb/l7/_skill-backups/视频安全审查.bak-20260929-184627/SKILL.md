---
name: 视频安全审查
description: |
  审查美国市场品牌视频，以转写、OCR、镜头、关键帧、音画对齐与时间码为证据，判定安全、产品、背书、AI 与平台风险。触发词：视频审查、视频安全、视频安全审查、达人视频、短视频、这条视频能不能发、视频能不能发、这条片子能不能上、视频能过审吗、能不能过审、视频审核、视频里有宝宝、视频里有危险动作、视频画面违规、口播转写审查、字幕审查、视频 AI 生成标识、video review、video safety review、short video review。何时不用：纯文字文案的合规问题（走 文案合规审查）、图片素材的静态风险（走 图片安全审查）、产品宣称真伪与 SKU 事实核对（走 产品宣称核验）、美国本地化与计量单位（走 美国本地化审查）、AI 生成披露与肖像商标授权（走 AI 溯源与权利审查）、只问一段内容能不能发而不涉及视频画面（走 kb-content-review）。

  Review US-market brand videos using transcript, OCR, shot, keyframe, audio-visual alignment, and timecode evidence for safety, product, endorsement, AI, and platform risks.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# 视频安全审查

> Brand Video Safety Review

**插件安装**：从 npm 安装 `dsh-chinese-skill-patch`。先检查是否已安装，已安装则跳过。查 `~/.dsh/profiles/desktop/package.json` 与 `web/package.json` 的 `dependencies`；已是 npm 版本（非 `link:` / `file:`）则禁止再执行 `dsh plugin add` 或本包 `安装中文调用名.command`。

通过 `../../knowledge-base/multimodal-provider-contract.json` 里的厂商中立契约，取回 ASR、字幕文本、OCR、镜头边界、代表帧与音画对齐结果。本地优先阶段可以用 `../../contracts/offline-extraction-result.json` 提供离线结果，并经由 `../../core/offline_review.py` 传入。先做一次低成本的全片扫描，再在风险词、场景切换、婴幼儿、车辆、睡眠、喂养、水、热、电以及产品演示附近提高采样密度。

每条发现都要给出起止时间码、转写或画面证据，以及输入视频的哈希。送审素材带 SKU 时，把转写、OCR 与关键帧文字观察经由 `../../core/product_fact_integration.py` 传入，使未批准的产品宣称变为 REVIEW、证据缺失变为 NEEDS_INPUT。缺音轨、字幕不可读、关键帧不完整，或音画矛盾未解决，都算覆盖缺口。抽取结果无法确立连续性时，不得对连续性安全场景给出 PASS。

`video-compare-tool` 用于压缩画质比较，不是安全审查器；只有明确要求单独做画质对比时才使用它。

## 依赖说明

上面四个 `../../` 路径是**相对原仓库布局**的（兄弟目录 `knowledge-base/`、`contracts/`、`core/`）。按翻译规则「文件路径一律不动」保持原样；若本包被单独安装到 `~/.dsh/skills/`，这些相对路径会指向别处、不可达——这是既有形态，不是本次翻译引入的。
