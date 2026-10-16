#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_perf_bench.py —— L5 性能验收的**复算闸门**（PRD §12「P0 层响应 ≤1s」）。

## 为什么要有它（这正是它存在的理由）

`kb/l5/benchmark.json` 的 `verdict` 是 `kb/.work/l5_bench.py` 写下的**结论**。
实测过的缺口：**全库没有任何周期闸门读这个文件** ——
`grep -rn benchmark kb/l8 kb/l7/scripts ci tools` = **0 命中**，
于是 2026-10-10 那次 FAIL（11 条模式 ⇒ 1MB 用例 1132 ms）**一直红着没人看见**，
直到人工定性才被发现。

⇒ 本闸门补的就是那一格：**读原始读数，按 bench 自己写下的判据复算**，
并比对「记下来的 verdict」与「复算出来的 verdict」是否一致。

## 它核什么（三问）

1. `kb/l5/benchmark.json` **在不在、读不读得动**（读不到 ⇒ 退出码 2，**不许当通过**）。
2. **复算**：按 JSON 里的 `criterion`（**单一真源，就是 bench 自己写下的那份**）重判每个用例。
   · 真实送审形态（`real_cases`）⇒ **严格 < 1000 ms**
   · 余量用例（`margin_cases`）⇒ **每模式中位 ≤ 120 ms**
3. **一致性**：JSON 里记的 `verdict` 必须等于复算值（**手改 verdict 逃不掉**）。

## 与 l5_bench.py 的分工

`l5_bench.py` = **测量 + 判定**（会写 `benchmark.json`，慢，且有副作用 ⇒ **不进周期跑**）；
本件 = **只读复算**（毫秒级，无副作用 ⇒ 进周期跑）。两者用**同一份判据口径**：
口径写在 `benchmark.json.criterion` 里，本件**从那里读**，不另抄一份。

## 用法

    python3 kb/l8/check_perf_bench.py             # 只读复算
    python3 kb/l8/check_perf_bench.py --selftest   # 自证（全合成用例，不读真文件）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
BENCH = os.path.join(KB, "l5", "benchmark.json")

#: 兜底口径 —— **只在 JSON 缺 `criterion` 时用**（老文件），并在输出里明写「用了兜底」。
FALLBACK = {"hard_limit_ms": 1000.0, "per_pattern_limit_ms": 120.0,
            "real_cases": ["single_primary_text", "single_with_hit", "batch_ad_copy"],
            "margin_cases": ["large_doc_1mb"]}


def recompute(bench):
    """按 bench 自带的 criterion 复算 ⇒ (逐档结果, 复算 verdict, 用的口径, 是否兜底)。"""
    crit = bench.get("criterion") or FALLBACK
    used_fallback = not bench.get("criterion")

    # ★ 取值一律「**键在就照它**」—— 不许用 `or` 兜底：空列表 / 0 都是**合法取值**，
    #   用 `or` 会把「显式声明为空」误读成「没声明」（自证 ⑦ 就是被这条抓出来的）。
    def pick(key, dflt):
        v = crit.get(key, dflt)
        return dflt if v is None else v

    hard = float(pick("hard_limit_ms", FALLBACK["hard_limit_ms"]))
    per_pat = float(pick("per_pattern_limit_ms", FALLBACK["per_pattern_limit_ms"]))
    real = set(pick("real_cases", FALLBACK["real_cases"]))
    margin = set(pick("margin_cases", FALLBACK["margin_cases"]))
    pc = max(1, int(bench.get("pattern_count") or 1))
    rows = []
    for c in bench.get("cases") or []:
        med = float((c.get("elapsed_ms") or {}).get("median") or 0.0)
        name = c.get("case")
        if name in margin:
            kind, ok, limit = "per_pattern", med / pc <= per_pat, per_pat
        elif name in real:
            kind, ok, limit = "hard_1s", med < hard, hard
        else:                                   # 未知用例 ⇒ 按硬门槛兜底（保守）
            kind, ok, limit = "hard_1s(unknown)", med < hard, hard
        rows.append({"case": name, "median_ms": med, "per_pattern_ms": round(med / pc, 3),
                     "kind": kind, "limit": limit, "pass": ok})
    verdict = "PASS" if rows and all(r["pass"] for r in rows) else "FAIL"
    return rows, verdict, crit, used_fallback


