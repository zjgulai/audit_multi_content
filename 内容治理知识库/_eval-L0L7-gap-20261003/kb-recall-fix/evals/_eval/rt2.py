#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-recall **fix 版（v1.3.0）** 盲测轮次执行器（回填员侧）。

与源版 rt.py 的差别（全部来自本批踩过的坑）：
  1. **profile = eval-recallfix**：装载位副本 = `_mount-recallfix/kb-recall`，
     源 `~/.dsh/skills/kb-recall` 已 `chmod -R a-w`，盲测会话**只能**看到 fix 版。
  2. **PER_CASE_TIMEOUT 默认 120s**：只评 skill、不跑底层作业；触发判定只取
     session.jsonl 里的 `skill` 工具调用 / 斜杠注入的 skill_content（会话开头就出现）。
  3. **★ 防假分**：限时会导致 reply 空/半截 —— 这类记录标 `valid=False / reason`，
     **不许按「不触发」计**，由 score2.py 单列补跑清单。
  4. **答案键密封**：加载完用例后把 cases-*.json / *.xlsx chmod 000，
     跑完（含异常退出）由 atexit 还原 —— 结果目录全程可写。
  5. **按 delegationDepth 隔离**：只认本会话直接 spawn 的一次性会话（depth 0），
     被测模型自己 spawn 的子会话不进统计。
  6. 逐条落盘 rounds/{paper}-round{N}.jsonl + heartbeat-fix.txt。
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_session  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
WORK = os.environ.get("KB_RECALL_FIX_CWD_ROOT", "/tmp/kbrecall-fix-cwd")
ROUNDS = os.path.join(EV, "rounds")
HEART = os.path.join(HERE, "heartbeat-fix.txt")
PROFILE = os.environ.get("KB_RECALL_FIX_PROFILE", "eval-recallfix")

APP = "/Applications/DSH Desktop.app.pre-lute-20260907-111753"
EXE = os.path.join(APP, "Contents/MacOS/DSH Desktop")
BIN = os.path.join(APP, "Contents/Resources/app.asar.unpacked/node_modules/@deepseek-ai/dsh/lib/bin.js")

# 答案键：跑轮期间密封（模式 000），跑完还原
KEYS = ["cases-a.json", "cases-b.json", "kb-recall.xlsx", "kb-recall-b-cases.xlsx"]

MIN_REPLY_KILLED = int(os.environ.get("KB_RECALL_MIN_REPLY_KILLED", "100"))  # 被杀的负例最少回复字符数

lock = threading.Lock()


