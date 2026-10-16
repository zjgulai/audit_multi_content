#!/usr/bin/env python3
"""按「三类 + 美国」重建采集集：吸奶器 / 清洗机 / 婴儿监控器，35 文案 / 35 图片 / 10 视频。

美国口径（三条硬规则，逐条可核）：
  · Amazon —— 一律 https://www.amazon.com/dp/<ASIN>（美国站）
  · 官网   —— momcozy.com 的默认市场（currency=USD / locale=en），
              且**排除 10 个地区专属集合**（CA/UK/FR/EU，实测清单见 REGION_COLS）
  · YouTube—— Momcozy 官方频道，**排除欧洲内容**（Cologne Baby Show）

产品线字段：直接用 Owner 点名的三个词 —— 吸奶器 / 清洗机 / 婴儿监控器。
"""
import json, re, html, os, collections

HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")

TARGET = {("文案"): 35, ("图片"): 35, ("视频"): 10}
PER_CAT = {  # (文案, 图片, 视频)
    "吸奶器": (15, 15, 4),
    "清洗机": (12, 12, 3),
    "婴儿监控器": (8, 8, 3),
}

# 实测得到的地区专属集合 handle —— 美国口径要排掉它们
REGION_COLS = {"baby-care-fr", "weekly-deals-fr-copy", "bundle-sale-copy",
               "buy-more-save-more-ca", "buy-more-save-more-ca-copy", "baby-care-copy",
               "ca-featured-breast-pumps", "ca-nasal-aspirator", "new-in-ca",
               "maternity-pillow-eu"}
REGION_VIDS = {"_xyLF4_AgAw"}   # Come With Us to the Cologne Baby Show 2026


