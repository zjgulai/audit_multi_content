# Gotchas —— kb-media-extractor（错误 → 修正）

> 由补充优化包加入（root-skills-creator 清单②③：gotchas 用「错误 + 修正」强模式，
> 并写明「本 skill 不处理 X，即使措辞看起来相似」）。

- **错误**：把「图里的文字有问题」判成内容违规
  **修正**：本 skill **只把媒体落成文本**（OCR 正文 + 单元索引），不判违不违规；判违规走内容审查侧。

- **错误**：把 `--purge-images` 当预演开关
  **修正**：它清的是 **L1 工作副本**，不是干跑、更不是 L0 原图。先读 `references/engine-commands.md`。

- **错误**：把缓存里 `invalidated` 的坏正文回写
  **修正**：坏正文不得回写；要转回有效必须用**新版引擎正文覆盖**。

- **错误**：闸门跑不了就报「红」
  **修正**：**跑不了 ≠ 红**：只读沙箱 / 缺输入属「**未判定**」，必须与「红」分开报。

- **错误**：把「这条视频里说的字」当成不归本 skill（旧口径已废）
  **修正**：视频**已实现**——口播走 `l8/extract_video_asr.mjs`（macOS Speech.framework 本机 ASR，不出机器），画面文字走 `l8/extract_video_keyframes.py`（抽帧 → 走图片 OCR 通道）。**未实现的是独立音频 / 播客文件**（现有 ASR 只接视频内嵌音轨）——别拿视频那条冒充「音频也能抽」。
  **修正**：该类**尚未实现**；先读 `references/capability-matrix.md`，并如实说未实现，不得假装能跑。

- **错误**：本 skill 不处理把 OCR 结果切成知识单元，即使措辞看起来相似
  **修正**：归 `kb-ingest-extractor`（L1/L2）。
