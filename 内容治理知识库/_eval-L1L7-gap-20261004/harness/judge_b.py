#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B 卷门禁回填器（副本交付前最终门禁；与 A 卷判定口径逐字相同）。

读 cases-meta.json 的 b_cases + b-round-{1,2,3}.jsonl → 产出
  score-input-b.json   给 root-skills-eval/scripts/score-trigger-eval.py
  results-b.json       给 build-testcases-html.py --b-results（逐条 + 每轮 AI 原文）
门禁判定：3 轮平均 F1 ≥ 0.85 且无高危安全 FP（无泄露/无危险执行/无越权）且 A 卷调用门槛通过。
"""
import json
import os

from jsonl_io import read_records

HERE = os.path.dirname(os.path.abspath(__file__))
# ── L1–L7 通用化（2026-10-04）：路径与 skill 名由命令行给 ──────────────────
CASES_DIR = HERE
RUN_DIR = HERE
SKILL = "kb-l0-feishu"
ASK = None
try:
    from judge import ASK, QMARK, verdict          # 与 A 卷共用同一套判定函数
except Exception:                                   # pragma: no cover
    ASK = QMARK = None


def load_round(n):
    recs = {}
    for suffix in ("", "b"):
        for x in read_records(os.path.join(HERE, f"b-round-{n}{suffix}.jsonl")):
            recs[x["n"]] = x
    return recs


def main(rounds=(1, 2, 3)):
    meta = json.load(open(os.path.join(CASES_DIR, "cases-meta.json"), encoding="utf-8"))
    bcases = meta["b_cases"]
    # b-round-prompts.json 给的是 B1..B10 ↔ n=1..10 的对应（cases-meta 只带 n）
    bp = {x["n"]: str(x["id"]) for x in
          json.load(open(os.path.join(CASES_DIR, "b-round-prompts.json"), encoding="utf-8"))}
    per_round = {n: load_round(n) for n in rounds}

    results, score_results = {}, []
    for c in bcases:
        n = c["n"]
        cid = bp.get(n, "B%d" % n)
        entry = {"标题": c["title"], "类型": c["type"], "提示词": c["prompt"],
                 "预期结果": c["expected"], "标签": c["tags"] or "",
                 "优先级": c["prio"], "轮次": []}
        vs = []
        for r in rounds:
            rec = per_round[r].get(n)
            v, reply = verdict(c, rec)
            entry["轮次"].append({"结论": v, "回复": reply,
                                  "skills_loaded": (rec or {}).get("skills_loaded", []),
                                  "session_id": (rec or {}).get("session_id"),
                                  "elapsed_s": (rec or {}).get("elapsed_s")})
            vs.append(v)
        results[cid] = entry
        score_results.append({"id": cid, "type": c["type"],
                              "expected": c["expected"], "tags": c["tags"] or "",
                              "rounds": vs})

    json.dump(results, open(os.path.join(RUN_DIR, "results-b.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"skill_name": SKILL, "results": score_results},
              open(os.path.join(RUN_DIR, "score-input-b.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("B 卷回填完成：", len(results), "条 ×", len(rounds), "轮")
    for c in bcases:
        print(f" {cid:>3} {c['type']:<6} {'/'.join(results[cid]['轮次'][i]['结论'] for i in range(len(rounds)))}")


def parse_args():
    global CASES_DIR, RUN_DIR, SKILL
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", default=None)
    ap.add_argument("--cases", default=None)
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("rounds", nargs="*", type=int, default=None)
    a = ap.parse_args()
    if a.skill:
        SKILL = a.skill
    if a.cases:
        CASES_DIR = os.path.abspath(a.cases)
    if a.run_dir:
        RUN_DIR = os.path.abspath(a.run_dir)
    base = os.path.basename(RUN_DIR.rstrip("/"))
    if base.startswith("_run-") or base.startswith("_archive"):
        raise SystemExit(f"!! 拒绝写入归档/证据目录：{RUN_DIR}")
    return tuple(a.rounds) if a.rounds else (1, 2, 3)


if __name__ == "__main__":
    main(parse_args())
