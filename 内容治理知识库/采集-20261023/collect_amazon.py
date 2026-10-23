#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Amazon 采集（只取 amazon.com 美国站，9 个产品）。

## 为什么改成「显式 ASIN 映射」而不是搜索发现

第一版走「搜索 → 按标题挑」，实测**两个方向都错**：
1. **标题提取错**：Amazon 搜索结果里 `<h2>` 只有品牌行（就一个词「Momcozy」），
   真标题在 `aria-label` 里 ⇒ 第一版标题全是 "Momcozy"、品牌校验把 9 个产品**全误剔除**。
2. **品牌校验弱**：改成「标题含 momcozy」后又**错放了第三方配件** ——
   `14Pack Breast Pump Parts Compatible with momcozy S9 Pro`、
   `Momcozy Air 1 Duckbill Valves`（都是配件，不是本体）。
   而且搜索页会被限流（候选数 29 → 24 → 0，不报错、只是变空）。

⇒ 现在**不靠搜索发现**：ASIN 来自**已核过的两个来源**，本脚本只做「取回 + 逐条复核」：
  · `采集-20261022/raw/amazon_rows.json`（上一批 26 条，当时已做品牌校验）；
  · 本批手工直试 dp 页验过的（`B0G4D8P3VS`=BM03、`B0GQBCFBJR`=洗涤剂片）。
**取不到就落 ok=False**，不拿近似品顶替。

## 复核三条（缺一条即剔除，落 ok=False 并记原因）
1. **品牌**：`id="bylineInfo"` 必须含 `Momcozy`（≈ "Visit the Momcozy Store"）
   —— **不看标题**：第三方「for Momcozy」配件标题里也有这三个字。
2. **型号 token** 必须命中（如 `s12 pro` / `kleanpal` / `5.5`+`no wifi`）。
3. **配件排除词**必须不命中（parts / valve / compatible / replacement / duckbill / flange …）。

## 慢速
实测请求打密了会被限流（表现为「结果变空」而非报错）⇒ 每次请求间隔 `SLEEP` 秒。

