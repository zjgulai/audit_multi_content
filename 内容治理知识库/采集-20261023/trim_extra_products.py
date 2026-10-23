#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「守衡测试」里**多余的产品**删掉，只留 Owner 指定的 9 个。

## 为什么有这件

Owner 2026-10-23 收窄：“**每个品线只采集 3 个具体产品**，多余的产品更新表格删除”。
原 15 个产品 → 9 个；被移出的 6 个产品 × 5 枚举 = **30 行**要删。

## 口径（**fail-closed**：拿不准就不删）

1. **保留集只有一个来源** —— `out_rows.json`（由 `build_prod_matrix.py` 的 `SPEC` 产出）。
   本件**不自己抄一份产品名单**（抄第二份必然过期 —— 本库栽过）。
2. **只删「本轮矩阵行」** —— record_id 必须落在 `MINE` 前缀内，**别人的行一行不碰**。
3. **只删「没有真东西」的行** —— 待删行的 `采集数据` / `渠道` 以及**全部人/引擎列**
   （问题等级 / 问题描述 / 证据+来源 / Codex* / 问题编号）**必须为空**。
   任何一个有值 ⇒ **整批不删**、打印是谁、退出码 1（宁可不删，不许把人的成果删掉）。
4. **只删 `产品中文名` 有值且不在保留集里的行** —— 空行不归本件管（那是 `drop_blank_rows.py` 的活）。
5. **先落清单再删** —— 清单 `deleted_extra_products.json`，含每个 record_id 的完整字段快照。
6. **默认预演** —— 不加 `--apply` 一行都不动。

用法：
  python3 trim_extra_products.py            # 预演（默认）
  python3 trim_extra_products.py --apply    # 真删
"""
import collections
import json
import sys

sys.path.insert(0, "../../tools")
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
MANIFEST = "deleted_extra_products.json"
MINE = "reczz28QgHoa"          # 本轮矩阵行的 record_id 前缀
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
    keep = {r["fields"]["产品中文名"] for r in json.load(open("out_rows.json", encoding="utf-8"))}
    print(f"保留集（来自 out_rows.json）：{len(keep)} 个产品")
    for k in sorted(keep):
        print(f"   ✓ {k}")

    rows = fetch_all()
    print(f"\n表内共 {len(rows)} 行")

    doomed, protected, foreign = [], [], []
    for r in rows:
        f = r["fields"]
        name = f.get("产品中文名")
        if not name or name in keep:
            continue
        if not r["record_id"].startswith(MINE):
            foreign.append((r["record_id"], name))
            continue
        dirty = {c: f.get(c) for c in PROTECT if f.get(c) not in (None, "", [], {})}
        (protected if dirty else doomed).append((r["record_id"], name, dirty))

    print(f"待删（多余产品、已确认无真东西）= {len(doomed)} 行")
    for c, n in collections.Counter(n for _, n, _ in doomed).items():
        print(f"   ✗ {n}  ×{c}")
    if foreign:
        print(f"⚠️ 非本轮行（前缀不是 {MINE}），**不碰**：{foreign}")
    if protected:
        print(f"\n❌ 有 {len(protected)} 行带着真东西，**整批不删**：")
        for rid, n, d in protected:
            print(f"   {rid} {n} → {d}")
        return 1

    ids = [rid for rid, _, _ in doomed]
    if not ids:
        print("\n✅ 没有多余产品，无需处理")
        return 0

    json.dump({"app": APP, "table": TABLE,
               "reason": "Owner 2026-10-23：每个品线只采集 3 个具体产品，多余的产品从表里删除",
               "keep": sorted(keep), "deleted_rows": len(ids),
               "records": [{"record_id": rid, "产品中文名": n,
                            "fields": next(r["fields"] for r in rows if r["record_id"] == rid)}
                           for rid, n, _ in doomed]},
              open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n清单已落 {MANIFEST}（{len(ids)} 行，含每行完整字段快照）")
    print(f"删后将剩 {len(rows) - len(ids)} 行")

    if not apply_:
        print("\n（预演，未删任何行；要真删加 --apply）")
        return 0

    url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_delete"
    r = _req(url, token(), {"records": ids})
    if r.get("code") != 0:
        print("❌ 删除失败:", json.dumps(r, ensure_ascii=False)[:400])
        return 1

    after = fetch_all()
    names = collections.Counter(x["fields"].get("产品中文名") for x in after)
    first = after[0]["fields"] if after else {}
    print(f"\n删除返回 OK ｜ 删后表内 {len(after)} 行")
    print(f"现在第 1 行 = {first.get('产品线')} | {first.get('产品中文名')} | {first.get('内容类型')}")
    print(f"剩余产品 {len(names)} 个，每个 5 行：{set(names.values()) == {5}}")
    left = [x["record_id"] for x in after if x["record_id"] in set(ids)]
    print(f"残留（应当 0）：{len(left)}")
    return 0 if not left and len(after) == len(rows) - len(ids) else 1


if __name__ == "__main__":
    sys.exit(main())