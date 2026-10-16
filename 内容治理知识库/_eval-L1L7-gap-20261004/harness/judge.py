#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-l0-feishu **修复版复测** 触发结论回填器（回填员侧）。

与源版 judge.py 判定口径**逐字相同**（口径不因修复而放宽）：
  · 触发判定的客观证据 = 被测会话 session.jsonl 里的 skill 工具调用 / 斜杠注入的
    skill_content（`skill_loaded == True`），不采信被测会话自报。
  · 结论串固定：触发 / 不触发 / 追问（调用题为 加载 / 未加载）。
  · 边界情况：未触发但回复在追问澄清 → 记「追问」，按预期（含「追问」）计 TN。
输出：results-a.json（build-testcases-html 输入）、verdicts-a.json、kb-l0-feishu.xlsx 回填。
"""
import json
import os
import re
from datetime import date

import openpyxl

from jsonl_io import read_records

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
# ── L1–L7 通用化（2026-10-04）：NAME 与用例目录由命令行给，不再硬编码 L0 ──────────
NAME = "kb-l0-feishu"
CASES_DIR = HERE
RUN_DIR = HERE
RUN_DATE = date.today().isoformat()

ASK = re.compile(r"(请问|确认一下|需要你|告诉我|哪一层|哪条链|哪张表|哪批|什么范围|指的是|"
                 r"你是要|你想|要我做|哪一个|说明一下|请补充|补一下)")
QMARK = re.compile(r"[?？]")


def load_round(n, paper="a"):
    recs = {}
    for suffix in ("", "b", "c"):
        for x in read_records(os.path.join(RUN_DIR, f"{paper}-round-{n}{suffix}.jsonl")):
            recs[x["n"]] = x
    return recs


def verdict(meta, rec):
    """判定口径（2026-10-04 限时 120s 版）：
    · 一切「触发/不触发」只取 skill_loaded（客观加载证据）—— 实测加载证据出现在会话开始后
      中位 14s / p95 28s / **最大 79s < 120s**（load-latency.json），故限时 120s 下
      「未加载」是真阴性，不是被限时截断出来的；
    · **例外：边界情况**题的结论要在「不触发 / 追问」间二选一，**必须有回复**——
      回复缺失时记「证据不足」并按口径**排除出四格**（score-trigger-eval 对未知结论返回 None），
      **绝不按「不触发」计**（那会把限时造成的空回复算成漏/真阴，P/R/F1 会假）。
    """
    if rec is None:
        return "", ""
    loaded = bool(rec.get("skill_loaded"))
    reply = rec.get("reply") or ""
    t = meta["type"]
    insuff = (rec.get("evidence") == "insufficient")
    if t == "调用":
        return ("加载" if loaded else "未加载"), reply
    if loaded:
        return "触发", reply
    if t == "边界情况":
        if not reply.strip():
            return "证据不足", reply          # 限时截断 ⇒ 不计入四格，进补跑清单
        if QMARK.search(reply) and ASK.search(reply):
            return "追问", reply
    if insuff and not reply.strip():
        # 非边界题的空回复：**仍以加载证据为准**（见 docstring），但打标记便于复核
        return "不触发", reply
    return "不触发", reply


def main(rounds=(1, 2, 3)):
    meta = json.load(open(os.path.join(CASES_DIR, "cases-meta.json"), encoding="utf-8"))
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

    json.dump(results, open(os.path.join(RUN_DIR, "results-a.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"skill_name": NAME, "results": score_results},
              open(os.path.join(RUN_DIR, "score-input-a.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ── xlsx 回填：**可选**。L1–L7 多数 skill 没有那本 xlsx，缺了就跳过并说明，
    #    绝不让「没这本表」把整条回填线炸掉（fail-visible，不 fail-silent）。
    filled, missing = 0, []
    xlsx = os.path.join(EVAL, f"{NAME}.xlsx")
    if os.path.exists(xlsx):
        wb = openpyxl.load_workbook(xlsx)
        ws = wb["触发评测用例"]
        hdr = [c.value for c in ws[1]]
        idx = {h: i + 1 for i, h in enumerate(hdr)}
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
        wb.save(xlsx)
    else:
        print(f"[skip] 无 xlsx（{xlsx}）⇒ 跳过 Excel 回填，results-a.json 照出")

    json.dump({"filled": filled, "missing": missing, "date": RUN_DATE,
               "verdicts": [{"n": n, "type": t, "rounds": v} for n, t, v in report]},
              open(os.path.join(RUN_DIR, "verdicts-a.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"回填 {filled} 格；缺 {len(missing)} 格 {missing[:8]}")
    for n, t, v in report:
        print(f"{n:>4} {t:<6} {'/'.join(v)}")


def parse_args():
    global NAME, CASES_DIR, RUN_DIR
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("rounds", nargs="*", type=int, default=None)
    ap.add_argument("--skill", default=None, help="被测 skill 名（决定 skill_loaded 判定与 xlsx 名）")
    ap.add_argument("--cases", default=None, help="用例目录（内含 cases-meta.json）")
    ap.add_argument("--run-dir", default=None, help="跑批产物目录（内含 a-round-*.jsonl）；默认当前目录")
    a = ap.parse_args()
    if a.skill:
        NAME = a.skill
    if a.cases:
        CASES_DIR = os.path.abspath(a.cases)
    if a.run_dir:
        RUN_DIR = os.path.abspath(a.run_dir)
    return tuple(a.rounds) if a.rounds else (1, 2, 3)


if __name__ == "__main__":
    main(parse_args())
