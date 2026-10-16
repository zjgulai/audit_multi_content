#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-l0-feishu 轨道 B 盲测执行器（回填员侧工具，不属于被测会话）。

用法：
  python3 run_round.py --round 1 [--paper a|b] [--concurrency 4] [--ids 1-10] [--resume]

盲测纪律（root-skills-eval v3.19.1 · Step 3）：
- 每条用例一个**全新的一次性会话**：`dsh --profile eval-l0 "<提示词>"`，
  只把「提示词」列原文当作用户消息；类型/标题/预期结果/标签/优先级一律不进被测会话。
- 每条用例独立 cwd（_work/{a|b}{round}/item-XXXX）→ 每条一个独立 session 目录，互不串会话。
- **只读沙箱**（DSH_PERMISSION_MODE=read-only）：被测会话无法写库/写飞书/落盘。
- 触发判定取**客观证据**：该会话 session.jsonl 里 `skill` 工具调用 / skill 内容注入，
  不看被测会话自报。
- 逐条 append 到 {a,b}-round-{n}.jsonl，可中断续跑（--resume）。

装载位说明：被测副本与 `~/.dsh/skills/kb-l0-feishu`（装载位）逐字节一致
（sha256 见 install-manifest.json），所以盲测读到的就是被测副本的内容。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import zstandard

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
APP = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"
BIN = ("/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/Resources/"
       "app.asar.unpacked/node_modules/@deepseek-ai/dsh/lib/bin.js")
PROFILE = "eval-l0"
SESSIONS = os.path.expanduser("~/.dsh/sessions")
PER_CASE_TIMEOUT = 1200
LOCK = threading.Lock()


def session_dir_for(cwd):
    """DSH 会话目录名 = '-' + 绝对路径(尾斜杠，'/'→'-'，非 ASCII→~XXXX) + '-'。"""
    esc = "".join(ch if ord(ch) < 128 else "~%04X" % ord(ch)
                  for ch in (os.path.abspath(cwd) + "/"))
    return "-" + esc.replace("/", "-") + "-"


def read_session(cwd):
    """返回 (skills_loaded, final_reply, session_id)。"""
    d = os.path.join(SESSIONS, session_dir_for(cwd))
    if not os.path.isdir(d):
        return [], "", None
    subs = [s for s in os.listdir(d) if os.path.isdir(os.path.join(d, s))]
    if not subs:
        return [], "", None
    subs.sort(key=lambda s: os.path.getmtime(os.path.join(d, s)))
    sid = subs[-1]
    p = os.path.join(d, sid, "session.jsonl.zstd")
    if not os.path.isfile(p):
        return [], "", sid
    raw = zstandard.ZstdDecompressor().stream_reader(open(p, "rb")).read()
    text = raw.decode("utf-8", "replace")
    loaded, reply = [], ""
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        t = o.get("type")
        data = o.get("data") or {}
        if t == "tool/call" and data.get("name") == "skill":
            try:
                arg = json.loads(data.get("arguments") or "{}")
            except Exception:
                arg = {}
            if arg.get("name"):
                loaded.append(arg["name"])
        elif t == "assistant/message":
            msg = data.get("message") or {}
            if msg.get("role") != "assistant":
                continue
            blocks = [b.get("text", "") for b in (msg.get("content") or [])
                      if b.get("type") == "text"]
            if any(b.strip() for b in blocks):
                reply = "\n\n".join(b for b in blocks if b.strip())
    # 斜杠调用：skill 内容作为消息注入（没走 skill 工具）→ 递归取所有字符串再匹配
    def _strings(o):
        if isinstance(o, str):
            yield o
        elif isinstance(o, dict):
            for v in o.values():
                yield from _strings(v)
        elif isinstance(o, list):
            for v in o:
                yield from _strings(v)

    NAME_OK = re.compile(r"^[A-Za-z0-9\u4e00-\u9fff_-]{1,64}$")
    for line in text.split("\n"):
        if "skill_content name=" not in line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        # 只看宿主注入的 user/message（斜杠调用路径）；tool/result 里出现的是文档正文/脚本源码
        if o.get("type") not in ("user/message", "agent/inbox/spliced"):
            continue
        for st in _strings(o.get("data")):
            for name in re.findall(r'<skill_content name="([^"]+)"', st):
                if NAME_OK.match(name) and name not in loaded:
                    loaded.append(name)
    return loaded, reply, sid


