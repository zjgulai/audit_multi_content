#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盲测回填器（回填员侧）

输入：
  _eval/run-ledger.json    {agent_id: {"round":1,"case_id":2,"prompt":"…"}}
  _eval/evidence-*.json    session_evidence.py 的产物（逐字回复 + 工具调用）
输出：
  _eval/verdicts.json      每条 × 每轮：结论 + 依据（skill 工具调用 / 命中）
  _eval/results-a.json     build-testcases-html.py 输入（{id: {标题,类型,…,轮次:[{结论,回复}]}}）
  _eval/score-input-a.json score-trigger-eval.py 输入（{"skill_name","results":[…]}
  _eval/results-b.json / score-input-b.json   B 卷（开卷时）
  kb-p0-check.xlsx / kb-p0-check-b-cases.xlsx 回填 1/2/3 轮执行结果 + 执行日期
"""
import argparse
import json
import os
from collections import defaultdict

from openpyxl import load_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
NAME = "kb-p0-check"
TARGET = "kb-p0-check"
TODAY = "2026-09-30"


def load(name, default):
    p = os.path.join(HERE, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


BOUNDARY = load("boundary-adjudication.json", {})


def judge(case, ev):
    """按客观证据判定单轮结论。

    - 正例 / 负例 / 近似命中：触发 ⟺ 该会话真的加载了 kb-p0-check
      （skill 工具调用，或斜杠点名被宿主展开成 <skill_content name="kb-p0-check">）。
    - 调用：加载 / 未加载，主语同样是本 skill。
    - 边界情况：读 boundary-adjudication.json 的逐轮裁定（判据 = 该轮有没有产出
      针对具体内容的 P0 判定；产出=触发，未产出且要求补输入=追问）。
    """
    loaded = bool(ev.get("loaded_target_skill"))
    via = ev.get("loaded_target_via") or ""
    typ = case["type"]
    if typ == "调用":
        return ("加载" if loaded else "未加载",
                f"kb-p0-check {'已加载（' + via + '）' if loaded else '未被加载'}")
    if typ == "边界情况":
        a = (BOUNDARY.get(str(case["id"]), {}) or {}).get(str(ev.get("_round")), {})
        if a:
            return (a["verdict"], a["why"])
        return ("不触发", "未加载 skill，也未追问")
    if loaded:
        return ("触发", f"kb-p0-check 已加载（{via}）")
    return ("不触发", "未加载 kb-p0-check")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="a")
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()
    paper = args.paper.lower()

    cases = load(f"cases-{paper}.json", [])
    ledger = load(os.environ.get("KB_LEDGER", "run-ledger.json"), {})
    by_case = defaultdict(dict)          # case_id -> {round: evidence}
    for aid, meta in ledger.items():
        if meta.get("paper", "a").lower() != paper:
            continue
        ev = (load(f"evidence-{paper}.json", {}) or {}).get(aid)
        if not ev or ev.get("error"):
            continue
        by_case[str(meta["case_id"])][int(meta["round"])] = ev

    verdicts, results, score_rows = {}, {}, []
    for c in cases:
        cid = str(c["id"])
        rounds, concls = [], []
        for r in range(1, args.rounds + 1):
            ev = by_case.get(cid, {}).get(r)
            if ev is not None:
                ev["_round"] = r
            if not ev:
                concl, why, reply = "", "未执行", ""
            else:
                concl, why = judge(c, ev)
                reply = ev.get("reply") or ""
            concls.append(concl)
            rounds.append({"结论": concl, "回复": reply, "_why": why,
                           "_agent": (ev or {}).get("agent_id", ""),
                           "_tools": (ev or {}).get("tools_used", []),
                           "_loaded": bool((ev or {}).get("loaded_target_skill")),
                           "_other_skills": (ev or {}).get("loaded_other_skills", [])})
        verdicts[cid] = {"type": c["type"], "rounds": rounds}
        results[cid] = {"标题": c["title"], "类型": c["type"], "提示词": c["prompt"],
                        "预期结果": c["expected"], "标签": c.get("tags", ""),
                        "优先级": c.get("prio", ""),
                        "轮次": [{"结论": x["结论"], "回复": x["回复"]} for x in rounds]}
        score_rows.append({"id": cid, "type": c["type"], "expected": c["expected"],
                           "tags": c.get("tags", ""), "title": c["title"], "rounds": concls})

    json.dump(verdicts, open(os.path.join(HERE, f"verdicts-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(results, open(os.path.join(HERE, f"results-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"skill_name": NAME, "results": score_rows},
              open(os.path.join(HERE, f"score-input-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 回填 Excel
    xlsx = os.path.join(EVAL, f"{NAME}.xlsx" if paper == "a" else f"{NAME}-b-cases.xlsx")
    wb = load_workbook(xlsx)
    ws = wb["Sheet1"]
    heads = [str(c.value).strip() if c.value else "" for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(heads)}
    done = 0
    for row in ws.iter_rows(min_row=2):
        cid = str(row[col["序号"] - 1].value)
        v = verdicts.get(cid)
        if not v:
            continue
        for i, r in enumerate(v["rounds"], 1):
            cell = ws.cell(row=row[0].row, column=col[f"{i}轮执行结果"])
            cell.value = (r["结论"] + "\n" + r["回复"]) if r["回复"] else r["结论"]
        ws.cell(row=row[0].row, column=col["执行日期"]).value = TODAY
        done += 1
    wb.save(xlsx)

    miss = [c for c in cases if any(not r["结论"] for r in verdicts[str(c["id"])]["rounds"])]
    print(f"[回填] {paper.upper()} 卷：{done} 条已回填；未执行 {len(miss)} 条 "
          f"{[c['id'] for c in miss] if miss else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
