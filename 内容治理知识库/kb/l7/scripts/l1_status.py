#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l1_status.py —— L1（文本抽取层）的**只读状态查询档**。

## 补的是哪个洞（2026-10-01）

`kb-ingest-extractor` 是 L1/L2 的层 skill，但它**只有写档** —— 入口全是
`extract_l1_new_resources.py <RUN> [--apply]`、`l2_split_run.py <RUN> --apply`。
想「查一下 L1 现在什么水位」时**没有只读入口可调**，只能绕过 skill 直接读文件。
本脚本就是那个入口：调它 = 调该层 skill 的查询档。

## 只读

只读 `kb/l1/manifest_l1.jsonl`。不写任何文件、不落报告、不追加台账。
（对照：`kb/l8/l2_staleness_audit.py` 会写 `kb/l2/runs/*.json`，所以它**不能**当查询档用。）

## 口径

`status` 是**资源级**的粗状态，本脚本**原样全列**，不替人合并 —— 因为下游
（`kb/.work/l6_scope_lib.py` 等）只认其中几个值，合并会抹掉它们要用的区分。

    已产出正文  ok / extracted                 → 下游可用
    待处理      pending_ocr / pending_fetch    → 还没抓完/还没 OCR
    不适用      no_scope / no_content_expected / empty → 本就不该有正文
    已失效      invalidated / retracted / forbidden / unreachable / failed → 不可用
    其他        audit_note 等自造值            → **单独列出，不并进上面任何桶**

## 退出码

    0 = 读成功（**不代表"没问题"**，只代表查得到）
    2 = 用法错 / 库根不对 / 台账读不到
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

MANIFEST = os.path.join("kb", "l1", "manifest_l1.jsonl")
ROOT_MARKER = os.path.join("kb", "KB-ROOT.json")

#: status 分桶。**未列出的值不并入任何桶**，单独进 "其他"——不猜。
BUCKETS = {
    "已产出正文": ("ok", "extracted"),
    "待处理": ("pending_ocr", "pending_fetch"),
    "不适用": ("no_scope", "no_content_expected", "empty"),
    "已失效": ("invalidated", "retracted", "forbidden", "unreachable", "failed"),
}


def check_root() -> None:
    if not os.path.isdir("kb"):
        sys.exit("l1_status: 没有 kb/ 目录。请把 cwd 设成 kb/ 的上一级（库根）。")
    if not os.path.exists(ROOT_MARKER):
        sys.exit("l1_status: 缺 %s —— 这里不是权威库根（派生视图没有这个标记）。" % ROOT_MARKER)


def main() -> int:
    ap = argparse.ArgumentParser(description="L1 只读状态查询档")
    ap.add_argument("--json", action="store_true", help="额外打印 JSON（供检查器消费）")
    a = ap.parse_args()
    check_root()

    if not os.path.exists(MANIFEST):
        print("l1_status: 台账不存在：%s" % MANIFEST, file=sys.stderr)
        return 2

    n = 0
    status = collections.Counter()
    kb_type = collections.Counter()
    media_res = 0          # 有媒体的资源（media_count > 0）
    with_media_text = 0    # 其中有文本的
    for line in open(MANIFEST, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            n += 1
            status["<不可解析行>"] += 1
            continue
        n += 1
        status[r.get("status") or "<空>"] += 1
        kb_type[r.get("kb_type") or "<空>"] += 1
        if (r.get("media_count") or 0) > 0:
            media_res += 1
            if (r.get("char_count") or 0) > 0:
                with_media_text += 1

    buckets = collections.OrderedDict()
    claimed = set()
    for name, vals in BUCKETS.items():
        buckets[name] = sum(status[v] for v in vals)
        claimed |= set(vals)
    other = collections.OrderedDict(
        (k, v) for k, v in sorted(status.items()) if k not in claimed
    )

    print("L1 状态（只读查询档）｜台账 %s ｜ %d 行" % (MANIFEST, n))
    for name in BUCKETS:
        print("  %-8s %5d" % (name, buckets[name]))
    if other:
        print("  %-8s %5d  ← 未归入以上任何桶（原样列出，不猜）" % ("其他", sum(other.values())))
        for k, v in other.items():
            print("      · %-28s %5d" % (k, v))
    print("  媒体资源 %d 个（其中有文本 %d 个）" % (media_res, with_media_text))
    print("  by kb_type: " + " ｜ ".join("%s=%d" % (k, v) for k, v in sorted(kb_type.items())))

    if a.json:
        print(json.dumps({
            "layer": "L1",
            "source": MANIFEST,
            "rows": n,
            "buckets": buckets,
            "other_status": other,
            "raw_status": dict(status),
            "kb_type": dict(kb_type),
            "media_resources": media_res,
            "media_with_text": with_media_text,
        }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
