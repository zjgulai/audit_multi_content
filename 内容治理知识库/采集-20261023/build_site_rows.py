#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把**官网已采到的数据**写进守衡测试表的 `采集数据` 列（只写 `渠道=官网` 的行）。

## 单元格写法（**沿用库内既有四段制，不自创**）

`采集-20261022/out_rows.json` 里官网行逐字是：
```
【文案】…
【发布】2026-09-23
【图片】https://cdn.shopify.com/…
【链接】https://momcozy.com/products/…
```
本轮 5 个 `内容类型` 是新的，按「同一套段名、只留该形态需要的那几段」组：
  · 单图   → 【图片】×1 ＋【发布】＋【链接】
  · 多图   → 【图片】×2 ＋【发布】＋【链接】
  · 单视频 → 【视频】×1 ＋【发布】＋【链接】   ← 【视频】是本轮新增的段名（库里原先没有视频素材）
  · 文本   → 【文案】≤200 词 ＋【发布】＋【链接】
  · 链接   → 【发布】＋【链接】
**每格都带【链接】**：没有链接的证据没法回源核对。

## 三条纪律

1. **采不到就不写** —— 该产品没采到（如官网 429 未补上）、或该形态无素材（如 BM04 站内 0 视频），
   **格子留空并在报告里点名**，不拿别的东西顶、不写「暂无」占位（占位会被当成已采集）。
2. **不覆盖** —— 目标格已有内容就整批拒绝，先报出是哪几格。
3. **只动 `渠道=官网` 的行**，且只动本轮 record_id 前缀的行。

用法：
  python3 build_site_rows.py            # 预演（默认，打印每格前 90 字）
  python3 build_site_rows.py --apply    # 真写
"""
import json
import sys

sys.path.insert(0, "../../tools")
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
MINE_PREFIXES = ("reczz28QhOqu", "reczz28QhOte")
FORMS = ["单图", "多图", "单视频", "文本", "链接"]


def words(s, n=200):
    w = s.split()
    return s if len(w) <= n else " ".join(w[:n]) + "…"


def cell(rec, form):
    """按形态组格子。返回 None = 该形态**无素材**（留空，不占位）。"""
    link, pub = rec["链接"], rec.get("published_at", "")
    imgs, vids = rec.get("图片") or [], rec.get("视频") or []
    txt = (rec.get("og_description") or "").strip() or (rec.get("body_text") or "").strip()
    if form == "单图":
        return f"【图片】{imgs[0]}\n【发布】{pub}\n【链接】{link}" if imgs else None
    if form == "多图":
        return (f"【图片】{imgs[0]}\n【图片】{imgs[1]}\n【发布】{pub}\n【链接】{link}"
                if len(imgs) >= 2 else None)
    if form == "单视频":
        return f"【视频】{vids[0]}\n【发布】{pub}\n【链接】{link}" if vids else None
    if form == "文本":
        return f"【文案】{words(txt)}\n【发布】{pub}\n【链接】{link}" if txt else None
    if form == "链接":
        return f"【发布】{pub}\n【链接】{link}" if link else None
    return None


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
    recs = [r for r in json.load(open("raw/site_products.json", encoding="utf-8")) if r.get("ok")]
    rows = [r for r in fetch_all() if r["record_id"].startswith(MINE_PREFIXES)
            and r["fields"].get("渠道") == "官网"]
    idx = {(r["fields"].get("产品中文名"), r["fields"].get("内容类型")): r for r in rows}
    print(f"官网行 {len(rows)} 行 ｜ 已采到素材的产品 {len(recs)} 个\n")

    updates, blank, conflict = [], [], []
    for rec in recs:
        name = rec["产品中文名"]
        for form in FORMS:
            v = cell(rec, form)
            key = (name, form)
            if key not in idx:
                conflict.append((key, "表里没有这一行"))
                continue
            if not v:
                blank.append((name, form, "该形态站内无素材"))
                continue
            cur = idx[key]["fields"].get("采集数据")
            if cur:
                conflict.append((key, f"已有内容：{str(cur)[:60]}"))
                continue
            updates.append((idx[key]["record_id"], key, v))

    print(f"将写入 {len(updates)} 格 ｜ 留空 {len(blank)} 格 ｜ 冲突 {len(conflict)} 格")
    if blank:
        print("\n留空（不占位、不编）：")
        for n, f, why in blank:
            print(f"   - {n} / {f}：{why}")
    if conflict:
        print("\n冲突（**整批不写**）：")
        for k, why in conflict:
            print(f"   - {k}：{why}")
        return 1

    print("\n样例（前 3 格）：")
    for rid, key, v in updates[:3]:
        print(f"  ── {key[0]} / {key[1]}\n     " + v.replace("\n", "\n     ")[:300])

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

    # 回读逐格核对（写完必验，不信写入返回）
    rows2 = {(r["fields"].get("产品中文名"), r["fields"].get("内容类型")): r
             for r in fetch_all() if r["record_id"].startswith(MINE_PREFIXES)
             and r["fields"].get("渠道") == "官网"}
    bad = [k for _, k, v in updates if (rows2.get(k, {}).get("fields", {}).get("采集数据") or "") != v]
    print(f"\n回读：{len(updates) - len(bad)}/{len(updates)} 格逐字一致"
          + ("" if not bad else f"；不一致：{bad[:5]}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())