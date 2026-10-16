#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-l0-feishu **修复版复测** 轨道 B 盲测执行器（回填员侧，不属于被测会话）。

用法：
  python3 run_round.py --round 1 [--paper a|b] [--concurrency 3] [--ids 1-52] [--resume]
                       [--work-root /tmp/kb-l0fix-blind-v2] [--outfile X.jsonl]

## 2026-10-04 接线修复（三个真实缺陷，都是"分数会假"的那种）

1. **会话目录解析错了 → reply 全是空串**。原实现用 `os.path.abspath(cwd)` 拼会话目录名，
   而 macOS 上 `/tmp` 是 `/private/tmp` 的软链接：算出来 `--tmp-…`，真实目录是
   `--private-tmp-…` ⇒ `read_session` 永远找不到会话，`reply=""`、`skill_loaded=False`、
   `session_id=None`。若拿这种记录去评分，**所有用例都会被判"不触发"**，F1/P/R 全是假的。
   → 现在一律 `os.path.realpath`，并**找不到会话就抛 SessionMissing 中止**（fail loud）。
2. **`reply` 被截断的 `stdout_tail` 顶替**。现在 `reply` 只从 session.jsonl 逐字取完整的
   assistant 文本；`raw_stdout` / `raw_stderr` 另存旁路字段，绝不顶替 `reply`。
3. **诊断字段是空的**（`session_id` / `skills_loaded` 全 None）。现在每条都带
   `session_found` / `session_id` / `session_dir` / `skills_loaded` / `skill_loaded` /
   `skill_tool_calls` / `session_bytes` / `reply_chars` / `exit_code` / `elapsed_s`。

## 盲测纪律（root-skills-eval v3.19.1 · Step 3，逐条不变）

- 每条用例一个**全新的一次性会话**：`dsh --profile eval-l0fix "<提示词>"`，
  只把「提示词」列原文当作用户消息；类型/标题/预期结果/标签/优先级一律不进被测会话。
- 每条用例**独立 cwd**（`<work-root>/{a|b}{round}/item-XXXX`）→ 每条一个独立 session 目录。
- cwd 落在 `/tmp` 下（**评测树之外**）⇒ 被测会话够不到答案键（cases-meta / 预期结果）。
- **只读沙箱**（DSH_PERMISSION_MODE=read-only）：被测会话无法写库/写飞书/落盘。
- 触发判定取**客观证据**：该会话 session.jsonl 里 `skill` 工具调用 / 斜杠注入的 skill_content。
- 逐条 append（写后 flush+fsync）到 `<outfile>`，可中断续跑（`--resume`）。
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
PROFILE = "eval-l0fix"
SESSIONS = os.path.expanduser("~/.dsh/sessions")
# ★ 2026-10-04 用户口径「只评 skill，不跑飞书侧对齐」：
#   触发判定只需「该不该加载」的客观证据，而实测（load-latency.json，312 条会话归档）
#   加载证据出现在会话开始后 **中位 14s / p95 28s / 最大 79s，0 条超过 120s** ⇒
#   把限时压到 120s **不会改变任何判定**，只是不再等会话把 L0↔飞书对齐作业跑完。
#   取值 120s = p95 的 4 倍余量，且远小于实测最长加载延迟；可用 --timeout 覆盖。
PER_CASE_TIMEOUT = 120
DEFAULT_WORK_ROOT = "/tmp/kb-l0fix-blind-v2"     # 全新根，避免与接线修复前的旧会话混
LOCK = threading.Lock()


class SessionMissing(RuntimeError):
    """找不到会话目录/会话文件 —— 必须炸，不许静默记一条空回复（2026-10-04 事故）。"""


def session_dir_for(cwd):
    """DSH 会话目录名 = '-' + 绝对路径(尾斜杠，'/'→'-'，非 ASCII→~XXXX) + '-'。

    ★ 必须 realpath：`/tmp` 在 macOS 上是 `/private/tmp` 的软链接，用 abspath 会算出
      另一个目录名，从而永远读到空会话（2026-10-04 复测线的根因）。
    """
    p = os.path.realpath(cwd) + "/"
    esc = "".join(ch if ord(ch) < 128 else "~%04X" % ord(ch) for ch in p)
    return "-" + esc.replace("/", "-") + "-"


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


