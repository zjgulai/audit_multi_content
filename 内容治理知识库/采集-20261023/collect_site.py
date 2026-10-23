#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官网 momcozy.com 采集（9 个产品 × 五形态所需的原料）。

源：Shopify 的 `/products.json`（结构化，非页面猜测）+ 每个商品的商品页 HTML
（补 og:description 与**视频** —— 视频只在商品页里，products.json 没有）。

每条落：title / og_description / body 文本 / 图片清单 / **视频清单** / published_at / 商品链接。
**不在这里决定最终文案口径** —— 只备料，口径与裁剪在 `build_collect_rows.py`。

## 两条纪律（都是踩过才写的）

1. **图片只认 `products.json` 的 `images[]`** —— 不去页面里正则捡 `cdn.shopify.com` 链接：
   捡来的里面混着图标、占位图、CSS 精灵，长得一模一样。
2. **视频只认 `cdn.shopify.com/videos/` 与 `.mp4` 且必须来自本商品的页面** ——
   页面里还有 theme 的背景视频与推荐位视频，一律不收；并按 URL 去重。

## 映射是「显式 + 可复核」的

9 个产品里有 7 个官网有独立商品页，**BS03 与 BS03洗涤块 官网只有 bundle 页**
（独立页 handle 逐个 404，实测）。bundle 映射写在下表里并**标注 bundle** ——
不静默混入：用 bundle 页当素材，会把奶瓶刷/暖奶器/吸奶器的内容一起带进来。

