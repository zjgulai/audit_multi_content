#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把三轮盲测回填成 score-input.json（不碰 Excel），支持两套判定口径。

口径 A（延续口径，与上一轮发布的 v1.2.0 数字同尺）：
    触发 = 该会话加载了 kb-canonical-lookup；不触发 = 未加载（含加载了别的 skill）；
    追问 = 未加载任何 skill 且以追问收尾；调用类记 加载 / 未加载。
口径 B（行为口径，v1.2.0 与 v1.3.0 两侧同尺重算）：
    与 A 的唯一差别在「边界情况」行 —— 该行的预期结果写的是行为（追问澄清），
    故按**实际是否以追问澄清收尾**判：追问 = transcript 末尾是未获答复的
    ask_user_question（加载了 skill 也算追问，只要它没在缺主语时硬答）。
    正例 / 负例 / 近似命中三行仍按「加载与否」判，不引入追问。
"""
import argparse
import json
import os

WORK = os.path.dirname(os.path.abspath(__file__))
TARGET = "kb-canonical-lookup"


def conclusion(rec, conv):
    t = rec.get("type", "")
    loaded = TARGET in (rec.get("skill_calls") or [])
    if t == "调用":
        return "加载" if loaded else "未加载"
    if conv == "B" and t == "边界情况":
        if rec.get("awaiting_user"):
            return "追问"
        return "触发" if loaded else "不触发"
    return "触发" if loaded else "不触发"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", nargs=3, required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True, help="输出 score-input.json 路径")
    ap.add_argument("--conv", choices=["A", "B"], required=True)
    ap.add_argument("--dump", default="", help="可选：同时落一份逐轮明细 JSON")
    args = ap.parse_args()

    cases = json.load(open(args.cases, encoding="utf-8"))["cases"]
    order = [str(c["id"]) for c in cases]
    meta = {str(c["id"]): c for c in cases}
    rounds = [json.load(open(p, encoding="utf-8")) for p in args.rounds]

    results, detail = [], {}
    for cid in order:
        rs, rows = [], []
        for r in rounds:
            rec = r.get(cid)
            if rec is None:
                rs.append("")
                rows.append({"结论": "", "session": ""})
                continue
            c = conclusion(rec, args.conv)
            rs.append(c)
            rows.append({"结论": c, "session": rec.get("session", ""),
                         "loaded": TARGET in (rec.get("skill_calls") or []),
                         "awaiting_user": bool(rec.get("awaiting_user")),
                         "auto": rec.get("auto_conclusion", "")})
        c = meta[cid]
        results.append({"id": cid, "type": c["type"], "expected": c["expect"],
                        "tags": c["tags"], "title": c["title"], "rounds": rs})
        detail[cid] = rows

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"skill_name": TARGET, "results": results}, f, ensure_ascii=False, indent=2)
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(detail, f, ensure_ascii=False, indent=2)
    print(f"[ok] 口径 {args.conv} → {args.out}（{len(order)} 条 × 3 轮）")
    for r in results:
        if r["type"] in ("边界情况", "调用") or "触发" == r["rounds"][0]:
            pass
    for r in results:
        if r["type"] == "边界情况":
            print("   边界 #%s: %s" % (r["id"], r["rounds"]))


if __name__ == "__main__":
    main()
