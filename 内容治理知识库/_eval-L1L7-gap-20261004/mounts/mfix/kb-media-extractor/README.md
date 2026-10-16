# kb-media-extractor

Momcozy 内容治理知识库 **L1（单元层）的媒体抽取入口**：把**图片 / 附件 / 落地页链接 / 视频**
转成可入库文本（OCR 正文 / 口播转写），落进 L1 的 `media` 区与单元索引。

- 上游：`kb-l0-feishu`（L0 字节与对账）｜下游：`kb-ingest-extractor`（L1 → 知识单元）
- 只读查询档：`kb/kbpy l7/scripts/media_status.py [--json]`
- 闸门：`kb/kbpy l7/scripts/l1_gate.py`（跑完必须过）

## 变更台账

| 版本 | 日期 | 改了什么 |
|---|---|---|
| 1.1.x | 2026-10 | 现役版基线 |
| 1.4.0 | 2026-10-04 | （前一轮修复）描述加负例块 |
| **1.5.0** | **2026-10-10** | ①**恢复全部正向触发表述**（前一轮挤掉它们导致召回 0.938→0.625）；②判定收口写成单一动作「带明确动作 ⇒ 要加载，不算欠定」；③负例只留**判归邻居**（实测有效），安全拒绝不再枚举（枚举拦不住、白占 500 字窗）；④修 `capability-matrix.md` / `gotchas.md` 的**视频能力错口径**（写"未实现"，实际已实现）；⑤路径引用补 `kb/` 前缀（14 处）；⑥§8 成员关系表下沉 `references/member-map.md`，正文 3943 ≤ 4000 留出余量 |

## 已知边界

- 独立音频 / 播客文件**未实现**（现有 ASR 只接视频内嵌音轨）；视频字幕/口播、关键帧 OCR **已实现**。
- 详情见 `references/capability-matrix.md`（能力矩阵）、`references/gotchas.md`（错误 → 修正）、
  `references/engine-commands.md`（命令行）、`references/member-map.md`（成员关系与删除边界）。
