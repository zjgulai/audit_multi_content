#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把会话目录映射回（轮次，用例）：按首条用户消息 == 提示词原文 + 创建时间聚类。

用法：/usr/bin/python3 map_rounds.py [--write]
写入 _eval/run-ledger.json（与已有手工台账合并）。
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scan_sessions as ss  # noqa: E402

EVAL = os.path.dirname(HERE)
GAP = 300          # 秒：相邻会话间隔 > 5 分钟 → 视为新一轮
ROUND1_START = "2026-09-30T15:50:00"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--since", default=ROUND1_START)
    args = ap.parse_args()

    import datetime as dt
    since_ts = dt.datetime.fromisoformat(args.since).timestamp()

    cases = {str(x["id"]): x["prompt"] for x in json.load(open(os.path.join(HERE, "cases-a.json"), encoding="utf-8"))}
    rev = {v: k for k, v in cases.items()}

    rows = []
    for aid, fp in ss.iter_sessions(since_ts=since_ts - 60):
        try:
            created, first_user, n = ss.read_head(fp)
        except Exception:
            continue
        if first_user in rev and n > 20:          # 排除空壳会话
            rows.append({"created": created or 0, "agent_id": aid,
                         "case_id": rev[first_user], "n_events": n})
    rows.sort(key=lambda r: r["created"])

    # 聚类成轮次：用显式时间边界（轮次启动时刻已知），避免批次间隔造成误切
    bounds = [("2026-09-30T16:15:00", 1), ("2026-09-30T16:45:00", 2)]
    def round_of(ms):
        for b, r in bounds:
            if ms < dt.datetime.fromisoformat(b).timestamp() * 1000:
                return r
        return 3
    rounds_map = {}
    for r in rows:
        r["round"] = round_of(r["created"])
        rounds_map.setdefault(r["round"], []).append(r)
    rounds = [rounds_map[k] for k in sorted(rounds_map)]

    print(f"匹配会话 {len(rows)} 个，聚成 {len(rounds)} 轮")
    ledger = {}
    if os.path.exists(os.path.join(HERE, "run-ledger.json")):
        ledger = json.load(open(os.path.join(HERE, "run-ledger.json"), encoding="utf-8"))
    for i, grp in enumerate(rounds, 1):
        ids = sorted({r["case_id"] for r in grp}, key=int)
        t0 = time.strftime("%H:%M:%S", time.localtime(grp[0]["created"] / 1000))
        t1 = time.strftime("%H:%M:%S", time.localtime(grp[-1]["created"] / 1000))
        print(f"  轮{i}: {len(grp)} 会话  {t0}–{t1}  覆盖 {len(ids)} 条用例；缺 {sorted(set(cases)-set(ids), key=int)}")
        for r in grp:
            r["round"] = i
            ledger[r["agent_id"]] = {"round": i, "case_id": int(r["case_id"]), "paper": "a"}

    if args.write:
        json.dump(ledger, open(os.path.join(HERE, "run-ledger.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("-> run-ledger.json （%d 条）" % len(ledger))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
