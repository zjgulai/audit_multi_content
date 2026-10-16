#!/usr/bin/env python3
"""用桌面 UA 重抓 Amazon 美国站商品页，把 feature-bullets 补回来。

实测（2026-10-13，同一 ASIN B0CZNQ7VH7 四种组合）：
  gp/aw + 移动 UA   → 717 KB，无 bullet 块
  gp/aw + 桌面 UA   → 2.73 MB，**有** bullet 块
  dp    + 移动 UA   → 3.8 KB（拦截）
  dp    + 桌面 UA   → 2.73 MB，**有** bullet 块
⇒ 拿 bullet 要靠**桌面 UA**，不是移动 UA。移动 UA 拿得到的是精简页。
"""
import json, re, html, subprocess, time, os, sys, random

DESK = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")


def txt(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def parse(asin, h):
    m = re.search(r"<title>(.*?)</title>", h, re.S)
    t = txt(m.group(1)) if m else ""
    t = re.sub(r"^Amazon\.com\s*:\s*", "", t)
    for c in ["Industrial & Scientific", "Baby Products", "Health & Household",
              "Home & Kitchen", "Everything Else", "Electronics", "Baby"]:
        t = re.sub(r"\s*:\s*" + re.escape(c) + r"\s*$", "", t)
    bullets = []
    fb = re.search(r'id="feature-bullets"(.*?)</ul>', h, re.S)
    if fb:
        for it in re.findall(r'<span class="a-list-item[^"]*">(.*?)</span>', fb.group(1), re.S):
            v = txt(it)
            if len(v) > 3:
                bullets.append(v)
    ids = list(dict.fromkeys(re.findall(r"/images/I/([A-Za-z0-9+%-]+?)\._AC_", h)))
    return {"asin": asin, "url": f"https://www.amazon.com/dp/{asin}", "title": t.strip(),
            "bullets": bullets,
            "images": [f"https://m.media-amazon.com/images/I/{i}.jpg" for i in ids]}


def main():
    asins = sys.argv[1:]
    outpath = os.path.join(OUT, "amazon_bullets.json")
    out = json.load(open(outpath)) if os.path.exists(outpath) else {}
    for n, asin in enumerate(asins, 1):
        h = subprocess.run(["curl", "-sS", "-L", "--max-time", "35", "-A", DESK,
                            "-H", "Accept-Language: en-US,en;q=0.9",
                            f"https://www.amazon.com/dp/{asin}"],
                           capture_output=True, text=True).stdout
        rec = parse(asin, h)
        rec["_bytes"] = len(h)
        rec["is_momcozy"] = "momcozy" in (rec["title"] + " " + " ".join(rec["bullets"])).lower()
        out[asin] = rec
        print(f"[{n:>2}/{len(asins)}] {asin} b={len(rec['bullets'])} i={len(rec['images'])} "
              f"sz={len(h)//1024}K {rec['title'][:52]}", flush=True)
        open(os.path.join(RAW, f"amz_desk_{asin}.html"), "w", encoding="utf-8").write(h)
        json.dump(out, open(outpath, "w"), ensure_ascii=False, indent=1)
        time.sleep(random.uniform(2.0, 3.0))
    got = sum(1 for v in out.values() if v["bullets"])
    print(f"done：{got}/{len(out)} 个 ASIN 拿到 bullet")


if __name__ == "__main__":
    main()
