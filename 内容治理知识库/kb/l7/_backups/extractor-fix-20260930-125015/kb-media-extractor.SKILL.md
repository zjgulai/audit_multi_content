---
name: kb-media-extractor
description: |
  Momcozy 内容治理知识库 **L1（单元层）的媒体抽取入口**：把图片 / 视频 / 附件变成**可入库的文本**
  （OCR 正文、关键帧 OCR、视频字幕），落进 L1 的 media 区与单元索引。
  当用户说「图片抽取 / 媒体抽取 / 这批图 OCR 一下 / 附件入库 / 视频字幕抽出来 / 关键帧 OCR /
  L1 媒体 / 链接下钻 / 图里的文字落库」时使用。
  触发词：图片抽取、媒体抽取、OCR 落库、图片入库、附件入库、视频字幕、关键帧、链接下钻、
  L1 媒体、media extractor、kb-media-extractor。
  不适用（各自点名）：
    · 只对账 L0、飞书侧改了什么 → 走 **kb-l0-feishu**（它只管 L0，不跑下游）；
    · 素材切成知识单元 / 补切 → 走 **kb-ingest-extractor**（L1→L2）；
    · 条款级抽取与规则蒸馏 → 走 **kb-clause-extractor**（L3）；
    · 整链同步 / 建索引 / 发号 → 走 **kb-pipeline**；只体检不跑 → **kb-check**。
version: "1.0.0"
last_updated: 2026-09-30
complexity: "medium"
enabled: "true"
user-invocable: true
---

# kb-media-extractor —— L1 媒体抽取

**一句话**：把「看不见的模态」变成 L1 里可检索的文本。字节存 L0，**文本落 L1**。

## 1. 它管哪一层

| 项 | 值 |
|---|---|
| 层 | **L1**（单元层） |
| 幂等键 | `(resource_id, extractor_version, source_sha256)`；OCR 缓存另有**按文件 sha256** 的缓存键 |
| 落盘 | `kb/l1/media/**`、`kb/l1/media/_cache/*.json`、`kb/l1/2_内部正负样本库/media_*.json` |

**上游**：`kb-l0-feishu`（只负责 L0 的字节与对账，**不跑下游**）。
**下游**：`kb-ingest-extractor`（把 L1 内容切成单元）→ `kb-clause-extractor`（L3）→ `kb-pipeline`（L4–L7）。

## 2. 干活的引擎（名字点齐，别让下一个人猜）

```bash
# ① 媒体抽取主引擎：建 kb/l1/media/**、下载图片附件、写 OCR 缓存、写 ocr.json
kb/kbpy l8/ocr_attachments.py <RUN>            # 预演
kb/kbpy l8/ocr_attachments.py <RUN> --apply    # 落盘
#   注意：--purge-images 是更激进的删除开关，**不是**预演开关

# ② 链接下钻两层（写 kb/l1/sources）
kb/kbpy l8/drill_links_2levels.py <RUN> [--apply]

# ③ 附件字节落 L0（只做存档，不产文本）
kb/kbpy l8/store_l0_attachments.py <RUN>

# ④ OCR 文本并入 L1 单元
kb/kbpy l8/apply_ocr_to_l1.py <OCR_RUN> <L1_RUN> [--apply]
```

**闸门（跑完必须过）**：`kb/kbpy l7/scripts/l1_gate.py`
—— 它把 `kb/.work/kb_ocr_gate.py::ocr_cache_reusable` **逐条**落到 169+ 条真实缓存上：
坏引擎版本 / `sha256_state` 非 full / 正文含 U+FFFF / 整图丢失，任一条命中即判红。

## 3. 三条红线

1. **缓存不达标不得复用**：按 file sha256 命中缓存时，必须先过 `ocr_cache_reusable`；
   它防的是把**坏 OCR 正文**灌进 L1（脏数据入口，比断链隐蔽）。
2. **认不出来就写认不出来**：OCR 空结果要如实登记，不许用别的字段凑正文。
3. **不许 python 写 `.md`**：本机 python 写的 `.md` 会落成**信封态**（宿主读不到）；
   要写报告就走「python 生成 → 无扩展名临时件 → `/bin/cp`」。

## 4. 验收（跑完逐条核）

| # | 判据 |
|---|---|
| A1 | `kb/kbpy l7/scripts/l1_gate.py` 退出 0（全部缓存可复用） |
| A2 | 本批新增的图片/视频资源，在 `kb/l1/manifest_l1.jsonl` 里都有对应行，且状态不是 `pending_ocr` 悬空 |
| A3 | `kb/kbpy l7/scripts/l2_gate.py` 仍过（L1 有内容的资源数 == 被切分数 + 明确跳过数的那套判据） |
| A4 | 落盘产物没有信封态（python getsize == node statSync，差 0） |

## 5. 与其他成员的关系

| 关系 | 成员 | 说明 |
|---|---|---|
| 上游 | `kb-l0-feishu` | L0 字节与对账；**它不跑下游**，本 skill 自己按幂等键收敛 |
| 下游 | `kb-ingest-extractor` | L1 内容 → 知识单元 |
| 只读查询 | `kb-recall` | 召回单元（不重建索引） |
| 编排 | `kb-pipeline` | 整链按 `layers.yaml` 拓扑序跑（本 skill 是 L1 的 owner） |
| 体检 / 修复 | `kb-check` / `kb-repair` | 闸门红了的定位与修复 |
