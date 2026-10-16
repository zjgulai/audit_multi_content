#!/usr/bin/env python3
"""把三个源的采集结果总装成 35 文案 + 35 图片 + 10 视频，并落成待写入的行。

产品线取值严格用库内受控词表：吸奶器 / 喂养电器 / 婴幼儿 / 家居 / 其他。
不做任何"补齐"：取不到就留空。
"""
import json, re, html, os, datetime

HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")

N_COPY, N_IMG, N_VIDEO = 35, 35, 10
N_AMZ_COPY = 15          # 只取有 bullet 的 Amazon 记录（有正文的才算真文案）
N_AMZ_IMG = 17

# ── 产品线映射：按顺序命中，先specific后general ──────────────────────────────
RULES = [
    ("喂养电器", ["bottle washer", "sterilizer", "bottle warmer", "bottle cleaner",
                  "formula dispenser", "milk modulator", "deepclean", "kleanpal",
                  "cleaning spray", "bottle brush", "drying rack"]),
    ("吸奶器", ["breast pump", "pumping", "wearable pump", "milk collector", "lactation",
                "nipple", "breast pad", "milk storage", "milk cooler", "flange",
                "breastmilk", "breast milk", "nursing pad", "milk bag"]),
    ("家居", ["maternity", "nursing bra", "bra ", "panties", "compression sock",
              "belly band", "home textile", "bedding", "pillow", "postpartum belt",
              "sleep bra", "underwear"]),
    ("婴幼儿", ["sleep sack", "swaddle", "baby monitor", "sound machine", "bassinet",
                "playard", "swing", "stroller", "carrier", "high chair", "teether",
                "oral care", "diaper", "wipe warmer", "wearable blanket", "baby",
                "newborn", "toddler", "infant", "kids"]),
]


def product_line(*texts):
    blob = " ".join(t or "" for t in texts).lower()
    for line, kws in RULES:
        if any(k in blob for k in kws):
            return line
    return "其他"


