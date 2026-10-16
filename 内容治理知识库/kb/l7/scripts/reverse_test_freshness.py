#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反测：裁定 A 的水位口径（三条，**全部用夹具，绝不拿真实库试**）。

判据（用户在批次18 第0块定的三条）：

    反测1  层 5 分钟前跑过、水位一致            → 期望 **新鲜**（改前判陈旧 = 要解决的问题）
    反测2  层 30 小时没跑                      → 期望 **陈旧**
    反测3  层刚跑过、**上游水位变了**           → 期望 **陈旧**
           ★ 这条不绿 ⇒ 说明判据退化成「只看跑过」

做法：造一个**最小 KB 夹具**（只有 L2 需要的文件），把 daily_health 指过去
（`--kb-root`，本轮为反测新加的旗标），读它的 `freshness_by_layer` 机读结论。
**不写真实库**（夹具在 /tmp 下，跑完即删）。

用法：kb/kbpy l7/scripts/reverse_test_freshness.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))          # …/kb
ROOT = os.path.dirname(KB)
sys.path.insert(0, HERE)
import layer_freshness as lf                          # noqa: E402

#: 夹具里只造 L2 关注的文件。`daily_health` 的 KEY_OUTPUTS 里 L2 的 data 产物是这两件；
#: 其余层在夹具里**不存在** ⇒ 它们会判陈旧，但**与本次反测无关**（我们只断言 L2）。
FIXTURE_FILES = {
    "l2/units.jsonl": 3,                 # L2 自己的 data 产物
    "l2/manifest_l2.jsonl": 2,
    "l1/manifest_l1.jsonl": 4,           # L2 的**上游**水位来源
}


def build_fixture(t):
    for rel, n in FIXTURE_FILES.items():
        p = os.path.join(t, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("".join("line%d\n" % i for i in range(n)))
    # 上游水位（此刻）
    wm = lf.watermark_digest(lf.current_watermark(t, "L2"))

    def write_run(age_s, cs, watermark):
        d = os.path.join(t, "l2", "runs")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "fixture-run.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"run_id": "fixture-run", "layer": "L2",
                       "change_state": cs, "input_watermark": watermark,
                       "executed_at": time.time() - age_s}, fh)
        os.utime(p, (time.time() - age_s, time.time() - age_s))
    return wm, write_run


def run_daily_health(t):
    """跑 daily_health 指到夹具，读机读结论里 L2 那一行。"""
    out = os.path.join(t, "_out")
    os.makedirs(out, exist_ok=True)
    p = subprocess.run([os.path.join(KB, "kbpy"), "l7/scripts/daily_health.py",
                        "--no-gates", "--kb-root", t, "--outdir", out],
                       capture_output=True, text=True, cwd=ROOT)
    j = os.path.join(out, "daily-health-latest.json")
    if not os.path.isfile(j):
        return None, p.stdout + p.stderr
    with open(j, encoding="utf-8") as fh:
        d = json.load(fh)
    for row in d.get("freshness_by_layer") or []:
        if row["layer"] == "L2":
            return row, p.stdout
    return None, p.stdout


CASES = []


def case(name, expect_fresh, setup):
    CASES.append((name, expect_fresh, setup))


def _setup_1(wm, write_run, t):
    write_run(300, "no_new_input", wm)                      # 5 分钟前，水位一致


def _setup_2(wm, write_run, t):
    write_run(30 * 3600, "no_new_input", wm)                # 30 小时前


def _setup_3(wm, write_run, t):
    write_run(60, "no_new_input", wm)                       # 刚跑过
    with open(os.path.join(t, "l1/manifest_l1.jsonl"), "a", encoding="utf-8") as fh:
        fh.write("NEW-UPSTREAM-LINE\n")                     # ★ 上游水位变了


case("反测1 层 5 分钟前跑过、水位一致", True, _setup_1)
case("反测2 层 30 小时没跑", False, _setup_2)
case("反测3 层刚跑过、上游水位变了", False, _setup_3)


def main():
    print("=" * 74)
    print("反测：裁定 A 的水位口径（夹具在 /tmp，**不碰真实库**）")
    print("=" * 74)
    allok = True
    for name, expect, setup in CASES:
        with tempfile.TemporaryDirectory(prefix="kb-fresh-rt-") as t:
            wm, write_run = build_fixture(t)
            setup(wm, write_run, t)
            row, raw = run_daily_health(t)
            if row is None:
                print("  %-38s **跑不出机读结论** ✗" % name)
                print(raw[-500:])
                allok = False
                continue
            got = bool(row["fresh"])
            ok = (got == expect)
            allok &= ok
            print("  %-38s 期望=%-6s 实得=%-6s %s"
                  % (name, "新鲜" if expect else "陈旧",
                     "新鲜" if got else "陈旧", "✅" if ok else "❌"))
            print("        change_state=%s  watermark_match=%s" % (
                row["change_state"], row["watermark_match"]))
            print("        判据：%s" % row["reason"][:150])
    print()
    print("三条反测：%s" % ("**全部通过 ✅**" if allok else "**有失败 ❌**"))
    if not allok:
        print("⚠️ 反测3 不绿 = 判据已退化成「只看跑过」—— **必须修，不许放过**。")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
