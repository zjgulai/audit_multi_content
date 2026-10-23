#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写库前闸门：15 条图片 + 15 条链接逐条真打一遍，任何一条不绿整批不写。

上一轮（2026-10-13）就是靠这把闸门拦下的：Amazon 图片 URL 第一版全 404、
标题尾部残留类目后缀。**闸门不绿就写库 = 把脏数据交给评审链。**

断言：
  A 图片 URL 必须 200 且 content-type 是 image/*
  B 链接必须 200（允许 3xx 跟随），且正文里能 grep 到品牌名（Amazon/官网）
  C 每条 采集数据 里的【图片】【链接】与校验过的 URL 完全一致

用法：python3 verify_rows.py
"""
import json
import re
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}


def head(url, timeout=25):
    req = urllib.request.Request(url, headers=UA, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("content-type", ""), r.read(200000)


def main():
    ctrl = "--controls" in sys.argv
    rows = json.load(open("out_rows.json", encoding="utf-8"))
    if ctrl:
        # ★ 反向对照：把第 1 行的图片换成必然 404 的地址，闸门**必须**变红。
        # 没有这一段，「red=0」只证明我这次没红，不证明它拦得住（AGENTS.md §2.4.1）。
        bad = {"fields": dict(rows[0]["fields"]), "_meta": dict(rows[0]["_meta"])}
        bad["_meta"]["图片"] = "https://momcozy.com/__definitely-404__.jpg"
        bad["fields"]["采集数据"] = bad["fields"]["采集数据"].replace(
            rows[0]["_meta"]["图片"], bad["_meta"]["图片"])
        rows = [bad]
        print("（反向对照：第 1 行图片已替换为 404 地址，闸门应当变红）\n")
    red = []
    for i, r in enumerate(rows, 1):
        cell = r["fields"]["采集数据"]
        img = r["_meta"]["图片"]
        link = r["_meta"]["链接"]

        # C：单元格里的 URL 必须与校验对象一致（防止「验的是 A、写的是 B」）
        assert f"【图片】{img}" in cell, f"第 {i} 行单元格图片与校验对象不一致"
        assert f"【链接】{link}" in cell, f"第 {i} 行单元格链接与校验对象不一致"

        try:
            st, ct, _ = head(img)
            if st != 200 or not ct.startswith("image/"):
                red.append((i, "图片", img, f"{st} {ct}"))
        except Exception as e:                                      # noqa: BLE001
            red.append((i, "图片", img, f"{type(e).__name__} {str(e)[:60]}"))

        try:
            st, ct, body = head(link)
            if st != 200:
                red.append((i, "链接", link, f"HTTP {st}"))
            elif r["_meta"]["渠道"] in {"官网", "Amazon"} and b"momcozy" not in body.lower():
                red.append((i, "链接", link, "正文里没有品牌名（疑似错配页）"))
        except Exception as e:                                      # noqa: BLE001
            red.append((i, "链接", link, f"{type(e).__name__} {str(e)[:60]}"))

        print(f"  [{i:2d}] {r['_meta']['渠道']:7s} {r['_meta']['产品线']:5s} {img[:46]}… / {link[:60]}")

    print(f"\nchecked={len(rows) * 2}  red={len(red)}")
    for x in red:
        print("  ✗", x)
    if red:
        print("\n❌ 闸门未过，不写库")
        return 1
    print("✅ 闸门通过：15 张图 + 15 条链接全部可点，单元格与校验对象一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
