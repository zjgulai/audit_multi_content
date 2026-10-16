#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话耗时分析器（零侵入性能测量 · 不改 kb/ 任何文件）

用途：把 DSH 会话留痕（~/.dsh/sessions/<cwd>/<id>/session.jsonl.zstd）解成
      「一次审查到底把时间花在哪」的表，作为改前/改后的同一把尺子。

为什么不用给 kbpy 加计时：会话留痕里已经有每次工具调用的起止时间与完整命令，
      再往 kb/ 里塞埋点属于重复建设，且会动到权威库。**测量不该改被测物。**

输出三段：
  ① 概览：span / 工具占用 / 模型生成（span 减去工具区间并集）
  ② 按工具聚合
  ③ 最慢 N 次调用（带命令原文）

用法：
  python3 _perf-20261005/analyze_session.py one <session.jsonl.zstd> [--json out.json]
  python3 _perf-20261005/analyze_session.py children <parent-session-id> [--since-hours 6]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

try:
    import zstandard
except ImportError:  # pragma: no cover
    sys.exit("需要 python-zstandard（/usr/bin/python3 已自带）")

SESS_ROOT = os.path.expanduser("~/.dsh/sessions")


def load(path: str) -> list[dict]:
    raw = zstandard.ZstdDecompressor().stream_reader(open(path, "rb")).read()
    out = []
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def meta(recs: list[dict]) -> dict:
    m = {"id": None, "parent": None, "origin": None}
    for r in recs:
        if r.get("type") == "session":
            m.update(id=r.get("id"), parent=r.get("parentSession"), origin=r.get("origin"),
                     cwd=r.get("cwd"))
        elif r.get("type") == "subagent/descriptor":
            d = r.get("data") or {}
            m.update(label=d.get("label"), model=d.get("agentModel"),
                     provider=d.get("agentProvider"), effort=d.get("agentReasoningEffort"))
    return m


def tool_calls(recs: list[dict]) -> list[dict]:
    """配平 tool/call 与 tool/result，返回 [{sec, name, desc, start, end}]。"""
    ends: dict[str, int] = {}
    for r in recs:
        if r.get("type") != "tool/result":
            continue
        d = r.get("data") or {}
        cid = (d.get("message") or {}).get("source", {}).get("callId") or d.get("callId")
        if cid and r.get("time"):
            ends[cid] = r["time"]
    out = []
    for r in recs:
        if r.get("type") != "tool/call":
            continue
        d = r.get("data") or {}
        cid = d.get("callId")
        try:
            a = json.loads(d.get("arguments") or "{}")
        except json.JSONDecodeError:
            a = {}
        name = d.get("name") or "?"
        desc = a.get("command") or a.get("description") or a.get("name") or json.dumps(a, ensure_ascii=False)
        desc = " ".join(str(desc).split())
        start, end = r.get("time"), ends.get(cid)
        out.append({"sec": ((end - start) / 1000.0) if end else None,
                    "name": name, "desc": desc, "start": start, "end": end})
    return out


def union_seconds(intervals: list[tuple[int, int]]) -> float:
    iv = sorted((s, e) for s, e in intervals if s is not None and e is not None and e > s)
    tot, cur_s, cur_e = 0.0, None, None
    for s, e in iv:
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            tot += cur_e - cur_s
            cur_s, cur_e = s, e
    if cur_s is not None:
        tot += cur_e - cur_s
    return tot / 1000.0


def report(path: str, top: int = 15) -> dict:
    recs = load(path)
    m = meta(recs)
    ev = [r for r in recs if isinstance(r.get("time"), (int, float))]
    calls = tool_calls(recs)
    span = (max(r["time"] for r in ev) - min(r["time"] for r in ev)) / 1000.0 if ev else 0.0
    busy = union_seconds([(c["start"], c["end"]) for c in calls])
    by_name: dict[str, list[float]] = {}
    for c in calls:
        by_name.setdefault(c["name"], []).append(c["sec"] or 0.0)
    ranked = sorted([c for c in calls if c["sec"] is not None], key=lambda c: -c["sec"])

    print("=" * 84)
    print(f"会话 {m['id']}  origin={m['origin']}  parent={m['parent']}")
    if m.get("label"):
        print(f"标签 {m['label']!r}  模型 {m.get('model')}  推理档 {m.get('effort')}")
    print("=" * 84)
    print(f"总 span            {span:9.1f}s")
    print(f"工具占用（并集）   {busy:9.1f}s   {busy / span * 100 if span else 0:5.1f}%")
    print(f"模型生成+开销      {span - busy:9.1f}s   {(span - busy) / span * 100 if span else 0:5.1f}%")
    print(f"工具调用次数       {len(calls):9d}")
    print()
    print("── 按工具聚合 ──")
    for n, xs in sorted(by_name.items(), key=lambda kv: -sum(kv[1])):
        print(f"  {n:<12} n={len(xs):<4} 合计{sum(xs):8.1f}s  最大{max(xs):7.1f}s")
    print()
    print(f"── 最慢 {top} 次调用 ──")
    for c in ranked[:top]:
        print(f"  {c['sec']:7.1f}s  {c['name']:<11} {c['desc'][:96]}")
    print()
    return {"meta": m, "span_s": round(span, 2), "tool_busy_s": round(busy, 2),
            "llm_plus_overhead_s": round(span - busy, 2), "n_calls": len(calls),
            "by_tool": {n: {"n": len(xs), "sum_s": round(sum(xs), 2), "max_s": round(max(xs), 2)}
                        for n, xs in by_name.items()},
            "top": [{"sec": round(c["sec"], 2), "name": c["name"], "desc": c["desc"][:200]}
                    for c in ranked[:top]]}


def children(parent_id: str, since_hours: float = 6.0) -> None:
    """找出某会话孵出的子代理会话（只看最近 N 小时动过的目录，避免全盘解码）。"""
    cutoff = time.time() - since_hours * 3600
    hits = []
    for dirpath, dirnames, filenames in os.walk(SESS_ROOT):
        if "session.jsonl.zstd" not in filenames:
            continue
        f = os.path.join(dirpath, "session.jsonl.zstd")
        try:
            if os.path.getmtime(f) < cutoff:
                continue
        except OSError:
            continue
        try:
            head = zstandard.ZstdDecompressor().stream_reader(open(f, "rb")).read(3000)
            first = head.decode("utf-8", "replace").splitlines()[0]
            d = json.loads(first)
        except Exception:
            continue
        if d.get("parentSession") == parent_id:
            hits.append((os.path.getmtime(f), f, d.get("id"), d.get("origin")))
    hits.sort()
    print(f"父会话 {parent_id} 的子会话（最近 {since_hours}h，共 {len(hits)} 个）：")
    for mt, f, sid, origin in hits:
        print(f"  {time.strftime('%H:%M:%S', time.localtime(mt))}  {sid}  origin={origin}")
        print(f"      {f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    p1 = sub.add_parser("one")
    p1.add_argument("path")
    p1.add_argument("--json", dest="json_out")
    p1.add_argument("--top", type=int, default=15)
    p2 = sub.add_parser("children")
    p2.add_argument("parent_id")
    p2.add_argument("--since-hours", type=float, default=6.0)
    a = ap.parse_args()

    if a.mode == "children":
        children(a.parent_id, a.since_hours)
        return 0

    res = report(a.path, a.top)
    if a.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(a.json_out)), exist_ok=True)
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        print(f"[已写] {a.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
