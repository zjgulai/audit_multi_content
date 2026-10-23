#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube 采产品级视频（**只收官方 @Momcozy 频道**，9 个产品各自找）。

## 为什么改成「按产品搜索 + 按 channelId 过滤」

第一版只扫「频道页最近 60 条」，结论是「清洗机/婴儿监控器 0 条」——
**那个结论是错的**，错在只看了一个切面：官方频道近期被育儿科普内容占满
（IBCLC 直播、Mom Truths 101 之类），产品视频沉在更早或不在首屏。

实测（2026-10-23）按型号搜 `YouTube` **每个型号都有视频**：
`S12 Pro Quick` / `M5 Smart` / `Air 1` / `KleanPal Pro` / `Washing Block` / `BM03` / `BM08` /
`Detergent Tablets` 全部有命中。

## 但搜索会混进第三方创作者 —— 必须过滤，不能当品牌内容

实测同一条搜索里既有官方号，也有 UGC 测评（如 `How to Use Momcozy S12 Pro Quick`
是官方，`Pumping made simple for busy moms` 的作者是 **Nitu**）。
判定字段用 watch 页的 **`channelId`**（比频道名可靠：名字可改、可重名）。
官方号 channelId 现从 `https://www.youtube.com/@Momcozy` 动态解析，**不写死**。

口径：**只收官方号**。理由 —— 任务 2 的源是《Momcozy社媒账号盘点》里的官方账号，不是 UGC。
（第三方测评**不是不可用**，但那是另一个口径；要收得先定，见交付件。）

用法：python3 collect_youtube.py
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
CHANNEL = "https://www.youtube.com/@Momcozy"

#: 产品中文名 → (搜索词, 标题必须命中的 token)
SPEC = [
    ("S12 Pro+吸奶器",             "momcozy S12 Pro Quick breast pump", [r"s12\s*pro"]),
    ("M5Smart吸奶器",              "momcozy M5 Smart breast pump", [r"m5\s*smart", r"m5\b"]),
    ("Air1吸奶器",                 "momcozy Air 1 breast pump", [r"air\s*1\b"]),
    ("BS03全自动清洗消毒器",        "momcozy KleanPal Pro bottle washer", [r"kleanpal"]),
    ("BW-NDT清洗机天然成分洗涤剂片", "momcozy bottle washer detergent tablets", [r"detergent", r"tablet"]),
    ("BS03全自动清洗消毒器洗涤块",   "momcozy washing block kleanpal", [r"washing block"]),
    ("BM03婴儿监视器",             "momcozy BM03 baby monitor", [r"bm03", r"5\.5"]),
    ("BM08智能婴儿监视器",          "momcozy BM08 contact free baby monitor", [r"bm08", r"contact.?free"]),
    ("BM04婴儿监视器",             "momcozy BM04 baby monitor", [r"bm04"]),
]
PER_PRODUCT = 3        # 每个产品最多留几条（多图需要 ≥2 条缩略图）


def get(url, timeout=30, tries=3):
    for i in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout).read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and i < tries - 1:
                time.sleep(6 * (i + 1))
                continue
            raise


def official_channel_id():
    h = get(CHANNEL)
    m = re.search(r'"externalId":"(UC[\w-]{20,24})"', h) or re.search(r'"channelId":"(UC[\w-]{20,24})"', h)
    if not m:
        raise SystemExit("解析不到官方 channelId —— 不猜，停")
    return m.group(1)


def watch(vid):
    p = get(f"https://www.youtube.com/watch?v={vid}")
    def f(k):
        m = re.search(r'"' + k + r'":"((?:[^"\\]|\\.){0,4000}?)","', p)
        return m.group(1) if m else ""
    title = f("title")
    if not title:
        m = re.search(r'<meta name="title" content="([^"]*)"', p)
        title = m.group(1) if m else ""
    desc = f("shortDescription").encode().decode("unicode_escape", "ignore")
    return {"videoId": vid, "title": title.encode().decode("unicode_escape", "ignore"),
            "channelId": f("channelId"), "channel": f("ownerChannelName"),
            "uploadDate": (f("uploadDate") or "")[:10], "desc": desc,
            "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "url": f"https://www.youtube.com/watch?v={vid}"}


def main():
    os.makedirs("raw", exist_ok=True)
    oc = official_channel_id()
    print(f"官方频道 channelId = {oc}")
    out = []
    for name, q, tokens in SPEC:
        print(f"\n### {name}")
        h = get("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q))
        vids = list(dict.fromkeys(re.findall(r'"videoId":"([\w-]{11})"', h)))[:10]
        kept = []
        for vid in vids:
            if len(kept) >= PER_PRODUCT:
                break
            time.sleep(2)
            try:
                w = watch(vid)
            except Exception as e:                                 # noqa: BLE001
                print(f"   ⚠️ {vid} {type(e).__name__}")
                continue
            if w["channelId"] != oc:
                continue
            if not any(re.search(t, w["title"], re.I) for t in tokens):
                continue
            kept.append(w)
            print(f"   ✅ {w['uploadDate']} {w['title'][:64]}")
        if not kept:
            print("   ⚠️ 官方号内无该型号视频 → 该产品 YouTube 侧无素材")
        out.append({"产品中文名": name, "ok": bool(kept), "videos": kept, "query": q})
    json.dump(out, open("raw/youtube_products.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n落 raw/youtube_products.json ｜ 有素材的产品 {sum(1 for x in out if x['ok'])}/9")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())