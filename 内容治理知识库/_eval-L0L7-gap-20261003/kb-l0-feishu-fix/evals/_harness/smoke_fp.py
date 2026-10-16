#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复后**定向冒烟**：只跑原 F1 的 FP 家族，验证描述层路由边界是否真收敛。
用法：python3 smoke_fp.py --ids 70,71,72,74,75,91,95,97,99,36,58,78,81 --round 98 --concurrency 4
不进正式 3 轮数据（outfile=smoke-round-<round>.jsonl）；正式轮次必须重跑这些 id。
"""
import argparse, json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_round as rr

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = threading.Lock()

ap = argparse.ArgumentParser()
ap.add_argument("--ids", required=True)
ap.add_argument("--round", type=int, default=98)
ap.add_argument("--concurrency", type=int, default=4)
ap.add_argument("--work-root", default="/tmp/kb-l0fix-smoke-fp")
a = ap.parse_args()
want = {int(x) for x in a.ids.split(",")}

items = json.load(open(os.path.join(HERE, "round-prompts.json"), encoding="utf-8")) \
      + json.load(open(os.path.join(HERE, "call-prompts.json"), encoding="utf-8"))
items = [x for x in items if x["n"] in want]
assert len(items) == len(want), (len(items), len(want))
out_path = os.path.join(HERE, f"smoke-round-{a.round}.jsonl")
open(out_path, "w").close()
work = os.path.join(os.path.realpath(a.work_root), f"r{a.round}")
os.makedirs(work, exist_ok=True)
print(f"[smoke] 待跑 {len(items)} 条 → {out_path}", flush=True)

def w(item):
    rec = rr.run_one(item, os.path.join(work, "item-%04d" % item["n"]), a.round, "smoke")
    with LOCK:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush(); os.fsync(f.fileno())
    print("[smoke] n=%s %ss loaded=%s reply=%dB" % (
        item["n"], rec["elapsed_s"], rec["skills_loaded"], len(rec.get("reply") or "")), flush=True)

with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
    list(ex.map(w, items))
print("[smoke] done", flush=True)
