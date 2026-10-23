#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给**所有采不到素材的格**写备注：一句话说清「为什么这格是空的」，原因 ≤5 个字。

## Owner 的两句话（2026-10-23）

> ①「若该产品没有采集到视频，就备注下，该产品无视频」
> ②「所有空的都备注下原因，不超过5个字」

## 三条纪律（都是前面踩过的）

1. **备注按「该形态各自的原因」写，不能一格通吃。**
   例如 YouTube 的洗涤剂片：`单视频` 缺的是视频、`单图` 缺的是图 ——
   往 `单图` 那格写「产品无视频」**解释不了一张图为什么没有**。
   所以「整个源都没有这个产品」时用**源级**原因（`官方无素材` / `无商品页面`），
   只是缺视频时才用 `产品无视频`。
2. **措辞必须与事实相符。** Owner 原话「该产品无视频」在这两种情形下**是假话**，不能照抄：
   · 官网页面上**有 12 个视频**，只是与另两页共享、归不到本产品 ⇒ `无归属视频`；
   · Amazon **根本没有该产品的商品页** ⇒ `无商品页面`。
   往治理表里写假话，比空着更坏。
3. **原因 ≤5 个字**（Owner 第②句）。⭐ 顺带指出：Owner 第①句的「该产品无视频」**是 6 个字**，
   超了，所以压成「产品无视频」。
   ⚠️ 第一次给这条上限做反向对照时**对照是空的**（格子已写好、脚本走「无需写备注」，
   闸门一次都没被碰到）⇒ 现在把它抽成 `over_long()`，并用 `--selftest` 喂样本证明它能红。

## 备注写法

`【说明】` ＋ ≤5 字原因。带段名是为了**可机读** —— 单元格是段名制
（`【文案】/【发布】/【图片】/【视频】/【链接】/【来源】`），裸文字会被当成素材。
★ `【说明】` 是本轮新增的第 7 个段名，需 Owner 坐实。

用法：
  python3 note_empty_cells.py             # 预演
  python3 note_empty_cells.py --apply
  python3 note_empty_cells.py --selftest  # ★ ≤5 字上限的反向对照
