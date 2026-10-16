#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l2_status.py —— L2（切分层）的**只读状态查询档**。

## 补的是哪个洞（2026-10-01）

`kb-ingest-extractor` 在 L2 只有写档（`l2_split_run.py <RUN> --apply`），
没有只读入口 —— 想查「切完没有 / 有没有陈旧单元」时无档可调。本脚本就是那个入口。

## 为什么不重跑审计（关键设计）

陈旧度判据**已经存在**：`kb/l8/l2_staleness_audit.py`（`current` / `stale_units` /
`missing_split` / `need_resplit` 等）。**本脚本不重写它**（同一判据写两处，第二处必然过期）。

但那个脚本**会写** `kb/l2/runs/<RUN>-staleness.json`（第 194 行 `json.dump(..., open(OUT,"w"))`），
**所以它不能当查询档用** —— 查询档必须只读。

本脚本因此**只读它的最新报告**，并**如实标出报告的可校验性缺口**：
该报告**不记输入文件的哈希/水位**（实测顶层键里没有任何 sha/input 字段），
因此**无法从报告自身判断它是否仍代表当前数据**。本脚本用
「报告 mtime vs 输入文件 mtime」给出**弱判据**，并把 `inputs_unverifiable` 标为 true。
弱判据只用于提示，不当结论 —— 要强判据得让审计脚本补记输入哈希（另立改动）。

## 只读

只读 `kb/l2/manifest_l2.jsonl`、`kb/l2/units.jsonl`、`kb/l2/registry/l2.json`、
以及**已有的** `kb/l2/runs/*-staleness.json`。**不跑审计、不写任何文件。**

## 退出码

    0 = 读成功（不代表"没问题"）
    2 = 用法错 / 库根不对 / 台账读不到
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

MANIFEST = os.path.join("kb", "l2", "manifest_l2.jsonl")
UNITS = os.path.join("kb", "l2", "units.jsonl")
L2REG = os.path.join("kb", "l2", "registry", "l2.json")
RUNS_GLOB = os.path.join("kb", "l2", "runs", "*-staleness.json")
ROOT_MARKER = os.path.join("kb", "KB-ROOT.json")


def check_root() -> None:
    if not os.path.isdir("kb"):
        sys.exit("l2_status: 没有 kb/ 目录。请把 cwd 设成 kb/ 的上一级（库根）。")
    if not os.path.exists(ROOT_MARKER):
        sys.exit("l2_status: 缺 %s —— 这里不是权威库根。" % ROOT_MARKER)


def count_lines(p):
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description="L2 只读状态查询档")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    check_root()

    if not os.path.exists(MANIFEST):
        print("l2_status: 台账不存在：%s" % MANIFEST, file=sys.stderr)
        return 2

    import collections
    result = collections.Counter()
    for line in open(MANIFEST, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                result[json.loads(line).get("result") or "<空>"] += 1
            except ValueError:
                result["<不可解析行>"] += 1

    units_n = count_lines(UNITS)

    # 已有的审计报告（只读；不重跑）
    reports = sorted(glob.glob(RUNS_GLOB))
    audit = None
    if reports:
        latest = reports[-1]
        try:
            d = json.load(open(latest, encoding="utf-8"))
        except (ValueError, OSError):
            d = None
        if d is not None:
            audit_mtime = os.path.getmtime(latest)
            # 弱判据：审计报告之后，输入台账动过没有
            moved = []
            for p in (MANIFEST, UNITS):
                if os.path.exists(p) and os.path.getmtime(p) > audit_mtime:
                    moved.append(p)
            audit = {
                "report": latest,
                "run": d.get("run"),
                "stale_resources": d.get("stale_resources"),
                "stale_units": d.get("stale_units"),
                "stale_chars": d.get("stale_chars"),
                "stale_units_in_l6_index": d.get("stale_units_in_l6_index"),
                "need_resplit_resources": d.get("need_resplit_resources"),
                "missing_split_resources": d.get("missing_split_resources"),
                "verdict_counts": d.get("verdict_counts"),
                # 该报告不记输入哈希 → 无法自证是否仍代表当前数据
                "inputs_unverifiable": True,
                "inputs_moved_after_report": moved,
            }

    print("L2 状态（只读查询档）｜台账 %s" % MANIFEST)
    print("  台账 result: " + " ｜ ".join("%s=%d" % (k, v) for k, v in sorted(result.items())))
    print("  单元行数 units.jsonl: %s" % (units_n if units_n is not None else "缺失"))
    if audit:
        print("  最新陈旧度审计: %s（run %s）" % (audit["report"], audit["run"]))
        print("    陈旧资源 %s 个 ｜ 陈旧单元 %s 条 / %s 字" % (
            audit["stale_resources"], audit["stale_units"], audit["stale_chars"]))
        print("    其中已进 L6 索引 %s 条（>0 = 需要退役）" % audit["stale_units_in_l6_index"])
        print("    要重切 %s 个 ｜ 有正文无单元缺口 %s 个" % (
            audit["need_resplit_resources"], audit["missing_split_resources"]))
        if audit["inputs_moved_after_report"]:
            print("    ⚠️ 弱判据：审计报告之后这些输入动过 → 上面数字可能已过期：%s"
                  % "、".join(audit["inputs_moved_after_report"]))
        print("    ⚠️ 该报告不记输入哈希，无法自证代表当前数据（inputs_unverifiable=true）")
    else:
        print("  最新陈旧度审计: **没有**（%s 无命中）→ 陈旧度**未评估**，不是「无陈旧」" % RUNS_GLOB)

    if a.json:
        print(json.dumps({
            "layer": "L2",
            "manifest": MANIFEST,
            "result_counts": dict(result),
            "units_lines": units_n,
            "audit": audit,
        }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
