#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫 @Momcozy 全频道视频标题（oEmbed 批量），再按三大品类分桶。

为什么不是"取最新 10 条"：实测最新 10 条全是品牌/母亲节片（`Choose You, Too` 系列），
**不属于**婴儿监控器/清洗机/吸奶器任何一类 —— 而本轮口径是「必须属于这 3 个品类」。

用法：python3 scan_all_videos.py [上限]
"""
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 124

CAT = [
    ("清洗机", r"washer|wash|clean|steriliz|sanitiz|dryer|kleanpal|deepclean|d8|d9|bottle wash"),
    ("婴儿监控器", r"monitor|camera|bm\d|surveillance"),
    ("吸奶器", r"pump|breast ?milk|milk supply|latch|letdown|wearable|m5|m6|m9|s12|s9|v1|v2|w1|nursing bra"),
]


def get(u, t=25):
    req = urllib.request.Request(u, headers=UA)
    with urllib.request.urlopen(req, timeout=t) as r:
        return r.read()


def main():
    html = get("https://www.youtube.com/@Momcozy")
    ids, seen = [], set()
    for m in re.finditer(rb'"videoId":"([\w-]{11})"', html):
        v = m.group(1).decode()
        if v not in seen:
            seen.add(v)
            ids.append(v)
    ids = ids[:LIMIT]
    print(f"频道 videoId: {len(seen)} 个，本轮扫前 {len(ids)} 个")

    rows = []
    for i, vid in enumerate(ids, 1):
        try:
            o = json.loads(get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"))
            rows.append({"videoId": vid, "title": o.get("title", ""),
                         "url": f"https://www.youtube.com/watch?v={vid}"})
        except Exception as e:                                     # noqa: BLE001
            rows.append({"videoId": vid, "title": "", "error": type(e).__name__})
        if i % 20 == 0:
            print(f"  …{i}/{len(ids)}")

    buckets = {}
    for r in rows:
        if not r.get("title"):
            continue
        for name, pat in CAT:
            if re.search(pat, r["title"], re.I):
                buckets.setdefault(name, []).append(r)
                break
    json.dump({"all": rows, "buckets": buckets},
              open("raw/youtube_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n=== 分桶 ===")
    for name, _ in CAT:
        print(f"  {name}: {len(buckets.get(name, []))} 条")
    for name, _ in CAT:
        for r in buckets.get(name, [])[:6]:
            print(f"     [{name}] {r['title'][:70]}")


if __name__ == "__main__":
    main()
