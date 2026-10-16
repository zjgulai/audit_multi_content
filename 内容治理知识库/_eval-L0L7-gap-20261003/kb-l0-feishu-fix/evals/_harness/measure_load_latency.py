#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用**已有 312 条会话归档**量「加载证据出现在会话开始后第几秒」。
用途：验证用户 2026-10-04 口径「触发判定只需加载证据，不必等 L0↔飞书对齐跑完」是否成立 ——
若 Δ(首次 skill 加载 - 会话开始) 普遍 ≤120s，则把 PER_CASE_TIMEOUT 压到 120s **不会改变任何判定**，
无须重跑全量。
"""
import json, os, glob, threading, statistics
import zstandard
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "load-latency.json")
LOCK = threading.Lock()

def measure(rec):
    p = os.path.join(rec["session_dir"] or "", rec["session_id"] or "", "session.jsonl.zstd")
    if not os.path.isfile(p):
        return None
    try:
        raw = zstandard.ZstdDecompressor().stream_reader(open(p, "rb")).read().decode("utf-8", "replace")
    except Exception as e:
        return {"n": rec["n"], "round": rec["round"], "error": str(e)}
    t0 = None; t_load = None
    for line in raw.split("\n"):
        if not line.strip():
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        t = o.get("time")
        if isinstance(t, (int, float)):
            if t0 is None or t < t0:
                t0 = t
        if t_load is not None:
            continue
        ty = o.get("type"); data = o.get("data") or {}
        hit = False
        if ty == "tool/call" and data.get("name") == "skill":
            hit = True
        elif ty in ("user/message", "agent/inbox/spliced"):
            s = json.dumps(data, ensure_ascii=False)
            if "skill_content name=" in s:
                hit = True
        if hit and isinstance(t, (int, float)):
            t_load = t
    return {"n": rec["n"], "round": rec["round"], "elapsed_s": rec.get("elapsed_s"),
            "skill_loaded": rec.get("skill_loaded"),
            "delta_to_load_s": (round((t_load - t0) / 1000.0, 1)
                                if (t0 and t_load and t_load >= t0) else None)}

recs = []
for f in glob.glob(os.path.join(HERE, "a-round-*.jsonl")):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            recs.append(json.loads(line))
print("待测会话:", len(recs), flush=True)
res = []
with ThreadPoolExecutor(max_workers=8) as ex:
    for i, r in enumerate(ex.map(measure, recs), 1):
        if r:
            res.append(r)
        if i % 40 == 0:
            print(f"  {i}/{len(recs)}", flush=True)

ok = [r for r in res if r.get("skill_loaded") and r.get("delta_to_load_s") is not None]
d = [r["delta_to_load_s"] for r in ok]
notloaded = [r for r in res if not r.get("skill_loaded")]
summary = {
    "sessions": len(res),
    "loaded_sessions": len(ok),
    "loaded_with_delta": len(d),
    "delta_median_s": round(statistics.median(d), 1) if d else None,
    "delta_mean_s": round(statistics.mean(d), 1) if d else None,
    "delta_p95_s": round(sorted(d)[int(len(d) * 0.95)] if d else 0, 1),
    "delta_max_s": max(d) if d else None,
    "loaded_after_120s": sum(1 for x in d if x > 120),
    "not_loaded_sessions": len(notloaded),
    "note": "delta = 首次 skill 加载事件 - 会话首个事件（秒）。≤120s 表示限时 120s 不会丢失加载证据。",
}
json.dump({"summary": summary, "records": res}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