"""
import json
import sys

sys.path.insert(0, "../../tools")
sys.path.insert(0, ".")
import site_video_scope as S                                     # noqa: E402
from lark_find import _req, token, BASE                          # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
MINE_PREFIXES = ("reczz28QhOqu", "reczz28QhOte")
MARK = "【说明】"
MAX_REASON = 5      #: Owner 定的上限
FORMS = ["单图", "多图", "单视频", "文本", "链接"]

#: 源级原因（整个源都没有这个产品）—— 该源 5 格全用它
NOTE_NO_PAGE = "无商品页面"      # Amazon 没有该产品的独立商品页
NOTE_NO_MATERIAL = "官方无素材"  # 官方号里没有该产品的素材
#: 形态级原因（只缺视频）—— 只用在「单视频」那一格
NOTE_NO_VIDEO = "产品无视频"
NOTE_SITE_SHARED = "无归属视频"  # 页面有视频，但与另两页共享、归不到本产品


def cell_value(reason):
    """**整格的值** = 段名 + ≤5 字原因 —— 只此一处拼。

    ⚠️ 2026-10-23 踩过：`fix_cells.py` 直接用了常量 `NOTE_NO_VIDEO`（**只有原因、没前缀**），
    于是它要把 9 格已写好的 `【说明】` **抹掉** —— 同一类 bug 的第 4 次
    （前三次：写入器 vs 修正器的视频口径、备注 vs 空串、留空判定两套）。
    根因都是「同一格的值由两处各自拼」⇒ 现在拼装也收口到这里。
    """
    return MARK + reason


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


def reason_map():
    """{(渠道, 产品中文名): [(形态, 原因), …]} —— 从**原始采集数据**推，不手判。

    「5 格全缺」时返回 5 条源级原因；「只缺视频」时只返回单视频那一条。
    """
    out = {}
    site = [r for r in json.load(open("raw/site_products.json", encoding="utf-8")) if r.get("ok")]
    uniq = S.site_video_scope(site)
    for r in site:
        n = r["产品中文名"]
        if not uniq.get(n):                      # 没有「仅本页独有」的视频
            note = NOTE_SITE_SHARED if (r.get("视频") or []) else NOTE_NO_VIDEO
            out[("官网", n)] = [("单视频", note)]

    for r in json.load(open("raw/amazon_products.json", encoding="utf-8")):
        n = r["产品中文名"]
        if not r.get("ok"):                      # 整个产品在 Amazon 没有独立页
            out[("Amazon", n)] = [(f, NOTE_NO_PAGE) for f in FORMS]
        elif not (r.get("视频") or []):           # 有页面、只是没有产品视频
            out[("Amazon", n)] = [("单视频", NOTE_NO_VIDEO)]

    for r in json.load(open("raw/youtube_products.json", encoding="utf-8")):
        n = r["产品中文名"]
        if not (r.get("videos") or []):
            # YouTube 的 5 个形态**全部**由视频派生（缩略图/标题/描述/发布日/链接）
            # ⇒ 没有视频就等于**该源没有这个产品的素材**，5 格同一个原因。
            out[("YouTube", n)] = [(f, NOTE_NO_MATERIAL) for f in FORMS]
    return out


def over_long(plan):
    """原因超过上限的那些 —— 抽成函数是为了能**喂样本自证**（见 --selftest）。"""
    return [n for _, _, n in plan if len(n.replace(MARK, "")) > MAX_REASON]


def selftest():
    """反向对照：证明这把闸门**真能变红**，不是恒绿的注释。"""
    cases = [
        ("正常样本不许红", over_long([("a", "b", cell_value("产品无视频"))]) == []),
        ("超限样本必须红（Owner 原话 6 字）",
         over_long([("a", "b", cell_value("该产品无视频"))]) == [cell_value("该产品无视频")]),
        ("边界 5 字不算超", over_long([("a", "b", cell_value("无商品页面"))]) == []),
        ("6 字必须算超", over_long([("a", "b", MARK + "无独立商品页")]) != []),
        ("空 plan 不许红", over_long([]) == []),
    ]
    for name, good in cases:
        print(f"  {'✅' if good else '❌'} {name}")
    return 0 if all(g for _, g in cases) else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    apply_ = "--apply" in sys.argv

    rows = [r for r in fetch_all() if r["record_id"].startswith(MINE_PREFIXES)]
    idx = {(r["fields"].get("渠道"), r["fields"].get("产品中文名"), r["fields"].get("内容类型")): r
           for r in rows}

    #  ⚠️ 不要写「有素材跳过 N 格」这种计数器去数 reason_map 里的格 ——
    #     reason_map **只会列出缺素材的格**，那个分支永远到不了，数出来恒为 0（假的）。
    #     改成能**对账的三个数**：有素材 / 已有备注 / 将写 = 总行数。
    plan, already = [], []
    for (chan, name), pairs in sorted(reason_map().items()):
        for form, why in pairs:
            row = idx.get((chan, name, form))
            if row is None:
                continue
            cur = (row["fields"].get("采集数据") or "").strip()
            if cur:
                already.append((chan, name, form))
                continue
            plan.append((row["record_id"], (chan, name, form), cell_value(why)))

    too_long = over_long(plan)
    if too_long:
        print("❌ 原因超过 5 个字（Owner 定的上限）：", set(too_long))
        return 1

    has_material = len(idx) - len(plan) - len(already)      # 对账：三数相加 = 总行数
    print(f"有素材 {has_material} 格 ｜ 已有备注 {len(already)} 格 ｜ 将写备注 {len(plan)} 格"
          f"  → 合计 {has_material + len(already) + len(plan)}（应等于 {len(idx)}）\n")
    for _, key, note in plan:
        print(f"  {key[0]:8s} {key[1]:26s} {key[2]:5s} {note}   ← 原因「{note.replace(MARK, '')}」"
              f"{len(note.replace(MARK, ''))} 字")
    by = {}
    for _, _, n in plan:
        by[n] = by.get(n, 0) + 1
    print("\n按措辞分：")
    for n, c in sorted(by.items()):
        print(f"  {c:2d} 格 ｜ {n}")
    if not plan:
        print("\n✅ 无需写备注")
        return 0
    if not apply_:
        print("\n（预演，未写；要真写加 --apply）")
        return 0

    for i in range(0, len(plan), 100):
        part = plan[i:i + 100]
        r = _req(f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_update", token(),
                 {"records": [{"record_id": rid, "fields": {"采集数据": note}}
                              for rid, _, note in part]})
        if r.get("code") != 0:
            print("❌ 写入失败:", json.dumps(r, ensure_ascii=False)[:400])
            return 1
        print(f"  已写 {i + len(part)}/{len(plan)}")

    rows2 = {(r["fields"].get("渠道"), r["fields"].get("产品中文名"), r["fields"].get("内容类型")): r
             for r in fetch_all() if r["record_id"].startswith(MINE_PREFIXES)}
    bad = [k for _, k, note in plan
           if (rows2.get(k, {}).get("fields", {}).get("采集数据") or "") != note]
    print(f"\n回读：{len(plan) - len(bad)}/{len(plan)} 格逐字一致" + ("" if not bad else f"；不符 {bad[:3]}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())