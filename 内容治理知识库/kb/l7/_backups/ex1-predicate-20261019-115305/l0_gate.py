#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l0_gate.py —— L0 层闸门（**判定档**）：把「原始差异」判成「真差异 / 预期内 / 已知阻断」。

## 它补的是哪个洞（实测依据）

库自带的 `kb/l8/align_l0_feishu.py --check` 报的是**原始**四类差异，判据是「四类差异全 0」。
但实测：`材料收集` 有 10 条记录**按声明就该排除**（`kb/l0/registry/kb.json → filter`
只收「材料审核状态 == 通过」）—— 它们会**永远**被算成「飞书多」，
于是 **L0 闸门永远红**。无人值守的日报每天报同一个假红，第三天就没人看了。

→ 本脚本把政策判断从对账器里**分出来**：
  * `align_l0_feishu.py`：**只报原始事实**（不动它，它是对的）；
  * `kb/l7/registry/l0-expected-diffs.yaml`：声明「哪些差异按声明就该存在」（带 evidence）；
  * **本脚本**：原始 − 预期 = **真差异**，只有真差异才判红。

## 输出纪律（**不许抹掉原始数**）

任何一次输出都同时给三个数：**原始 / 预期内 / 真差异**。
预期项只是被**分类出来**，不是被减掉不提。

## 判据

  真差异 == 0                    → 退出 0（过）
  真差异 > 0（实际多于预期）        → 退出 1（红）：**条数变了要重新评估，不是自动放宽**
  预期项实际 < 预期（少了）         → 退出 0，但打 ⚠️ 提示复核声明（可能是别人修好了，也可能口径变了）
  出现**没有声明**的差异表/类目      → 退出 1（红）

## 只读

只做两件事：跑 `align_l0_feishu.py --check`（其 --check 档自身零写）+ 读 YAML。
**不写 `kb/l0` 的任何东西**。

用法：
    kb/kbpy l7/scripts/l0_gate.py            # 判定档（默认，给人看）
    kb/kbpy l7/scripts/l0_gate.py --json     # 机器可读
    kb/kbpy l7/scripts/l0_gate.py --quiet    # 只出汇总
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))          # …/kb
ROOT = os.path.dirname(KB)                            # kb/ 的上一级（cwd 约定）
KBPY = os.path.join(KB, "kbpy")
REPORTER = "l8/align_l0_feishu.py"          # ← 相对 kb/（kbpy 的解析基准），别写 kb/l8/...
EXPECT = os.path.join(KB, "l7/registry/l0-expected-diffs.yaml")

ROW = re.compile(r"^\[(?P<name>[^\]]+)\]\s+飞书=(?P<f>\d+)\s+L0=(?P<l>\d+)\s+一致=(?P<same>\d+)"
                 r"\s+飞书多=(?P<of>\d+)\s+L0多=(?P<ol>\d+)\s+值变=(?P<ch>\d+)\s*$")
FAIL = re.compile(r"^\[拉取失败\]\s+(?P<name>\S+?)\s+(?P<tid>\S+?):")
TOTALS = re.compile(r"一致\s+(?P<same>\d+)\s*\|\s*飞书多\s+(?P<of>\d+)\s*\|\s*L0多\s+(?P<ol>\d+)"
                    r"\s*\|\s*值变\s+(?P<ch>\d+)\s*\|\s*拉取失败\s+(?P<pf>\d+)")


def load_yaml(p):
    try:
        import yaml as _y
        return _y.safe_load(io.open(p, encoding="utf-8"))
    except Exception:
        # 库内降级：复用 skills_check 的内置解析器（与其余闸门一致，不因缺 PyYAML 就崩）
        sys.path.insert(0, HERE)
        import skills_check as SC
        return SC.parse_yaml_subset(io.open(p, encoding="utf-8").read())


