# -*- coding: utf-8 -*-
"""Session batch runner.

Usage: python3 rt.py <round> [--concurrency N]

Runs one isolated headless session per item, each in its own working
directory, and merges the collected transcripts back into the round store.
"""
import sys, os, json, glob, time, stat, subprocess, argparse, threading

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, ".v")
WORK = os.path.join(HERE, "work")
APP = "/Applications/DSH Desktop.app.pre-lute-20260907-111753"
EXE = os.path.join(APP, "Contents/MacOS/DSH Desktop")
BIN = os.path.join(APP, "Contents/Resources/app.asar.unpacked/node_modules/@deepseek-ai/dsh/lib/bin.js")

ap = argparse.ArgumentParser()
ap.add_argument("round", type=int)
ap.add_argument("--concurrency", type=int, default=10)
ap.add_argument("--timeout", type=int, default=1200)
a = ap.parse_args()

# ── read everything we need BEFORE locking the store ────────────────────
spec = json.load(open(os.path.join(STORE, "spec.json"), encoding="utf-8"))[str(a.round)]
out_path = os.path.join(STORE, "a-round-%d.jsonl" % a.round)
keep = []
if os.path.exists(out_path):
    keep = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
drop = {str(x["n"]) for x in spec}
todo = [x for x in spec]
print("[rt] round=%d todo=%d keep=%d" % (a.round, len(todo), len(keep)), flush=True)

# ── lock the store: nothing under .v is listable or readable while running ──
os.chmod(STORE, 0o000)

def bucket_name(cwd):
    p = os.path.abspath(cwd).lstrip("/")
    out = []
    for ch in p:
        if ch == "/": out.append("-")
        elif ch.isascii() and (ch.isalnum() or ch in "-_."): out.append(ch)
        else: out.append("~%04X" % ord(ch))
    return "--" + "".join(out) + "--"

lock = threading.Lock()
q = list(todo)
new = []

def run_one(c):
    cwd = os.path.join(WORK, "a%d" % a.round, "item-%s" % str(c["n"]).zfill(4))
    os.makedirs(cwd, exist_ok=True)
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1", DSH_PERMISSION_MODE="read-only")
    t0 = time.time()
    try:
        p = subprocess.run([EXE, BIN, "--profile", "headless", c["prompt"]],
                           cwd=cwd, env=env, capture_output=True, timeout=a.timeout)
        code, so = p.returncode, p.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        code, so = -9, (e.stdout or b"").decode("utf-8", "replace")
    b = os.path.join(os.path.expanduser("~/.dsh/sessions"), bucket_name(cwd))
    sfs = glob.glob(os.path.join(b, "*", "session.jsonl.zstd"))
    sdir = os.path.basename(os.path.dirname(max(sfs, key=os.path.getmtime))) if sfs else None
    rec = dict(id="a-%s-r%d" % (c["n"], a.round), n=c["n"], type=c["type"], round=a.round,
               paper="a", cwd=cwd, session_dir=sdir, exit_code=code,
               elapsed_s=round(time.time() - t0, 1), reply=so.strip(), stderr_tail="")
    with lock:
        new.append(rec)
        print("[rt] %d/%d n=%s exit=%s %.0fs" % (len(new), len(todo), c["n"], code, rec["elapsed_s"]), flush=True)

def worker():
    while True:
        with lock:
            if not q: return
            c = q.pop(0)
        run_one(c)

ts = [threading.Thread(target=worker) for _ in range(max(1, a.concurrency))]
[t.start() for t in ts]; [t.join() for t in ts]

# ── unlock and persist ──────────────────────────────────────────────────
os.chmod(STORE, 0o700)
merged = [r for r in keep if str(r["n"]) not in drop] + new
with open(out_path, "w", encoding="utf-8") as f:
    for r in merged: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("[rt] round=%d wrote %d rows (new %d)" % (a.round, len(merged), len(new)), flush=True)
