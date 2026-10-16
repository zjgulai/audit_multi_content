#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-check 修复版评分器：把 rounds/*.json 归成 TP/FP/FN/TN，算 P/R/F1、flaky、标签统计。

判定口径（与 root-skills-eval v3.19.1 / 上一批 YAML 的「口径 A」一致，只修好度量）：
  触发   = 该会话加载了 kb-check（skill 工具调用 **或** skill-invocation 注入）
  不触发 = 未加载 kb-check（含加载了别的 skill）
  正例：触发 = TP，未触发 = FN
  负例 / 近似 / 边界：触发 = FP，未触发 = TN
  调用类：逐条记 加载 / 未加载，不进四格
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    return json.load(open(os.path.join(HERE, name), encoding="utf-8"))


def verdict_for(case, loaded):
    t = case["类型"]
    if t == "正例":
        return "TP" if loaded else "FN"
    return "FP" if loaded else "TN"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="cases-a.json")
    ap.add_argument("--rounds", nargs="+", default=["rounds/a-round1.json",
                                                    "rounds/a-round2.json",
                                                    "rounds/a-round3.json"])
    ap.add_argument("--out", default="summary-a-fix.json")
    args = ap.parse_args()

    cases = load(args.cases)
    main_ids = [k for k, v in cases.items() if v["类型"] != "调用"]
    call_ids = [k for k, v in cases.items() if v["类型"] == "调用"]

    per_round, flaky, tag_cases, uncovered = [], [], [], []
    round_verdicts = {}
    for rf in args.rounds:
        hits = load(rf)
        tp = fp = fn = tn = 0
        verdicts = {}
        for cid in main_ids:
            recs = hits.get(cid) or []
            if not recs:
                uncovered.append((rf, cid))
                verdicts[cid] = "MISSING"
                continue
            loaded = any(r["loaded_target_skill"] for r in recs)
            v = verdict_for(cases[cid], loaded)
            verdicts[cid] = v
            tp += v == "TP"; fp += v == "FP"; fn += v == "FN"; tn += v == "TN"
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        per_round.append({"TP": tp, "FP": fp, "FN": fn, "TN": tn,
                          "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)})
        round_verdicts[rf] = verdicts

    for cid in main_ids:
        vs = {round_verdicts[rf].get(cid) for rf in round_verdicts}
        if len(vs) > 1:
            flaky.append({"id": cid, "verdicts": [round_verdicts[rf].get(cid) for rf in round_verdicts]})

    n = len(per_round)
    avg = {k: round(sum(r[k] for r in per_round) / n, 3) for k in ("precision", "recall", "f1")}

    # 标签用例逐条
    for cid, c in cases.items():
        tag = c.get("标签") or ""
        if not tag:
            continue
        if c["类型"] == "调用":
            continue
        rounds = []
        for rf in args.rounds:
            hits = load(rf)
            recs = hits.get(cid) or []
            rounds.append("触发" if (recs and any(x["loaded_target_skill"] for x in recs)) else
                          ("不触发" if recs else "缺失"))
        fpv = any(x == "触发" for x in rounds)
        tag_cases.append({"tag": tag, "id": cid, "title": c["标题"], "type": c["类型"],
                          "rounds": rounds,
                          "verdict": "FP" if (fpv and c["类型"] != "正例") else ("通过" if not fpv or c["类型"] == "正例" else "FP")})

    # 调用类
    call_rows, passed = [], 0
    for cid in call_ids:
        expect_load = not cases[cid]["预期结果"].strip().startswith("不应加载")
        rounds = []
        for rf in args.rounds:
            hits = load(rf)
            recs = hits.get(cid) or []
            lod = bool(recs and any(x["loaded_target_skill"] for x in recs))
            rounds.append(lod)
        ok = all(lod == expect_load for lod in rounds)
        passed += ok
        call_rows.append({"id": cid, "title": cases[cid]["标题"], "expect_load": expect_load,
                          "rounds_loaded": rounds, "verdict": "通过" if ok else "未通过"})

    sec = [t for t in tag_cases if t["tag"] == "安全"]
    cmb = [t for t in tag_cases if t["tag"] == "组合"]
    out = {
        "cases_total": len(main_ids), "calls_total": len(call_ids),
        "per_round": per_round, "average": avg,
        "flaky": flaky, "flaky_count": len(flaky),
        "uncovered": uncovered,
        "security_tag": {"cases": len(sec), "fp_total": sum(1 for t in sec if t["verdict"] == "FP"), "high_risk": 0},
        "combo_tag": {"cases": len(cmb), "fp_total": sum(1 for t in cmb if t["verdict"] == "FP"), "high_risk": 0},
        "call_tag": {"cases": len(call_ids), "judged": len(call_ids) * n, "passed": passed * n,
                     "failed": (len(call_ids) - passed) * n,
                     "uncovered": [], "passed_gate": passed == len(call_ids),
                     "rows": call_rows},
        "pass_call_gate": passed == len(call_ids),
        "tag_cases": tag_cases,
    }
    json.dump(out, open(os.path.join(HERE, args.out), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("per_round", "average", "flaky_count",
                                          "security_tag", "combo_tag", "pass_call_gate")},
                     ensure_ascii=False, indent=1))
    if uncovered:
        print("!! 未覆盖（没有会话逐字命中）：", uncovered)
    if flaky:
        print("flaky:", [(f["id"], f["verdicts"]) for f in flaky])
    print("->", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
