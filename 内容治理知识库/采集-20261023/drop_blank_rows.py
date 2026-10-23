#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「守衡测试」**最前面的全空行**删掉，让数据从第 1 行开始落。

## 为什么有这件

2026-10-23 Owner 当场纠正：「你要从第一行开始落数据，不要从中间开始落数据」。
成因：表里前 16 行是 2026-10-22 的残留（已被 Owner 于 10-23 09:45 / 10:02 逐格清空），
新写的 75 行只能追加在其后 ⇒ 数据落在第 17 行起，**上面顶着 16 行空白**。

## 口径（**保守**：只删「全空」，且只删「最前面连续的那一段」）

1. **只认全空**：一行 15 个字段**全部**为空才算空行（`问题等级` / `Codex 问题编号`
   这类 user/select 字段的空值是 `[]`，也算空）。**任何一个字段有值就不删** ——
   哪怕只有一个字，那也是人的东西。
2. **只删最前面连续的一段**：从第 1 行往后数，遇到第一个非空行就停。
   表中间的空行**不碰**（那可能是排版留白，不是本次要处理的对象）。
3. **先落清单再删**：被删的 record_id 全量写进 `dropped_blank_rows.json`，
   删完用它核对行数与剩余行序。
4. **默认预演**：不加 `--apply` 只打印将删什么、一行都不动。

用法：
  python3 drop_blank_rows.py            # 预演（默认）
  python3 drop_blank_rows.py --apply    # 真删
"""
import json
import sys

sys.path.insert(0, "../../tools")
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
MANIFEST = "dropped_blank_rows.json"


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


def is_blank(rec):
    """15 个字段全空才算空。空值形态：None / "" / [] / {}。"""
    for v in (rec.get("fields") or {}).values():
        if v not in (None, "", [], {}):
            return False
    return True


def main():
    apply_ = "--apply" in sys.argv
    rows = fetch_all()
    print(f"表内共 {len(rows)} 行")

    head = []
    for r in rows:
        if not is_blank(r):
            break                       # 口径 2：遇到第一个非空行就停
        head.append(r)

    print(f"最前面连续的全空行 = {len(head)} 行")
    if not head:
        print("✅ 第 1 行已经有数据，无需处理")
        return 0

    ids = [r["record_id"] for r in head]
    json.dump({"app": APP, "table": TABLE, "reason": "让数据从第 1 行开始（Owner 2026-10-23）",
               "blank_rows": len(ids), "record_ids": ids},
              open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"清单已落 {MANIFEST}（{len(ids)} 个 record_id）")
    print(f"删后将剩 {len(rows) - len(ids)} 行，数据从第 1 行开始")

    if not apply_:
        print("\n（预演，未删任何行；要真删加 --apply）")
        return 0

    url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_delete"
    r = _req(url, token(), {"records": ids})
    if r.get("code") != 0:
        print("❌ 删除失败:", json.dumps(r, ensure_ascii=False)[:400])
        return 1

    after = fetch_all()
    print(f"\n删除返回 OK ｜ 删后表内 {len(after)} 行")
    first = after[0]["fields"] if after else {}
    print(f"现在第 1 行 = {first.get('产品线')} | {first.get('产品中文名')} | {first.get('内容类型')}")
    still = [r["record_id"] for r in after if r["record_id"] in set(ids)]
    print(f"残留（应当 0）：{len(still)}")
    return 0 if not still and len(after) == len(rows) - len(ids) else 1


if __name__ == "__main__":
    sys.exit(main())