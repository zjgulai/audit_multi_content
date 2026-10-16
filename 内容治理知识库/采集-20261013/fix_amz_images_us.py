#!/usr/bin/env python3
"""给每个 ASIN 找出一张**验证过能打开**的首图，缓存到 out/amz_first_img.json。

为什么需要：`m.media-amazon.com/images/I/` 下带 `_AC_` 后缀的不全是商品图 ——
实测 `01sXCetMp1L`（图标/精灵图，ID 以 01 开头）裸 `.jpg` 取回来是 404。
判据是**真发一次请求**，不是靠命名规则猜。
"""
import json, os, subprocess, sys

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def probe(u):
    r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code} %{content_type}",
                        "-L", "--max-time", "20", "-A", UA, u], capture_output=True, text=True)
    p = r.stdout.split()
    return bool(p) and p[0] == "200" and len(p) > 1 and p[1].startswith("image/")


def main():
    bl = json.load(open(os.path.join(OUT, "amazon_bullets.json")))
    cache = {}
    for asin, rec in bl.items():
        for u in rec.get("images") or []:
            iid = u.split("/I/")[-1]
            if iid.startswith("01"):          # Amazon 精灵图前缀，跳过（实测会 404）
                continue
            if probe(u):
                cache[asin] = u
                print(f"  {asin} -> {iid[:44]}", flush=True)
                break
        else:
            print(f"  {asin} -> 没有可用图", flush=True)
    json.dump(cache, open(os.path.join(OUT, "amz_first_img.json"), "w"), ensure_ascii=False, indent=1)
    print(f"\n可用首图: {len(cache)}/{len(bl)}")


if __name__ == "__main__":
    main()
