#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写库前闸门：逐条 HTTP 校验 80 行的素材 URL，全绿才放行。

为什么非要它：上次 80 条就是靠它拦下 3 个真缺陷 —— ① Amazon 图片 URL 第一版全是 404
（ID 取成了 CSS/JS 资源）、② 标题残留 Amazon 类目后缀、③ 5 个 ASIN 是诱饵页。
**没有这一关，脏数据就直接进治理表了。**

判据：
  · 图片 / 视频缩略图：HTTP 200 且 content-type 是 image/*
  · 文案：必须有 `—— 来源：` 与可解析 URL（文案不下载正文，只核来源可点）
  · 每行必需的库字段齐（内容 ID / 内容类型 / 渠道 / 产品线 / 采集数据 / 状态）
  · 内容 ID 全局唯一

用法：python3 verify_rows.py       # 红 ⇒ 退出码 3
"""
import collections
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
REQUIRED = ["内容 ID", "内容类型", "渠道", "产品线", "采集数据", "状态"]


def head(url, t=20):
    try:
        req = urllib.request.Request(url, headers=UA, method="GET")
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, r.headers.get("Content-Type", ""), len(r.read(4096))
    except Exception as e:                                         # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:60]}", 0


def main():
    rows = json.load(open("out/rows.json", encoding="utf-8"))
    red, checked = [], 0

    # ① 字段齐 + ID 唯一
    ids = [r.get("内容 ID") for r in rows]
    dup = [k for k, v in collections.Counter(ids).items() if v > 1]
    if dup:
        red.append(f"内容 ID 重复 {len(dup)} 个: {dup[:5]}")
    for i, r in enumerate(rows, 1):
        missing = [k for k in REQUIRED if not str(r.get(k) or "").strip()]
        if missing:
            red.append(f"第{i}行缺字段 {missing}")

    # ② 文案：来源可点
    for i, r in enumerate(rows, 1):
        if r.get("内容类型") != "文案":
            continue
        if "—— 来源：" not in (r.get("采集数据") or ""):
            red.append(f"第{i}行文案没有「—— 来源：」")
            continue
        u = r["采集数据"].split("—— 来源：")[-1].strip()
        if not re.match(r"^https?://", u):
            red.append(f"第{i}行文案来源不是 URL: {u[:60]}")

    # ③ 图片/视频：逐条 HTTP 校验
    for i, r in enumerate(rows, 1):
        if r.get("内容类型") not in ("图片", "视频"):
            continue
        url = r.get("_url") or ""
        if not re.match(r"^https?://", url):
            red.append(f"第{i}行 {r['内容类型']} 无可用素材 URL")
            continue
        st, ct, n = head(url)
        checked += 1
        if st != 200:
            red.append(f"第{i}行 {r['内容类型']} {url[:70]} → {st} {ct}")
        elif "image" not in ct:
            red.append(f"第{i}行 {r['内容类型']} content-type 不是图片: {ct} ← {url[:60]}")

    print(f"checked={checked}  red={len(red)}")
    for x in red[:25]:
        print("  ❌", x)
    if red:
        print("\n结论：❌ 不放行（先修红项）")
        return 3
    print("\n结论：✅ 全绿，可写库")
    return 0


if __name__ == "__main__":
    sys.exit(main())
