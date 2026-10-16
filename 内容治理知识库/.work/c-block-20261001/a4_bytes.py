#!/usr/bin/env python3
# A4 复验：python os.path.getsize 与 node fs.statSync().size 逐文件对账（差 0 才算通路）
# 用法： /usr/bin/python3 a4_bytes.py <file> [<file> ...]
import json
import os
import subprocess
import sys

NODE = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"

CHECK = (
    "const fs=require('fs');"
    "console.log(JSON.stringify({size:fs.statSync(process.argv[1]).size,"
    "first3:fs.readFileSync(process.argv[1]).slice(0,3).toString('utf8')}))"
)

for p in sys.argv[1:]:
    ap = os.path.abspath(p)
    py = os.path.getsize(ap)
    r = subprocess.run([NODE, "-e", CHECK, ap], capture_output=True, text=True,
                       env=dict(os.environ, ELECTRON_RUN_AS_NODE="1"))
    if r.returncode != 0:
        print(f"{p}\n  node 读失败 rc={r.returncode}: {(r.stderr or '')[-200:]}")
        continue
    j = json.loads(r.stdout.strip().splitlines()[-1])
    print(f"{p}\n  python getsize = {py}\n  node statSync  = {j['size']}\n"
          f"  差 = {py - j['size']}\n  首 3 字节 = {j['first3']!r}")