用法：python3 collect_amazon.py
"""
import html
import json
import os
import re
import sys
import time
import urllib.request

SLEEP = 12          # 秒；别调小 —— 打了密就被限流，且**限流不报错、只变空**
HDRS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="120", "Not:A-Brand";v="24"',
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document", "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none", "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}

#: 产品中文名 → (候选 ASIN 列表（按优先序）, 必须命中的 token 任一, 必须同时命中, 排除)
SPEC = [
    ("S12 Pro+吸奶器",             ["B0D4QV8DSP"], [r"s12\s*pro"], [], []),
    ("M5Smart吸奶器",              ["B0FHQJWPTN", "B0G647K9TN"], [r"m5\s*smart"], [], []),
    ("Air1吸奶器",                 ["B0FW4XC8MG"], [r"air\s*1\b"], [], []),
    ("BS03全自动清洗消毒器",        ["B0FFN1RJ8V", "B0CWLHKQNT"], [r"kleanpal"], [], []),
    ("BW-NDT清洗机天然成分洗涤剂片", ["B0GQBCFBJR"], [r"detergent tablet", r"cleaning tablet"], [], []),
    ("BS03全自动清洗消毒器洗涤块",   ["B0FZHZG1GC", "B0FZJ5TPYY", "B0G648DM5H"], [r"washing block"], [], []),
    ("BM03婴儿监视器",             ["B0G4D8P3VS"], [r"bm03", r"no\s*wifi"], [r"5\.?5"], []),
    ("BM08智能婴儿监视器",          ["B0GJ8PJQT8", "B0GJ89DMYC"], [r"bm08", r"contact-?free"], [], []),
    ("BM04婴儿监视器",             ["B0DR18KGBW"], [r"bm04"], [], []),
]
#: 配件/第三方排除词 —— 这些词出现即**不是本体**（第一版就是被它们骗过）
ACCESSORY = re.compile(r"\b(parts?|valve|valves|duckbill|compatible|replacement|"
                       r"membrane|tubing|refill|adapter)\b", re.I)
CAT_RE = re.compile(r"\s*:\s*[A-Z][A-Za-z &,\-]{2,40}$")
IMGID_RE = re.compile(r"m\.media-amazon\.com/images/I/([A-Za-z0-9+%\-]+)\._")
MP4_RE = re.compile(r"https://[^\"'\\ ]+?\.mp4")


def get(url, timeout=35, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HDRS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and i < tries - 1:
                time.sleep(20 * (i + 1))
                continue
            raise


def visible(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    return re.sub(r"[ \t\u00a0]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def dp(asin):
    h = get(f"https://www.amazon.com/dp/{asin}")
    t = re.search(r'id="productTitle"[^>]*>([^<]+)', h)
    title = CAT_RE.sub("", html.unescape(t.group(1)).strip()) if t else ""
    by = re.search(r'id="bylineInfo"[^>]*>(.*?)</a>', h, re.S)
    byline = re.sub(r"\s+", " ", visible(by.group(1))) if by else ""
    bl = re.search(r'id="feature-bullets"(.*?)</div>\s*</div>', h, re.S)
    bullets = []
    if bl:
        for li in re.findall(r"<li[^>]*>(.*?)</li>", bl.group(1), re.S):
            v = visible(li)
            if v and len(v) > 8:
                bullets.append(v)
    # ★★ 图片只认 `"hiRes"` —— 这是**商品图库**（39 张 vs 全页 150 个 `images/I/` 链接）。
    #   第一版抓全页 `m.media-amazon.com/images/I/<id>._` 是**错的**：8 个产品的
    #   「第一张图」全是同一个 `215CM2Cgm9L`（页面 chrome / 广告位 / 推荐位），
    #   等于把站内通用素材当成了各产品的主图。真请求验证时 8/8 首图相同才暴露。
    imgs = list(dict.fromkeys(re.findall(r'"hiRes":"([^"]+)"', h)))
    # ★★ 视频：解析 `ImageBlockATF` 里的 videos JSON 数组；`videos[].url` 是**真 mp4**
    #   （实测 200 video/mp4）。**不要**用页面里其它 `.mp4` —— 那些是
    #   `default.jobtemplate.mp4` 模板占位（实测 404），或字幕/预览件。
    vids = []
    m = re.search(r"'videos':\s*A\.\$\.parseJSON\('(\[.*?\])'\)", h, re.S)
    if m:
        try:
            for v in json.loads(m.group(1).replace("\\'", "'")):
                u = (v.get("url") or "").replace("\\/", "/")
                # 只留**可播放**的 mp4：`….jobtemplate.mp4.<档位>.mp4` 实测 200；
                # `…videopreview.jobtemplate.mp4` 实测 **404**（模板占位），一律丢掉。
                if u and re.search(r"\.jobtemplate\.mp4\.\d+\.mp4$", u):
                    vids.append({"url": u, "title": v.get("title", ""),
                                 "duration": v.get("durationSeconds"), "thumb": v.get("thumb", "")})
        except Exception as e:                                     # noqa: BLE001
            print(f"   ⚠️ videos JSON 解析失败：{e}")
    return {"title": title, "byline": byline, "bullets": bullets,
            "imgs": imgs, "videos": vids, "link": f"https://www.amazon.com/dp/{asin}"}


def main():
    os.makedirs("raw", exist_ok=True)
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    prev = {}
    if only and os.path.exists("raw/amazon_products.json"):
        prev = {x["产品中文名"]: x for x in json.load(open("raw/amazon_products.json", encoding="utf-8"))}
    out = []
    first = True
    for name, asins, must, also, deny in SPEC:
        if only and not any(o in name for o in only):
            if name in prev:
                out.append(prev[name])
            continue
        print(f"\n### {name}")
        rec = None
        for asin in asins:
            if not first:
                time.sleep(SLEEP)
            first = False
            try:
                d = dp(asin)
            except Exception as e:                                 # noqa: BLE001
                print(f"   ⚠️ {asin} 取不到：{type(e).__name__} {str(e)[:50]}")
                continue
            tt = (d["title"] + " " + d["byline"]).lower()
            if "momcozy" not in d["byline"].lower():
                print(f"   ✗ {asin} byline 非 Momcozy Store（{d['byline'][:38]!r}）→ 剔")
                continue
            if not any(re.search(m, tt, re.I) for m in must):
                print(f"   ✗ {asin} 型号 token 未命中：{d['title'][:52]}")
                continue
            if also and not all(re.search(m, tt, re.I) for m in also):
                print(f"   ✗ {asin} 附加条件未命中：{d['title'][:52]}")
                continue
            acc = ACCESSORY.search(d["title"])
            if acc:
                print(f"   ✗ {asin} 命中配件/第三方排除词 «{acc.group(0)}»：{d['title'][:52]}")
                continue
            rec = {"产品中文名": name, "ok": True, "asin": asin, "byline": d["byline"],
                   "标题": d["title"], "bullets": d["bullets"], "图片": d["imgs"],
                   "视频": d["videos"], "链接": d["link"]}
            print(f"   ✅ {asin}  {d['title'][:56]}")
            print(f"      图={len(d['imgs'])} 视频={len(d['videos'])} bullet={len(d['bullets'])}")
            break
        if not rec:
            print("   ⚠️ 全部候选未通过复核 → ok=False（不拿近似品顶替）")
            rec = {"产品中文名": name, "ok": False,
                   "reason": "候选 ASIN 均未通过品牌/型号/配件复核", "tried": asins}
        out.append(rec)

    json.dump(out, open("raw/amazon_products.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n落 raw/amazon_products.json（{len(out)} 条，成功 {sum(1 for x in out if x.get('ok'))}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())