def clean_html(b):
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", b or "", flags=re.S | re.I)
    b = re.sub(r"</(p|div|h[1-6]|li|tr|table|br)>", "\n", b, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", b))


def paras(b, minlen=45):
    out = []
    for ln in clean_html(b).split("\n"):
        ln = re.sub(r"\s+", " ", ln).strip()
        if len(ln) >= minlen:
            out.append(ln)
    return out


def one_para(b, limit=900):
    ps = paras(b)
    s = " ".join(ps).strip()
    return s[:limit].strip()


def d(ts):
    return (ts or "")[:10]


AMZ_CATS = ["Industrial & Scientific", "Baby Products", "Health & Household",
            "Home & Kitchen", "Everything Else", "Tools & Home Improvement",
            "Sports & Outdoors", "Electronics", "Clothing, Shoes & Jewelry",
            "Baby", "Amazon Renewed"]


def clean_amz_title(t):
    """Amazon 移动页 <title> 会把类目缀在商品名后：'... 26 Spray Jets : Industrial & Scientific'。"""
    t = (t or "").strip()
    for c in AMZ_CATS:
        t = re.sub(r"\s*:\s*" + re.escape(c) + r"\s*$", "", t)
    return t.strip()


def main():
    rows = []

    # ══════════ 1. 官网 momcozy.com ══════════
    cols = json.load(open(os.path.join(RAW, "mc_collectionsjsonlimit250.json")))["collections"]
    prods = json.load(open(os.path.join(RAW, "mc_products.json")))["products"]

    # 文案候选：集合营销描述（过滤掉导航碎片 / 对比表残句）
    col_copy = []
    for c in cols:
        body = one_para(c.get("description", ""))
        if len(body) < 220:
            continue
        # 剔除明显是表格残句的（短句堆叠）
        if len(body) < 220:
            continue
        col_copy.append({
            "id": f"MC-WEB-COL-{c['handle']}",
            "title": c.get("title") or "",
            "text": body,
            "url": f"https://momcozy.com/collections/{c['handle']}",
            "date": d(c.get("published_at") or c.get("updated_at")),
            "line": product_line(c.get("title"), body),
        })
    col_copy.sort(key=lambda x: -len(x["text"]))

    # 图片候选：官网产品图（取每个产品首图）
    web_imgs = []
    for p in prods:
        im = p.get("images") or []
        if not im:
            continue
        web_imgs.append({
            "id": f"MC-WEB-IMG-{p['id']}",
            "alt": p.get("title") or "",
            "url": im[0].get("src"),
            "purl": f"https://momcozy.com/products/{p['handle']}",
            "date": d(p.get("published_at")),
            "line": product_line(p.get("title"), " ".join(p.get("tags") or []),
                                 p.get("product_type")),
        })
    web_imgs.sort(key=lambda x: x["date"], reverse=True)

    # ══════════ 2. Amazon ══════════
    amz_path = os.path.join(OUT, "amazon.json")
    amz = json.load(open(amz_path)) if os.path.exists(amz_path) else []
    amz_ok = [a for a in amz if a.get("ok")]
    amz_copy = [a for a in amz_ok if a.get("bullets")]
    amz_img = [a for a in amz_ok if a.get("images")]
    print(f"[amazon] 命中 {len(amz_ok)} 条；有 bullet {len(amz_copy)} 条；有校验过的图 {len(amz_img)} 条")

    # ══════════ 3. 组装 ══════════
    # ---- 文案 ----
    n_amz_copy = min(N_AMZ_COPY, len(amz_copy))
    n_web_copy = N_COPY - n_amz_copy
    for a in amz_copy[:n_amz_copy]:
        b = a["bullets"][2] if len(a["bullets"]) > 2 else a["bullets"][0]
        at = clean_amz_title(a["title"])
        text = f"{at}\n\n{b}\n\n—— 来源：{a['url']}"
        rows.append({
            "内容类型": "文案", "渠道": "Amazon", "内容 ID": f"MC-AMZ-{a['asin']}",
            "产品线": product_line(a["title"], " ".join(a["bullets"])),
            "发布时间": "", "采集数据": text, "_url": a["url"],
        })
    for c in col_copy[:n_web_copy]:
        rows.append({
            "内容类型": "文案", "渠道": "官网", "内容 ID": c["id"],
            "产品线": c["line"], "发布时间": c["date"],
            "采集数据": f"{c['title']}\n\n{c['text']}\n\n—— 来源：{c['url']}",
            "_url": c["url"],
        })

    # ---- 图片 ----
    n_amz_img = min(N_AMZ_IMG, len(amz_img))
    for a in amz_img[:n_amz_img]:
        rows.append({
            "内容类型": "图片", "渠道": "Amazon", "内容 ID": f"MC-AMZ-{a['asin']}-IMG",
            "产品线": product_line(a["title"], " ".join(a["bullets"])),
            "发布时间": "",
            "采集数据": f"{a['images'][0]}\n\n图注：{clean_amz_title(a['title'])}\n来源页：{a['url']}",
            "_url": a["url"],
        })
    for w in web_imgs[:N_IMG - n_amz_img]:
        rows.append({
            "内容类型": "图片", "渠道": "官网", "内容 ID": w["id"],
            "产品线": w["line"], "发布时间": w["date"],
            "采集数据": f"{w['url']}\n\n图注：{w['alt']}\n来源页：{w['purl']}",
            "_url": w["purl"],
        })

    # ---- 视频 ----
    yt_path = os.path.join(OUT, "youtube.json")
    yt = json.load(open(yt_path)) if os.path.exists(yt_path) else []
    yt = [v for v in yt if v.get("title")]
    for v in yt[:N_VIDEO]:
        line = product_line(v["title"])
        thumb = v.get("thumb") or f"https://i.ytimg.com/vi/{v['videoId']}/hqdefault.jpg"
        rows.append({
            "内容类型": "视频", "渠道": "YouTube", "内容 ID": f"MC-YT-{v['videoId']}",
            "产品线": line, "发布时间": d(v.get("uploadDate")),
            "采集数据": (f"{v['title']}\n{v['url']}\n缩略图：{thumb}"
                       + (f"\n发布：{v['uploadDate']}" if v.get("uploadDate") else "")),
            "_url": v["url"],
        })

    json.dump(rows, open(os.path.join(OUT, "rows.json"), "w"), ensure_ascii=False, indent=1)

    # ---- 自检 ----
    from collections import Counter
    c = Counter(r["内容类型"] for r in rows)
    print("总计:", len(rows), dict(c))
    for t, want in [("文案", N_COPY), ("图片", N_IMG), ("视频", N_VIDEO)]:
        got = c.get(t, 0)
        print(f"  {t}: {got}/{want} {'OK' if got == want else '<<< 不足'}")
    print("渠道分布:", dict(Counter(r["渠道"] for r in rows)))
    print("产品线分布:", dict(Counter(r["产品线"] for r in rows)))
    noline = [r["内容 ID"] for r in rows if not r["产品线"]]
    print("产品线为空:", noline[:10], "共", len(noline))


if __name__ == "__main__":
    main()