def run():
    print("L5 性能验收 · 复算闸门（PRD §12「P0 层响应 ≤1s」）")
    print("★ 只读：读 kb/l5/benchmark.json 的**原始读数**，按它自带的 criterion 复算，")
    print("  再比对「记下来的 verdict」与「复算 verdict」——手改 verdict 逃不掉。\n")
    if not os.path.exists(BENCH):
        print("读不到 %s ⇒ 判不了（**不许当通过**；先跑 kb/.work/l5_bench.py）" % BENCH)
        return 2
    try:
        bench = json.load(io.open(BENCH, encoding="utf-8"))
    except Exception as e:                                     # noqa: BLE001
        print("解析失败：%r ⇒ 判不了（不许当通过）" % (e,))
        return 2
    rows, verdict, crit, used_fallback = recompute(bench)
    if not rows:
        print("benchmark.json 里没有用例 ⇒ 判不了（不许当通过）")
        return 2
    print("模式数 %s ｜ 门槛：真实形态 < %s ms ｜ 余量用例每模式 ≤ %s ms%s"
          % (bench.get("pattern_count"), crit.get("hard_limit_ms"), crit.get("per_pattern_limit_ms"),
             "　⚠️ 用了**兜底口径**（JSON 无 criterion 字段，可能是老文件）" if used_fallback else ""))
    if crit.get("ruling"):
        print("口径出处：%s" % crit["ruling"])
    print()
    for r in rows:
        print("  %-20s 中位 %9.3f ms ｜ 每模式 %8.3f ms ｜ %-18s %s"
              % (r["case"], r["median_ms"], r["per_pattern_ms"], r["kind"],
                 "✅" if r["pass"] else "❌ 超线"))
    recorded = bench.get("verdict")
    print()
    if recorded != verdict:
        print("❌ **记下来的 verdict（%s）≠ 复算 verdict（%s）** —— 有人手改过，或判据变过" % (recorded, verdict))
        return 3
    if verdict == "FAIL":
        print("❌ **FAIL** —— 见上（真实形态超 1s = 真劣化；余量用例超 120 ms/模式 = matcher 真的变慢了）")
        return 3
    print("✅ PASS —— 真实送审形态 <1s，余量用例每模式 ≤ %s ms（记录与复算一致）"
          % crit.get("per_pattern_limit_ms"))
    return 0


def selftest():
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    def mk(cases, pc=11, criterion=True):
        b = {"pattern_count": pc, "cases": cases, "verdict": "PASS"}
        if criterion:
            b["criterion"] = dict(FALLBACK)
        return b

    def case(name, med):
        return {"case": name, "elapsed_ms": {"median": med}}

    # ① 现账形状（11 模式、1MB 1185 ms）⇒ 复算 PASS
    b = mk([case("single_with_hit", 0.965), case("batch_ad_copy", 147.2), case("large_doc_1mb", 1185.5)])
    _r, v, _c, fb = recompute(b)
    ck("① 现账（1MB 1185 ms / 11 模式 = 107.8 ms）⇒ PASS", v == "PASS" and not fb, v)
    # ★ 反向对照：真实形态超 1 s ⇒ 必须 FAIL（分级**不覆盖**真实形态）
    b2 = mk([case("batch_ad_copy", 1200.0), case("large_doc_1mb", 1185.5)])
    _r, v2, _c, _f = recompute(b2)
    ck("② 反向对照：**真实形态** 1200 ms ⇒ FAIL（分级不覆盖它）", v2 == "FAIL", v2)
    # ★ 反向对照：余量用例超 120 ms/模式 ⇒ 必须 FAIL
    b3 = mk([case("large_doc_1mb", 1400.0)])
    _r, v3, _c, _f = recompute(b3)
    ck("③ 反向对照：余量用例 1400/11=127.3 ms ⇒ FAIL（判据不是恒绿）", v3 == "FAIL", v3)
    # ★ 一致性：手改 verdict ⇒ 复算出不一致（退出码 3 那条路）
    b4 = mk([case("large_doc_1mb", 1400.0)])
    b4["verdict"] = "PASS"
    _r, v4, _c, _f = recompute(b4)
    ck("④ 反向对照：手把 verdict 改成 PASS ⇒ 复算仍是 FAIL（不一致会被抓）",
       v4 == "FAIL" and b4["verdict"] != v4, "%s vs %s" % (b4["verdict"], v4))
    # ⑤ 边界：正好 120.000 ms/模式 ⇒ PASS；多一点点 ⇒ FAIL
    _r, v5, _c, _f = recompute(mk([case("large_doc_1mb", 120.0 * 11)]))
    _r, v6, _c, _f = recompute(mk([case("large_doc_1mb", 120.0 * 11 + 1)]))
    ck("⑤ 边界：正好 120.000 ms/模式 ⇒ PASS", v5 == "PASS", v5)
    ck("⑤b 边界：120.09 ms/模式 ⇒ FAIL", v6 == "FAIL", v6)
    # ⑥ 缺 criterion（老文件）⇒ 用兜底口径且**明写出来**
    b7 = mk([case("large_doc_1mb", 1185.5)], criterion=False)
    _r, v7, _c, fb7 = recompute(b7)
    ck("⑥ 老文件缺 criterion ⇒ 用兜底口径且标记 used_fallback", v7 == "PASS" and fb7, str(fb7))
    # ⑦ 变异测试：把余量用例从 margin 挪进 real ⇒ 1185 ms 立刻 FAIL（证明分级是**真的在生效**）
    b8 = mk([case("large_doc_1mb", 1185.5)])
    b8["criterion"] = dict(FALLBACK, margin_cases=[])
    _r, v8, _c, _f = recompute(b8)
    ck("⑦ 变异测试：把余量用例当真实形态判 ⇒ 1185 ms 精确变 FAIL", v8 == "FAIL", v8)
    # ⑧ 空用例 / 没有 cases ⇒ 判不了，不许 PASS
    _r, v9, _c, _f = recompute({"pattern_count": 11, "cases": []})
    ck("⑧ 无用例 ⇒ FAIL（不给出 PASS）", v9 == "FAIL", v9)
    print("check_perf_bench --selftest")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + ex) if ex else ""))
    bad = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad, len(res), "" if not bad else "  ← 有失败"))
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run())
