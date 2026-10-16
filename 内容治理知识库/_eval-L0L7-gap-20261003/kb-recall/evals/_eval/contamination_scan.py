#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盲测污染扫描（v2）：区分「真读了回填员产物」与「只看见文件名」。

  SEVERE  = tool/call 的**参数**里出现回填员产物路径（cases-a/b.json / rounds/ / results-*.json /
            scorein-*.json / _eval/*.py / *_report* / heartbeat）→ 该轮该条作废、必须隔离重跑
  MILD    = 只在 tool/result（目录列表）里出现文件名 → 记录，不单独作废
  豁免    = 被测 skill 自身文件（kb-recall/SKILL.md、kb-recall/references/*、kb-recall/scripts/*）

用法：python3 contamination_scan.py [--paper a]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_session as rs  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
WORK = os.environ.get("KB_RECALL_EVAL_CWD_ROOT", "/tmp/kbrecall-eval-cwd")

SEVERE_PAT = re.compile(
    r"(cases-[ab]\.json|rounds/[ab]-round|results-[ab]\.json|scorein-|selfcheck-17|"
    r"build_cases\.py|make_xlsx\.py|rt\.py|contamination_scan\.py|assertions\.py|"
    r"read_session\.py|output-assertions|heartbeat|evaluation-report|final-report|"
    r"evals/_eval|_eval/STATE)")


def classify(cwd: str):
    """返回 (severe_hits, mild_hits)。"""
    sev, mild = set(), set()
    for aid, fp in rs.session_files(cwd):
        for e in rs.read_events(fp):
            t = e.get("type")
            d = e.get("data") or {}
            if t == "tool/call":
                s = json.dumps(d, ensure_ascii=False)
                for m in SEVERE_PAT.findall(s):
                    sev.add(m)
            elif t == "tool/result":
                s = json.dumps(d, ensure_ascii=False)
                for m in SEVERE_PAT.findall(s):
                    mild.add(m)
        break
    return sorted(sev), sorted(mild - sev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="a")
    a = ap.parse_args()
    out = {"severe": [], "mild": []}
    for p in ("a", "b"):
        for r in (1, 2, 3):
            base = os.path.join(WORK, f"{p}{r}")
            if not os.path.isdir(base):
                continue
            for item in sorted(os.listdir(base)):
                sev, mild = classify(os.path.join(base, item))
                if sev:
                    out["severe"].append({"paper": p, "round": r, "item": item, "hits": sev})
                elif mild:
                    out["mild"].append({"paper": p, "round": r, "item": item, "hits": mild})
    json.dump(out, open(os.path.join(HERE, f"contamination-{a.paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("SEVERE（真读了回填员产物，必须重跑）：", len(out["severe"]))
    for x in out["severe"]:
        print("  ", x["paper"], "r%d" % x["round"], x["item"], x["hits"])
    print("MILD（只在目录列表里看见文件名）：", len(out["mild"]))
    for x in out["mild"][:40]:
        print("  ", x["paper"], "r%d" % x["round"], x["item"], x["hits"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
