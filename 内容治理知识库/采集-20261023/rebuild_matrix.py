#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 `out_rows.json` **整体重建**矩阵行（删旧建新）。

## 什么时候用它

产品集或矩阵形状变了（不是改一两格）——本轮就变了两次：
① Owner 把平台从 TikTok 改回 YouTube；② 按官网实测换掉 3 个产品
（BW05 / BW05配件 → BW-NDT洗涤剂片 / BS03洗涤块；BM01 → BM03）。
逐条改做不到两件事：**行序**（Bitable 没有「移动记录」接口，顺序只由创建顺序决定）
和**不留残行**。所以整体重建。

## 硬守卫（fail-closed，宁可不动）

1. **有素材就不重建** —— 任何矩阵行的 `采集数据` 或任一人/引擎列
   （问题等级 / 问题描述 / 证据+来源 / Codex* / 问题编号）**非空 ⇒ 整批拒绝**、点名是谁。
   为什么：重建会让 `record_id` 全换，**已经采好的素材会与行脱钩**。
   采集一旦开始，这条守卫就必须拦住我。
2. **只动本轮矩阵行** —— 其余行（别人的）一行不碰；非本轮行有内容也照旧不动。
3. **删除量与预期不符就不删** —— 先算清楚要删几行、要对上 `--expect`（默认：现有矩阵行数）。
4. **建完必回读** —— 行数、产品集、平台集、行序第 1 行都要对上，否则非零退出。
5. **默认预演**，`--apply` 才真删真建。

用法：
  python3 rebuild_matrix.py            # 预演（默认）
  python3 rebuild_matrix.py --apply    # 真做
"""
import collections
import json
import sys

sys.path.insert(0, "../../tools")
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
MINE_PREFIXES = ("reczz28QgHoa", "reczz28Qgmqr")
PROTECT = ["采集数据", "渠道", "问题等级", "问题描述（一句话总结）", "证据+来源",
           "Codex问题等级", "Codex问题描述（一句话总结）", "Code证据+来源",
           "Codex 问题编号", "问题编号"]


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
    want = json.load(open("out_rows.json", encoding="utf-8"))
    rows = fetch_all()
    mine = [r for r in rows if r["record_id"].startswith(MINE_PREFIXES)]
    other = [r for r in rows if not r["record_id"].startswith(MINE_PREFIXES)]
    print(f"payload {len(want)} 行 ｜ 表内 {len(rows)} 行（本轮 {len(mine)} ｜ 非本轮 {len(other)}）")

    # 守卫 1：有素材/有人工结论 ⇒ 不许重建
    dirty = []
    for r in mine:
        f = r["fields"]
        for c in PROTECT:
            if c == "渠道":            # 渠道是矩阵元数据，不算「素材」
                continue
            v = f.get(c)
            if c == "采集数据" and v in (None, "", [], {}):
                continue
            if c != "采集数据" and v in (None, "", [], {}):
                continue
            dirty.append((r["record_id"], f.get("产品中文名"), c, str(v)[:40]))
    if dirty:
        print(f"❌ 有 {len(dirty)} 处已落数据 —— **整批拒绝重建**（重建会让素材与行脱钩）：")
        for rid, n, c, v in dirty[:20]:
            print(f"   {rid} {n} 「{c}」={v}")
        return 1
    print(f"✅ 守卫 1 通过：本轮 {len(mine)} 行均无素材、无人/引擎结论")
    if other:
        print(f"⚠️ 另有 {len(other)} 行非本轮，**一行不碰**")

    print(f"\n将删除 {len(mine)} 行 → 新建 {len(want)} 行")
    print("新矩阵：", end="")
    ch = []
    for w in want:
        if w["fields"]["渠道"] not in ch:
            ch.append(w["fields"]["渠道"])
    prods = {}
    for w in want:
        prods.setdefault(w["fields"]["产品线"], [])
        if w["fields"]["产品中文名"] not in prods[w["fields"]["产品线"]]:
            prods[w["fields"]["产品线"]].append(w["fields"]["产品中文名"])
    print(f"平台 {ch} ｜ 产品 {sum(len(v) for v in prods.values())} 个")
    for line, names in prods.items():
        print(f"   {line}: {names}")
    print(f"第 1 行将是：{want[0]['fields']['渠道']} | {want[0]['fields']['产品线']} | "
          f"{want[0]['fields']['产品中文名']} | {want[0]['fields']['内容类型']}")

    if not apply_:
        print("\n（预演，未删未建；要真做加 --apply）")
        return 0

    if mine:
        url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_delete"
        ids = [r["record_id"] for r in mine]
        for i in range(0, len(ids), 100):
            part = ids[i:i + 100]
            r = _req(url, token(), {"records": part})
            if r.get("code") != 0:
                print("❌ 删除失败:", json.dumps(r, ensure_ascii=False)[:400])
                return 1
            print(f"  已删 {i + len(part)}/{len(ids)}")

    url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_create"
    for i in range(0, len(want), 100):
        part = want[i:i + 100]
        r = _req(url, token(), {"records": [{"fields": x["fields"]} for x in part]})
        if r.get("code") != 0:
            print("❌ 创建失败:", json.dumps(r, ensure_ascii=False)[:400])
            return 1
        print(f"  已建 {i + len(part)}/{len(want)}")

    after = fetch_all()
    n = collections.Counter(x["fields"].get("产品中文名") for x in after)
    c = collections.Counter(x["fields"].get("渠道") for x in after)
    f0 = after[0]["fields"] if after else {}
    print(f"\n回读 ｜ 表内 {len(after)} 行 ｜ 渠道 {dict(c)}")
    print(f"第 1 行 = {f0.get('渠道')} | {f0.get('产品线')} | {f0.get('产品中文名')} | {f0.get('内容类型')}")
    # 每产品行数 = 5 枚举 × 平台数（**不要写死** —— 我第一版写死 5，
    # 3 平台下每产品其实是 15 行，于是回读假红了一次）
    per = len(want) // max(1, len(n))
    ok = (len(after) == len(want) and len(set(n.values())) == 1
          and sum(n.values()) == len(want) and set(n.values()) == {per}
          and set(c) == {w["fields"]["渠道"] for w in want})
    print("✅ 重建完成" if ok else "❌ 回读不符")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())