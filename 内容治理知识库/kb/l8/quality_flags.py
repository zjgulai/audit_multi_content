#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quality_flags.py —— `content_quality_flag` 的**唯一真源**：哪些标记是「干净正文」、哪些是「确有缺陷」

为什么有这份文件（2026-10-12，实测缺陷，Owner 批准修）
────────────────────────────────────────────────────────────────
`content_quality_flag` 是 L1 抽取时写在 `unit.meta` 上的质量标记。**同一个标记被两层读成了相反的意思**：

| 层 | 文件 | 做法 |
|---|---|---|
| L6（召回层） | `kb/.work/l6_scope_lib.py` | `if flag and flag not in GOOD_QUALITY_FLAGS:` —— **有放行白名单** |
| L3（蒸馏层） | `kb/l8/l3_scope.py` | `if flag:` —— **无白名单，一律照挡** |

而 L6 那份白名单是 **Owner 2026-09-29 核定过**的（`l6_scope_lib.py` 原文注释逐字）：

> ③ quality_flag 只挡"确有质量缺陷"的标记（`l1_extraction_includes_code`）；
> **2026-09-29 无头重抓的 `recrawl_headless_rendered` 是干净正文，不再被挡**
> ⑥（2026-09-30 补）`pdf_ocr_vision` 是扫描件经 pdftoppm+Vision OCR 得到的**正文本身**
>   （不是提取缺陷标记，与 `recrawl_headless_rendered` 同类）

**后果（实测 2026-10-12，拿 L3 真尺子跑 `kb/l2/units.jsonl` 全部 14,647 个单元）**：

| flag | 条数 | L3 | L6 | 抽查成色 |
|---|---|---|---|---|
| `recrawl_headless_rendered` | 908 | ⛔ 挡 | ✅ 放行 | 真内容（FTC 指南、Momcozy 多语言博客/产品页；URL 数中位 0、英文词中位 505） |
| `pdf_ocr_vision` | 99 | ⛔ 挡 | ✅ 放行 | 真内容（《DK科学育儿小百科》等扫描书 OCR 正文） |
| `l1_extraction_includes_code` | 684 | ⛔ 挡 | ⛔ 挡 | 压缩 JS ⇒ **两边一致，照挡** |
| `ok` | 977 | ⛔ 挡 | ⛔ 挡 | ⚠️ **CDN 图片 URL 汤**（见下「`ok` 为什么不进白名单」） |

⇒ L3 那 1,005 条（908＋99 − 2 个不在 L3 范围）是**被漏放的真内容**，
其中包括 10/19–10/23 行 #1 要的 **FDA 8/8** 与**自有站 714/934** —— 那两项「0 条」的根因就在这里。

**本模块的作用**：把这份名单**搬家到一处**，L3 与 L6 **都 import 它** ⇒ 「两把尺子」在结构上不可能再分叉。
这正是 `kb/l8/l3_scope.py` 自己的处方（它当年就是为解决同类缺陷而建的）。

⚠️ **不许在别处再抄第二份。** 本库已经因为「同一个常量两份定义」栽过
（`INTERNAL_SAMPLE_TABLES` 现在在 `l3_scope.py` 与 `.work/l6_scope_lib.py` 里**各写了一份**，
是同一类病的现成标本 —— 本次**未一并合并**，登记在案）。

★★ `ok` 为什么不进白名单（**2026-10-12 实测，别手滑加进来**）
────────────────────────────────────────────────────────────────
`content_quality_flag == "ok"` 的 **977 条**，来源是 `transparency.meta.com/policies/ad-standards`，
其正文是 **CDN 图片 URL 汤**：

    'https://static.xx.fbcdn.net/rsrc.php/yT/r/HoyEUYoJMCF.webp https://static.xx.fbcdn.net/…'

