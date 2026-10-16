#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补跑器：把某一轮里 `valid=False`（证据不足/无效）的记录剔出 jsonl，再用更长限时重跑。

为什么需要它（本批的防假分纪律）：
  限时强杀会让 reply 变空/半截 ⇒ 这类记录**不许**按「不触发」计（那会把限时造成的空回复
  算成漏触发/真阴性，P/R/F1 全假）。做法是单独列清单、换更长限时重跑，重跑后仍无效的
  才如实记为「证据不足」，并从四格里剔除、单独披露。

用法：
  python3 rerun2.py --paper a --round 1 [--timeout 420] [--concurrency 6] [--max 30]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
ROUNDS = os.path.join(EV, "rounds")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", choices=["a", "b"], required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--max", type=int, default=60, help="单次最多补跑多少条")
    a = ap.parse_args()

    path = os.path.join(ROUNDS, f"{a.paper}-round{a.round}.jsonl")
    recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    bad = [r for r in recs if not r.get("valid")]
    good = [r for r in recs if r.get("valid")]
    # ★ 还要补「根本没落盘」的（runner 撞 zstd 半截文件时整条记录会丢）
    have = {str(r["id"]) for r in recs}
    cases = json.load(open(os.path.join(EV, f"cases-{a.paper}.json"), encoding="utf-8"))
    missing = [{"id": str(c["id"]), "type": c["类型"], "loaded_target_skill": None,
                "reply_chars": 0, "invalid_reason": "missing_record（没落盘）"}
               for c in cases if str(c["id"]) not in have]
    if not bad and not missing:
        print(f"[rerun2] {a.paper}-round{a.round}: 无无效/缺失记录，跳过")
        return 0
    bad = bad + missing
    bad = bad[: a.max]
    ids = [str(r["id"]) for r in bad]
    print(f"[rerun2] {a.paper}-round{a.round}: 无效 {len(bad)} 条 → 换 {a.timeout}s 重跑")
    for r in bad:
        print(f"    id={r['id']:>3} {r['type']:<6} loaded={r['loaded_target_skill']} "
              f"reply={r.get('reply_chars', 0)}c reason={r.get('invalid_reason')}")

    # 剔掉无效行（保留其余），交给 rt2 重跑这些 id
    with open(path, "w", encoding="utf-8") as f:
        for r in good:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cmd = [sys.executable, os.path.join(HERE, "rt2.py"), "--paper", a.paper,
           "--round", str(a.round), "--ids", ",".join(ids),
           "--timeout", str(a.timeout), "--concurrency", str(a.concurrency)]
    print("[rerun2]", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
