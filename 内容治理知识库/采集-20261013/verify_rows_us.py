#!/usr/bin/env python3
"""写库前闸门（美国口径 + 可访问性），任何一条红 ⇒ 退出码 3，不许写库。

两道尺子：
  A. 可访问性 —— 图片必须 200 且 content-type=image/*；其余必须 200
  B. 美国口径 —— 每个来源 URL 必须落在美国源上：
       · amazon.com/dp/          美国站
       · momcozy.com/...         美国默认市场（USD/en），且**不得**命中地区集合
       · youtube.com/watch?v=    Momcozy 官方频道，且**不得**是欧洲内容
"""
import json, re, subprocess, os, sys

HERE = os.path.dirname(__file__)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 必须排除的非美资源（实测所得）
REGION_COLS = {"baby-care-fr", "weekly-deals-fr-copy", "bundle-sale-copy",
               "buy-more-save-more-ca", "buy-more-save-more-ca-copy", "baby-care-copy",
               "ca-featured-breast-pumps", "ca-nasal-aspirator", "new-in-ca",
               "maternity-pillow-eu"}
NON_US_VIDS = {"_xyLF4_AgAw"}   # Cologne Baby Show 2026（欧洲展会）


def probe(url, want_image=False, attempts=4):
    """429/5xx 是**暂时**的（限流），要退避重试；404/403 才是真死链。

    2026-10-13 实测踩过：连续校验把 momcozy.com 打到 429，
    若不区分就会把「限流」误判成「死链」，白拦一道。
    """
    import time
    last = ""
    for k in range(attempts):
        r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code} %{content_type}",
                            "-L", "--max-time", "25", "-A", UA, url], capture_output=True, text=True)
        p = r.stdout.split()
        code = p[0] if p else "000"
        ct = p[1] if len(p) > 1 else ""
        last = f"{code} {ct}"
        ok = (code == "200" and ct.startswith("image/")) if want_image else (code == "200")
        if ok:
            return True, last
        if code in ("429", "503", "502", "504") and k < attempts - 1:
            time.sleep(3 * (k + 1))          # 退避：3s / 6s / 9s
            continue
        return False, last
    return False, last


def us_check(row):
    """返回 (是否美国, 原因)"""
    blob = row["采集数据"]
    urls = re.findall(r"https?://[^\s]+", blob)
    for u in urls:
        if "amazon.com" in u and "/dp/" in u:
            return True, "Amazon 美国站"
        if "momcozy.com" in u:
            for h in REGION_COLS:
                if h in u:
                    return False, f"命中地区集合 {h}"
            return True, "官网美国默认市场"
        if "youtube.com/watch" in u or "youtu.be/" in u:
            vid = re.search(r"[?&]v=([\w-]{11})", u) or re.search(r"youtu\.be/([\w-]{11})", u)
            if vid and vid.group(1) in NON_US_VIDS:
                return False, f"欧洲内容 {vid.group(1)}"
            return True, "Momcozy 官方频道（非欧洲）"
        if "i.ytimg.com" in u:
            continue
        if "m.media-amazon.com" in u or "cdn.shopify.com" in u:
            continue
        return False, f"未知来源域 {u[:60]}"
    return False, "没有可核的来源 URL"


def main():
    rows = json.load(open(os.path.join(HERE, "out", "rows_us.json")))
    fails = []
    us_counts = {}
    for i, r in enumerate(rows, 1):
        t = r["内容类型"]
        u = re.findall(r"https?://[^\s]+", r["采集数据"])
        u = [x for x in u if "cdn.shopify" not in x or t == "图片"] or u
        target = u[0]
        # 图片行取图床 URL 做可达性判定
        if t == "图片":
            target = re.findall(r"https?://[^\s]+", r["采集数据"])[0]
        ok, info = probe(target, want_image=(t == "图片"))
        is_us, why = us_check(r)
        us_counts[why] = us_counts.get(why, 0) + 1
        if not ok or not is_us:
            fails.append((i, t, r["内容 ID"], info, why))
            print(f"  RED [{i:>2}] {t} {r['内容 ID']}  可达={info}  美国={why}", flush=True)
    print("\n美国来源分布:", us_counts)
    print(f"checked={len(rows)}  red={len(fails)}")
    if fails:
        print("!!! 有问题，不许写库"); sys.exit(3)
    print("全部可访问 + 全部美国来源 —— 可以写库")


if __name__ == "__main__":
    main()
