#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 out_rows.json 写进飞书表，然后**以服务端为准**读回核验。

目标：base `RY2UbCRjXaeeWwscUPScVN5AnQc`（wiki `Lntdw8XqmifewjkdEckcXYH8nOV` 的真实 obj_token）
      / table `tblTPsjiyOHYfUc0`（「守衡测试」）

只写四列：`采集数据` / `产品线` / `渠道` / `内容类型`。
**人/引擎的列一个都不碰**（`序号` / `DSH问题数量` / `DSH（知识库）报告` /
`Codex问题数量` / `Codex(裸模型）报告` / `审核人`）—— 采集不等于判定。

用法：python3 write_rows.py [--dry-run]
"""
import json
import sys

sys.path.insert(0, "../../tools")
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
ALLOWED = {"采集数据", "产品线", "渠道", "内容类型"}
LIMIT = 100          # 单次 batch_create 上限


def chunk(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    dry = "--dry-run" in sys.argv
    rows = json.load(open("out_rows.json", encoding="utf-8"))

    # 写前自证：只写白名单里的列
    for r in rows:
        extra = set(r["fields"]) - ALLOWED
        assert not extra, f"出现白名单外字段: {extra}"
        assert set(r["fields"]) == ALLOWED, sorted(r["fields"])
    print(f"待写 {len(rows)} 行；字段 = {sorted(rows[0]['fields'])}；dry_run={dry}")

    t = token()
    url = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_create"

    if dry:
        print("dry-run：不发请求")
        return 0

    before = _req(f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records?page_size=200", t)
    n_before = before["data"].get("total")
    print(f"写前服务端 total = {n_before}")

    created = 0
    for part in chunk(rows, LIMIT):
        r = _req(url, t, {"records": [{"fields": p["fields"]} for p in part]})
        if r.get("code") != 0:
            print("❌ 写入失败:", json.dumps(r, ensure_ascii=False)[:600])
            return 1
        created += len(r["data"].get("records", []))
        print(f"  已创建 {created} 条")

    # ── 读回核验（以服务端为准）─────────────────────────────────────────────
    got, page = [], ""
    while True:
        u = f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records?page_size=200" + (f"&page_token={page}" if page else "")
        d = _req(u, t)
        got += d["data"].get("items", [])
        page = d["data"].get("page_token") or ""
        if not d["data"].get("has_more"):
            break
    print(f"读回服务端记录 {len(got)} 条（写前 {n_before}）")

    want = {json.dumps(p["fields"], ensure_ascii=False, sort_keys=True) for p in rows}
    have = set()
    for it in got:
        f = {k: v for k, v in (it.get("fields") or {}).items() if k in ALLOWED}
        if set(f) == ALLOWED:
            have.add(json.dumps({k: f[k] for k in ALLOWED}, ensure_ascii=False, sort_keys=True))
    missing = want - have
    print(f"本次 15 行在服务端逐字命中: {len(want) - len(missing)}/{len(want)}")
    if missing:
        print("❌ 读回缺行:", list(missing)[:2])
        return 1

    import collections
    print(" 内容类型:", dict(collections.Counter(it["fields"].get("内容类型") for it in got if it["fields"].get("内容类型"))))
    print(" 渠道    :", dict(collections.Counter(it["fields"].get("渠道") for it in got if it["fields"].get("渠道"))))
    print(" 产品线  :", dict(collections.Counter(it["fields"].get("产品线") for it in got if it["fields"].get("产品线"))))
    print("✅ 写入 + 读回核验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
