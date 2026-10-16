#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""envelope_gate.py —— 信封闸门：同一路径 **Python getsize** 与 **node statSync().size** 一比。

## 判据

同一路径上：`abs(getsize_python - size_node) == 4096` → **信封态**。

成因（实测）：在这台机器上，**用 python 写 `.py` / `.txt` / `.md`** 会落成
「stat 虚高 4096」的信封 —— 宿主 Electron 侧 `readFileSync` 读出来是乱码。
python 写 `.json` / `.yaml`、bash 重定向、`cp`、node 写盘都是安全的。

**规定的写通道**：
    python 生成内容 → 写到**无扩展名**的临时件 → `cp` 落到目标

## 与库自带脚本的分工

| 脚本 | 覆盖范围 |
|---|---|
| `kb/l8/envelope_census.py`（库自带） | **只扫 `.md`** |
| 本脚本 `tools/envelope_gate.py` | `.py` / `.txt` / `.md`（三件套，与上面互补） |

两个都要跑，谁也替代不了谁。

## 用法

    python3 tools/envelope_gate.py                     # 扫默认范围（见 DEFAULT_ROOTS）
    python3 tools/envelope_gate.py <路径> [<路径>...]   # 扫指定文件或目录
    python3 tools/envelope_gate.py --json              # 机器可读
    python3 tools/envelope_gate.py --quiet             # 只输出汇总与退出码

退出码：0 无信封 / 1 发现信封 / 2 环境错（node 不可用等）

**只读**：本脚本不修改任何文件，只统计与报告。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

SUFFIXES = (".py", ".txt", ".md")
ENVELOPE_DELTA = 4096
DEFAULT_ROOTS = ["kb/l0", "kb/l1", "kb/l2", "kb/l3", "kb/l4", "kb/l5", "kb/l6", "kb/l7",
                 "kb/l8", "kb/.work", "kb/view", "kb/versions", "tools", "_eval-kb-manage"]
#: 默认跳过的目录名（归档 / 备份 / 缓存）——**活路径**不该有信封，备份里有一堆是历史事实。
#: 要看全量就加 `--all`。
SKIP_DIR_NAMES = {"__pycache__", ".git", "node_modules",
                  "_archive", "_backups", "_skill-backups", "_stage"}
SKIP_PREFIXES = ("hostlib",)


def find_node():
    """按顺序找可用的 node 侧运行时。返回 (argv_prefix, 说明)。

    1. PATH 里的 node
    2. 环境变量 KB_NODE
    3. DSH Desktop 自带的 Electron —— 用 `ELECTRON_RUN_AS_NODE=1` 当 node 用
       （本机实测：PATH 里**没有** node，只有桌面端内置的那个）
    """
    n = shutil.which("node")
    if n:
        return [n], "PATH 里的 node"
    env_n = os.environ.get("KB_NODE")
    if env_n and os.path.exists(os.path.expanduser(env_n)):
        return [os.path.expanduser(env_n)], "KB_NODE"
    import glob
    # 注意：本机桌面端目录名形如 `DSH Desktop.app.pre-lute-20260907-111753`
    # —— `.app` 在中间，所以模式要写成 `DSH Desktop*/Contents/...`（不能写 `*.app/Contents/...`）
    for pat in ("/Applications/DSH Desktop*/Contents/MacOS/DSH Desktop",
                os.path.expanduser("~/Applications/DSH Desktop*/Contents/MacOS/DSH Desktop")):
        for p in sorted(glob.glob(pat)):
            if os.access(p, os.X_OK):
                return [p], "DSH Desktop 内置 Electron（ELECTRON_RUN_AS_NODE=1）"
    raise RuntimeError("找不到 node 侧运行时：PATH 无 node、KB_NODE 未设、也没找到 DSH Desktop。"
                       "信封判据需要 node 的 statSync().size，无法降级 —— 用 KB_NODE=<node 绝对路径> 指定")


