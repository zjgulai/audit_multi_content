#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""视频 10 行总装：YouTube @Momcozy（北美）三大品类内选。

选法（不是"取最新 10 条"）：实测最新 10 条全是品牌片（`Choose You, Too` 系列），
**不属于**三类任何一类。所以按「产品相关性」排：
  ① 优先真·产品视频（含产品名/型号：BM08、D8、KleanPal、DeepClean、M5/M6/M9…）
  ② 其次品类相关（宝宝监控/吸奶/清洗主题）
  ③ 三类都要有 —— 否则又变成"品类没覆盖"

发布时点取 oEmbed 之外的真实上传日：从 watch 页 `uploadDate` 取（拿不到就留空，**不编**）。

用法：python3 build_video_rows.py
"""
import json
import re
import urllib.request

import collections

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
PLINE = {"吸奶器": "吸奶器", "清洗机": "喂养电器", "婴儿监控器": "婴幼儿"}
# 每类配额（合计 10）：清洗机与监控器产品视频多 ⇒ 给足；吸奶器留给真·产品/使用类
QUOTA = {"清洗机": 4, "婴儿监控器": 3, "吸奶器": 3}
PRODUCT_HINT = re.compile(r"BM\d|D8|D9|KleanPal|DeepClean|M5|M6|M9|S12|S9|V1|W1|how to|setup|unbox|review|use ", re.I)


def get(u, t=25):
    req = urllib.request.Request(u, headers=UA)
    with urllib.request.urlopen(req, timeout=t) as r:
        return r.read()


def upload_date(vid):
    try:
        b = get(f"https://www.youtube.com/watch?v={vid}")
        m = re.search(rb'"uploadDate":"([^"]*)"', b)
        return m.group(1).decode() if m else ""
    except Exception:                                              # noqa: BLE001
        return ""


def main():
    scan = json.load(open("raw/youtube_scan.json", encoding="utf-8"))
    buckets = scan["buckets"]
    picked = []
    for cat, q in QUOTA.items():
        items = buckets.get(cat, [])
        items = sorted(items, key=lambda r: (not PRODUCT_HINT.search(r["title"]), r["title"]))
        for r in items[:q]:
            picked.append((cat, r))
    print(f"选中 {len(picked)} 条（配额 {QUOTA}）")
    rows = []
    for i, (cat, r) in enumerate(picked, 1):
        ud = upload_date(r["videoId"])
        rows.append({
            "内容类型": "视频",
            "渠道": "YouTube",
            "内容 ID": f"MC-YT-{cat}-V{i:02d}",
            "产品线": PLINE[cat],
            "发布时间": ud[:19],
            "采集数据": (f"{r['title']}\n视频地址：{r['url']}\n"
                      f"缩略图：https://i.ytimg.com/vi/{r['videoId']}/hqdefault.jpg\n"
                      f"账号：YouTube @Momcozy（北美）\n\n—— 来源：{r['url']}"),
            "_url": f"https://i.ytimg.com/vi/{r['videoId']}/hqdefault.jpg",
            "_video": r["url"],
        })
        print(f"  [{i:2d}] {cat:6s} {r['title'][:66]}")
    json.dump(rows, open("out_video_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n视频行数 {len(rows)} ｜ 品类:", dict(collections.Counter(r["内容 ID"].split("-")[2] for r in rows)))
    print("⚠️ 发布时间拿不到的留空，**不编**")
    print("已写 out_video_rows.json")


if __name__ == "__main__":
    main()