def beat(msg: str):
    with open(HEART, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")


def seal_keys(seal: bool):
    for name in KEYS:
        p = os.path.join(EV, name)
        if not os.path.exists(p):
            continue
        try:
            os.chmod(p, 0o000 if seal else stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError:
            pass


def unseal():
    seal_keys(False)


atexit.register(unseal)


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
        timed_out = False
        code = None
        # ★★ 不用 subprocess.run(capture_output=True)：那样 stdout/stderr 是 PIPE，
        #    限时强杀主进程后，**被它 spawn 的孙进程仍持有管道写端** ⇒ communicate() 会
        #    等 EOF 一直挂住（实测：连 120s 限时都不生效，8 条卡 8 分钟、rt2 烧 CPU、
        #    heartbeat 一条不落）。改成落文件 + 独立进程组 + 超时杀整组。
        os.makedirs(os.path.join(cwd, ".run"), exist_ok=True)
        logf = open(os.path.join(cwd, ".run", "dsh.log"), "wb")
        try:
            proc = subprocess.Popen([EXE, BIN, "--profile", PROFILE, c["提示词"]],
                                    cwd=cwd, env=env, stdout=logf,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = proc.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                code = -9
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:  # noqa: BLE001
                    proc.kill()
                try:
                    proc.wait(timeout=30)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            logf.close()

        # ★ realpath：macOS /tmp → /private/tmp，用 abspath 会找不到会话（先例：全批评"不触发"）
        # ★ 限时强杀后 DSH 异步落盘 ⇒ 必须**重试等会话文件**，否则会被误判成 session_not_found
        #   （实测 id=36 被杀的当下读不到，几秒后 depth=0 的会话就在了）
        ev, sid, depth = {}, "", None
        rcwd = os.path.realpath(cwd)
        deadline = time.time() + 60
        # ★ 限时强杀后 DSH 异步落盘：文件可能只写了一半 ⇒ 读它会 zstd "Data corruption"。
        #   必须**重试**（实测 id=5/7/8 首读就撞上），否则会丢记录（早先版本直接抛异常丢掉 3 条）。
        while True:
            try:
                for aid, fp, meta in read_session.session_files_top(rcwd):
                    ev = read_session.analyse(fp, "kb-recall")
                    sid, depth = aid, meta.get("delegationDepth")
                    break
            except Exception as exc:  # noqa: BLE001
                beat(f"READRETRY {self.paper}-r{self.rnd} id={cid} {exc}")
                ev = {}
            if ev.get("session_path") or time.time() > deadline:
                break
            time.sleep(3)

        reply = ev.get("reply", "") or ""
        loaded = bool(ev.get("loaded_target_skill"))
        any_skill = bool(ev.get("loaded_any_skill"))
        session_found = bool(ev.get("session_path"))
        # ★ 防假分（口径）：限时空回复**不许**按「不触发」计
        #   · 加载证据在（skill 工具调用 / 注入）= 铁证 ⇒ 有效（即使 reply 空/半截）
        #   · 无加载证据 + reply 空/超时 ⇒ 证据不足/无效 ⇒ 单列补跑，不进四格
        #   · 无加载证据 + reply 非空 ⇒ 有效（不触发/追问）
        if loaded or any_skill:
            valid, reason = True, ""
        elif not session_found:
            valid, reason = False, "session_not_found（会话未定位到，判接线问题）"
        elif not reply.strip():
            valid, reason = False, ("timeout_empty_reply（限时空回复，证据不足）" if timed_out
                                    else "empty_reply（空回复，证据不足）")
        elif timed_out and len(reply.strip()) < MIN_REPLY_KILLED:
            # 被限时强杀、无加载证据、回复又短 ⇒ 可能是被截断的半截话，不足以判「不触发」
            valid, reason = False, "timeout_partial_reply（限时半截回复，证据不足）"
        else:
            valid, reason = True, ""

        rec = {
            "id": cid, "round": self.rnd, "paper": self.paper, "type": c["类型"],
            "title": c["标题"], "prompt": c["提示词"], "expect": c["预期结果"],
            "tags": c["标签"], "prio": c["优先级"], "cwd": cwd,
            "session_id": sid, "delegation_depth": depth, "session_found": session_found,
            "exit_code": code, "timed_out": timed_out, "elapsed_s": round(time.time() - t0, 1),
            "valid": valid, "invalid_reason": reason,
            "loaded_target_skill": loaded,
            "loaded_any_skill": any_skill,
            "skill_tool_calls": ev.get("skill_tool_calls", []),
            "injected_skills": ev.get("injected_skills", []),
            "loaded_other_skills": ev.get("loaded_other_skills", []),
            "ends_with_question": bool(ev.get("ends_with_question")),
            "reply": reply,
            "reply_chars": len(reply),
            "session_path": ev.get("session_path", ""),
            "user_texts": ev.get("user_texts", []),
        }
        with lock:
            self.done[cid] = rec
            with open(self.out, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            beat(f"{self.paper}-r{self.rnd} id={cid} valid={valid} "
                 f"loaded={rec['loaded_target_skill']} exit={code} {rec['elapsed_s']}s "
                 f"reply={rec['reply_chars']}c {reason}")
            print(f"[{self.paper}-r{self.rnd}] {len(self.done)}/{len(self.cases)} id={cid} "
                  f"valid={valid} loaded={rec['loaded_target_skill']} exit={code} "
                  f"{rec['elapsed_s']}s reply={rec['reply_chars']}c {reason}", flush=True)

    def run(self):
        todo = [c for c in self.cases if str(c["id"]) not in self.done]
        print(f"[rt2] {self.paper}-round{self.rnd} total={len(self.cases)} "
              f"done={len(self.done)} todo={len(todo)}", flush=True)
        beat(f"START {self.paper}-r{self.rnd} todo={len(todo)} profile={PROFILE}")
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
        print(f"[rt2] {self.paper}-round{self.rnd} written {len(self.done)}/{len(self.cases)}",
              flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", choices=["a", "b"], required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--ids", default="", help="只跑这些 id（逗号分隔），用于冒烟/补跑")
    a = ap.parse_args()
    os.makedirs(ROUNDS, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    print("[rt2] profile =", PROFILE, "| cwd root =", WORK, "| timeout =", a.timeout, flush=True)
    cases = json.load(open(os.path.join(EV, f"cases-{a.paper}.json"), encoding="utf-8"))
    if a.ids:
        want = {x.strip() for x in a.ids.split(",") if x.strip()}
        cases = [c for c in cases if str(c["id"]) in want]
    # ★ 用例已读入内存 → 密封答案键（atexit 还原）
    seal_keys(True)
    try:
        Runner(a.paper, a.round, cases, a.concurrency, a.timeout).run()
    finally:
        unseal()
    return 0


if __name__ == "__main__":
    sys.exit(main())
