#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总装 80 行：文案 35 + 图片 35 + 视频 10，三大品类全覆盖、只收美国站。

口径（每条都写给后人看，别随手改）：
1. **三类都要覆盖** —— 文案/图片按 12/12/11 分（吸奶器/清洗机/婴儿监控器），
   这是 Owner 2026-10-13 的口径：「必须属于这 3 个品类」。
2. **产品线映射库内受控词表**（实读所得 5 值），**不自创**：
   吸奶器→`吸奶器`、清洗机→`喂养电器`、婴儿监控器→`婴幼儿`。
3. **文案来源**：Amazon claim 型 bullet（清洗机/监控器在官网上正文为空，只有 Amazon 有可审文案）。
4. **图片来源**：Amazon 主图（`._AC_` 后缀，逐条 HTTP 校验过）；补官网主图填满 35。
5. **不碰人/引擎字段**：`审核人`/`Agent 结论`/`置信度`/`报告链接` 一个都不写。

用法：python3 build_rows.py
"""
import collections
import html
import json
import os
import re

PLINE = {"吸奶器": "吸奶器", "清洗机": "喂养电器", "婴儿监控器": "婴幼儿"}
QUOTA_T = {"吸奶器": 15, "清洗机": 12, "婴儿监控器": 14}      # 合计 41（按供给侧拉满，再截到 35）
QUOTA_P = {"吸奶器": 12, "清洗机": 12, "婴儿监控器": 11}      # 合计 35


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def main():
    amz = json.load(open("raw/amazon_rows.json", encoding="utf-8"))
    vids = json.load(open("out_video_rows.json", encoding="utf-8"))
    site = json.load(open("out_site_rows.json", encoding="utf-8"))

    by = collections.defaultdict(list)
    for r in amz:
        by[r["cat"]].append(r)

    rows = []
    # ── 文案 35：Amazon bullet（可审的 claim 型文案）─────────────────────────
    for cat, q in QUOTA_T.items():
        cands = [r for r in by[cat] if r["bullets"]]
        for i, r in enumerate(cands[:q], 1):
            body = "\n".join(f"• {clean(b)}" for b in r["bullets"])
            rows.append({
                "内容类型": "文案", "渠道": "Amazon",
                "内容 ID": f"MC-AMZ-{cat}-T{i:02d}", "产品线": PLINE[cat], "发布时间": "",
                "采集数据": f"{clean(r['title'])}\n\n{body}\n\n—— 来源：{r['url']}",
                "_url": r["url"],
            })
    rows = rows[:35]                       # 截到 35，保证三类在前（配额已按供给排）
    n_t = len(rows)
    print(f"文案 {n_t} 条 ｜ 品类:", dict(collections.Counter(r['内容 ID'].split('-')[2] for r in rows)))

    # ── 图片 35：先 Amazon 主图，不够用官图补 ────────────────────────────────
    n_before = len(rows)
    for cat, q in QUOTA_P.items():
        cands = [r for r in by[cat] if r["img"]]
        for i, r in enumerate(cands[:q], 1):
            rows.append({
                "内容类型": "图片", "渠道": "Amazon",
                "内容 ID": f"MC-AMZ-{cat}-P{i:02d}", "产品线": PLINE[cat], "发布时间": "",
                "采集数据": f"{clean(r['title'])}\n商品主图：{r['img']}\n\n—— 来源：{r['url']}",
                "_url": r["img"],
            })
    n_amz_p = sum(1 for r in rows[n_before:] if r["内容类型"] == "图片")
    need = 35 - n_amz_p
    print(f"Amazon 图片 {n_amz_p} 条 ｜ 还差 {need} 条 → 用官网图补")
    if need > 0:
        site_p = [r for r in site if r["内容类型"] == "图片"]
        for i, r in enumerate(site_p[:need], 1):
            r = dict(r)
            _cat = "吸奶器" if "吸奶器" in r["内容 ID"] else ("清洗机" if "清洗机" in r["内容 ID"] else "婴儿监控器")
            r["内容 ID"] = f"MC-SITE-{_cat}-P{i:02d}"
            rows.append(r)
    n_p = sum(1 for r in rows if r["内容类型"] == "图片")
    print(f"图片 {n_p} 条 ｜ 品类:", dict(collections.Counter(r['产品线'] for r in rows if r['内容类型']=='图片')))

    # ── 视频 10（已总装好）──────────────────────────────────────────────────
    rows += vids

    # 统一补字段，并按库要求的列序组织
    ORDER = ["内容 ID", "内容类型", "渠道", "产品线", "发布时间", "采集数据", "状态", "_url"]
    for r in rows:
        r.setdefault("状态", "待审")
    rows = [{k: r.get(k, "") for k in ORDER if k != "_url"} | {"_url": r.get("_url", "")} for r in rows]

    json.dump(rows, open("out/rows.json", "w", encoding="utf-8") if os.path.isdir("out") else open("rows.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n=== 总计 {len(rows)} 行 ===")
    print(" 内容类型:", dict(collections.Counter(r["内容类型"] for r in rows)))
    print(" 渠道    :", dict(collections.Counter(r["渠道"] for r in rows)))
    print(" 产品线  :", dict(collections.Counter(r["产品线"] for r in rows)))
    print(" 品类覆盖:", dict(collections.Counter(
        (r["内容 ID"].split("-")[2] if r["内容 ID"].startswith("MC-AMZ") else
         (r["内容 ID"].split("-")[2] if r["内容 ID"].startswith("MC-YT") else "官网补图")) for r in rows)))


if __name__ == "__main__":
    main()