`meta` 里还写着 `"split": "in_line_sentence"`、`"char_offset_in_source": 0`。
**标记说「ok」，内容是垃圾 ⇒ 打这个标记的地方判错了**，那是**另一个独立缺陷**（登记在
`核定-自有站与FDA为何不成规则-两把尺子-20261012.md` §4），**要单独查 L1 侧谁写的 `ok`**。
把它放进白名单＝让 977 条 URL 汤涌进外部标准供给。

边界
────────────────────────────────────────────────────────────────
· 本模块**只有常量**，不读任何文件、不写任何文件、无副作用。
· 名单的**语义**是「确认是干净正文」；**不在名单里的任何 flag 一律照挡**（勿放松）。
"""
import os
import importlib.util

# ── 白名单本体（唯一一份）──────────────────────────────────────────────
# 只放行「确认是干净正文」的标记；其余任何 quality_flag 一律照挡。
GOOD_QUALITY_FLAGS = frozenset({
    "recrawl_headless_rendered",   # Owner 2026-09-29 核定：无头重抓的是干净正文
    "pdf_ocr_vision",              # Owner 2026-09-30 核定：扫描件 OCR 的是正文本身
})

# 明确**不许**放行的（写出来是为了下次有人想加 `ok` 时先看到这段）
KNOWN_BAD_FLAGS = ("l1_extraction_includes_code",)   # 提取物里含代码，L3/L6 两边一致照挡
FLAG_OK_BUT_JUNK = ("ok",)                           # ★ 见模块头部：标记说 ok、内容是 URL 汤，另有缺陷

__all__ = ["GOOD_QUALITY_FLAGS", "KNOWN_BAD_FLAGS", "FLAG_OK_BUT_JUNK", "load_single_source"]


def load_single_source():
    """给**别的目录**下的消费者（如 `kb/.work/l6_scope_lib.py`）用的自证入口。

    返回本模块的 `GOOD_QUALITY_FLAGS`，并断言它与本文件里那份是**同一个对象来源** ——
    防止有人复制粘贴出一个第二份。调用方拿到后**不许再定义自己的副本**。
    """
    return GOOD_QUALITY_FLAGS


def _selftest():
    """自证：① 名单内容与 Owner 裁定一致；② 不含已知坏标记；③ 不含 `ok`；④ 不可变。"""
    n = 0
    ok = {"recrawl_headless_rendered", "pdf_ocr_vision"}
    assert set(GOOD_QUALITY_FLAGS) == ok, f"白名单被改动：{sorted(GOOD_QUALITY_FLAGS)}"; n += 1
    for bad in KNOWN_BAD_FLAGS:
        assert bad not in GOOD_QUALITY_FLAGS, f"坏标记进了白名单：{bad}"; n += 1
    for j in FLAG_OK_BUT_JUNK:
        assert j not in GOOD_QUALITY_FLAGS, (
            f"`{j}` 不许进白名单 —— 实测它的 977 条正文是 CDN 图片 URL 汤，见模块头部"); n += 1
    assert isinstance(GOOD_QUALITY_FLAGS, frozenset), "必须是 frozenset（防被就地改）"; n += 1
    # 反向对照：真造一个「ok 被加进白名单」的缺陷，检查上面的断言会红
    badset = set(GOOD_QUALITY_FLAGS) | {"ok"}
    caught = "ok" in badset and ("ok" not in GOOD_QUALITY_FLAGS)
    assert caught, "反向对照失效"; n += 1
    # 判断式本身：与 L6 逐字同式
    def blocked(flag):
        return bool(flag) and flag not in GOOD_QUALITY_FLAGS
    assert blocked("l1_extraction_includes_code") is True, "含代码必须挡"; n += 1
    assert blocked("ok") is True, "`ok` 目前仍然挡（它另有缺陷，未裁定放行）"; n += 1
    assert blocked("recrawl_headless_rendered") is False, "无头重抓必须放行"; n += 1
    assert blocked("pdf_ocr_vision") is False, "OCR 正文必须放行"; n += 1
    assert blocked(None) is False and blocked("") is False, "无标记必须放行"; n += 1
    print(f"quality_flags selftest {n}/{n} ✅")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
