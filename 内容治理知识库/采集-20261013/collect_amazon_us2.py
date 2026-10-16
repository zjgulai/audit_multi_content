#!/usr/bin/env python3
"""扩充采集：把 ASIN 池跑一遍 Amazon 美国站，结果写到 amazon_us2.json（不覆盖已有）。

与 collect_amazon.py 的差别：
  · 输出文件名可指定，避免覆盖
  · 品牌判据放宽到「标题含 Momcozy」——监控器页常常没有 bullet，标题是唯一线索
  · 仍然逐条落 HTML 原文，便于事后复核
"""
import json, re, html, subprocess, time, sys, os, random

MOB = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
       "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")


def txt(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def parse(asin, h):
    d = {"asin": asin, "url": f"https://www.amazon.com/dp/{asin}", "ok": False}
    m = re.search(r"<title>(.*?)</title>", h, re.S)
    t = txt(m.group(1)) if m else ""
    t = re.sub(r"^Amazon\.com\s*:\s*", "", t)
    for c in ["Industrial & Scientific", "Baby Products", "Health & Household",
              "Home & Kitchen", "Everything Else", "Electronics", "Baby"]:
        t = re.sub(r"\s*:\s*" + re.escape(c) + r"\s*$", "", t)
    d["title"] = t.strip()

    bullets = []
    fb = re.search(r'id="feature-bullets"(.*?)</ul>', h, re.S)
    if fb:
        for it in re.findall(r'<span class="a-list-item[^"]*">(.*?)</span>', fb.group(1), re.S):
            v = txt(it)
            if len(v) > 3:
                bullets.append(v)
    d["bullets"] = bullets

    ids = list(dict.fromkeys(re.findall(r"/images/I/([A-Za-z0-9+%-]+?)\._AC_", h)))
    d["images"] = [f"https://m.media-amazon.com/images/I/{i}.jpg" for i in ids]

    blob = (d["title"] + " " + " ".join(bullets)).lower()
    d["is_momcozy"] = "momcozy" in blob
    d["is_decoy"] = any(k in d["title"].lower() for k in
                        ["gift card", "american express", "reload", "sign in"])
    d["ok"] = bool(d["title"]) and d["is_momcozy"] and not d["is_decoy"]
    return d


def main():
    outfile = sys.argv[1]
    asins = sys.argv[2:]
    out = []
    for n, asin in enumerate(asins, 1):
        h = subprocess.run(["curl", "-sS", "-L", "--max-time", "30", "-A", MOB,
                            "-H", "Accept-Language: en-US,en;q=0.9",
                            f"https://www.amazon.com/gp/aw/d/{asin}"],
                           capture_output=True, text=True).stdout
        rec = parse(asin, h)
        out.append(rec)
        flag = "OK " if rec["ok"] else ("DECOY" if rec["is_decoy"] else "MISS")
        print(f"[{n:>2}/{len(asins)}] {flag} {asin} b={len(rec['bullets'])} i={len(rec['images'])} "
              f"{rec['title'][:58]}", flush=True)
        open(os.path.join(RAW, f"amz_{asin}.html"), "w", encoding="utf-8").write(h)
        json.dump(out, open(os.path.join(OUT, outfile), "w"), ensure_ascii=False, indent=1)
        time.sleep(random.uniform(2.0, 3.2))
    print("done", sum(1 for r in out if r["ok"]), "/", len(out))


if __name__ == "__main__":
    main()
