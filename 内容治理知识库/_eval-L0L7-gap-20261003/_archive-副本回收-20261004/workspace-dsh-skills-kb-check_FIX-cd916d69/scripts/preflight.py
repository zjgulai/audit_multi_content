#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-check 预检查 —— **只读**，不写任何文件。

在跑六道闸门之前先回答三件事，免得把「缺输入」报成「数据坏了」：

  1. cwd 是不是本次库根（库根 = 同时有 kb/kbpy 与 kb/l7/registry/layers.yaml 的目录）；
  2. 六道闸门的脚本在不在（kbpy 按**自身所在目录**解析 `l7/...` 这类参数，不是按 cwd）；
  3. 门③ 的赢家表输入在不在 —— 缺它 `routes_reconcile.py` 会退出码 2，
     不是「路由表全不一致」。

用法：
    cd "<本次库根>"
    python3 <本 skill 目录>/scripts/preflight.py [--run <RUN>] [--json]

退出码：0 = 六道闸门的**静态前置**齐（输入缺失只报不拦）；2 = 库根或脚本缺失（跑不了）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.dont_write_bytecode = True

# 六道闸门：label -> (探针路径, 说明)
GATES = [
    ("① 登记表自检", "kb/l7/scripts/skills_check.py"),
    ("② 层契约", "kb/l7/scripts/layers_check.py"),
    ("③ 路由表对账", "kb/l7/scripts/routes_reconcile.py"),
    ("④ 链路收口", "kb/l8/workflow_check.py"),
    ("⑤ 信封闸门(库自带,只扫 .md)", "kb/l8/envelope_census.py"),
    ("⑤ 信封闸门(.py/.txt/.md)", "tools/envelope_gate.py"),
    ("⑥ 投影一致性", "kb/l8/projection_reconcile.py"),
]

# 会写库的闸门（无干跑档）—— 预检查只提示，不替调用者决定
WRITES = {"④ 链路收口": "kb/l8/workflow_check_<RUN>.json", "⑥ 投影一致性": "（无干跑档）"}


def find_lib_root(start: str) -> str | None:
    """库根 = 同时有 kb/kbpy 与 kb/l7/registry/layers.yaml 的目录。找不到回 None。"""
    cur = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(cur, "kb", "kbpy")) and \
           os.path.isfile(os.path.join(cur, "kb", "l7", "registry", "layers.yaml")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def find_winners(root: str) -> list[str]:
    """只读扫 kb/l7/reports/ 下的赢家表（任何形态）。"""
    d = os.path.join(root, "kb", "l7", "reports")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if "routes-winners" in f or "routes_winners" in f)


def main() -> int:
    ap = argparse.ArgumentParser(description="kb-check 只读预检查")
    ap.add_argument("--run", default="<RUN>", help="本次体检的 RUN 标识（只用于提示写盘文件名）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    cwd = os.getcwd()
    root = find_lib_root(cwd)
    out: dict = {"cwd": cwd, "library_root": root, "gates": {}, "blocking": [], "notes": []}

    if root is None:
        out["blocking"].append(
            "cwd 不在库内：向上找不到同时含 kb/kbpy 与 kb/l7/registry/layers.yaml 的目录。"
            "先 cd 到本次库根再跑，否则六道闸门的相对路径全部落空。")
    else:
        if os.path.abspath(root) != cwd:
            out["notes"].append(f"cwd 不是库根本身（库根 = {root}）；kbpy 仍按自身目录解析参数，但只读脚本的相对路径按 cwd 走。")
        for label, rel in GATES:
            ok = os.path.isfile(os.path.join(root, rel))
            out["gates"][label] = {"path": rel, "present": ok}
            if not ok:
                out["blocking"].append(f"{label}：找不到 {rel}")
        # 解释器（kbpy 写死约定）
        kbpy = os.path.join(root, "kb", "kbpy")
        out["kbpy"] = {"path": "kb/kbpy", "present": os.path.isfile(kbpy)}
        kb_python = os.path.join(root, "kb", ".kb-python")
        out["kb_python"] = {"path": "kb/.kb-python",
                            "present": os.path.isfile(kb_python),
                            "note": "存在即由 kbpy 直接使用；不存在则 kbpy 回落 bootstrap python 探测。"}

        wins = find_winners(root)
        out["routes_winners"] = wins
        if not wins:
            out["notes"].append(
                "门③ 缺输入：kb/l7/reports/ 下没有 *routes-winners* 文件 ⇒ "
                "`routes_reconcile.py` 将**退出码 2**（输入缺失），**不是**「路由表 65 条全不一致」。"
                "赢家表是触发评测的运行时产物、全库无生成者；要今天的数据先按 kb-manage 的触发电测重新生成。")

        writes = {k: v for k, v in WRITES.items() if out["gates"].get(k, {}).get("present")}
        if writes:
            out["notes"].append("会写库的闸门（无干跑档，先声明再跑）：" +
                                "；".join(f"{k} → {v}" for k, v in writes.items()))
        out["notes"].append("本预检查全程只读：不写 kb/、不建目录、不落 __pycache__。")

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("kb-check 预检查（只读）")
        print(f"  cwd          : {cwd}")
        print(f"  库根         : {root or '**未找到**'}")
        if root:
            for label, rel in GATES:
                print(f"  {'OK  ' if out['gates'][label]['present'] else 'MISS'} {label:32s} {rel}")
            print(f"  赢家表输入   : {out['routes_winners'] or '**无**（门③ 将 exit 2）'}")
        for n in out["notes"]:
            print(f"  note: {n}")
        for b in out["blocking"]:
            print(f"  BLOCK: {b}")
        print("结论：" + ("前置齐，可开跑闸门" if not out["blocking"] else "前置不全，先补齐再跑"))
    return 0 if not out["blocking"] else 2


if __name__ == "__main__":
    sys.exit(main())
