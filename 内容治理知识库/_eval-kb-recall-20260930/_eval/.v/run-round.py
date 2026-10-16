# -*- coding: utf-8 -*-
"""kb-recall 轨道 B 盲测执行器（回填员侧，不属于被测会话）。

用法: python3 run-round.py <round> [--paper a|b] [--ids 1-10] [--concurrency N] [--resume]

盲测纪律（root-skills-eval v3.19.1 · Step 3）：
- 每条用例一个**全新的一次性 DSH 会话**（headless profile），只把「提示词」列原文当用户消息；
  类型/标题/预期结果/标签/优先级一律不进被测会话。
- 每条用例独立 cwd（_eval/work/{a|b}<round>/item-XXXX）→ 会话互不串，且 cwd 即台账锚点。
- 只读沙箱 DSH_PERMISSION_MODE=read-only：被测会话物理上无法写源目录。
- 客观触发证据不靠被测会话自报：回读真实会话 transcript 的 tool/call（见 oracle.py）。
"""
import sys, os, json, time, subprocess, argparse, threading, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cases
from oracle import bucket_name

HERE = os.path.dirname(os.path.abspath(__file__))
WB   = os.path.dirname(HERE)
APP  = "/Applications/DSH Desktop.app.pre-lute-20260907-111753"
EXE  = os.path.join(APP, "Contents/MacOS/DSH Desktop")
BIN  = os.path.join(APP, "Contents/Resources/app.asar.unpacked/node_modules/@deepseek-ai/dsh/lib/bin.js")
WORK = os.path.join(HERE, "work")

ap = argparse.ArgumentParser()
ap.add_argument("round", type=int)
ap.add_argument("--paper", default="a")
ap.add_argument("--ids", default=None)
ap.add_argument("--concurrency", type=int, default=5)
ap.add_argument("--resume", action="store_true")
ap.add_argument("--timeout", type=int, default=900)
a = ap.parse_args()

NS = "a" if a.paper == "a" else "b"
items = (cases.A + cases.CALL) if NS == "a" else list(cases.B)
if a.ids:
    lo, _, hi = a.ids.partition("-"); lo = int(lo); hi = int(hi or lo)
    items = [c for c in items if isinstance(c["n"], int) and lo <= c["n"] <= hi] or \
            [c for c in items if str(c["n"]) in {str(lo), str(hi)}]
out = os.path.join(HERE, "%s-round-%d.jsonl" % (NS, a.round))
for c in items:
    c["id"] = "%s-%s-r%d" % (NS, c["n"], a.round)
if a.resume and os.path.exists(out):
    done = set()
    for l in open(out, encoding="utf-8"):
        if l.strip():
            try: done.add(json.loads(l)["id"])
            except Exception: pass
    items = [c for c in items if c["id"] not in done]
    print("[resume] 已完成 %d 条，剩 %d 条" % (len(done), len(items)))
print("[setup] 卷=%s 轮=%d 待跑 %d 条 → %s" % (NS.upper(), a.round, len(items), out))

lock = threading.Lock()
q = list(items); stats = {"ok": 0, "fail": 0}

def run_one(c):
    cwd = os.path.join(WORK, "%s%d" % (NS, a.round), "item-%s" % str(c["n"]).zfill(4))
    os.makedirs(cwd, exist_ok=True)
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1", DSH_PERMISSION_MODE="read-only")
    t0 = time.time()
    try:
        p = subprocess.run([EXE, BIN, "--profile", "headless", c["prompt"]],
                           cwd=cwd, env=env, capture_output=True, timeout=a.timeout)
        code, so, se = p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        code, so, se = -9, (e.stdout or b"").decode("utf-8", "replace"), "TIMEOUT"
    b = bucket_name(cwd)
    sfs = glob.glob(os.path.join(os.path.expanduser("~/.dsh/sessions"), b, "*", "session.jsonl.zstd"))
    sdir = os.path.basename(os.path.dirname(max(sfs, key=os.path.getmtime))) if sfs else None
    rec = dict(id=c["id"], n=c["n"], type=c["type"], round=a.round, paper=NS,
               cwd=cwd, session_dir=sdir, exit_code=code, elapsed_s=round(time.time() - t0, 1),
               reply=so.strip(), stderr_tail=se[-2000:])
    with lock:
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        stats["ok" if code == 0 else "fail"] += 1
        print("[%s%d] %d/%d n=%s exit=%s %.0fs reply=%dB" %
              (NS, a.round, stats["ok"] + stats["fail"], len(items) + (len(items) - len(q) if False else 0),
               c["n"], code, rec["elapsed_s"], len(rec["reply"])), flush=True)

def worker():
    while True:
        with lock:
            if not q: return
            c = q.pop(0)
        run_one(c)

ts = [threading.Thread(target=worker) for _ in range(max(1, a.concurrency))]
[t.start() for t in ts]; [t.join() for t in ts]
print("[%s%d] 完成 %d 条（exit!=0: %d）→ %s" % (NS, a.round, stats["ok"] + stats["fail"], stats["fail"], out))
