#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按「实际证据不足集合」补跑（v1.3.0 · 宽限时）。

与 rerun-queue.jsonl 的关系（2026-10-04 实测，必须说清）：
  · rerun-queue.jsonl 有 67 条（run_round.py 在证据不足时追加，且**会追加两次**：
    首次跑 + 上一次补跑），它是「补跑清单」不是「当前缺口清单」；
  · v130-120s 全量归档里实际 `evidence=insufficient` 的是 **79 条** ——
    队列 ∪「跑过但又超时」的 12 条（n=1/2/6/7/9/14 等）。
  ⇒ 本驱动按**实际缺口**补跑，取并集，不重复、不遗漏。

纪律：
  · 只补这些 (round, n)，不碰已判定成立的 233 条；
  · 限时放宽到 420s（120s 版实测 79 条被截），补的是「回复」而不是重判触发；
  · 落盘到 a-round-N<SUFFIX>.jsonl（默认 .rerun），**最后一步由 merge_rerun.py 合并**，
    不直接覆盖正式归档。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "_run-v130-120s")
SUFFIX = os.environ.get("RERUN_SUFFIX", ".rerun")
TIMEOUT = int(os.environ.get("RERUN_TIMEOUT", "420"))
CONC = int(os.environ.get("RERUN_CONC", "4"))
WORKROOT = os.environ.get("RERUN_WORK_ROOT", "/tmp/kb-l0fix-rerun-v130")


def gaps():
    """返回 {round: sorted([ids])}：实际证据不足的 (round, n) 并集。"""
    by = {}
    for tag in ("1", "2", "3"):
        ids = set()
        for suf in ("", "b"):
            p = os.path.join(RUN, f"a-round-{tag}{suf}.jsonl")
            if not os.path.exists(p):
                continue
            for line in open(p, encoding="utf-8"):
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("evidence") == "insufficient":
                    ids.add(int(r["n"]))
        by[tag] = sorted(ids)
    return by


def main():
    by = gaps()
    tot = sum(len(v) for v in by.values())
    print(f"[gap] 证据不足并集：{tot} 条 —— " +
          " / ".join(f"r{k}:{len(v)}" for k, v in sorted(by.items())), flush=True)
    if tot == 0:
        print("[gap] 无缺口，退出")
        return 0
    for tag, ids in sorted(by.items()):
        if not ids:
            continue
        out = os.path.join(HERE, f"a-round-{tag}{SUFFIX}.jsonl")
        # 逐条已存在的跳过（可中断续跑）
        done = set()
        if os.path.exists(out):
            for line in open(out, encoding="utf-8"):
                if line.strip():
                    try:
                        done.add(int(json.loads(line)["n"]))
                    except Exception:
                        pass
        todo = [i for i in ids if i not in done]
        if not todo:
            print(f"[r{tag}] 已全部补过，跳过", flush=True)
            continue
        # 拆成连续区间，减少进程数
        ranges, start, prev = [], todo[0], todo[0]
        for x in todo[1:]:
            if x == prev + 1:
                prev = x
                continue
            ranges.append((start, prev))
            start = prev = x
        ranges.append((start, prev))
        print(f"[r{tag}] 待补 {len(todo)} 条 → {os.path.basename(out)}；"
              f"区间 {ranges}", flush=True)
        procs = []
        for lo, hi in ranges:
            cmd = [sys.executable, os.path.join(HERE, "run_round.py"),
                   "--paper", "a", "--round", str(tag),
                   "--ids", f"{lo}-{hi}" if lo != hi else str(lo),
                   "--concurrency", str(CONC), "--timeout", str(TIMEOUT),
                   "--outfile", out, "--work-root", WORKROOT]
            procs.append(subprocess.Popen(cmd, cwd=HERE))
        for p in procs:
            p.wait()
        n = sum(1 for line in open(out, encoding="utf-8") if line.strip())
        print(f"[r{tag}] 补跑落盘 {n} 条", flush=True)
    print("[done] 补跑结束；下一步 python3 merge_rerun.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
