#!/usr/bin/env python3
"""80 行里，有多少行的链跑**只收到了链接占位符**。

## 判法（不猜、可复核）

`守衡 review_gate.mjs:270-274`：无图无视频、且正文里有链接 ⇒ 送给链的 `text` 就是
`【待读的链接】\n<链接>`（正文丢弃）。而 `review.py` 的 `content_id = "text-" + sha256(text)[:12]`
（已用实测反推并逐字对齐过一条）。

⇒ 对每一行：算出「占位符文本」的指纹，去 `kb/l7/reports/*.json` 的 `content_id` 里找。
   找到 ⇒ **这一行链收到的是占位符**；找不到 ⇒ 它拿到的是别的（真内容或另一形态）。

用法：`python3 采集-20261013/audit_placeholder.py`
"""
import glob
import hashlib
import json
import os
import re
import ssl
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def cid_of(text):
    return "text-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def clean(t):
    """与 runner 的 `clean()` 逐字同口径：markdown 链接 → 裸 URL。"""
    return re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)", r"\2", t or "")


def main():
    import importlib.util
    spec = importlib.util.spec_from_file_location("p", os.path.join(HERE, "parse_table80.py"))
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    rows = p.parse(os.path.join(HERE, "out/table80_after.txt"))

    # 报告库：content_id -> (文件, 文本长度)
    seen = {}
    for f in glob.glob(os.path.join(ROOT, "kb/l7/reports/*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        c = d.get("content_id")
        if not c:
            continue
        t = (d.get("input_manifest") or {}).get("text") or ""
        seen.setdefault(c, []).append((os.path.basename(f), len(t)))

    hit = miss = na = 0
    bad = []
    for r in rows:
        ctype = p.flat(r["内容类型"])
        txt = clean(r["采集数据"])
        urls = re.findall(r"https?://[^\s|]+", txt)
        if ctype != "文案" or not urls:
            na += 1
            continue
        ph = "【待读的链接】\n" + "\n".join(urls)
        c = cid_of(ph)
        got = seen.get(c)
        if got:
            hit += 1
            bad.append((r["内容 ID"], got[0][0], got[0][1]))
        else:
            miss += 1
    print(f"80 行：文案行（走占位符分支的）{hit + miss} ｜ 非文案/无链接 {na}")
    print(f"  ★ 链**确实只收到占位符**：{hit}")
    print(f"  · 未在报告库里找到占位符指纹（拿到别的）：{miss}")
    print()
    for cid, f, n in bad[:40]:
        print(f"    {cid:<36} -> {f}  (链收到的正文长度 {n})")
    print()
    print("边界：找不到 ≠ 拿到真内容 —— 可能是那一行没跑、或用别的形态跑的。此处只报**确证**。")


if __name__ == "__main__":
    sys.exit(main())
