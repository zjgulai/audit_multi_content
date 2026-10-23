#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把三个源已采到的数据写进 `采集数据`（Amazon / YouTube / 官网补采，三源通用）。

## 单元格写法（沿用库内既有四段制，只新增【视频】一个段名）

官网（`采集-20261023/build_site_rows.py` 已按此写）：
  【图片】/【发布】/【视频】/【文案】/【链接】
Amazon（无发布日期，故不带【发布】）：
  · 单图   →【图片】×1 ＋【链接】
  · 多图   →【图片】×2 ＋【链接】
  · 单视频 →【视频】×1 ＋【链接】
  · 文本   →【文案】标题＋bullets ≤200 词 ＋【链接】
  · 链接   →【链接】
YouTube：
  · 单视频 →【视频】＋【发布】＋【链接】
  · 文本   →【文案】标题＋描述 ≤200 词 ＋【发布】＋【链接】
  · 单图   →【图片】缩略图 ＋【发布】＋【链接】
  · 多图   →【图片】×2（两条视频的缩略图）＋【发布】＋【链接】
  · 链接   →【发布】＋【链接】

## 纪律
1. **无素材 = 留空并点名**，不写「暂无」占位（占位会被当成已采集）。
2. **不覆盖**：目标格已有内容 ⇒ **跳过并计数**（官网那 29 格就是上一轮写好的，重跑要幂等）。
3. 只动本轮 record_id 前缀 + 指定 `渠道` 的行。
4. 写完**逐格回读比对**。

用法：
  python3 build_collect_rows.py            # 预演
  python3 build_collect_rows.py --apply
