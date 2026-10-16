#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从美国站 164 篇真实博客（2.1M 字）抽取「美国市场表达基线」。

**为什么这么做**（而不是让模型自己想）：Owner 明确要求「不要只盯知识库和 skill」。
本文件的语料 100% 来自品牌**自己的美国站**（`momcozy.com/blogs/*.atom`，公开可回源），
是「品牌已经这么对美国消费者说话」的**真实样本**，不是模型常识。

维度（每个都先量证据量，证据不足的维度**如实标薄**，不许拿常识填）：
  1. 计量单位：美制/公制 的语域分野（正文 vs 规格表）
  2. 温度与尺寸
  3. 美国语境锚点：机构与认证（AAP/CDC/FDA/CPSC…）
  4. 美式拼写 vs 英式（color/colour 等）
  5. 育儿语境高频搭配（护理、喂养、睡眠）
  6. 标题句式（美式营销句式）

用法：python3 extract_baseline.py        # 产出 out/baseline.json + out/baseline.md
"""
import collections
import html
import json
import os
import re

DIMENSIONS = {
    "unit_imperial": r"\b\d+(?:\.\d+)?\s*(?:fl\.?\s*oz|oz|ounces?|lbs?|pounds?|inches?|feet|ft|°F|℉)\b",
    "unit_metric": r"\b\d+(?:\.\d+)?\s*(?:ml|mL|L|liters?|litres?|kg|g|grams?|cm|mm|°C|℃)\b",
    "us_institution": r"\b(?:AAP|American Academy of Pediatrics|CDC|FDA|CPSC|FTC|IHDI|WIC|NIH|WHO|UNICEF)\b",
    "us_spelling": r"\b(?:color|colors|flavor|center|liter|meter|fiber|defense|pediatrician|mom|mommy)\b",
    "uk_spelling": r"\b(?:colour|colours|flavour|centre|litre|metre|fibre|defence|paediatrician|mum|mummy)\b",
    "care_context": r"\b(?:pediatrician|ob-gyn|OB/GYN|midwife|doula|NICU|daycare|pediatric)\b",
    "feeding_context": r"\b(?:formula|nursing|pumping session|milk supply|latch|letdown|cluster feeding|pace feeding)\b",
    "sleep_context": r"\b(?:safe sleep|back to sleep|SIDS|bassinet|sleep sack|white noise|sleep regression)\b",
    "us_cultural_anchor": r"\b(?:Thanksgiving|Halloween|Christmas|Mother'?s Day|Father'?s Day|Black Friday|registry|baby shower)\b",
}

SPELL_PAIRS = [("color", "colour"), ("flavor", "flavour"), ("center", "centre"),
               ("liter", "litre"), ("mom", "mum"), ("pediatrician", "paediatrician")]


def plain(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h or "", flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def load_articles():
    arts = []
    for f in sorted(os.listdir("raw/blogs")):
        if not f.endswith(".atom"):
            continue
        raw = open(f"raw/blogs/{f}", encoding="utf-8").read()
        cat = f[:-5]
        for m in re.finditer(r"<entry>(.*?)</entry>", raw, re.S):
            e = m.group(1)
            t = re.search(r"<title[^>]*>(.*?)</title>", e, re.S)
            u = re.search(r'<link[^>]*href="([^"]+)"', e)
            c = re.search(r"<content[^>]*>(.*?)</content>", e, re.S)
            d = re.search(r"<(?:published|updated)>([^<]+)<", e)
            body = plain(c.group(1)) if c else ""
            if body:
                arts.append({"cat": cat, "title": plain(t.group(1)) if t else "",
                             "url": u.group(1) if u else "", "date": (d.group(1) if d else "")[:10],
                             "body": body})
    return arts


def main():
    arts = load_articles()
    corpus = "\n".join(a["body"] for a in arts)
    titles = "\n".join(a["title"] for a in arts)
    print(f"语料：{len(arts)} 篇 ｜ 正文 {len(corpus):,} 字 ｜ 标题 {len(titles)} 条\n")

    out = {"articles": len(arts), "chars": len(corpus), "by_cat": dict(collections.Counter(a["cat"] for a in arts)),
           "dimensions": {}}
    for name, pat in DIMENSIONS.items():
        ms = list(re.finditer(pat, corpus, re.I))
        cnt = collections.Counter(m.group(0).strip().lower() for m in ms)
        out["dimensions"][name] = {"hits": len(ms), "top": dict(cnt.most_common(12))}
        print(f"  {name:20s} {len(ms):6d} 处 ｜ top: {list(cnt.most_common(5))}")

    print("\n=== 美式 vs 英式拼写（美国站该用哪边）===")
    sp = {}
    for us, uk in SPELL_PAIRS:
        a = len(re.findall(r"\b%s\b" % us, corpus, re.I))
        b = len(re.findall(r"\b%s\b" % uk, corpus, re.I))
        sp[us] = {"us": a, "uk": b}
        print(f"  {us:14s} 美式={a:5d} ｜ 英式({uk})={b:4d}  ⇒ {'✅美式' if a > b else '⚠️英式更多'}")
    out["spelling"] = sp

    print("\n=== 单位并用时的顺序（正文语域）===")
    order = collections.Counter()
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(ml|mL)\s*[\(（/]\s*(\d+(?:[.,]\d+)?)\s*(oz|fl\.?\s*oz)|(\d+(?:[.,]\d+)?)\s*(oz|fl\.?\s*oz)\s*[\(（/]\s*(\d+(?:[.,]\d+)?)\s*(ml|mL)", corpus, re.I):
        order["metric_first" if m.group(2) else "imperial_first"] += 1
    out["unit_order"] = dict(order)
    print(" ", dict(order))

    os.makedirs("out", exist_ok=True)
    json.dump(out, open("out/baseline.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 样例：给每条维度留 3 条带回源的可核证据
    samples = {}
    for name, pat in DIMENSIONS.items():
        got = []
        for a in arts:
            m = re.search(pat, a["body"], re.I)
            if m:
                s = max(0, m.start() - 120)
                got.append({"url": a["url"], "date": a["date"],
                            "ctx": a["body"][s:m.end() + 120]})
            if len(got) >= 3:
                break
        samples[name] = got
    json.dump(samples, open("out/baseline_samples.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写 out/baseline.json ＋ out/baseline_samples.json")


if __name__ == "__main__":
    main()
