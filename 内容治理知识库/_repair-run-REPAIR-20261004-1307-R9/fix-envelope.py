#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 9 轮 kb-repair：把工作区里唯一的信封态 .md（⑥ 段的实质红）按登记修法重写。

修法（kb-repair §2「信封态（差值 4096）」那一行）：**不许用 python 直写目标**，
一律「python 读内容 → 写到**无扩展名**临时件 → `cp` 落到目标」。
本脚本**不**自己写目标文件，只做三件事：读内容、打印 BEFORE/AFTER 读数、调 `cp`。
"""
import hashlib
import os
import subprocess
import sys
import time

TARGET = "_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md"
TMP = "/tmp/kb-repair-R9-md-tmp"          # ← 无扩展名（带扩展名会被 python 通道加信封）
DSH = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"


def node_size(p):
    r = subprocess.run([DSH, "-e", 'const fs=require("fs");console.log(fs.statSync(process.argv[1]).size)',
                        p], capture_output=True, text=True, env=dict(os.environ, ELECTRON_RUN_AS_NODE="1"))
    try:
        return int(r.stdout.strip())
    except Exception:
        return None


def node_tail(p, n=32):
    r = subprocess.run([DSH, "-e", 'const fs=require("fs");const b=fs.readFileSync(process.argv[1]);'
                                    'console.log(JSON.stringify(b.slice(-Number(process.argv[2])).toString("hex")))',
                        p, str(n)], capture_output=True, text=True, env=dict(os.environ, ELECTRON_RUN_AS_NODE="1"))
    return r.stdout.strip()[:200]


def reading(tag, p):
    py = os.path.getsize(p)
    nd = node_size(p)
    body = open(p, "rb").read()
    return {"when": tag, "path": p, "py_size": py, "node_size": nd,
            "delta": (nd - py) if (nd is not None) else None,
            "enveloped": nd != py, "py_read_bytes": len(body),
            "py_read_sha256": hashlib.sha256(body).hexdigest(),
            "py_read_tail_hex": body[-24:].hex(), "node_read_tail_hex": node_tail(p),
            "mtime": time.strftime("%F %T", time.localtime(os.path.getmtime(p)))}


import json
out = {"target": TARGET, "before": reading("BEFORE", TARGET)}

# ── 修法：python 读内容 → 无扩展名临时件 → cp ──
with open(TARGET, "rb") as fh:
    body = fh.read()
with open(TMP, "wb") as fh:                     # 无扩展名 ⇒ 不触发 4096 信封
    fh.write(body)
out["tmp"] = reading("TMP(after python write, no extension)", TMP)

cp = subprocess.run(["/bin/cp", TMP, TARGET], capture_output=True, text=True)
out["cp"] = {"rc": cp.returncode, "cmd": f"/bin/cp {TMP} {TARGET}", "stderr": cp.stderr[-200:]}

out["after"] = reading("AFTER", TARGET)
out["content_preserved"] = out["before"]["py_read_sha256"] == out["after"]["py_read_sha256"]
print(json.dumps(out, ensure_ascii=False, indent=1))
sys.exit(0 if (out["after"]["enveloped"] is False and out["content_preserved"]) else 1)
