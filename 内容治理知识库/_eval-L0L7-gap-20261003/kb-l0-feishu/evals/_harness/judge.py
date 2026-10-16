#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-l0-feishu 触发结论回填器（回填员侧）。

读 cases-meta.json（类型/预期/标签/攻击面/组合场景）+ a-round-{1,2,3}.jsonl（每轮真实会话），
产出：
  results-a.json        build-testcases-html.py 的输入（逐条 + 每轮 AI 原文）
  score-input-a.json    score-trigger-eval.py 的输入（TP/FP/FN/TN 归类）
  ../kb-l0-feishu.xlsx  回填 1/2/3 轮执行结果 + 执行日期
  verdicts-a.json       逐条逐轮结论 + 客观证据（skills_loaded）

判定口径（root-skills-eval v3.19.1 Step 3/4）：
- 触发判定的**客观证据**是被测会话 session.jsonl 里的 skill 工具调用（含斜杠调用注入的
  skill_content），不采信被测会话自报。
- 结论串固定为：触发 / 不触发 / 追问（调用题为 加载 / 未加载）。
- 边界情况：未触发但回复在追问澄清 → 记「追问」，按预期（含「追问」）计 TN。
"""
import json
import os
import re
from datetime import date

import openpyxl

from jsonl_io import read_records

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
NAME = "kb-l0-feishu"
RUN_DATE = date.today().isoformat()

ASK = re.compile(r"(请问|确认一下|需要你|告诉我|哪一层|哪条链|哪张表|哪批|什么范围|指的是|"
                 r"你是要|你想|要我做|哪一个|说明一下|请补充|补一下)")
QMARK = re.compile(r"[?？]")


def load_round(n, paper="a"):
    """读该轮全部结果文件（a-round-N.jsonl 与分片 a-round-Nb.jsonl），按 n 去重取最后一条。"""
    recs = {}
    for suffix in ("", "b", "c"):
        for x in read_records(os.path.join(HERE, f"{paper}-round-{n}{suffix}.jsonl")):
            recs[x["n"]] = x
    return recs


def verdict(meta, rec):
    if rec is None:
        return "", ""
    loaded = bool(rec.get("skill_loaded"))
    reply = rec.get("reply") or ""
    t = meta["type"]
    if t == "调用":
        return ("加载" if loaded else "未加载"), reply
    if loaded:
        return "触发", reply
    if t == "边界情况" and (QMARK.search(reply) and ASK.search(reply)):
        return "追问", reply
    return "不触发", reply


def main(rounds=(1, 2, 3)):
    meta = json.load(open(os.path.join(HERE, "cases-meta.json"), encoding="utf-8"))
    all_meta = {c["n"]: c for c in meta["a_cases"] + meta["call_cases"]}
    per_round = {n: load_round(n) for n in rounds}

    results, score_results = {}, []
    report = []
    for n in sorted(all_meta):
        m = all_meta[n]
        entry = {"标题": m["title"], "类型": m["type"], "提示词": m["prompt"],
                 "预期结果": m["expected"], "标签": m["tags"] or "",
                 "优先级": m["prio"], "轮次": []}
        vs = []
        for r in rounds:
            rec = per_round[r].get(n)
            v, reply = verdict(m, rec)
            entry["轮次"].append({"结论": v, "回复": reply,
                                  "skills_loaded": (rec or {}).get("skills_loaded", []),
                                  "session_id": (rec or {}).get("session_id"),
                                  "elapsed_s": (rec or {}).get("elapsed_s")})
            vs.append(v)
        results[str(n)] = entry
        score_results.append({"id": str(n), "type": m["type"],
                              "expected": m["expected"], "tags": m["tags"] or "",
                              "rounds": vs})
        report.append((n, m["type"], vs))

    json.dump(results, open(os.path.join(HERE, "results-a.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"skill_name": NAME, "results": score_results},
              open(os.path.join(HERE, "score-input-a.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 回填 Excel
    wb = openpyxl.load_workbook(os.path.join(EVAL, f"{NAME}.xlsx"))
    ws = wb["触发评测用例"]
    hdr = [c.value for c in ws[1]]
    idx = {h: i + 1 for i, h in enumerate(hdr)}
    filled, missing = 0, []
    for row in ws.iter_rows(min_row=2):
        n = row[0].value
        key = str(n)
        if key not in results:
            continue
        for j, r in enumerate(rounds):
            v = results[key]["轮次"][j]["结论"]
            row[idx[f"{r}轮执行结果"] - 1].value = v or ""
            if not v:
                missing.append((n, r))
            else:
                filled += 1
        row[idx["执行日期"] - 1].value = RUN_DATE
    wb.save(os.path.join(EVAL, f"{NAME}.xlsx"))

    json.dump({"filled": filled, "missing": missing, "date": RUN_DATE,
               "verdicts": [{"n": n, "type": t, "rounds": v} for n, t, v in report]},
              open(os.path.join(HERE, "verdicts-a.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"回填 {filled} 格；缺 {len(missing)} 格 {missing[:8]}")
    for n, t, v in report:
        print(f"{n:>4} {t:<6} {'/'.join(v)}")


if __name__ == "__main__":
    import sys
    rs = tuple(int(x) for x in sys.argv[1:]) or (1, 2, 3)
    main(rs)
