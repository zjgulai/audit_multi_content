#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总装官网 70 行（文案 35 + 图片 35），三类各占配额。

三条口径（每条都有理由，别随手改）：
1. **产品线映射回库内受控词表** —— 库内实读所得只有 `吸奶器/喂养电器/婴幼儿/家居/其他`。
   本轮三类 → `吸奶器`→吸奶器、`清洗机`→喂养电器、`婴儿监控器`→婴幼儿。
   **不自创新值**（上次 80 行就是这么做并且通过的）。
2. **采集数据 = 可审的原文** —— 文案取「标题 + 商品页正文」，图片取原图 URL（非缩略图）。
   每条末尾附 `—— 来源：<url>`，供回源。
3. **不碰人/引擎字段** —— `审核人` / `Agent 结论` / `置信度` / `报告链接` 一个都不写。

用法：python3 build_site_rows.py
"""
import html
import json
import os
import re

import collections

CATS = {
    "吸奶器": ("吸奶器", 15),
    "清洗机": ("喂养电器", 10),
    "婴儿监控器": ("婴幼儿", 10),
}


def plain(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h or "", flags=re.S | re.I)
    h = re.sub(r"<(title|h1|h2|h3|h4|p|li|br|/p|/li|/h1|/h2|/h3|/h4|/tr)[^>]*>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    return re.sub(r"\n{2,}", "\n", html.unescape(h)).strip()


def main():
    site = json.load(open("raw/site_products.json", encoding="utf-8"))
    pages = {}
    for f in os.listdir("raw/products"):
        if f.endswith(".json"):
            try:
                d = json.load(open(f"raw/products/{f}", encoding="utf-8"))
                pages[d.get("handle")] = d
            except Exception:                                      # noqa: BLE001
                pass
    print(f"商品页可用: {len(pages)}")

    # 每个集合商品 → 带正文的候选，按正文长度降序
    cand = {}
    for cat, (_, _n) in CATS.items():
        items = []
        for p in site.get(cat, []):
            d = pages.get(p["handle"])
            if not d:
                continue
            body = plain(d.get("body_html"))
            if len(body) < 120:            # 太短的不算「可审文案」
                continue
            items.append((len(body), d))
        items.sort(key=lambda x: -x[0])
        cand[cat] = items
        print(f"  {cat}: 有正文候选 {len(items)} 个（最长 {items[0][0] if items else 0} 字）")

    rows = []
    for cat, (pline, quota) in CATS.items():
        items = cand[cat]
        if not items:
            print(f"⚠️ {cat} 无可审文案候选")
            continue
        # 文案：取前 quota 个（正文长的优先）
        for i, (_ln, d) in enumerate(items[:quota], 1):
            title = html.unescape(d.get("title") or "")
            body = plain(d.get("body_html"))
            url = f"https://momcozy.com/products/{d['handle']}"
            rows.append({
                "内容类型": "文案",
                "渠道": "官网",
                "内容 ID": f"MC-SITE-{cat}-T{i:02d}",
                "产品线": pline,
                "发布时间": (d.get("published_at") or "")[:19],
                "采集数据": f"{title}\n\n{body[:1500]}\n\n—— 来源：{url}",
                "_url": url,
            })
        # 图片：取 quota 个商品的首图（原图 src，非缩略图）
        imgs = [(d, (d.get("images") or [])) for _l, d in items if (d.get("images") or [])]
        for i, (d, imgs_) in enumerate(imgs[:quota], 1):
            src = imgs_[0].get("src") or ""
            rows.append({
                "内容类型": "图片",
                "渠道": "官网",
                "内容 ID": f"MC-SITE-{cat}-P{i:02d}",
                "产品线": pline,
                "发布时间": (d.get("published_at") or "")[:19],
                "采集数据": f"{html.unescape(d.get('title') or '')}\n商品主图：{src}\n\n—— 来源：https://momcozy.com/products/{d['handle']}",
                "_url": src,
            })

    json.dump(rows, open("out_site_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n官网行数: {len(rows)}")
    print(" 内容类型:", dict(collections.Counter(r["内容类型"] for r in rows)))
    print(" 产品线  :", dict(collections.Counter(r["产品线"] for r in rows)))
    print(" 品类    :", dict(collections.Counter(r["内容 ID"].split("-")[2] for r in rows)))
    print("已写 out_site_rows.json")


if __name__ == "__main__":
    main()
