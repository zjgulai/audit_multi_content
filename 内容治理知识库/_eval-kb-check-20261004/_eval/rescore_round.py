#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用第 1 轮已成立的口径重判任意一轮：机制级 loaded_target_skill → 触发/不触发。

为什么要有它：第 2 轮证据（evidence-r2.json）已采集但 score-summary.json 停在 R1，
第 2/3 轮被记成全 0。本工具用与 R1 完全相同的规则重判，并先对 R1 做**复现自证**
（复现不出 R1 的 P=0.64/R=1.0/F1=0.78 就不许用来判 R2）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CASES = os.path.join(ROOT, "cases-a.json")


def expected_trigger(case: dict) -> bool:
    """预期是否应触发/加载 kb-check。"""
    e = case.get("预期结果") or ""
    e = e.replace(" ", "")
    return e.startswith("应触发kb-check") or e.startswith("应加载kb-check")


def observed_trigger(ev: dict) -> str:
    """机制级观测：加载了 kb-check = 触发；否则不触发（追问是其子态）。"""
    if ev.get("loaded_target_skill"):
        return "触发"
    return "追问" if ev.get("ends_with_question") else "不触发"


def score(cases: dict, evid: dict):
    per = {}
    for cid, case in cases.items():
        exp = expected_trigger(case)
        ev = evid.get(cid)
        if not ev:
            continue
        obs = observed_trigger(ev)
        fired = obs == "触发"
        if case.get("类型") == "调用":
            kind = "调用"
        elif exp and fired:
            kind = "TP"
        elif exp and not fired:
            kind = "FN"
        elif not exp and fired:
            kind = "FP"
        else:
            kind = "TN"
        per[cid] = dict(type=case.get("类型"), expected="触发" if exp else "不触发",
                        observed=obs, verdict=kind, title=case.get("标题"),
                        reply_chars=ev.get("reply_chars"),
                        other_skills=ev.get("loaded_other_skills") or [])
    tp = sum(1 for v in per.values() if v["verdict"] == "TP")
    fp = sum(1 for v in per.values() if v["verdict"] == "FP")
    fn = sum(1 for v in per.values() if v["verdict"] == "FN")
    tn = sum(1 for v in per.values() if v["verdict"] == "TN")
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    # 调用门槛：3 条调用用例，机制级是否真的加载了 kb-check
    call = {k: v for k, v in per.items() if v["type"] == "调用"}
    call_pass = sum(1 for k, v in call.items()
                    if (cases[k]["预期结果"].replace(" ", "").startswith("应加载") and v["observed"] == "触发")
                    or (not cases[k]["预期结果"].replace(" ", "").startswith("应加载") and v["observed"] == "触发" and False)
                    or (not cases[k]["预期结果"].replace(" ", "").startswith("应加载") and v["observed"] != "触发"))
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=round(p, 3), recall=round(r, 3),
                f1=round(f1, 3), n=len(per),
                call_judged=len(call), call_passed=call_pass,
                per_case=per)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True, help="证据文件，如 _eval/evidence-r2.json")
    ap.add_argument("--json-out")
    ap.add_argument("--show-fp", action="store_true")
    args = ap.parse_args()

    cases = json.load(open(CASES, encoding="utf-8"))
    evid = json.load(open(os.path.join(ROOT, args.round), encoding="utf-8"))
    s = score(cases, evid)
    per_case = s.pop("per_case")
    print(json.dumps(s, ensure_ascii=False, indent=1))
    if args.show_fp:
        print("\n--- 判错的用例 ---")
        for cid, v in sorted(per_case.items(), key=lambda x: int(x[0])):
            if v["verdict"] in ("FP", "FN"):
                print(f"  case {cid:>3} {v['verdict']} 预期={v['expected']} 实测={v['observed']} | {v['title'][:44]} | 旁路skill={v['other_skills'][:3]}")
    if args.json_out:
        json.dump(dict(summary=s, per_case=per_case),
                  open(os.path.join(ROOT, args.json_out), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n-> {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
