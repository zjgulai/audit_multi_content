#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改正 `渠道` 的平台名（2026-10-23 任务 2 暴露的一处**我自己的错**）。

## 错在哪

上一轮（`expand_platforms.py`）我从库内 `渠道` 的**既有值**推断三平台 = 官网 / Amazon / YouTube。
Owner 2026-10-23 任务 2 给的三个来源是：**官方独立站（momcozy.com）/ Amazon / TikTok** ——
第三个是 **TikTok**，不是 YouTube。依据是链接 3《Momcozy社媒账号盘点》第 51 行：
`Tiktok ｜ 北美 ｜ momcozyofficial ｜ https://www.tiktok.com/@momcozyofficial`。

⇒ 表里 45 行 `渠道 = YouTube` 必须改成 `TikTok`。

## 口径

1. **只改这一个值** —— 只动 `渠道`，`写死` 的映射 `{old: new}`，不做任何模糊匹配。
2. **只改该值的行** —— 其他行（`官网` / `Amazon`）一行不碰。
3. **fail-closed** —— 待改行的 `采集数据` 必须为空（有素材就说明采集已经跑过，
   改名会让「素材来自哪个平台」对不上 ⇒ 整批不改，先查清）。
4. **幂等** —— 已经是 `TikTok` 的行跳过；跑第二遍不会重复改。
5. 先落清单 `renamed_channel.json`；**默认预演**，`--apply` 才真改。

用法：
  python3 rename_channel.py            # 预演（默认）
  python3 rename_channel.py --apply    # 真改
"""
import json
import sys

sys.path.insert(0, "../../tools")
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
OLD, NEW = "YouTube", "TikTok"
MANIFEST = "renamed_channel.json"


def fetch_all():
    out, page = [], None
    while True:
        url = (f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records?page_size=500"
               + (f"&page_token={page}" if page else ""))
        r = _req(url, token())
        if r.get("code") != 0:
            raise SystemExit(f"读表失败：{json.dumps(r, ensure_ascii=False)[:400]}")
        d = r["data"]
        out += d.get("items", [])
        if not d.get("has_more"):
            return out
        page = d.get("page_token")


def main():
    apply_ = "--apply" in sys.argv
    rows = fetch_all()
    print(f"表内共 {len(rows)} 行 ｜ 改名 {OLD} → {NEW}")

    todo, dirty, already = [], [], 0
    for r in rows:
        c = r["fields"].get("渠道")
        if c == NEW:
            already += 1
        elif c == OLD:
            if r["fields"].get("采集数据") not in (None, "", [], {}):
                dirty.append((r["record_id"], r["fields"].get("产品中文名")))
            else:
                todo.append({"record_id": r["record_id"], "fields": {"渠道": NEW}})
    print(f"待改 {len(todo)} 行 ｜ 已是 {NEW}：{already} 行")
    if dirty:
        print(f"❌ 有 {len(dirty)} 行带素材，改名会让「素材来自哪个平台」对不上 —— 整批不改：")
        for rid, n in dirty:
            print(f"   {rid} {n}")
        return 1
    if not todo:
        print("✅ 无需改动")
        return 0

    json.dump({"app": APP, "table": TABLE, "old": OLD, "new": NEW,
               "reason": "任务 2 给的第三个来源是 TikTok（链接 3 第 51 行），不是 YouTube",
               "record_ids": [x["record_id"] for x in todo]},
              open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"清单已落 {MANIFEST}")

    if not apply_:
        print("\n（预演，未改；要真改加 --apply）")
        return 0

    url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_update"
    for i in range(0, len(todo), 100):
        part = todo[i:i + 100]
        r = _req(url, token(), {"records": part})
        if r.get("code") != 0:
            print("❌ 改名失败:", json.dumps(r, ensure_ascii=False)[:400])
            return 1
        print(f"  已改 {i + len(part)}/{len(todo)}")

    after = fetch_all()
    import collections
    print(f"\n完成 ｜ 渠道分布 {dict(collections.Counter(x['fields'].get('渠道') for x in after))}")
    return 0 if not [x for x in after if x["fields"].get("渠道") == OLD] else 1


if __name__ == "__main__":
    sys.exit(main())