def run_one(item, cwd, round_no, paper):
    os.makedirs(cwd, exist_ok=True)
    env = {**os.environ, "ELECTRON_RUN_AS_NODE": "1",
           "DSH_PERMISSION_MODE": "read-only"}
    t0 = time.time()
    out, err, code = "", "", None
    try:
        pr = subprocess.run([APP, BIN, "--profile", PROFILE, item["prompt"]],
                            cwd=cwd, env=env, capture_output=True, timeout=PER_CASE_TIMEOUT)
        out = pr.stdout.decode("utf-8", "replace")
        err = pr.stderr.decode("utf-8", "replace")
        code = pr.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace")
        err = "TIMEOUT after %ss" % PER_CASE_TIMEOUT
        code = -9
    elapsed = round(time.time() - t0, 1)
    loaded, reply, sid = read_session(cwd)
    rec = {"id": item["id"], "n": item["n"], "round": round_no, "paper": paper,
           "exit_code": code, "elapsed_s": elapsed, "session_id": sid,
           "skills_loaded": loaded, "skill_loaded": "kb-l0-feishu" in loaded,
           "reply": reply, "stdout_tail": out[-4000:], "stderr_tail": err[-2000:]}
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--paper", default="a")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--include-calls", action="store_true", default=True)
    ap.add_argument("--outfile", default=None)
    a = ap.parse_args()

    paper = a.paper.lower()
    src = os.path.join(HERE, "b-round-prompts.json" if paper == "b" else "round-prompts.json")
    items = json.load(open(src, encoding="utf-8"))
    if a.include_calls and paper == "a":
        items = items + json.load(open(os.path.join(HERE, "call-prompts.json"),
                                       encoding="utf-8"))
    if a.ids:
        m = re.match(r"^(\d+)-(\d+)$", a.ids)
        lo, hi = (int(m.group(1)), int(m.group(2))) if m else (int(a.ids), int(a.ids))
        items = [x for x in items if lo <= x["n"] <= hi]

    out_path = (a.outfile if a.outfile else
                os.path.join(HERE, f"{paper}-round-{a.round}.jsonl"))
    if a.resume and os.path.exists(out_path):
        done = set()
        for line in open(out_path, encoding="utf-8"):
            if line.strip():
                try:
                    done.add(json.loads(line)["n"])
                except Exception:
                    pass
        items = [x for x in items if x["n"] not in done]
        print(f"[resume] 已完成 {len(done)} 条，剩 {len(items)} 条", flush=True)

    total, counter = len(items), {"done": 0}
    print(f"[setup] 卷={paper.upper()} 轮={a.round} 待跑 {total} 条 → {out_path}",
          flush=True)
    work = os.path.join(EVAL, "_work", f"{paper}{a.round}")

    def worker(item):
        cwd = os.path.join(work, f"item-{item['n']:04d}")
        rec = run_one(item, cwd, a.round, paper)
        with LOCK:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            counter["done"] += 1
            d = counter["done"]
        print(f"[{paper}{a.round}] {d}/{total} n={item['n']} {rec['elapsed_s']}s "
              f"exit={rec['exit_code']} loaded={rec['skills_loaded']} "
              f"reply={len(rec['reply'])}B", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as ex:
        list(ex.map(worker, items))
    print(f"[{paper}{a.round}] 完成 {counter['done']} 条，用时 "
          f"{round(time.time()-t0,1)}s → {out_path}", flush=True)


if __name__ == "__main__":
    main()