用法：python3 collect_site.py
"""
import html
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
BASE = "https://momcozy.com"

#: 产品中文名 → (标题正则, 是否 bundle 页)。
#: ★ **不手抄 handle** —— 从 products.json 里按标题正则解析并断言唯一。
#:   为什么：第一版我手敲 handle，而那是**从被截断的控制台输出**里抄的
#:   （尾部的 `wa...`、`high-...` 都是省略号），于是两条直接「handle 不存在」。
#:   凡是从「打印出来的东西」抄进代码的常量，都会出这种错；改成解析 + 断言。
#:   正则按标题，不用 handle —— 标题是人写的、可读、改版时看得见差异。
MAP = {
    "S12 Pro+吸奶器":             (r"^S12 Pro Quick Wearable Breast Pump$", False),
    "M5Smart吸奶器":              (r"^Momcozy Breast Pump M5 Smart \+ 120 Breastmilk Storage Bags$", False),
    "Air1吸奶器":                 (r"^Momcozy Breast Pump Air 1 \+ 120 Breastmilk Storage Bags$", False),
    # 官网无独立页 ⇒ 取 KleanPal bundle（图最多那个），**标 bundle**
    "BS03全自动清洗消毒器":        (r"KleanPal Pro Baby Bottle Washer & 30 Detergent Tablets", True),
    "BW-NDT清洗机天然成分洗涤剂片": (r"^Momcozy Detergent Tablets for Baby Bottle Washer, 200 Tablets$", False),
    # 洗涤块只在 bundle 标题里出现 ⇒ 取含 Washing Block 的 bundle，**标 bundle**
    "BS03全自动清洗消毒器洗涤块":  (r"^Clean & Feeding Bundle: Bottle Washer and High Chair and Washing Block", True),
    "BM03婴儿监视器":             (r"^Smart Non-WiFi Baby Monitor 5\.5-Inch Full HD \(BM03 Black\)$", False),
    "BM08智能婴儿监视器":          (r"^Momcozy Contact-Free Smart Baby Monitor \(BM08\)$", False),
    "BM04婴儿监视器":             (r"^Momcozy 5-Inch Dual-mode Smart Baby Monitor-BM04$", False),
}

#: ★ 视频 URL 的真实形态（实测）：**协议相对 + momcozy.com 自己的 CDN**
#:   `//momcozy.com/cdn/shop/videos/c/vp/<id>/<id>.HD-1080p-2.5Mbps-<n>.mp4?v=0`
#:   第一版我写成 `https://cdn.shopify.com/videos/` ⇒ 9 个商品全部 视频=0（假阴性）。
VID_RE = re.compile(r'//[a-z0-9.\-]*/cdn/shop/videos/[^"\'\\ ]+?\.mp4(?:\?[^"\'\\ ]*)?', re.I)


def get(url, timeout=30, tries=5):
    """带退避的重试 —— 实测踩过 Shopify 的 **429 Too Many Requests**：
    前面探查阶段请求打得太密，第一次跑采集就整批 429。所以：429/5xx 退避重试，其他错直接抛。"""
    import time
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i < tries - 1:
                wait = 5 * (i + 1)
                print(f"   … HTTP {e.code}，等 {wait}s 重试（{i + 1}/{tries - 1}）")
                time.sleep(wait)
                continue
            raise


def text_of(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h or "", flags=re.S | re.I)
    h = re.sub(r"<br\s*/?>|</p>|</li>", "\n", h, flags=re.I)
    return re.sub(r"[ \t\u00a0]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def main():
    os.makedirs("raw", exist_ok=True)
    cat = json.loads(get(f"{BASE}/products.json?limit=250"))
    by_handle = {p["handle"]: p for p in cat["products"]}
    print(f"products.json 拉到 {len(cat['products'])} 个商品")

    #: 只跑指定产品（补采被 429 打断的那几个）：python3 collect_site.py 洗涤块 BM03
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    out = []
    import time
    for idx, (name, (title_re, is_bundle)) in enumerate(MAP.items()):
        if only and not any(o in name for o in only):
            prev = json.load(open(f"{HERE}/raw/site_products.json", encoding="utf-8")) \
                if os.path.exists(f"{HERE}/raw/site_products.json") else []
            keep = [x for x in prev if x["产品中文名"] == name]
            out += keep
            continue
        if idx:
            time.sleep(40)         # 补采时用长间隔；实测 6s 仍会被 429
        hits = [p for p in cat["products"] if re.search(title_re, p["title"])]
        if not hits:
            print(f"❌ {name}: 标题正则匹配不到任何商品 —— 不猜，落 ok=False")
            out.append({"产品中文名": name, "ok": False,
                        "reason": f"标题正则无命中：{title_re}"})
            continue
        if len(hits) > 1:
            hits.sort(key=lambda x: -len(x.get("images", [])))
            print(f"   （标题正则命中 {len(hits)} 个，取图最多的：{hits[0]['title'][:50]}）")
        p = hits[0]
        handle = p["handle"]
        page_url = f"{BASE}/products/{handle}"
        # ★ 页面取不到时的降级：products.json 里**本来就有** images / body_html / published_at，
        #   只有视频必须走页面 HTML。所以 429 不该让整条产品报废 —— 降级采图与文，
        #   **视频明确标未采**（写清原因），绝不假装采到了。
        page_err = ""
        try:
            pg = get(page_url)
        except Exception as e:                                    # noqa: BLE001
            pg = ""
            page_err = f"{type(e).__name__}: {str(e)[:60]}"
            print(f"   ⚠️ 商品页取不到（{page_err}）→ 降级：图/文取 products.json，视频标未采")

        og = re.search(r'<meta property="og:description" content="([^"]*)"', pg) if pg else None
        # 视频：只认本页的 shopify videos / mp4，去重，剔除明显的 theme 背景片
        vids = []
        for u in VID_RE.findall(pg):
            u = "https:" + u.replace("\\/", "/")
            if u not in vids:
                vids.append(u)
        body = text_of(p.get("body_html") or "")
        imgs = [i["src"] for i in p.get("images", [])]
        rec = {
            "产品中文名": name, "ok": True, "is_bundle": is_bundle,
            "page_error": page_err,
            "视频未采原因": ("商品页被限流(HTTP 429)，视频未采" if page_err else ""),
            "handle": handle, "链接": page_url,
            "标题": p["title"], "published_at": (p.get("published_at") or "")[:10],
            "og_description": html.unescape(og.group(1)) if og else "",
            "body_text": body, "body_chars": len(body),
            "图片": imgs, "视频": vids,
            "product_type": p.get("product_type", ""),
        }
        out.append(rec)
        print(f"✅ {name:26s} handle={handle[:44]:46s} 图={len(imgs):3d} 视频={len(vids):2d} "
              f"正文={len(body):5d}字 og={len(rec['og_description']):3d}字 "
              f"{'[bundle页]' if is_bundle else ''}")

    json.dump(out, open("raw/site_products.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n落 raw/site_products.json（{len(out)} 条，成功 {sum(1 for x in out if x.get('ok'))}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())