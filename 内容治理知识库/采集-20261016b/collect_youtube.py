#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube @Momcozy（北美）视频采集 —— 取最新 10 条，带标题/发布时间/缩略图/URL。

为什么是它：北美社媒 11 个账号里，只有 YouTube 这一个实测能出内容
（IG/TikTok/FB/X/Pinterest/Threads/Reddit/LinkedIn 全部被登录墙或反爬挡住，实测原始结果见交付件）。
站点列经实读原表确认为「北美」（sheet `de1db3` 行 46），**不是**上次交付件里写的"没标北美"。

用法：python3 collect_youtube.py [N]      # 默认 10
"""
import json
import os
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
CHANNEL = "https://www.youtube.com/@Momcozy"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    os.makedirs("raw", exist_ok=True)
    html = get(CHANNEL)
    ids, seen = [], set()
    for m in re.finditer(rb'"videoId":"([\w-]{11})"', html):
        vid = m.group(1).decode()
        if vid not in seen:
            seen.add(vid)
            ids.append(vid)
    print(f"频道页解析出 videoId: {len(ids)} 个（去重后）")

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
                "author": "Momcozy",
                "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                "uploadDate": d.group(1).decode() if d else "",
                "viewCount": int(v.group(1)) if v else None,
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
            print(f"  [{len(out):2d}] {title[:72]}")
        except Exception as e:                                    # noqa: BLE001
            print(f"  ⚠️ {vid}: {type(e).__name__} {str(e)[:60]}")

    json.dump(out, open("raw/youtube.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已写 raw/youtube.json ｜ {len(out)} 条")


if __name__ == "__main__":
    main()
