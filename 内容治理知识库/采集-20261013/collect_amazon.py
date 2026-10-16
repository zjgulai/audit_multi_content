#!/usr/bin/env python3
"""Amazon Momcozy 商品页抽取器。

只走移动端只读页面（/gp/aw/d/<ASIN>），不登录、不下单、不碰任何账号数据。
每个 ASIN 之间 sleep，避免触发反爬。
"""
import json, re, html, subprocess, time, sys, os, random

MOB = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
       "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
RAW = os.path.join(os.path.dirname(__file__), "raw")


def txt(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def fetch(url, timeout=30):
    p = subprocess.run(["curl", "-sS", "-L", "--max-time", str(timeout),
                        "-A", MOB, "-H", "Accept-Language: en-US,en;q=0.9", url],
                       capture_output=True, text=True)
    return p.stdout


def parse(asin, h):
    d = {"asin": asin, "url": f"https://www.amazon.com/dp/{asin}", "ok": False}

    # ---- title：移动页的 <title> 才可靠，productTitle 经常不渲染 ----
    m = re.search(r"<title>(.*?)</title>", h, re.S)
    if m:
        t = txt(m.group(1))
        t = re.sub(r"^Amazon\.com\s*:\s*", "", t)
        t = re.sub(r"\s*:\s*(Baby|Home & Kitchen|Health & Household|Amazon\.com).*$", "", t)
        d["title"] = t.strip()
    else:
        d["title"] = ""

    # ---- feature bullets ----
    bullets = []
    fb = re.search(r'id="feature-bullets"(.*?)</ul>', h, re.S)
    if fb:
        for it in re.findall(r'<span class="a-list-item[^"]*">(.*?)</span>', fb.group(1), re.S):
            v = txt(it)
            if len(v) > 3:
                bullets.append(v)
    d["bullets"] = bullets

    # ---- images：按图片 ID 去重，还原成全尺寸 ----
    ids = list(dict.fromkeys(re.findall(r"m\.media-amazon\.com/images/I/([A-Za-z0-9+._-]+?)\._", h)))
    ids += list(dict.fromkeys(re.findall(r"m\.media-amazon\.com/images/I/([A-Za-z0-9+._-]+?)\.jpg", h)))
    seen, imgs = set(), []
    for i in ids:
        base = i.split(".")[0]
        if base in seen:
            continue
        seen.add(base)
        imgs.append(f"https://m.media-amazon.com/images/I/{base}.jpg")
    d["images"] = imgs

    # ---- 判定这一页到底是不是 Momcozy 的真商品（防诱饵页） ----
    blob = (d.get("title", "") + " " + " ".join(bullets)).lower()
    d["is_momcozy"] = "momcozy" in blob
    d["is_decoy"] = any(k in (d.get("title") or "").lower() for k in
                        ["gift card", "american express", "reload", "sign in"])
    d["ok"] = bool(d["title"]) and d["is_momcozy"] and not d["is_decoy"]
    return d


def main():
    asins = sys.argv[1:]
    out = []
    for n, asin in enumerate(asins, 1):
        h = fetch(f"https://www.amazon.com/gp/aw/d/{asin}")
        rec = parse(asin, h)
        rec["_bytes"] = len(h)
        out.append(rec)
        flag = "OK " if rec["ok"] else ("DECOY" if rec["is_decoy"] else "MISS")
        print(f"[{n:>2}/{len(asins)}] {flag} {asin}  bullets={len(rec['bullets'])} "
              f"imgs={len(rec['images'])}  {(rec.get('title') or '')[:60]}", flush=True)
        with open(os.path.join(RAW, f"amz_{asin}.html"), "w", encoding="utf-8") as f:
            f.write(h)
        with open(os.path.join(os.path.dirname(__file__), "out", "amazon.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        time.sleep(random.uniform(2.0, 3.5))
    print("done", sum(1 for r in out if r["ok"]), "/", len(out))


if __name__ == "__main__":
    main()
