#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""envelope_gate.py —— 信封闸门：同一路径 **Python getsize** 与 **node statSync().size** 一比。

## 判据

同一路径上：`abs(getsize_python - size_消费方读者) == 4096` → **信封态**。

★★ 2026-10-03 修（kb-repair）：**判据读者 = 消费方运行时（宿主 Electron）**，不是 PATH 里的 node。

旧实现先取 `shutil.which("node")`，其 docstring 断言「本机实测：PATH 里没有 node」—— 该前提
**已过期**。同一文件三读者实测（`kb/l3/runs/20261001-1650.report.md`）：

| 读者 | `stat` 读数 | 头几个字节 |
|---|---|---|
| python `getsize` | 14005 | `# L3 蒸馏报告 …`（明文） |
| PATH `/usr/local/bin/node` | **14005** | 明文 |
| 宿主 Electron（`ELECTRON_RUN_AS_NODE=1`） | **18101** | 乱码 |

⇒ PATH 里有 node 时旧闸门**恒定报绿（假绿）**，而真正的读者（宿主 `readFileSync`、
agent 的 `read` 工具）读到的仍是乱码。设 `ELECTRON_RUN_AS_NODE=1` 改变不了「选谁」。

**判据跟着消费方走**：默认 `--reader consumer`；`--reader path` 只作对照；`--reader auto` 是旧口径。
另加**两读者交叉核对**：消费方读者与 PATH 读者判定不一致 ⇒ 直接报红
（「静默换读者」本身就是缺陷，必须可见）。

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


def _find_path_node():
    """PATH 里的 node（**不是**判据读者，只作对照——见 find_node 的 ★ 注）。"""
    n = shutil.which("node")
    return ([n], "PATH 里的 node") if n else (None, None)


def _find_kb_node():
    env_n = os.environ.get("KB_NODE")
    if env_n and os.path.exists(os.path.expanduser(env_n)):
        return [os.path.expanduser(env_n)], "KB_NODE"
    return (None, None)


def _find_consumer():
    """消费方运行时：DSH Desktop 自带 Electron（`ELECTRON_RUN_AS_NODE=1` 当 node 用）。"""
    import glob
    # 注意：本机桌面端目录名形如 `DSH Desktop.app.pre-lute-20260907-111753`
    # —— `.app` 在中间，所以模式要写成 `DSH Desktop*/Contents/...`（不能写 `*.app/Contents/...`）
    for pat in ("/Applications/DSH Desktop*/Contents/MacOS/DSH Desktop",
                os.path.expanduser("~/Applications/DSH Desktop*/Contents/MacOS/DSH Desktop")):
        for p in sorted(glob.glob(pat)):
            if os.access(p, os.X_OK):
                return [p], "DSH Desktop 内置 Electron（ELECTRON_RUN_AS_NODE=1）"
    return (None, None)


CONSUMER_PREFIX = "DSH Desktop"


def find_node(reader="consumer"):
    """按 `reader` 选定**判据读者**。返回 (argv_prefix, 说明)。

    ★★ 2026-10-03 修（kb-repair）：判据读者**默认改为消费方运行时**（宿主 Electron）。

    旧实现先取 `shutil.which("node")`，而它的 docstring 断言「本机实测：PATH 里**没有** node」。
    该前提**已过期** —— PATH 现在有 `/usr/local/bin/node`，而它读出的 size 会被同一层封装机制
    一并抵掉。同一文件三读者实测（`kb/l3/runs/20261001-1650.report.md`）：

        python `getsize` = **14005**（明文）｜PATH node `statSync` = **14005**｜宿主 Electron = **18101**（乱码）

    ⇒ 只要 PATH 里有 node，本闸门**永远走错读者、恒定报绿**（假绿），
      而真正的读者（宿主 `readFileSync`、agent 的 `read` 工具）读到的仍是乱码。
      设 `ELECTRON_RUN_AS_NODE=1` 无效（那只是 Electron 要的开关，不改变「选谁」）。

    判据必须跟着**消费方**走，不能跟着 PATH 走。

    reader:
      consumer —— 消费方运行时（DSH Electron）优先，其次 KB_NODE，最后 PATH node（**默认**）
      path     —— PATH 里的 node（只作对照，不得单独用于判绿）
      auto     —— 旧口径：PATH node 优先
    """
    fns = {"consumer": _find_consumer, "kbnode": _find_kb_node, "path": _find_path_node}
    order = {"auto": ("path", "kbnode", "consumer"),
             "path": ("path",),
             "consumer": ("consumer", "kbnode", "path")}[reader]
    for kind in order:
        prefix, how = fns[kind]()
        if prefix:
            return prefix, how
    raise RuntimeError("找不到 node 侧运行时：PATH 无 node、KB_NODE 未设、也没找到 DSH Desktop。"
                       "信封判据需要 node 的 statSync().size，无法降级 —— 用 KB_NODE=<node 绝对路径> 指定")