"""
import json
import os
import sys

sys.path.insert(0, "../../tools")
import removed_rows as RR
import site_video_scope
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
MINE_PREFIXES = ("reczz28QhOqu", "reczz28QhOte")
FORMS = ["单图", "多图", "单视频", "文本", "链接"]


def words(s, n=200):
    s = " ".join((s or "").split())
    w = s.split()
    return s if len(w) <= n else " ".join(w[:n]) + "…"


#: 官网视频的取舍口径 —— **只此一处**（`site_video_scope.py` 的模块头写了依据）。
#: 原先 build 与 fix 各写一份，结果 build 把 fix 清空的 3 格又填回去 ⇒ 抽成一个模块。
REMOVED = RR.keys_3()               #: 已声明移除的组合（形状与下面的 key 一致，见 removed_rows.keys_3）
_SITE_UNIQ = site_video_scope.site_video_scope(
    json.load(open("raw/site_products.json", encoding="utf-8")))


def cell_site(r, form):
    link, pub = r["链接"], r.get("published_at", "")
    imgs = r.get("图片") or []
    # ★ 用**仅本页独有**的视频；跨页共享的不算（见 site_video_scope 头部依据）
    vids = _SITE_UNIQ.get(r["产品中文名"], [])
    txt = (r.get("og_description") or "").strip() or (r.get("body_text") or "").strip()
    return {
        "单图": lambda: f"【图片】{imgs[0]}\n【发布】{pub}\n【链接】{link}" if imgs else None,
        "多图": lambda: (f"【图片】{imgs[0]}\n【图片】{imgs[1]}\n【发布】{pub}\n【链接】{link}"
                       if len(imgs) >= 2 else None),
        "单视频": lambda: f"【视频】{vids[0]}\n【发布】{pub}\n【链接】{link}" if vids else None,
        "文本": lambda: f"【文案】{words(txt)}\n【发布】{pub}\n【链接】{link}" if txt else None,
        "链接": lambda: f"【发布】{pub}\n【链接】{link}" if link else None,
    }[form]()


def cell_amazon(r, form):
    link = r["链接"]
    imgs, vids = r.get("图片") or [], r.get("视频") or []
    body = " ".join([r.get("标题", "")] + list(r.get("bullets") or []))
    return {
        "单图": lambda: f"【图片】{imgs[0]}\n【链接】{link}" if imgs else None,
        "多图": lambda: f"【图片】{imgs[0]}\n【图片】{imgs[1]}\n【链接】{link}" if len(imgs) >= 2 else None,
        "单视频": lambda: f"【视频】{vids[0]}\n【链接】{link}" if vids else None,
        "文本": lambda: f"【文案】{words(body)}\n【链接】{link}" if body.strip() else None,
        "链接": lambda: f"【链接】{link}",
    }[form]()


def cell_youtube(r, form):
    vs = r.get("videos") or []
    if not vs:
        return None
    v = vs[0]
    pub, url, thumb = v.get("uploadDate", ""), v.get("url", ""), v.get("thumb", "")
    body = v.get("title", "") + " " + (v.get("desc") or "")
    return {
        "单视频": lambda: f"【视频】{url}\n【发布】{pub}\n【链接】{url}",
        "文本": lambda: f"【文案】{words(body)}\n【发布】{pub}\n【链接】{url}",
        "单图": lambda: f"【图片】{thumb}\n【发布】{pub}\n【链接】{url}",
        "多图": lambda: (f"【图片】{vs[0]['thumb']}\n【图片】{vs[1]['thumb']}\n【发布】{pub}\n【链接】{url}"
                       if len(vs) >= 2 else None),
        "链接": lambda: f"【发布】{pub}\n【链接】{url}",
    }[form]()


SOURCES = [
    ("官网", "raw/site_products.json", cell_site, "is_bundle"),
    ("Amazon", "raw/amazon_products.json", cell_amazon, None),
    ("YouTube", "raw/youtube_products.json", cell_youtube, None),
]


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

    updates, blanks, skipped, problems = [], [], [], []
    for chan, path, fn, bundle_key in SOURCES:
        if not os.path.exists(path):
            problems.append((chan, "原始数据文件不存在"))
            continue
        data = json.load(open(path, encoding="utf-8"))
        got = [r for r in data if r.get("ok")]
        missing = [r for r in data if not r.get("ok")]
        print(f"\n### {chan}：{len(got)}/{len(data)} 个产品有素材"
              + (f" ｜ 整个产品无素材 {len(missing)} 个" if missing else ""))
        # ★ 整个产品没采到 ⇒ 它的 5 格都要算「留空」，否则统计会少报
        for rec in missing:
            why = (rec.get("reason") or "该源未采到")[:60]
            for form in FORMS:
                # ★ 先看这格有没有内容 —— 与下面 got 那条路**同一判法**。
                #   原先这条路不看，于是把**已写过备注**的格也算成「留空」
                #   （实测多报 3 格：报 15、表里其实只有 12 格真空）。
                k = (chan, rec["产品中文名"], form)
                if k in REMOVED:            # 已声明移除 ⇒ 行都没了，不算「留空」
                    continue
                if (idx.get(k, {}).get("fields", {}).get("采集数据") or "").strip():
                    skipped.append(k)
                    continue
                blanks.append((chan, rec["产品中文名"], form, why))
        for rec in got:
            name = rec["产品中文名"]
            for form in FORMS:
                key = (chan, name, form)
                if key in REMOVED:          # 已声明移除（`removed_rows.py`）→ 不再补
                    continue
                if key not in idx:
                    problems.append((chan, f"{name}/{form} 表里没有这一行"))
                    continue
                cur = idx[key]["fields"].get("采集数据")
                if cur:
                    skipped.append(key)
                    continue
                v = fn(rec, form)
                if not v:
                    blanks.append((chan, name, form,
                                   "bundle 页" if bundle_key and rec.get(bundle_key) else "该形态无素材"))
                    continue
                if bundle_key and rec.get(bundle_key) and form in ("单图", "多图", "单视频", "文本"):
                    v = v.replace("\n【链接】", "\n【来源】bundle 页（官网无独立商品页）\n【链接】", 1)
                updates.append((idx[key]["record_id"], key, v))

    print(f"\n{'='*66}")
    print(f"待写入 {len(updates)} 格 ｜ 已有内容跳过 {len(skipped)} 格 ｜ 无素材留空 {len(blanks)} 格")
    if blanks:
        print("\n留空（不占位、不编）：")
        for c, n, f, why in blanks:
            print(f"   - {c:7s} {n:26s} {f:5s}：{why}")
    if problems:
        print("\n异常：")
        for p in problems:
            print("   -", p)

    if updates:
        print("\n将写这些格（预演也列出来，便于核对）：")
        for rid, k, v in updates:
            cur = (idx[k]["fields"].get("采集数据") or "（空）").replace("\n", " ⏎ ")
            print(f"   + {k[0]:7s} {k[1]:26s} {k[2]:5s}  改前：{cur[:70]}")

    if not apply_:
        print("\n（预演，未写；要真写加 --apply）")
        return 0

    url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_update"
    for i in range(0, len(updates), 100):
        part = updates[i:i + 100]
        r = _req(url, token(), {"records": [{"record_id": rid, "fields": {"采集数据": v}}
                                            for rid, _, v in part]})
        if r.get("code") != 0:
            print("❌ 写入失败:", json.dumps(r, ensure_ascii=False)[:400])
            return 1
        print(f"  已写 {i + len(part)}/{len(updates)}")

    rows2 = {(r["fields"].get("渠道"), r["fields"].get("产品中文名"), r["fields"].get("内容类型")): r
             for r in fetch_all() if r["record_id"].startswith(MINE_PREFIXES)}
    bad = [k for _, k, v in updates if (rows2.get(k, {}).get("fields", {}).get("采集数据") or "") != v]
    print(f"\n回读：{len(updates) - len(bad)}/{len(updates)} 格逐字一致"
          + ("" if not bad else f"；不一致 {len(bad)}：{bad[:3]}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())