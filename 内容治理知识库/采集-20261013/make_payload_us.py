#!/usr/bin/env python3
"""生成 US 版写入载荷，并列出「我上一轮那 80 行」的 record_id（待撤）。

原则：**只动我自己写的行** —— 另一批（16:01:42）的 record_id 一律不碰。
"""
import json, os, re, sys

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out")
MINE_STAMP = "2026-10-13T15:59:26"


def main():
    rows = json.load(open(os.path.join(OUT, "rows_us.json")))
    recs = []
    for r in rows:
        rec = {"内容 ID": r["内容 ID"], "采集数据": r["采集数据"],
               "内容类型": r["内容类型"], "渠道": r["渠道"],
               "产品线": r["产品线"], "状态": ["待审"]}
        dt = (r.get("发布时间") or "").strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
            rec["发布时间"] = dt
        recs.append(rec)
    json.dump({"create_records": recs}, open(os.path.join(OUT, "write_payload_us.json"), "w"),
              ensure_ascii=False)
    print("待写入:", len(recs), "行")
    ids = [r["内容 ID"] for r in recs]
    assert len(ids) == len(set(ids)), "内容 ID 重复"
    assert all(r["采集数据"].strip() for r in recs), "有空采集数据"
    from collections import Counter
    print("  类型:", dict(Counter(r["内容类型"] for r in recs)))
    print("  品类:", dict(Counter(r["产品线"] for r in recs)))

    # 我自己那 80 行（待撤）
    b = json.load(open(os.path.join(OUT, "backup_table_20261013.json")))
    mine = [r for r in b if (r.get("写入时间") or "").startswith(MINE_STAMP)]
    other = [r for r in b if not (r.get("写入时间") or "").startswith(MINE_STAMP)]
    mids = [r["_record_id"] for r in mine if r.get("_record_id")]
    json.dump(mids, open(os.path.join(OUT, "delete_ids_mine.json"), "w"), indent=1)
    print(f"\n待撤（我自己的）: {len(mids)} 行")
    print(f"保留（另一批，绝不碰）: {len(other)} 行")
    print("  另一批写入时间:", sorted({(r.get('写入时间') or '')[:19] for r in other}))


if __name__ == "__main__":
    main()