def node_sizes(paths, reader="consumer"):
    """一次 node 调用拿全部文件的 statSync().size。返回 {path: size}。

    路径走 **stdin** 传（不走 argv）：本机被测文件上千个，走 argv 会
    `OSError: [Errno 7] Argument list too long`（实测踩过）。
    """
    if not paths:
        return {}
    prefix, how = find_node(reader)
    script = (
        "let d='';process.stdin.on('data',c=>d+=c);"
        "process.stdin.on('end',()=>{const fs=require('fs');"
        "const out={};for(const p of JSON.parse(d)){"
        "try{out[p]=fs.statSync(p).size}catch(e){out[p]=-1}}"
        "process.stdout.write(JSON.stringify(out));});"
    )
    env = dict(os.environ)
    if CONSUMER_PREFIX in how:
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


def judge(files, reader):
    """按 `reader` 判定信封集合。返回 (env, ok, missing)；env 元素为 (路径, py, node)。"""
    nz = node_sizes(files, reader)
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
    return env, ok, missing


def main(argv=None):
    ap = argparse.ArgumentParser(description="信封闸门：python getsize vs node statSync().size")
    ap.add_argument("targets", nargs="*", help="文件或目录；缺省扫 DEFAULT_ROOTS")
    ap.add_argument("--root", default=None, help="基准目录（缺省：kb/ 的上一级）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--all", action="store_true",
                    help="连归档/备份目录一起扫（默认只扫活路径）")
    ap.add_argument("--reader", choices=("consumer", "path", "auto"), default="consumer",
                    help="判据读者：consumer=消费方运行时（宿主 Electron，**默认**）｜"
                         "path=PATH 里的 node（仅供对照）｜auto=旧口径（PATH 优先）")
    a = ap.parse_args(argv)

    base = os.path.abspath(os.path.expanduser(a.root)) if a.root else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    targets = a.targets or [os.path.join(base, r) for r in DEFAULT_ROOTS]

    files = walk(targets, include_all=a.all)
    try:
        env, ok, missing = judge(files, a.reader)
    except RuntimeError as e:
        print("环境错：%s" % e, file=sys.stderr)
        return 2
    # ⚠ `node_sizes.how` 是**函数属性**（全局可变）：下面交叉核对会再调一次 node_sizes，
    #   把标签覆写成对照读者。判据读者的标签必须在**第一次判完之后立刻**取走。
    reader_how = getattr(node_sizes, "how", "?")

    # ★ 2026-10-03 修（kb-repair）：**两读者交叉核对**。
    #   判据读者是消费方运行时（默认）；只要 PATH 里也有 node，就再用它读一遍。
    #   两读者**判定不一致 ⇒ 报红**（而不是按旧口径报绿）—— 这是「静默换读者 ⇒ 假绿」的封堵：
    #   换读者能改变读数，就说明「谁在读」本身是判据的一部分，必须可见。
    cross = None
    if CONSUMER_PREFIX in reader_how:
        _pp, _phow = _find_path_node()
        if _pp:
            try:
                env_p, _, _ = judge(files, "path")
                sc = {f for f, _, _ in env}
                sp = {f for f, _, _ in env_p}
                cross = {"reader": _phow, "envelope": len(sp), "agree": sc == sp,
                         "only_consumer": sorted(sc - sp)[:10],
                         "only_path": sorted(sp - sc)[:10]}
            except RuntimeError:
                cross = None
    cross_red = cross is not None and not cross["agree"]

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
        print("node 侧 : %s（判据读者；--reader 可换）" % reader_how)
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
        if cross is not None:
            print()
            print("--- 两读者交叉核对（%s）--- %s"
                  % (cross["reader"], "一致" if cross["agree"] else "**不一致 ⇒ 报红**"))
            print("    该读者读到的信封态：%d 个" % cross["envelope"])
            if cross_red:
                print("    只有消费方读者判为信封（PATH 读者判绿）：%s" % "、".join(cross["only_consumer"]))
                print("    只有 PATH 读者判为信封：%s" % "、".join(cross["only_path"]))
        print()
        print("=" * 74)
        print("正常：%d ｜ 信封态：%d ｜ 读不到：%d" % (ok, len(env), len(missing)))
        if cross_red:
            print("结论：判据读者与 PATH 读者**读数不一致** —— 信封判据本身不可信，报红。")
        else:
            print("结论：%s。" % ("活路径上没有信封" if not env else "发现信封态，按「python 生成 → 无扩展名临时件 → cp」重写"))
        _rc = 0 if (not env and not cross_red) else 1
        print("退出码：%d" % _rc)

    _rc = 0 if (not env and not cross_red) else 1
    if a.json:
        sys.stdout = _real
        print(json.dumps({
            "base": base, "scanned": len(files), "ok": ok,
            "reader": reader_how, "reader_mode": a.reader,
            "cross_check": cross,
            "envelope": [{"path": f, "python_size": p, "node_size": n, "delta": p - n} for f, p, n in env],
            "missing": missing, "exit_code": _rc,
        }, ensure_ascii=False, indent=2))

    return _rc


if __name__ == "__main__":
    sys.exit(main())
