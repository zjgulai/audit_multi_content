# kb-media-extractor · 引擎命令行与闸门口径

> 本文件由 SKILL.md §2 / §2.1 下沉而来（信息**逐字保留**，正文只留引擎名与何时用）。
> 正文 §2 是**索引**，这里是**细节**：要敲命令、要对闸门口径时读本文件。

## 一、四个写档引擎的完整命令行

```bash
# ① 媒体抽取主引擎：建 kb/l1/media/**、下载图片附件、写 OCR 缓存、写 ocr.json
kb/kbpy l8/ocr_attachments.py <RUN>            # 预演
kb/kbpy l8/ocr_attachments.py <RUN> --apply    # 落盘
#   注意：--purge-images 是更激进的删除开关，**不是**预演开关

# ② 链接下钻两层（写 kb/l1/sources）
kb/kbpy l8/drill_links_2levels.py <RUN> [--apply]

# ③ 附件字节落 L0（只做存档，不产文本）—— 归档归属见 SKILL.md §3
kb/kbpy l8/store_l0_attachments.py <RUN>

# ④ OCR 文本并入 L1 单元
kb/kbpy l8/apply_ocr_to_l1.py <OCR_RUN> <L1_RUN> [--apply]
```

## 二、闸门（跑完必须过）

`kb/kbpy l7/scripts/l1_gate.py`
—— 它把 `kb/.work/kb_ocr_gate.py::ocr_cache_reusable` **逐条**落到 169+ 条真实缓存上：
坏引擎版本 / `sha256_state` 非 full / 正文含 U+FFFF / 整图丢失，任一条命中即判红。

## 三、只读查询档

```bash
kb/kbpy l7/scripts/media_status.py [--json]
```

**只读**：只读 `kb/l1/media/_cache/*.json` 与 `kb/l1/manifest_l1.jsonl`。
**不写任何文件、不下载图片、不跑 OCR、不改缓存。**

两条口径，别当成缺陷去"修"：

1. **复用判据不重写。** 「OCR 缓存能否复用」的判据在
   `kb/.work/kb_ocr_gate.py::ocr_cache_reusable`（version `vision-jxa-2.0`），
   `l1_gate.py` 是 import 它、不是复述它。本查询档照同一条纪律 **import 那个函数逐条调用**。
2. **两个计数不是一个量，不互相校验。** `_cache/*.json` 是**逐图**条目；
   `manifest_l1.jsonl` 的 `media_count` 是**逐资源**的媒体数。查询档**分别报出**，不拿一个去核另一个。
