#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-recall 盲测轮次执行器（回填员侧）。

每个用例起一个**独立的一次性被测会话**（DSH headless，`--profile eval-l0`），
每个用例一个独立 cwd，**只把「提示词」列原文**作为用户消息发出；
类型 / 标题 / 预期结果 / 标签 / 优先级一律不进入被测会话。

结果逐条落盘：rounds/{paper}-round{N}.jsonl（含逐字 AI 原文与加载证据），
每落一条更新 heartbeat.txt —— 进度以磁盘为准。

用法：python3 rt.py --paper a --round 1 [--concurrency 6] [--timeout 900]
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
import read_session  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
# ★ 隔离：每条用例的 cwd 必须在**评测产物树之外**。
#   第一遍把 cwd 放在 evals/work/<paper><round>/ 下，被会话用 `ls ..` 摸到了回填员侧的
#   cases-a.json（含「预期结果」列）—— 38 个会话污染、全批作废（见 rounds-INVALID-cwdleak/）。
#   现在 cwd 落在 /tmp 下的独立运行根，被测会话从自身 cwd 无法走到评测产物。
WORK = os.environ.get("KB_RECALL_EVAL_CWD_ROOT", "/tmp/kbrecall-eval-cwd")
ROUNDS = os.path.join(EV, "rounds")
HEART = os.path.join(HERE, "heartbeat.txt")

APP = "/Applications/DSH Desktop.app.pre-lute-20260907-111753"
EXE = os.path.join(APP, "Contents/MacOS/DSH Desktop")
BIN = os.path.join(APP, "Contents/Resources/app.asar.unpacked/node_modules/@deepseek-ai/dsh/lib/bin.js")

lock = threading.Lock()


def beat(msg: str):
    with open(HEART, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")


class Runner:
    def __init__(self, paper, rnd, cases, concurrency, timeout):
        self.paper, self.rnd, self.cases = paper, rnd, cases
        self.concurrency, self.timeout = concurrency, timeout
        self.out = os.path.join(ROUNDS, f"{paper}-round{rnd}.jsonl")
        self.done = {}
        if os.path.exists(self.out):
            for line in open(self.out, encoding="utf-8"):
                if line.strip():
                    r = json.loads(line)
                    self.done[str(r["id"])] = r

    def run_one(self, c):
        cid = str(c["id"])
        cwd = os.path.join(WORK, f"{self.paper}{self.rnd}", f"item-{cid.zfill(4)}")
        os.makedirs(cwd, exist_ok=True)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1", DSH_PERMISSION_MODE="read-only")
        t0 = time.time()
        try:
            p = subprocess.run([EXE, BIN, "--profile", "eval-l0", c["提示词"]],
                               cwd=cwd, env=env, capture_output=True, timeout=self.timeout)
            code = p.returncode
        except subprocess.TimeoutExpired:
            code = -9
        ev = {}
        for aid, fp in read_session.session_files(cwd):
            ev = read_session.analyse(fp, "kb-recall")
            ev["agent_id"] = aid
            break
        rec = {
            "id": cid, "round": self.rnd, "paper": self.paper, "type": c["类型"],
            "title": c["标题"], "prompt": c["提示词"], "expect": c["预期结果"],
            "tags": c["标签"], "prio": c["优先级"], "cwd": cwd, "exit_code": code,
            "elapsed_s": round(time.time() - t0, 1),
            "loaded_target_skill": bool(ev.get("loaded_target_skill")),
            "loaded_any_skill": bool(ev.get("loaded_any_skill")),
            "skill_tool_calls": ev.get("skill_tool_calls", []),
            "injected_skills": ev.get("injected_skills", []),
            "loaded_other_skills": ev.get("loaded_other_skills", []),
            "ends_with_question": bool(ev.get("ends_with_question")),
            "reply": ev.get("reply", ""),
            "reply_chars": ev.get("reply_chars", 0),
            "session_path": ev.get("session_path", ""),
            "user_texts": ev.get("user_texts", []),
        }
        with lock:
            self.done[cid] = rec
            with open(self.out, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            beat(f"{self.paper}-r{self.rnd} id={cid} loaded={rec['loaded_target_skill']} "
                 f"exit={code} {rec['elapsed_s']}s reply={rec['reply_chars']}c")
            print(f"[{self.paper}-r{self.rnd}] {len(self.done)}/{len(self.cases)} id={cid} "
                  f"loaded={rec['loaded_target_skill']} exit={code} {rec['elapsed_s']}s", flush=True)

    def run(self):
        todo = [c for c in self.cases if str(c["id"]) not in self.done]
        print(f"[rt] {self.paper}-round{self.rnd} total={len(self.cases)} "
              f"done={len(self.done)} todo={len(todo)}", flush=True)
        beat(f"START {self.paper}-r{self.rnd} todo={len(todo)}")
        q = list(todo)

        def worker():
            while True:
                with lock:
                    if not q:
                        return
                    c = q.pop(0)
                try:
                    self.run_one(c)
                except Exception as exc:  # noqa: BLE001
                    beat(f"ERR {self.paper}-r{self.rnd} id={c['id']} {exc}")

        ts = [threading.Thread(target=worker) for _ in range(max(1, self.concurrency))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        beat(f"DONE {self.paper}-r{self.rnd} n={len(self.done)}")
        print(f"[rt] {self.paper}-round{self.rnd} written {len(self.done)}/{len(self.cases)}",
              flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", choices=["a", "b"], required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()
    os.makedirs(ROUNDS, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    print("[rt] cwd root =", WORK, flush=True)
    cases = json.load(open(os.path.join(EV, f"cases-{a.paper}.json"), encoding="utf-8"))
    Runner(a.paper, a.round, cases, a.concurrency, a.timeout).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
