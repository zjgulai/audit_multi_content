#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话索引器（回填员侧）：按「首条用户消息」把 DSH 会话目录映射回用例。

用途：用 workflow 批量跑盲测时，agent() 不返回 agent_id，于是按
「会话首条用户消息 == 提示词原文」+ 创建时间窗口做一一映射；顺带逐字取证
（skill 工具调用 / 最终回复原文）。

用法：
  /usr/bin/python3 scan_sessions.py --since 2026-09-30T16:10:00 --out _eval/wf-round-2.json
  /usr/bin/python3 scan_sessions.py --match "这个算 P0 吗"     # 单条排查
"""
import argparse
import datetime as dt
import json
import os
import sys

import zstandard

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_evidence as se  # noqa: E402

SESS = os.path.expanduser("~/.dsh/sessions")


def iter_sessions(since_ts=None):
    for base in sorted(os.listdir(SESS)):
        if "~5185~5BB9~6CBB~7406" not in base:      # 「内容治理」cwd 命名空间
            continue
        d = os.path.join(SESS, base)
        for aid in sorted(os.listdir(d)):
            p = os.path.join(d, aid)
            if not os.path.isdir(p):
                continue
            files = [os.path.join(p, f) for f in os.listdir(p) if f.endswith(".jsonl.zstd")]
            if not files:
                continue
            fp = max(files, key=os.path.getmtime)
            if since_ts and os.path.getmtime(fp) < since_ts:
                continue
            yield aid, fp


def read_head(fp, max_bytes=3_000_000):
    with open(fp, "rb") as fh:
        txt = zstandard.ZstdDecompressor().stream_reader(fh).read().decode("utf-8", "replace")
    created, first_user, n_ev = None, "", 0
    for line in txt.split("\n"):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        n_ev += 1
        if e.get("type") == "session" and created is None:
            created = e.get("createdAt")
        if e.get("type") == "user/message" and not first_user:
            t = se._msg_text(e.get("data") or {})
            if t.strip():
                first_user = t
    return created, first_user, n_ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO 本地时间，只扫此后的会话")
    ap.add_argument("--match", help="只打印首条用户消息含该串的会话")
    ap.add_argument("--out")
    args = ap.parse_args()

    since_ts = None
    if args.since:
        since_ts = dt.datetime.fromisoformat(args.since).timestamp()

    rows = []
    for aid, fp in iter_sessions(since_ts):
        try:
            created, first_user, n_ev = read_head(fp)
        except Exception as exc:
            print(f"[warn] {aid}: {exc}")
            continue
        if args.match and args.match not in first_user:
            continue
        rows.append({"agent_id": aid, "created": created, "first_user": first_user,
                     "n_events": n_ev, "path": fp})

    rows.sort(key=lambda r: r["created"] or 0)
    for r in rows:
        ts = dt.datetime.fromtimestamp((r["created"] or 0) / 1000).strftime("%H:%M:%S")
        print(f"{ts} {r['agent_id'][:8]} ev={r['n_events']:>4} {r['first_user'][:70]!r}")
    if args.out:
        json.dump(rows, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("->", args.out)
    print(f"共 {len(rows)} 个会话")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
