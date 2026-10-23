#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官网 momcozy.com 采集（三品类：吸奶器 / 清洗机 / 婴儿监控器）。

数据来源：Shopify 的 `/products.json`（结构化、非页面猜测），逐个商品再取一次
商品页 HTML 补 `og:description`（body_html 为空的那几个 SKU 只有这里有文案）。

每条落：title / og_description / body 里的候选短句（≤50 与 ≤50 词两种口径都留着）
/ 首图 / 商品链接。**不在这里决定最终文案口径** —— 口径由 Owner 定，这里只备料。

用法：python3 collect_site.py
"""
import html
import json
import os
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

TYPE2CAT = {"Breast Pump": "吸奶器", "Washer": "清洗机", "Baby Monitor": "婴儿监控器"}

# 选品：每类挑「有真文案、且不是纯配件/纯 bundle」的主力 SKU（sku 清单来自 products.json 实读）
PICKS = [
    ("吸奶器", "8877403177158"),   # V3 Double Electric Breast Pump
    ("吸奶器", "9069974683846"),   # Air 1 + 120 bags
    ("吸奶器", "8905189621958"),   # M5 Smart + 120 bags
    ("清洗机", "9076837908678"),   # DeepClean Lite（body_html 空 → 靠商品页 og:description）
    ("婴儿监控器", "8828255666374"),  # BM08 Contact-Free
]


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def sentences(body):
    out = []
    for s in re.split(r"(?<=[.!?])\s+", body):
        s = s.strip()
        if 8 <= len(s) <= 400:
            out.append(s)
    return out


def main():
    prods = {str(p["id"]): p for p in json.load(open("raw/site_products_1.json", encoding="utf-8"))["products"]}
    rows = []
    for cat, pid in PICKS:
        p = prods[pid]
        url = f"https://momcozy.com/products/{p['handle']}"
        body = clean(p.get("body_html"))
        og = ""
        try:
            page = get(url).decode("utf-8", "ignore")
            m = re.search(r'<meta property="og:description" content="([^"]*)"', page)
            og = clean(m.group(1)) if m else ""
        except Exception as e:                                     # noqa: BLE001
            print(f"  ⚠️ og:description 取失败 {pid}: {type(e).__name__}")
        imgs = [i["src"] for i in (p.get("images") or [])]
        rows.append({
            "品类": cat,
            "产品线": cat,
            "sku_id": pid,
            "title": clean(p["title"]),
            "og_description": og,
            "body_chars": len(body),
            "sent_short": [s for s in sentences(body) if len(s) <= 50],       # 口径A：≤50 字符的完整句
            "sent_words": [s for s in sentences(body) if len(s.split()) <= 50],  # 口径B：≤50 词
            "first_sent": (sentences(body) or [""])[0],
            "image": imgs[0] if imgs else "",
            "image_count": len(imgs),
            "url": url,
            "published_at": (p.get("published_at") or "")[:10],
        })
        print(f"  ✅ {cat} {p['title'][:52]} | body={len(body)} | 短句候选={len(rows[-1]['sent_short'])} | og={len(og)}")
    json.dump(rows, open("raw/site_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n官网候选 {len(rows)} 条 → raw/site_rows.json")


if __name__ == "__main__":
    main()
