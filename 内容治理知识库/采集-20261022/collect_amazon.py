#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Amazon 采集（三品类，只取 amazon.com 美国站）。

沿用 2026-10-13 那一版的三条纪律（上一轮就是靠它们拦下 3 个真缺陷）：
1. **品牌校验**：页面标题必须含 Momcozy，否则剔除 —— 上一轮 23 个 ASIN 里有 5 个是
   `Amazon Gift Card Balance Reload` 这类诱饵页。
2. **图片只认 `._AC_<尺寸>_.jpg` 后缀** —— `m.media-amazon.com/images/I/` 下多数 ID 是
   CSS/JS 资源，长得一模一样，直接重建 URL 会全是 404。
3. **剥掉标题尾部的类目后缀**（` : Industrial & Scientific`）。

用法：python3 collect_amazon.py
"""
import collections
import json
import os
import re
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

QUERIES = {
    "吸奶器": "momcozy+breast+pump",
    "清洗机": "momcozy+bottle+washer",
    "婴儿监控器": "momcozy+baby+monitor",
}
CAT_RE = re.compile(r"\s*:\s*[A-Z][A-Za-z &,\-]{2,40}$")


def get(u, t=30, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=t) as r:
                return r.read()
        except Exception:                                          # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(2 + i * 2)
    return b""


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def enum_asins():
    out = {}
    for cat, q in QUERIES.items():
        b = get(f"https://www.amazon.com/s?k={q}")
        asins = list(dict.fromkeys(a.decode() for a in re.findall(rb'data-asin="(B0[A-Z0-9]{8})"', b)))
        out[cat] = asins
        print(f"  {cat:8s} 搜到 ASIN {len(asins)} 个")
    json.dump(out, open("raw/asins.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


def parse_page(b, asin):
    txt = b.decode("utf-8", "ignore")
    t = re.search(r'id="productTitle"[^>]*>(.*?)</span>', txt, re.S)
    title = clean(clean(t.group(1))) if t else ""
    if "momcozy" not in title.lower():
        return None                                                # 品牌校验
    title = CAT_RE.sub("", title)
    bullets = []
    for m in re.finditer(r'id="feature-bullets".*?</div>', txt, re.S):
        for li in re.finditer(r"<li[^>]*>(.*?)</li>", m.group(0), re.S):
            s = clean(li.group(1))
            if 20 < len(s) < 600:
                bullets.append(s)
    img = re.search(r'"hiRes":"(https://m\.media-amazon\.com/images/I/[^"]+)"', txt)
    if not img:
        img = re.search(r'(https://m\.media-amazon\.com/images/I/[A-Za-z0-9\-\._]+?\._AC_[^"]*?\.jpg)', txt)
    src = img.group(1) if img else ""
    if src and not re.search(r"\._AC_[^/]*\.jpg$", src):
        src = ""                                                   # 只认真商品图后缀
    return {"asin": asin, "title": title, "bullets": bullets[:6], "img": src,
            "url": f"https://www.amazon.com/dp/{asin}"}


def main():
    os.makedirs("raw/amazon", exist_ok=True)
    asins = json.load(open("raw/asins.json", encoding="utf-8")) if os.path.exists("raw/asins.json") else enum_asins()
    rows = []
    for cat, ids in asins.items():
        keep = 0
        for asin in ids[:12]:
            fp = f"raw/amazon/{asin}.json"
            if os.path.exists(fp):
                d = json.load(open(fp, encoding="utf-8"))
            else:
                try:
                    d = parse_page(get(f"https://www.amazon.com/dp/{asin}"), asin)
                except Exception as e:                             # noqa: BLE001
                    print(f"    ⚠️ {asin} {type(e).__name__}")
                    continue
                if d:
                    json.dump(d, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
            if not d:
                print(f"    ✗ {asin} 品牌校验没过（剔除）")
                continue
            rows.append({"cat": cat, **d})
            keep += 1
            print(f"    ✅ {cat} {asin} {d['title'][:56]}")
        print(f"  {cat}: 确认 Momcozy 商品 {keep} 个 / 试了 {min(len(ids),12)} 个")
    json.dump(rows, open("raw/amazon_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nAmazon 确认商品 {len(rows)} 个 | 按品类 {dict(collections.Counter(r['cat'] for r in rows))}")
    print("  有 bullet:", sum(1 for r in rows if r["bullets"]), "| 有主图:", sum(1 for r in rows if r["img"]))


if __name__ == "__main__":
    main()
