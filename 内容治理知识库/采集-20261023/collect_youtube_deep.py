#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube 深采：专治「整个产品 0 条」与「只有 1 条凑不出多图」。

`collect_youtube.py` 每个产品只搜 1 个词、只看前 10 个候选、型号 token 卡得死。
实测后果：Air1 / 洗涤剂片 / 洗涤块 **0 条**，S12 / M5 / BS03 / BM04 **只有 1 条**
（`多图` 需要 ≥2 条缩略图，于是空着）。

这里换三件事：
1. **一个产品多个搜索词**（型号名、功能词、品类词各来一遍）；
2. **候选看到 20 个**（官方号的旧视频常沉在后面）；
3. **token 放松到「任一命中」**（如洗涤块 `washing block|tablet`、Air1 `air\s*1|air1`）。
仍**只收官方 channelId**（第三方 UGC 不算品牌内容），并**与已有结果合并去重**。

用法：python3 collect_youtube_deep.py
"""
import json
import re
import time
import urllib.parse

from collect_youtube import official_channel_id, get, watch       # noqa: E402

#: 产品中文名 → (搜索词列表, token 任一命中)
TARGETS = {
    "Air1吸奶器": (["momcozy air1 wearable breast pump", "momcozy Air 1 breast pump review",
                   "momcozy air 1 ultra slim"], [r"air\s*1\b", r"air1"]),
    "BW-NDT清洗机天然成分洗涤剂片": (["momcozy detergent tablets", "momcozy bottle washer tablets",
                              "momcozy kleanpal tablets"], [r"tablet"]),
    "BS03全自动清洗消毒器洗涤块": (["momcozy washing block", "momcozy kleanpal washing block",
                            "momcozy kleanpal detergent"], [r"washing block", r"tablet"]),
    "S12 Pro+吸奶器": (["momcozy S12 Pro Quick", "momcozy S12 pro wearable pump review",
                     "momcozy S12"], [r"s12"]),
    "M5Smart吸奶器": (["momcozy M5 smart wearable", "momcozy M5 breast pump how to use",
                    "momcozy M5"], [r"m5\b"]),
    "BS03全自动清洗消毒器": (["momcozy kleanpal pro how to use", "momcozy kleanpal pro review",
                       "momcozy bottle washer"], [r"kleanpal"]),
    "BM04婴儿监视器": (["momcozy BM04", "momcozy 5-inch dual mode baby monitor",
                   "momcozy wifi baby monitor"], [r"bm04", r"dual.?mode"]),
}
WANT = 4          # 每产品目标条数（够 多图 用）


def main():
    oc = official_channel_id()
    data = json.load(open("raw/youtube_products.json", encoding="utf-8"))
    by = {r["产品中文名"]: r for r in data}
    print(f"官方 channelId = {oc}\n")
    for name, (queries, tokens) in TARGETS.items():
        rec = by[name]
        have = {v["videoId"] for v in rec.get("videos", [])}
        print(f"### {name}（已有 {len(have)} 条）")
        for q in queries:
            if len(have) >= WANT:
                break
            try:
                h = get("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q))
            except Exception as e:                                 # noqa: BLE001
                print(f"   搜索失败 {e}")
                continue
            vids = list(dict.fromkeys(re.findall(r'"videoId":"([\w-]{11})"', h)))[:20]
            for vid in vids:
                if len(have) >= WANT:
                    break
                if vid in have:
                    continue
                time.sleep(1.5)
                try:
                    w = watch(vid)
                except Exception:                                  # noqa: BLE001
                    continue
                if w["channelId"] != oc:
                    continue
                if not any(re.search(t, w["title"], re.I) for t in tokens):
                    continue
                have.add(vid)
                rec.setdefault("videos", []).append(w)
                print(f"   ✅ {w['uploadDate']} {w['title'][:60]}")
        rec["ok"] = bool(rec.get("videos"))
        if not rec["ok"]:
            print("   ⚠️ 仍无官方号视频")
        time.sleep(1.5)
    json.dump(data, open("raw/youtube_products.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n合并后：有素材产品 {sum(1 for r in data if r.get('ok'))}/9 ｜ "
          f"总视频 {sum(len(r.get('videos', [])) for r in data)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())