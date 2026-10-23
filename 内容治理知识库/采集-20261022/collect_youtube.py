#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube @Momcozy（北美）采集 —— 社媒里唯一实测能出内容的通道。

口径来自 2026-10-16 实读原表：账号盘点表 `de1db3` 第 46 行 YouTube @Momcozy 的站点列
**标的是「北美」**（上一版交付件写的"没标北美"是错的，已更正）。
IG / TikTok / FB / X / Reddit 六个北美账号本轮复测仍全部被登录墙或反爬挡住（原始读数见交付件）。

只收与本项目三个品类（吸奶器 / 清洗机 / 婴儿监控器）相关的视频。

用法：python3 collect_youtube.py [N]
"""
import json
import os
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
CHANNEL = "https://www.youtube.com/@Momcozy"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20

CATS = [
    ("清洗机", re.compile(r"wash|washer|steril|clean|deepclean|kleanpal", re.I)),
    ("吸奶器", re.compile(r"pump|pumping|breast", re.I)),
    ("婴儿监控器", re.compile(r"monitor|camera|bm0\d|bm1\d", re.I)),
]


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def cat_of(title):
    for cat, rx in CATS:
        if rx.search(title):
            return cat
    return ""


def main():
    os.makedirs("raw", exist_ok=True)
    html = get(CHANNEL)
    ids, seen = [], set()
    for m in re.finditer(rb'"videoId":"([\w-]{11})"', html):
        vid = m.group(1).decode()
        if vid not in seen:
            seen.add(vid)
            ids.append(vid)
    print(f"频道页解析出 videoId {len(ids)} 个（去重后）")

    out = []
    for vid in ids:
        if len(out) >= N:
            break
        try:
            page = get(f"https://www.youtube.com/watch?v={vid}")
            t = re.search(rb'<meta name="title" content="([^"]*)"', page)
            d = re.search(rb'"uploadDate":"([^"]*)"', page)
            v = re.search(rb'"viewCount":"(\d+)"', page)
            title = t.group(1).decode("utf-8", "ignore") if t else ""
            if not title:
                continue
            out.append({
                "videoId": vid,
                "title": title,
                "channel": "Momcozy",
                "cat": cat_of(title),
                "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                "uploadDate": d.group(1).decode() if d else "",
                "viewCount": int(v.group(1)) if v else None,
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
            print(f"  [{len(out):2d}] {title[:66]}  → {out[-1]['cat'] or '（非三品类）'}")
        except Exception as e:                                     # noqa: BLE001
            print(f"  ⚠️ {vid}: {type(e).__name__} {str(e)[:60]}")

    json.dump(out, open("raw/youtube.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    hit = [r for r in out if r["cat"]]
    print(f"\n抓到 {len(out)} 条，其中命中三品类 {len(hit)} 条 → raw/youtube.json")


if __name__ == "__main__":
    main()
