#!/usr/bin/env python3
"""把 out/rows.json 变成 lark-cli base +record-batch-create 的载荷。

只写这些字段（其余字段是人/引擎的，不碰）：
  内容 ID / 采集数据 / 内容类型 / 渠道 / 产品线 / 发布时间 / 状态
状态一律「待审」—— 采集不等于判定，不替评审链下结论。
"""
import json, os, re

HERE = os.path.dirname(__file__)
FIELDS = ["内容 ID", "采集数据", "内容类型", "渠道", "产品线", "发布时间", "状态"]


def main():
    rows = json.load(open(os.path.join(HERE, "out", "rows.json")))
    recs = []
    for r in rows:
        rec = {
            "内容 ID": r["内容 ID"],
            "采集数据": r["采集数据"],
            "内容类型": r["内容类型"],
            "渠道": r["渠道"],
            "产品线": r["产品线"],
            "状态": ["待审"],
        }
        dt = (r.get("发布时间") or "").strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
            rec["发布时间"] = dt
        recs.append(rec)

    payload = {"create_records": recs}
    p = os.path.join(HERE, "out", "write_payload.json")
    json.dump(payload, open(p, "w"), ensure_ascii=False)

    print("records:", len(recs))
    print("字节:", os.path.getsize(p))
    print("字段集合:", sorted({k for r in recs for k in r}))
    print("带发布时间的行:", sum(1 for r in recs if "发布时间" in r))
    # 自检：内容 ID 必须唯一，采集数据不能空
    ids = [r["内容 ID"] for r in recs]
    assert len(ids) == len(set(ids)), "内容 ID 有重复"
    assert all(r["采集数据"].strip() for r in recs), "有空的采集数据"
    print("自检通过：ID 唯一、采集数据非空")


if __name__ == "__main__":
    main()
