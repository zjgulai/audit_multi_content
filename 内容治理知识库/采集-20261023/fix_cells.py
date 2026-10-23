#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修正**已写错**的格（覆盖 + 清空），并逐格留改前改后。

## 为什么要这个脚本

第一版 `build_collect_rows.py` 有两条**采集口径错误**，已落表：
1. **Amazon 图片/视频抓错来源** —— 抓的是全页 `images/I/<id>._`，那里面混着
   页面 chrome、广告位、推荐位。铁证：8 个产品的「第一张图」**全是同一个**
   `215CM2Cgm9L`。正解是 `"hiRes"`（商品图库）与 `videos[]` JSON 里的 `url`（真 mp4）。
2. **官网视频抓了全局嵌入** —— 12 个视频同时出现在**3 个不相关页面**
   （S12 Pro+ / BW-NDT洗涤剂片 / 洗涤块）。正解：**只认「仅本页出现」的视频**，
   共享的一律不用（那是版块/主题视频，不是这个产品的视频）。

## 改法

- **Amazon 单图/多图/单视频**：用新抽取结果覆盖。
- **官网 单视频**：若该产品**没有独有视频** ⇒ **清空**（不是写「无」占位）。
- 其余格不动（Amazon 文本/链接 取自 bullets/ASIN，未受两条口径影响）。

## 纪律

- 只动本轮 record_id 前缀 + 指定渠道的行；
- 每格打印「改前 → 改后」摘要；
- 写完逐格回读比对；**清空也算一次断言**（回读必须是空）。

用法：
  python3 fix_cells.py            # 预演
  python3 fix_cells.py --apply
"""
import json
import re
import sys

sys.path.insert(0, "../../tools")
import note_empty_cells as NV
import removed_rows as RR
import site_video_scope
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
MINE_PREFIXES = ("reczz28QhOqu", "reczz28QhOte")


def fetch_all():
    out, page = [], None
    while True:
        url = (f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records?page_size=500"
               + (f"&page_token={page}" if page else ""))
        d = _req(url, token())["data"]
        out += d.get("items", [])
        if not d.get("has_more"):
            return out
        page = d.get("page_token")


def main():
    apply_ = "--apply" in sys.argv
    rows = [r for r in fetch_all() if r["record_id"].startswith(MINE_PREFIXES)]
    idx = {(r["fields"].get("渠道"), r["fields"].get("产品中文名"), r["fields"].get("内容类型")): r
           for r in rows}

    plan = []      # (key, 新值, 原因)

    # ── Amazon：单图/多图/单视频 用新抽取覆盖 ──────────────────────────────
    amz = {r["产品中文名"]: r for r in json.load(open("raw/amazon_products.json", encoding="utf-8"))
           if r.get("ok")}
    for name, r in amz.items():
        link, imgs, vids = r["链接"], r["图片"], r["视频"]
        if imgs:
            plan.append((("Amazon", name, "单图"), f"【图片】{imgs[0]}\n【链接】{link}", "改用 hiRes 商品图库"))
            if len(imgs) >= 2:
                plan.append((("Amazon", name, "多图"),
                             f"【图片】{imgs[0]}\n【图片】{imgs[1]}\n【链接】{link}", "改用 hiRes 商品图库"))
        # ★ 只认**可播放的真 mp4**：实测 `videos[]` 里两类 URL 并存 ——
        #   `…default.jobtemplate.mp4.480.mp4`（真档位，200 video/mp4）与
        #   `…videopreview.jobtemplate.mp4`（**模板占位，实测 404**）。
        #   没有可播放的 ⇒ **清空**（第一版留了旧值，`videopreview` 就是这么残留下来的）。
        play = [v for v in vids if re.search(r"\.jobtemplate\.mp4\.\d+\.mp4$", v["url"])]
        if play:
            plan.append((("Amazon", name, "单视频"),
                         f"【视频】{play[0]['url']}\n【链接】{link}",
                         f"改用 videos[] 真 mp4（可播 {len(play)}/{len(vids)} 条）"))
        else:
            # ★ 无素材时的正确值 = **≤5 字备注**，不是空串。
            #   原先这里写 ""，于是它会把备注又抹掉（第三次出现「两个脚本同一格两个答案」）。
            #   备注的定义只此一份，在 note_no_video 里。
            plan.append((("Amazon", name, "单视频"),
                         NV.cell_value(NV.NOTE_NO_VIDEO if r.get("ok") else NV.NOTE_NO_PAGE),
                         f"无产品视频（{len(vids)} 条均为占位/无视频）→ 写备注"))

    # ── 官网：单视频只认「仅本页出现」的视频 ───────────────────────────────
    site = [r for r in json.load(open("raw/site_products.json", encoding="utf-8")) if r.get("ok")]
    # ★ 口径从 site_video_scope 来，**不在这里再写一份**（写两份必然互相推翻）
    uniq_by = site_video_scope.site_video_scope(site)
    for r in site:
        uniq = uniq_by.get(r["产品中文名"], [])
        key = ("官网", r["产品中文名"], "单视频")
        if key not in idx:
            continue
        if uniq:
            plan.append((key, f"【视频】{uniq[0]}\n【发布】{r.get('published_at','')}\n【链接】{r['链接']}",
                         f"仅本页独有（{len(uniq)} 个可选）"))
        else:
            n_ = len(r.get("视频") or [])
            plan.append((key, NV.cell_value(NV.NOTE_SITE_SHARED if n_ else NV.NOTE_NO_VIDEO),
                         f"无独有视频（{n_} 个均为跨页共享）→ 写备注"))

    REMOVED = RR.keys_3()        # 已声明移除（形状与 key 一致，见 removed_rows.keys_3）
    changes = []
    for key, new, why in plan:
        if key in REMOVED:
            continue
        cur = idx[key]["fields"].get("采集数据") or ""
        if cur == new:
            continue
        changes.append((idx[key]["record_id"], key, cur, new, why))

    print(f"将修正 {len(changes)} 格（覆盖 {sum(1 for c in changes if c[3])} ｜ 清空 {sum(1 for c in changes if not c[3])}）\n")
    for rid, key, old, new, why in changes:
        print(f"── {key[0]} / {key[1]} / {key[2]}：{why}")
        print(f"   改前：{(old or '（空）').replace(chr(10), ' ⏎ ')[:110]}")
        print(f"   改后：{(new or '（清空）').replace(chr(10), ' ⏎ ')[:110]}")
    if not changes:
        print("✅ 无需修正")
        return 0

    if not apply_:
        print("\n（预演，未写；要真写加 --apply）")
        return 0

    url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_update"
    for i in range(0, len(changes), 100):
        part = changes[i:i + 100]
        r = _req(url, token(), {"records": [{"record_id": rid, "fields": {"采集数据": new}}
                                            for rid, _, _, new, _ in part]})
        if r.get("code") != 0:
            print("❌ 写入失败:", json.dumps(r, ensure_ascii=False)[:400])
            return 1
        print(f"  已写 {i + len(part)}/{len(changes)}")

    rows2 = {(r["fields"].get("渠道"), r["fields"].get("产品中文名"), r["fields"].get("内容类型")): r
             for r in fetch_all() if r["record_id"].startswith(MINE_PREFIXES)}
    bad = [k for _, k, _, new, _ in changes
           if ((rows2.get(k, {}).get("fields", {}).get("采集数据") or "") != new)]
    print(f"\n回读：{len(changes) - len(bad)}/{len(changes)} 格逐字一致" + ("" if not bad else f"；不符 {bad[:3]}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())