def read_session(cwd):
    """返回 dict：session_id / session_dir / skills_loaded / reply / skill_tool_calls。

    找不到会话目录或会话文件 → 抛 SessionMissing（fail loud）。
    """
    d = os.path.join(SESSIONS, session_dir_for(cwd))
    if not os.path.isdir(d):
        raise SessionMissing(f"会话目录不存在: {d}（cwd={cwd} → realpath={os.path.realpath(cwd)}）")
    subs = [s for s in os.listdir(d) if os.path.isdir(os.path.join(d, s))]
    if not subs:
        raise SessionMissing(f"会话目录为空: {d}")
    subs.sort(key=lambda s: os.path.getmtime(os.path.join(d, s)))
    sid = subs[-1]
    p = os.path.join(d, sid, "session.jsonl.zstd")
    if not os.path.isfile(p):
        raise SessionMissing(f"会话记录文件不存在: {p}")
    raw = zstandard.ZstdDecompressor().stream_reader(open(p, "rb")).read()
    text = raw.decode("utf-8", "replace")
    loaded, reply, tool_calls = [], "", 0
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
            tool_calls += 1
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
    for line in text.split("\n"):
        if "skill_content name=" not in line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") not in ("user/message", "agent/inbox/spliced"):
            continue
        for st in _strings(o.get("data")):
            for name in re.findall(r'<skill_content name="([^"]+)"', st):
                if NAME_OK.match(name) and name not in loaded:
                    loaded.append(name)
    return {"session_id": sid, "session_dir": d, "skills_loaded": loaded,
            "reply": reply, "skill_tool_calls": tool_calls,
            "session_bytes": len(raw)}


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

    rec = {"id": item["id"], "n": item["n"], "round": round_no, "paper": paper,
           "exit_code": code, "elapsed_s": elapsed,
           # ── 判定与诊断字段（真实接线，2026-10-04 修）────────────────────────
           "session_found": False, "session_id": None, "session_dir": None,
           "skills_loaded": [], "skill_loaded": False, "skill_tool_calls": 0,
           "session_bytes": 0, "reply": "", "reply_chars": 0,
           # ── 旁路原始输出（**不顶替 reply**）────────────────────────────────
           "raw_stdout": out[-20000:], "raw_stderr": err[-4000:],
           }
    try:
        s = read_session(cwd)
    except SessionMissing as e:
        rec["session_error"] = str(e)
        rec["stdout_tail"] = out[-4000:]
        # ★ 不许静默：会话根本没建起来 ⇒ 证据不足，进补跑清单，**绝不按「不触发」计**
        rec["evidence"] = "insufficient"
        rec["insufficient_reason"] = "session_missing"
        return rec
    rec.update({"session_found": True, "session_id": s["session_id"],
                "session_dir": s["session_dir"], "skills_loaded": s["skills_loaded"],
                "skill_loaded": "kb-l0-feishu" in s["skills_loaded"],
                "skill_tool_calls": s["skill_tool_calls"],
                "session_bytes": s["session_bytes"], "reply": s["reply"],
                "reply_chars": len(s["reply"])})
    rec["stdout_tail"] = out[-4000:]
    # ★ 限时可能把回复截断：进程被 SIGKILL(-9) 或限时后仍无回复 ⇒ 打标记
    rec["timed_out"] = (code == -9)
    if not s["reply"]:
        # 判定口径：正例/负例/近似/调用 的「触发/不触发」只取 skill_loaded（加载证据，早于限时），
        # 空回复**不影响**该判定；但 边界情况 要在「不触发/追问」间二选一，**必须有回复**。
        rec["evidence"] = "insufficient"
        rec["insufficient_reason"] = ("timeout_no_reply" if code == -9 else "no_reply")
    else:
        rec["evidence"] = "ok"
        if code == -9:
            # 回复有了但会话被限时截断 —— 逐字原文可能不完整，交报告标注，但仍可判定
            rec["reply_may_be_truncated"] = True
    return rec


def main():
    global PER_CASE_TIMEOUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--paper", default="a")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--include-calls", action="store_true", default=True)
    ap.add_argument("--outfile", default=None)
    ap.add_argument("--work-root", default=DEFAULT_WORK_ROOT)
    ap.add_argument("--timeout", type=int, default=PER_CASE_TIMEOUT,
                    help=f"单条限时秒数（默认 {PER_CASE_TIMEOUT}；见文件顶部 2026-10-04 口径说明）")
    a = ap.parse_args()
    PER_CASE_TIMEOUT = a.timeout

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

    total, counter = len(items), {"done": 0, "empty_reply": 0, "no_session": 0,
                                  "insufficient": 0}
    print(f"[setup] 卷={paper.upper()} 轮={a.round} 待跑 {total} 条 → {out_path}", flush=True)
    print(f"[setup] profile={PROFILE} work_root={os.path.realpath(a.work_root)}", flush=True)
    work = os.path.join(os.path.realpath(a.work_root), f"{paper}{a.round}")
    os.makedirs(work, exist_ok=True)

    def worker(item):
        cwd = os.path.join(work, f"item-{item['n']:04d}")
        rec = run_one(item, cwd, a.round, paper)
        with LOCK:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            counter["done"] += 1
            if not rec.get("reply"):
                counter["empty_reply"] += 1
            if not rec.get("session_found"):
                counter["no_session"] += 1
            if rec.get("evidence") == "insufficient":
                counter["insufficient"] += 1
                # ★ 记账失败绝不许把跑批带崩（2026-10-04 教训：这里曾用错变量名 round_no，
                #   第一条证据不足就把 6 个分片全 NameError 掉，只落了 91/312）
                try:
                    with open(os.path.join(HERE, "rerun-queue.jsonl"), "a",
                              encoding="utf-8") as q:
                        q.write(json.dumps({"paper": paper, "round": a.round,
                                            "n": item["n"],
                                            "reason": rec.get("insufficient_reason"),
                                            "session_dir": rec.get("session_dir")},
                                           ensure_ascii=False) + "\n")
                except Exception as e:                      # noqa: BLE001
                    print(f"[warn] 补跑清单写入失败（不影响本批）：{e}", flush=True)
            d = counter["done"]
        print(f"[{paper}{a.round}] {d}/{total} n={item['n']} {rec['elapsed_s']}s "
              f"exit={rec['exit_code']} loaded={rec['skills_loaded']} "
              f"reply={len(rec.get('reply') or '')}B", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as ex:
        list(ex.map(worker, items))
    print(f"[{paper}{a.round}] 完成 {counter['done']} 条，用时 "
          f"{round(time.time()-t0,1)}s → {out_path}", flush=True)
    print(f"[{paper}{a.round}] 空回复 {counter['empty_reply']} 条 / "
          f"会话缺失 {counter['no_session']} 条", flush=True)
    if counter["insufficient"]:
        print(f"[{paper}{a.round}] ⚠️ 证据不足 {counter['insufficient']} 条（限时/无会话）——"
              f"已进 rerun-queue.jsonl，**评分前必须重跑，不许当'不触发'计**", flush=True)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
