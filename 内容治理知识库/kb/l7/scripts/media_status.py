#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""media_status.py —— L1 媒体区（图片 / 附件 / 落地页）的**只读状态查询档**。

## 补的是哪个洞（2026-10-01）

`kb-media-extractor` 只有写档（`ocr_attachments.py` / `apply_ocr_to_l1.py` / `drill_links_2levels.py`），
查「OCR 缓存能不能复用 / 有多少张图还没落文本」时无档可调。本脚本就是那个入口。

## 不重写判据（关键设计）

「OCR 缓存能否复用」的判据**已经存在**：`kb/.work/kb_ocr_gate.py::ocr_cache_reusable`
（version `vision-jxa-2.0`；判 `sha256_state` / `ocr_version` / U+FFFF 中文丢失 / 空文本但图 >4096B）。
`kb/l7/scripts/l1_gate.py` 也是**import 它、不重写**。本脚本照同一条纪律：
**import 那个函数逐条调用**，不在这里复述判据（同一判据写两处，第二处必然过期）。

## 只读

只读 `kb/l1/media/_cache/*.json` 与 `kb/l1/manifest_l1.jsonl`（取 media 计数）。
**不写任何文件、不下载、不跑 OCR。**

## 口径

    _cache/*.json 是**逐图**的 OCR 缓存（键 = 图片 sha256）
    manifest_l1.jsonl 的 media_count 是**逐资源**的媒体数
两者不是一个量，**不互相校验**，本脚本分别报出。

## 退出码

    0 = 读成功（不代表"没问题"）
    2 = 用法错 / 库根不对 / 缓存目录读不到
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

CACHE_DIR = os.path.join("kb", "l1", "media", "_cache")
MANIFEST = os.path.join("kb", "l1", "manifest_l1.jsonl")
GATE_FUNC = os.path.join("kb", ".work", "kb_ocr_gate.py")
ROOT_MARKER = os.path.join("kb", "KB-ROOT.json")


def check_root() -> None:
    if not os.path.isdir("kb"):
        sys.exit("media_status: 没有 kb/ 目录。请把 cwd 设成 kb/ 的上一级（库根）。")
    if not os.path.exists(ROOT_MARKER):
        sys.exit("media_status: 缺 %s —— 这里不是权威库根。" % ROOT_MARKER)


def load_gate():
    """import kb/.work/kb_ocr_gate.py 里的 ocr_cache_reusable（**用它，不重写**）。"""
    if not os.path.exists(GATE_FUNC):
        return None, "闸门函数不存在：%s" % GATE_FUNC
    import importlib.util
    spec = importlib.util.spec_from_file_location("kb_ocr_gate_status", GATE_FUNC)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        return None, "闸门函数装载失败：%r" % (e,)
    fn = getattr(mod, "ocr_cache_reusable", None)
    if fn is None:
        return None, "kb_ocr_gate.py 里没有 ocr_cache_reusable"
    return fn, None


def main() -> int:
    ap = argparse.ArgumentParser(description="L1 媒体区只读状态查询档")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    check_root()

    if not os.path.isdir(CACHE_DIR):
        print("media_status: 缓存目录不存在：%s" % CACHE_DIR, file=sys.stderr)
        return 2

    gate, gate_err = load_gate()

    files = sorted(f for f in os.listdir(CACHE_DIR) if f.endswith(".json"))
    reasons = collections.Counter()
    reusable = 0
    with_text = 0
    empty_text = 0
    unreadable = 0
    for fn in files:
        p = os.path.join(CACHE_DIR, fn)
        try:
            entry = json.load(open(p, encoding="utf-8"))
        except (ValueError, OSError):
            unreadable += 1
            continue
        if not isinstance(entry, dict):
            unreadable += 1
            continue
        if (entry.get("ocr_text") or "").strip():
            with_text += 1
        else:
            empty_text += 1
        if gate is not None:
            ok, why = gate(entry)
            if ok:
                reusable += 1
            else:
                reasons[why.split("（")[0].split(":")[0].strip()] += 1

    # manifest 侧的媒体计数（逐资源，与逐图的 _cache 不是一个量）
    media_res = 0
    media_sum = 0
    if os.path.exists(MANIFEST):
        for line in open(MANIFEST, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            mc = r.get("media_count") or 0
            if mc > 0:
                media_res += 1
                media_sum += mc

    print("L1 媒体区状态（只读查询档）｜缓存 %s" % CACHE_DIR)
    print("  缓存条目 %d 个（有文本 %d ｜ 空文本 %d ｜ 不可解析 %d）"
          % (len(files), with_text, empty_text, unreadable))
    if gate is None:
        print("  ⚠️ 复用判据**未评估**：%s" % gate_err)
    else:
        print("  按 kb_ocr_gate.ocr_cache_reusable 判：可复用 %d ｜ 不可复用 %d"
              % (reusable, len(files) - reusable - unreadable))
        for k, v in reasons.most_common():
            print("      · 不可复用原因 %-28s %d" % (k, v))
    print("  manifest 侧：有媒体的资源 %d 个 ｜ media_count 合计 %d（逐资源，与逐图缓存不是一个量）"
          % (media_res, media_sum))

    if a.json:
        print(json.dumps({
            "layer": "L1-media",
            "cache_dir": CACHE_DIR,
            "cache_entries": len(files),
            "with_text": with_text,
            "empty_text": empty_text,
            "unreadable": unreadable,
            "gate": ("ok" if gate else "unavailable"),
            "gate_error": gate_err,
            "reusable": reusable if gate else None,
            "not_reusable_reasons": dict(reasons),
            "media_resources": media_res,
            "media_count_sum": media_sum,
        }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