def node_sizes(paths):
    """一次 node 调用拿全部文件的 statSync().size。返回 {path: size}。

    路径走 **stdin** 传（不走 argv）：本机被测文件上千个，走 argv 会
    `OSError: [Errno 7] Argument list too long`（实测踩过）。
    """
    if not paths:
        return {}
    prefix, how = find_node()
    script = (
        "let d='';process.stdin.on('data',c=>d+=c);"
        "process.stdin.on('end',()=>{const fs=require('fs');"
        "const out={};for(const p of JSON.parse(d)){"
        "try{out[p]=fs.statSync(p).size}catch(e){out[p]=-1}}"
        "process.stdout.write(JSON.stringify(out));});"
    )
    env = dict(os.environ)
    if "Electron" in how:
        env["ELECTRON_RUN_AS_NODE"] = "1"
    res = subprocess.run(prefix + ["-e", script],
                         input=json.dumps(paths), capture_output=True, text=True, env=env)
    if res.returncode != 0:
        raise RuntimeError("node 取 size 失败（%s）：%s" % (how, (res.stderr or res.stdout)[:300]))
    out = json.loads(res.stdout)
    node_sizes.how = how
    return out


def walk(targets, include_all=False):
    out = []
    for t in targets:
        p = os.path.abspath(os.path.expanduser(t))
        if os.path.isfile(p):
            out.append(p)
            continue
        if not os.path.isdir(p):
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            if not include_all:
                keep = []
                for d in dirnames:
                    if d in SKIP_DIR_NAMES or any(d.startswith(x) for x in SKIP_PREFIXES):
                        continue
                    keep.append(d)
                dirnames[:] = keep
            for f in filenames:
                if f.endswith(SUFFIXES):
                    out.append(os.path.join(dirpath, f))
    return sorted(set(out))


def main(argv=None):
    ap = argparse.ArgumentParser(description="信封闸门：python getsize vs node statSync().size")
    ap.add_argument("targets", nargs="*", help="文件或目录；缺省扫 DEFAULT_ROOTS")
    ap.add_argument("--root", default=None, help="基准目录（缺省：kb/ 的上一级）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--all", action="store_true",
                    help="连归档/备份目录一起扫（默认只扫活路径）")
    a = ap.parse_args(argv)

    base = os.path.abspath(os.path.expanduser(a.root)) if a.root else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    targets = a.targets or [os.path.join(base, r) for r in DEFAULT_ROOTS]

    files = walk(targets, include_all=a.all)
    try:
        nz = node_sizes(files)
    except RuntimeError as e:
        print("环境错：%s" % e, file=sys.stderr)
        return 2

    env, ok, missing = [], 0, []
    for f in files:
        n = nz.get(f, -1)
        if n < 0:
            missing.append(f)
            continue
        p = os.path.getsize(f)
        if abs(p - n) == ENVELOPE_DELTA:
            env.append((f, p, n))
        else:
            ok += 1

    _real = sys.stdout
    if a.json:
        sys.stdout = sys.stderr
    if not a.quiet:
        print("=" * 74)
        print("envelope_gate —— 信封闸门（python getsize vs node statSync().size）")
        print("=" * 74)
        print("基准目录: %s" % base)
        print("扫描范围: %s" % "、".join(os.path.relpath(t, base) if t.startswith(base) else t for t in targets))
        print("扩展名  : %s" % " ".join(SUFFIXES))
        print("node 侧 : %s" % getattr(node_sizes, "how", "?"))
        print("扫描到  : %d 个文件" % len(files))
        print()
        print("--- 信封态（|差值| == %d）--- %d 个" % (ENVELOPE_DELTA, len(env)))
        for f, p, n in env[:a.limit]:
            print("    · %s ｜ python=%d node=%d 差=%+d" % (f, p, n, p - n))
        if len(env) > a.limit:
            print("    … 另有 %d 个未列" % (len(env) - a.limit))
        if missing:
            print()
            print("--- 读不到（node 侧不存在）--- %d 个" % len(missing))
            for f in missing[:a.limit]:
                print("    · %s" % f)
        print()
        print("=" * 74)
        print("正常：%d ｜ 信封态：%d ｜ 读不到：%d" % (ok, len(env), len(missing)))
        print("结论：%s。" % ("活路径上没有信封" if not env else "发现信封态，按「python 生成 → 无扩展名临时件 → cp」重写"))
        print("退出码：%d" % (0 if not env else 1))

    if a.json:
        sys.stdout = _real
        print(json.dumps({
            "base": base, "scanned": len(files), "ok": ok,
            "envelope": [{"path": f, "python_size": p, "node_size": n, "delta": p - n} for f, p, n in env],
            "missing": missing, "exit_code": 0 if not env else 1,
        }, ensure_ascii=False, indent=2))

    return 0 if not env else 1


if __name__ == "__main__":
    sys.exit(main())