def _rec(ok, real, n_exp):
    """run 记录：L0 每日只读对账这一趟（kb-l0-feishu 是 L0 的 owner）。"""
    try:
        import os as _o, sys as _s
        _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
        from run_record import record as _rr
        _rr(source="l0_daily", trigger="L0 对齐（每日只读）", skills=["kb-l0-feishu"],
            commands=["kb/kbpy l7/scripts/l0_gate.py"],
            products=["kb/l7/reports/2026-09-30-daily-health.md"],   # 明细在日报里
            verdict="%s ｜ 真差异=%d ｜ 预期内=%d" % ("过" if ok else "未过", real, n_exp),
            human_involved=False)
    except Exception as exc:              # noqa: BLE001
        print("[warn] run_record 没写成：%r" % (exc,), file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="L0 层闸门（判定档）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    # ---- 1. 跑库内对账器（--check 只读档）
    p = subprocess.run([KBPY, REPORTER, "--check"], cwd=ROOT,
                       capture_output=True, text=True, timeout=900)
    raw = (p.stdout or "") + (p.stderr or "")

    tables, failed, totals = {}, [], None
    for line in raw.splitlines():
        m = ROW.match(line.strip())
        if m:
            tables[m.group("name")] = {k: int(m.group(k)) for k in ("f", "l", "same", "of", "ol", "ch")}
            continue
        m = FAIL.match(line.strip())
        if m:
            failed.append({"name": m.group("name"), "table_id": m.group("tid")})
            continue
        m = TOTALS.search(line)
        if m:
            totals = {k: int(m.group(k)) for k in ("same", "of", "ol", "ch", "pf")}

    if totals is None:
        print("环境错：读不出对账器的汇总行（对账器可能没跑起来）", file=sys.stderr)
        print(raw[-1500:], file=sys.stderr)
        return 2

    # ---- 2. 读声明
    try:
        doc = load_yaml(EXPECT) or {}
    except Exception as e:
        print("环境错：读不出 %s：%s" % (EXPECT, e), file=sys.stderr)
        return 2
    expected = doc.get("expected") or []

    # ---- 3. 逐条比对：实际 vs 预期
    rows, real_diffs, fewer = [], [], []
    covered = set()          # (table, kind) 已被声明覆盖
    for e in expected:
        tbl, kind = e.get("table"), e.get("kind")
        exp = int(e.get("expected", 0) or 0)
        if kind == "only_feishu":
            act = (tables.get(tbl) or {}).get("of", 0)
        elif kind == "pull_failed":
            act = sum(1 for f in failed if f["name"] == tbl)
        else:
            act = 0
        covered.add((tbl, kind))
        resid = max(0, act - exp)
        verdict = "预期内" if resid == 0 and act == exp else ("**实际多于预期 → 真差异**" if resid else "⚠️ 少于预期，请复核声明")
        rows.append({"id": e.get("id"), "table": tbl, "kind": kind,
                     "actual": act, "expected": exp, "residual": resid,
                     "verdict": verdict, "owner_action": e.get("owner_action", ""),
                     "reason": (e.get("reason") or "").strip()})
        if resid:
            real_diffs.append(rows[-1])
        elif act < exp:
            fewer.append(rows[-1])

    # ---- 4. 有没有**没被声明覆盖**的差异（新表 / 新类目）
    uncovered = []
    for name, t in tables.items():
        if t["of"] and (name, "only_feishu") not in covered:
            uncovered.append("%s：飞书多 %d（**没有声明**）" % (name, t["of"]))
        if t["ol"]:
            uncovered.append("%s：L0多 %d（**不允许豁免**）" % (name, t["ol"]))
        if t["ch"]:
            uncovered.append("%s：值变 %d（**不允许豁免**）" % (name, t["ch"]))
    for f in failed:
        if (f["name"], "pull_failed") not in covered:
            uncovered.append("%s（%s）：拉取失败（**没有声明**）" % (f["name"], f["table_id"]))
    man_unreg = 0
    m = re.search(r"manifest 未登记的 L0 记录文件:\s*(\d+)", raw)
    if m:
        man_unreg = int(m.group(1))
        if man_unreg:
            uncovered.append("manifest 未登记的 L0 记录文件 %d 条（**不允许豁免**）" % man_unreg)

    exp_of = sum(r["actual"] for r in rows if r["kind"] == "only_feishu")
    exp_pf = sum(r["actual"] for r in rows if r["kind"] == "pull_failed")
    n_real = sum(r["residual"] for r in real_diffs) + len(uncovered)
    ok = (n_real == 0)

    # ---- 5. 输出
    _real = sys.stdout
    if args.json:
        sys.stdout = sys.stderr
    if not args.quiet:
        print("=" * 74)
        print("L0 层闸门（判定档） · %s" % ("过" if ok else "**未过**"))
        print("=" * 74)
        print("原始事实（来自 kb/l8/align_l0_feishu.py --check，**不抹掉**）：")
        print("  一致 %d ｜ 飞书多 %d ｜ L0多 %d ｜ 值变 %d ｜ 拉取失败 %d"
              % (totals["same"], totals["of"], totals["ol"], totals["ch"], totals["pf"]))
        print("分类：**预期内 %d**（飞书多 %d + 拉取失败 %d） ｜ **真差异 %d**"
              % (exp_of + exp_pf, exp_of, exp_pf, n_real))
        print()
        print("--- 预期差异声明（kb/l7/registry/l0-expected-diffs.yaml）---")
        for r in rows:
            print("  [%s] %s / %s：实际 %d，预期 %d → %s"
                  % (r["id"], r["table"], r["kind"], r["actual"], r["expected"], r["verdict"]))
            if r["residual"]:
                print("        ↳ 超出预期 %d，**判红**；要人做什么：%s" % (r["residual"], r["owner_action"]))
        if fewer:
            print()
            print("--- ⚠️ 少于预期的声明（请复核，不是错误）---")
            for r in fewer:
                print("  [%s] %s / %s：实际 %d < 预期 %d —— 可能已修好，也可能口径变了"
                      % (r["id"], r["table"], r["kind"], r["actual"], r["expected"]))
        print()
        print("--- 未声明的差异（一律判红，不许预豁免）--- %d 条" % len(uncovered))
        for u in uncovered:
            print("  · %s" % u)
        print()
        print("=" * 74)
        print("结论：%s" % ("✅ 过（真差异 0）" if ok else "❌ 未过（真差异 %d）" % n_real))
        print("退出码：%d" % (0 if ok else 1))

    if args.json:
        sys.stdout = _real
        print(json.dumps({
            "gate": "L0", "ok": ok, "exit_code": 0 if ok else 1,
            "raw": totals,
            "expected_rows": rows,
            "real_diff_total": n_real,
            "uncovered": uncovered,
            "fewer_than_expected": [r["id"] for r in fewer],
        }, ensure_ascii=False, indent=1))

    _rec(ok, n_real, 0)          # run 记录：放在最后，--quiet 也要记（否则等于没接）
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
