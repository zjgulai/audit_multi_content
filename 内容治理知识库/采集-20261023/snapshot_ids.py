#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写前快照：把「守衡测试」当前所有 record_id 存成 before_ids.json。

**必须在写库之前跑**。它的唯一用途是给 `verify_rows.py` 断言 E 提供依据：
「本批新建的行不许出现在写前快照里」—— 也就是证明这次写入**没有覆盖既有行**。

为什么非要它（2026-10-23 的真实教训）：当天表里有一行样例数据在我读完之后、写之前
被**人**手动逐格清空了（10:02:16–19，见记录历史）。光看「现在没值」分不清
「是我写坏的」还是「别人清的」—— 有前后快照 + 记录历史才分得清。

用法：python3 snapshot_ids.py        # 输出 before_ids.json + 表内行数
"""
import json
import sys

sys.path.insert(0, "../../tools")
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
OUT = "before_ids.json"


def main():
    ids, page = [], None
    while True:
        url = (f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records?page_size=500"
               + (f"&page_token={page}" if page else ""))
        r = _req(url, token())
        if r.get("code") != 0:
            raise SystemExit(f"读表失败：{json.dumps(r, ensure_ascii=False)[:400]}")
        d = r["data"]
        ids += [x["record_id"] for x in d.get("items", [])]
        if not d.get("has_more"):
            break
        page = d.get("page_token")

    json.dump(sorted(ids), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"写前快照：{len(ids)} 行 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())