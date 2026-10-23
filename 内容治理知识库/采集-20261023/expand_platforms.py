#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把矩阵从「9 产品 × 5 枚举 = 45 行」扩到「× 3 平台 = 135 行」。

Owner 2026-10-23 选定：**数据采集要 3 个平台的** ⇒ 选 ② 135 行（9 × 5 × 3）。

## 怎么扩（**不加删除**，这是关键）

行序 = **渠道优先**：官网 45 → Amazon 45 → YouTube 45（与 `采集-20261022` 的
`_site()` → `_amazon()` → `_youtube()` 惯例一致，也贴合「按平台逐个抓」的采集方式）。

表里**现有那 45 行正好就是官网那一段**（同为 产品 → 形态 序）⇒ 所以：

1. **给现有 45 行补 `渠道 = 官网`**（batch_update，只写这一列）；
2. **新建 Amazon 45 + YouTube 45 = 90 行**（batch_create）。

**不删任何行** —— 前两次删除是你明确要求的（表首空行、多余产品），
这次的「换顺序」不值得再删一次（上一次删除已经丢掉 46 个 record_id 与记录历史）。

## 口径（fail-closed）

1. 现有行必须**逐格对上** payload 的前 45 行（`产品线` / `产品中文名` / `内容类型`），
   对不上 ⇒ **整批不动**、退出码 1（说明表已不是我以为的样子，先查清再说）。
2. 现有行的 `渠道` **必须是空的**才补；**已经有值的行不许覆盖**（那可能是人填的）⇒ fail-closed。
   为什么这条特别要守：`feishu_publish.py` 里记着两起「元数据被占位值冲掉」的事故
   （rev77 内容类型「广告语」→「未指定」，两次都靠人恢复原值）。
3. 待建行若表里**已存在同组合**（产品+平台+形态）⇒ 跳过（幂等，重跑不重复建）。
4. **默认预演** —— 不加 `--apply` 一行都不动。

用法：
  python3 expand_platforms.py            # 预演（默认）
  python3 expand_platforms.py --apply    # 真做
"""
import json
import sys

sys.path.insert(0, "../../tools")
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
FIRST_CHANNEL = "官网"
KEY = ("产品线", "产品中文名", "内容类型")


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
    payload = json.load(open("out_rows.json", encoding="utf-8"))
    chs = []
    for r in payload:
        if r["fields"]["渠道"] not in chs:
            chs.append(r["fields"]["渠道"])
    n_web = sum(1 for r in payload if r["fields"]["渠道"] == FIRST_CHANNEL)
    print(f"payload {len(payload)} 行 ｜ 平台 {chs} ｜ 首个平台「{FIRST_CHANNEL}」{n_web} 行")

    rows = fetch_all()
    print(f"表内现有 {len(rows)} 行")

    # ── 1) 对齐检查：现有行必须 = payload 的首段（逐格）
    head = payload[:n_web]
    if len(rows) != n_web:
        print(f"❌ 现有 {len(rows)} 行 ≠ 首段 {n_web} 行 —— 表已不是预期形状，整批不动")
        return 1
    for i, (a, b) in enumerate(zip(rows, head), 1):
        fa, fb = a["fields"], b["fields"]
        for c in KEY:
            if fa.get(c) != fb.get(c):
                print(f"❌ 第 {i} 行「{c}」对不上：表={fa.get(c)!r} payload={fb.get(c)!r} —— 整批不动")
                return 1

    # ── 2) 渠道列：只补空的，已有值的一律不动
    to_update, already = [], 0
    for a in rows:
        cur = a["fields"].get("渠道")
        if cur in (None, "", [], {}):
            to_update.append({"record_id": a["record_id"], "fields": {"渠道": FIRST_CHANNEL}})
        elif cur == FIRST_CHANNEL:
            already += 1
        else:
            print(f"❌ {a['record_id']} 的「渠道」已有值 {cur!r}，不许覆盖 —— 整批不动")
            return 1
    print(f"待补 渠道={FIRST_CHANNEL}：{len(to_update)} 行 ｜ 已是该值：{already} 行")

    # ── 3) 待建：payload 首段之后的行，跳过表里已存在的组合
    exist = {(a["fields"].get("产品线"), a["fields"].get("产品中文名"),
              a["fields"].get("内容类型"), a["fields"].get("渠道")) for a in rows}
    to_create = [r for r in payload[n_web:]
                 if (r["fields"]["产品线"], r["fields"]["产品中文名"],
                     r["fields"]["内容类型"], r["fields"]["渠道"]) not in exist]
    print(f"待建：{len(to_create)} 行（payload 其余 {len(payload) - n_web} 行，已存在的跳过）")

    if not apply_:
        print("\n（预演，未改未建；要真做加 --apply）")
        return 0

    if to_update:
        url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_update"
        for i in range(0, len(to_update), 100):
            part = to_update[i:i + 100]
            r = _req(url, token(), {"records": part})
            if r.get("code") != 0:
                print("❌ 更新失败:", json.dumps(r, ensure_ascii=False)[:400])
                return 1
            print(f"  已补 渠道 {i + len(part)}/{len(to_update)}")

    if to_create:
        url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_create"
        for i in range(0, len(to_create), 100):
            part = to_create[i:i + 100]
            r = _req(url, token(), {"records": [{"fields": x["fields"]} for x in part]})
            if r.get("code") != 0:
                print("❌ 创建失败:", json.dumps(r, ensure_ascii=False)[:400])
                return 1
            print(f"  已建 {i + len(part)}/{len(to_create)}")

    after = fetch_all()
    print(f"\n完成 ｜ 表内现有 {len(after)} 行")
    return 0 if len(after) == len(payload) else 1


if __name__ == "__main__":
    sys.exit(main())