def txt(b):
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", b or "", flags=re.S | re.I)
    b = re.sub(r"</(p|div|h[1-6]|li|tr|table)>", "\n", b, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", b))


def paras(b, minlen=45):
    return [re.sub(r"\s+", " ", x).strip()
            for x in txt(b).split("\n") if len(re.sub(r"\s+", " ", x).strip()) >= minlen]


def one_para(b, limit=900):
    return " ".join(paras(b)).strip()[:limit].strip()


def cat_of(t):
    """三类口径（收紧版）——只认"机/泵/监控器"本体及其直接配件。

    明确排除（它们不属于这三个品类）：
      · 温奶器 / 储奶袋 / 储奶 cooler  → 喂养与储奶，不是吸奶器
      · 奶瓶刷 / 干燥架 / 滤芯 / 清洗片 → 清洗耗材，不是清洗机
      · 防溢乳垫 / 乳头霜 / 哺乳内衣    → 哺乳护理与服饰
    """
    t = (t or "").lower()
    if any(k in t for k in ["baby monitor", "video monitor", "baby camera",
                            "monitor add-on", "add-on camera"]):
        return "婴儿监控器"
    if any(k in t for k in ["bottle washer", "steriliz", "deepclean", "kleanpal",
                            "bottle cleaner"]):
        return "清洗机"
    if any(k in t for k in ["breast pump", "wearable pump", "pumping bra",
                            "breast pump flange", "pump parts", "hands-free pump"]):
        return "吸奶器"
    return None


def cat_of_video(t):
    """视频标题是营销语，不是商品名 —— 用更宽的口径判定它讲的是哪个品类。"""
    t = (t or "").lower()
    if any(k in t for k in ["baby monitor", "video monitor", "baby camera", "bm0", "bm1"]):
        return "婴儿监控器"
    if any(k in t for k in ["bottle washer", "steriliz", "deepclean", "kleanpal",
                            "bottle clean"]):
        return "清洗机"
    if any(k in t for k in ["breast pump", "breastpump", "wearable pump", "pumping",
                            "lactation", "breastfeed", "milk supply", "letdown", "latch"]):
        return "吸奶器"
    return None


def prio(t, cat):
    """同一品类内的优先级：越"本体"越靠前，配件靠后。"""
    t = (t or "").lower()
    if cat == "清洗机":
        if any(k in t for k in ["bottle washer", "steriliz"]):
            return 0
        return 2                      # 滤芯/刷子等
    if cat == "吸奶器":
        if "breast pump" in t or "wearable pump" in t:
            return 0
        return 2                      # pumping bra 等配件
    return 0


def amz_title(t):
    t = (t or "").strip()
    for c in ["Industrial & Scientific", "Baby Products", "Health & Household",
              "Home & Kitchen", "Everything Else", "Electronics", "Baby"]:
        t = re.sub(r"\s*:\s*" + re.escape(c) + r"\s*$", "", t)
    return t.strip()


def main():
    prods = json.load(open(os.path.join(RAW, "mc_products.json")))["products"]
    cols = json.load(open(os.path.join(RAW, "mc_collectionsjsonlimit250.json")))["collections"]
    # ── Amazon：三个来源合并，同一 ASIN 取 bullet 最多的那一版 ──────────
    #   amazon.json          —— 首轮（移动 UA，部分带 bullet）
    #   amazon_us2.json      —— 扩充 37 个 ASIN（移动 UA，无 bullet）
    #   amazon_bullets.json  —— 桌面 UA 重抓，bullet 最全
    def _load(name):
        p = os.path.join(OUT, name)
        return json.load(open(p)) if os.path.exists(p) else []

    bullets_map = _load("amazon_bullets.json")          # dict: asin -> rec
    _fi = os.path.join(OUT, "amz_first_img.json")
    FIRST_IMG = json.load(open(_fi)) if os.path.exists(_fi) else {}
    pool = _load("amazon.json") + _load("amazon_us2.json") + list(bullets_map.values())
    best = {}
    for a in pool:
        asin = a.get("asin")
        if not asin:
            continue
        if not (a.get("ok") or a.get("is_momcozy")):
            continue
        cur = best.get(asin)
        if cur is None or len(a.get("bullets") or []) > len(cur.get("bullets") or []):
            best[asin] = a
    print(f"Amazon 合并后 {len(best)} 个 ASIN，其中 {sum(1 for v in best.values() if v.get('bullets'))} 个有 bullet")

    amz_copy = collections.defaultdict(list)
    amz_img = collections.defaultdict(list)
    for a in best.values():
        cat = cat_of(a.get("title", ""))
        if not cat:
            continue
        a = dict(a); a["ok"] = True
        amz_copy[cat].append(a)
        if a.get("images"):
            amz_img[cat].append(a)
    for _c in amz_copy:
        amz_copy[_c].sort(key=lambda a: (prio(a.get("title"), _c),
                                         0 if a.get("bullets") else 1))
        amz_img[_c].sort(key=lambda a: prio(a.get("title"), _c))
    print("Amazon US 命中:", {k: len(v) for k, v in amz_copy.items()})

    # ── 官网：排除地区集合 ────────────────────────────────────────────
    web_col = collections.defaultdict(list)
    for c in cols:
        if c["handle"] in REGION_COLS:
            continue
        cat = cat_of(c.get("title"))
        if not cat:
            continue
        body = one_para(c.get("description", ""))
        if len(body) < 220:
            continue
        web_col[cat].append({"prio": prio(c.get("title"), cat), "handle": c["handle"], "title": c.get("title"),
                             "text": body, "date": (c.get("published_at") or c.get("updated_at") or "")[:10]})

    for _c in web_col:
        web_col[_c].sort(key=lambda x: (x["prio"], -len(x["text"])))

    web_img = collections.defaultdict(list)
    web_prd = collections.defaultdict(list)
    for p in prods:
        cat = cat_of((p.get("title") or "") + " " + " ".join(p.get("tags") or []))
        if not cat:
            continue
        body = one_para(p.get("body_html", ""))
        web_prd[cat].append({"prio": prio(p.get("title"), cat), "id": p["id"], "title": p.get("title"), "body": body,
                             "handle": p["handle"], "date": (p.get("published_at") or "")[:10]})
        if p.get("images"):
            web_img[cat].append({"id": p["id"], "title": p.get("title"),
                                 "src": p["images"][0]["src"], "handle": p["handle"],
                                 "date": (p.get("published_at") or "")[:10]})
    for cat in web_img:
        web_img[cat].sort(key=lambda x: (prio(x["title"], cat), x["date"]), reverse=False)
    for _c in web_prd:
        web_prd[_c].sort(key=lambda x: (x["prio"], -len(x.get("body") or "")))

    # ── YouTube：官方频道，排除欧洲 ────────────────────────────────────
    ytv = []
    for f in ["youtube.json", "yt_shorts_resolved.json"]:
        p = os.path.join(OUT, f)
        if os.path.exists(p):
            ytv += json.load(open(p))
    ytv = [v for v in ytv if v.get("title") and v["videoId"] not in REGION_VIDS]
    yt_by = collections.defaultdict(list)
    seen_v = set()
    for v in ytv:
        if v["videoId"] in seen_v:
            continue
        seen_v.add(v["videoId"])
        c = cat_of_video(v["title"])
        if c:
            yt_by[c].append(v)
    print("YouTube 官方（非欧洲）:", {k: len(v) for k, v in yt_by.items()})

    # ── 组装 ────────────────────────────────────────────────────────
    rows = []
    short = {}
    for cat, (nc, ni, nv) in PER_CAT.items():
        got_c = got_i = got_v = 0

        # 文案：Amazon 有 bullet 的先行（listing 宣称最全），再官网集合文案，再 Amazon 标题
        # 配比：官网集合营销长文案保底 ~40%（它与 Amazon listing 是两类不同文本，
        # 都对内容审查有价值），其余用 Amazon listing（有 bullet 的优先）。
        col_pool = [("COL", c) for c in web_col[cat]]
        n_col = min(len(col_pool), max(1, nc * 2 // 5))
        pool = (col_pool[:n_col]
                + [("AMZ", a) for a in amz_copy[cat] if a.get("bullets")]
                + col_pool[n_col:]
                + [("PRD", p) for p in web_prd[cat] if len(p.get("body") or "") > 150]
                + [("AMZ", a) for a in amz_copy[cat] if not a.get("bullets")])
        for kind, o in pool:
            if got_c >= nc:
                break
            if kind == "AMZ":
                b = o["bullets"][2] if len(o["bullets"]) > 2 else (o["bullets"][0] if o["bullets"] else "")
                body = f"{amz_title(o['title'])}\n\n{b}" if b else amz_title(o["title"])
                rows.append({"内容类型": "文案", "渠道": "Amazon", "产品线": cat,
                             "内容 ID": f"MC-US-AMZ-{o['asin']}",
                             "发布时间": "",
                             "采集数据": f"{body}\n\n—— 来源（美国站）：{o['url']}"})
            elif kind == "COL":
                rows.append({"内容类型": "文案", "渠道": "官网", "产品线": cat,
                             "内容 ID": f"MC-US-WEB-COL-{o['handle']}",
                             "发布时间": o["date"],
                             "采集数据": f"{o['title']}\n\n{o['text']}\n\n—— 来源（美国站）："
                                        f"https://momcozy.com/collections/{o['handle']}"})
            else:
                rows.append({"内容类型": "文案", "渠道": "官网", "产品线": cat,
                             "内容 ID": f"MC-US-WEB-PRD-{o['id']}",
                             "发布时间": o["date"],
                             "采集数据": f"{o['title']}\n\n{o['body']}\n\n—— 来源（美国站）："
                                        f"https://momcozy.com/products/{o['handle']}"})
            got_c += 1

        # 图片：同样配比 —— 官网产品首图保底 ~40%，其余 Amazon 主图
        n_webimg = min(len(web_img[cat]), max(1, ni * 2 // 5))
        img_pool = ([("WEB", w) for w in web_img[cat][:n_webimg]]
                    + [("AMZ", a) for a in amz_img[cat]]
                    + [("WEB", w) for w in web_img[cat][n_webimg:]])
        for _k, _o in img_pool:
            if got_i >= ni:
                break
            if _k == "WEB":
                w = _o
                rows.append({"内容类型": "图片", "渠道": "官网", "产品线": cat,
                             "内容 ID": f"MC-US-WEB-IMG-{w['id']}", "发布时间": w["date"],
                             "采集数据": f"{w['src']}\n\n图注：{w['title']}\n"
                                         f"来源页（美国站）：https://momcozy.com/products/{w['handle']}"})
                got_i += 1
                continue
            a = _o
            img = FIRST_IMG.get(a["asin"]) or (a["images"][0] if a.get("images") else None)
            if not img:          # 这张 ASIN 没有验证过的可用图 ⇒ 换下一张，不写死链
                continue
            rows.append({"内容类型": "图片", "渠道": "Amazon", "产品线": cat,
                         "内容 ID": f"MC-US-AMZ-{a['asin']}-IMG", "发布时间": "",
                         "采集数据": f"{img}\n\n图注：{amz_title(a['title'])}\n"
                                     f"来源页（美国站）：{a['url']}"})
            got_i += 1
        for a in []:
            if got_i >= ni:
                break
            rows.append({"内容类型": "图片", "渠道": "Amazon", "产品线": cat,
                         "内容 ID": f"MC-US-AMZ-{a['asin']}-IMG", "发布时间": "",
                         "采集数据": f"{a['images'][0]}\n\n图注：{amz_title(a['title'])}\n"
                                     f"来源页（美国站）：{a['url']}"})
            got_i += 1


        # 视频
        for v in yt_by[cat]:
            if got_v >= nv:
                break
            rows.append({"内容类型": "视频", "渠道": "YouTube", "产品线": cat,
                         "内容 ID": f"MC-US-YT-{v['videoId']}",
                         "发布时间": (v.get("uploadDate") or "")[:10],
                         "采集数据": f"{v['title']}\n{v.get('url') or 'https://www.youtube.com/watch?v='+v['videoId']}\n"
                                     f"缩略图：{v.get('thumb') or 'https://i.ytimg.com/vi/'+v['videoId']+'/hqdefault.jpg'}"
                                     + (f"\n发布：{v['uploadDate']}" if v.get("uploadDate") else "")})
            got_v += 1

        short[cat] = (got_c, got_i, got_v)
        print(f"  {cat}: 文案 {got_c}/{nc}  图片 {got_i}/{ni}  视频 {got_v}/{nv}")

    json.dump(rows, open(os.path.join(OUT, "rows_us.json"), "w"), ensure_ascii=False, indent=1)
    c = collections.Counter(r["内容类型"] for r in rows)
    print("\n总计:", len(rows), dict(c))
    for t, want in TARGET.items():
        print(f"  {t}: {c.get(t,0)}/{want} {'OK' if c.get(t,0)==want else '<<< 不足'}")
    print("渠道:", dict(collections.Counter(r["渠道"] for r in rows)))
    print("产品线:", dict(collections.Counter(r["产品线"] for r in rows)))
    miss = {k: v for k, v in short.items() if v != PER_CAT[k]}
    if miss:
        print("!! 未达配额的品类:", miss)


if __name__ == "__main__":
    main()
