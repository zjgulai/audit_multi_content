#!/usr/bin/env python3
"""从已落盘的 Amazon 页面 HTML 重建图片列表（不需要重新抓取）。

关键教训（2026-10-13 实测）：`m.media-amazon.com/images/I/` 下绝大多数是
CSS/JS 资源（.js/.css 结尾），它们的 ID 长得和图片 ID 一样。
只有带 `._AC_` 尺寸后缀的才是真商品图 —— 按 ID 去重后用裸 `.jpg` 取原图
（实测 148KB > SL1500 的 64KB > UF894 的 31KB）。
"""
import json, re, os, subprocess

HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# 只要真商品图：带 _AC_ 尺寸后缀的 .jpg
PAT = re.compile(r"https://m\.media-amazon\.com/images/I/([A-Za-z0-9+%-]+?)\._AC_[A-Za-z0-9,_]+_\.jpg")


def rebuild(asin, h):
    ids = list(dict.fromkeys(PAT.findall(h)))
    return [f"https://m.media-amazon.com/images/I/{i}.jpg" for i in ids]


def verify(url):
    r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code} %{content_type}",
                        "-L", "--max-time", "20", "-A", UA, url], capture_output=True, text=True)
    parts = r.stdout.split()
    return (parts[0] == "200" and parts[1].startswith("image/")), r.stdout.strip()


def main():
    recs = json.load(open(os.path.join(OUT, "amazon.json")))
    for rec in recs:
        f = os.path.join(RAW, f"amz_{rec['asin']}.html")
        if not os.path.exists(f):
            rec["images"] = []
            continue
        h = open(f, encoding="utf-8", errors="ignore").read()
        rec["images"] = rebuild(rec["asin"], h)

    # 逐条校验，只保留真能打开的
    verified_total = 0
    for rec in recs:
        good = []
        for u in rec["images"]:
            ok, info = verify(u)
            if ok:
                good.append(u)
            if len(good) >= 4:
                break
        rec["images"] = good
        rec["images_verified"] = len(good)
        verified_total += len(good)
        print(f"  {rec['asin']}  imgs={len(good)}  {rec.get('title','')[:52]}", flush=True)

    json.dump(recs, open(os.path.join(OUT, "amazon.json"), "w"), ensure_ascii=False, indent=1)
    print("verified images total:", verified_total,
          "| products with >=1 img:", sum(1 for r in recs if r["images"]))


if __name__ == "__main__":
    main()
