#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""污染用例的**密封重跑**（第三遍，仅 12 个会话）。

背景：第二遍已把 cwd 移到 /tmp，但被测会话仍能用
`grep -rl "kbrecall-eval-cwd" ~/Documents/skill-test` 找到 rt.py / cases-a.json
（12 个会话命中，其中 7 个真读了 cases-*.json 答案键）。

本脚本的密封做法：
  1) 先把 cases-*.json 读进内存；
  2) 把整个评测产物树 `chmod 000`（owner 也读不了，实测 cat → Permission denied）——
     这正是 09-30 那批探针用过的 `.v` 封印手法；
  3) 在封印期间起被测会话（cwd 仍是评测树之外的 /tmp）；
  4) 结束时恢复权限，结果落 /tmp/kbrecall-rerun-out.jsonl。

用法：python3 rerun.py [--concurrency 4]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_session as rs  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
SEALED = [EV]
RUNROOT = "/tmp/kbrecall-eval-rerun"
OUT = "/tmp/kbrecall-rerun-out.jsonl"

APP = "/Applications/DSH Desktop.app.pre-lute-20260907-111753"
EXE = os.path.join(APP, "Contents/MacOS/DSH Desktop")
BIN = os.path.join(APP, "Contents/Resources/app.asar.unpacked/node_modules/@deepseek-ai/dsh/lib/bin.js")

TARGETS = [(24, 1), (24, 2), (24, 3), (43, 2), (45, 2), (49, 2), (53, 3),
           (51, 1), (53, 1), (5, 2), (37, 2), (50, 3)]
PAPER = "a"

lock = threading.Lock()


def seal(mode):
    for p in SEALED:
        try:
            os.chmod(p, mode)
        except Exception as exc:  # noqa: BLE001
            print("[warn] chmod", p, oct(mode), exc, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()

    cases = {str(c["id"]): c for c in json.load(open(os.path.join(EV, f"cases-{PAPER}.json"), encoding="utf-8"))}
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                done.add((str(r["id"]), r["round"]))
    todo = [(cid, r) for cid, r in TARGETS if (str(cid), r) not in done]
    print(f"[rerun] todo={len(todo)} done={len(done)}", flush=True)

    q = list(todo)
    results = []

    def worker():
        while True:
            with lock:
                if not q:
                    return
                cid, rnd = q.pop(0)
            c = cases[str(cid)]
            cwd = os.path.join(RUNROOT, f"{PAPER}{rnd}", f"item-{str(cid).zfill(4)}")
            os.makedirs(cwd, exist_ok=True)
            env = dict(os.environ, ELECTRON_RUN_AS_NODE="1", DSH_PERMISSION_MODE="read-only")
            t0 = time.time()
            try:
                p = subprocess.run([EXE, BIN, "--profile", "eval-l0", c["提示词"]],
                                   cwd=cwd, env=env, capture_output=True, timeout=a.timeout)
                code = p.returncode
            except subprocess.TimeoutExpired:
                code = -9
            ev = {}
            for aid, fp in rs.session_files(cwd):
                ev = rs.analyse(fp, "kb-recall")
                ev["agent_id"] = aid
                break
            rec = {"id": str(cid), "round": rnd, "paper": PAPER, "type": c["类型"],
                   "title": c["标题"], "prompt": c["提示词"], "expect": c["预期结果"],
                   "tags": c["标签"], "prio": c["优先级"], "cwd": cwd, "exit_code": code,
                   "elapsed_s": round(time.time() - t0, 1),
                   "loaded_target_skill": bool(ev.get("loaded_target_skill")),
                   "loaded_any_skill": bool(ev.get("loaded_any_skill")),
                   "skill_tool_calls": ev.get("skill_tool_calls", []),
                   "injected_skills": ev.get("injected_skills", []),
                   "loaded_other_skills": ev.get("loaded_other_skills", []),
                   "ends_with_question": bool(ev.get("ends_with_question")),
                   "reply": ev.get("reply", ""), "reply_chars": ev.get("reply_chars", 0),
                   "session_path": ev.get("session_path", ""),
                   "user_texts": ev.get("user_texts", []),
                   "rerun_sealed": True}
            with lock:
                results.append(rec)
                with open(OUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"[rerun] {len(results)}/{len(todo)} id={cid} r{rnd} "
                      f"loaded={rec['loaded_target_skill']} exit={code}", flush=True)

    ts = [threading.Thread(target=worker) for _ in range(max(1, a.concurrency))]
    seal(0o000)
    print("[rerun] sealed", EV, flush=True)
    try:
        [t.start() for t in ts]
        [t.join() for t in ts]
    finally:
        seal(0o700)
        print("[rerun] unsealed", flush=True)
    print(f"[rerun] wrote {len(results)} rows -> {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
