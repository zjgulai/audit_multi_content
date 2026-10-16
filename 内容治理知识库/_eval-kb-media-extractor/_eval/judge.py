#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kb-media-extractor 触发结论回填器（回填员侧）

从 _eval/{a,b}-round-*.jsonl 逐条产出结论：
  正例             → 触发 / 不触发
  负例 / 近似命中  → 触发 / 不触发
  边界情况         → 触发 / 追问 / 不触发
  调用             → 加载 / 未加载
并产出 build-testcases-html.py 用的 results.json（逐条 + 每轮 AI 原文）
与 score-trigger-eval.py 用的 score-input.json。

用法： /usr/bin/python3 judge.py
"""
import json
import os
import re
import glob
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)

ASK = re.compile(
    r"(需要你(补充|提供|确认|给)|请(补充|提供|确认|告诉)|先(确认|补|问)|"
    r"是哪(批|一个|条|张)|哪批|哪个批次|麻烦(你)?(确认|提供|补充)|"
    r"能(不能)?(先)?告诉我|你(能)?给我|还差|缺少(材料|输入)|需要确认|"
    r"确认一下|可以(先)?告诉我|方便(先)?说|材料在哪|落(到)?哪一层)")


def load_expect():
    exp = {}
    for path, is_b in ((os.path.join(EVAL, "kb-media-extractor.xlsx"), False),
                       (os.path.join(EVAL, "kb-media-extractor-b-cases.xlsx"), True)):
        ws = openpyxl.load_workbook(path)["触发评测用例"]
        hdr = [c.value for c in ws[1]]
        for r in ws.iter_rows(min_row=2, values_only=True):
            if r[0] is None:
                continue
            d = dict(zip(hdr, r))
            key = str(d["序号"])
            exp[key] = d
    return exp


def conclude(typ, oracle, reply):
    trig = bool(oracle.get("triggered_hint"))
    if typ == "调用":
        return "加载" if trig else "未加载"
    if typ == "边界情况":
        if trig:
            return "触发"
        return "追问" if ASK.search(reply) else "不触发"
    if typ == "正例":
        return "触发" if trig else "不触发"
    return "触发" if trig else "不触发"


MANUAL = json.load(open(os.path.join(HERE, "manual-verdicts.json"), encoding="utf-8"))
MANUAL_FIX = json.load(open(os.path.join(HERE, "manual-verdicts-fix.json"), encoding="utf-8"))


def main():
    exp = load_expect()
    by_key = {}
    for fp in sorted(glob.glob(os.path.join(HERE, "a-round-*.jsonl")) +
                     glob.glob(os.path.join(HERE, "b-round-*.jsonl"))):
        tag = os.path.basename(fp).replace(".jsonl", "")
        paper = "b" if tag.startswith("b-") else "a"
        rnd = int(tag.rsplit("-", 1)[1])
        for line in open(fp, encoding="utf-8"):
            if not line.strip():
                continue
            rec = json.loads(line)
            key = f"B{rec['n']}" if paper == "b" else str(rec["n"])
            e = exp[key]
            m = (MANUAL_FIX if rnd >= 4 else MANUAL).get(key)
            if m:
                concl = m["rounds"][rnd - 4 if rnd >= 4 else rnd - 1]
                why = m["why"]
            else:
                concl = conclude(e["类型"], rec.get("oracle", {}), rec["reply"] or "")
                why = "自动粗筛（未定案）"
            d = by_key.setdefault(key, {
                "key": key, "n": rec["n"], "paper": paper,
                "标题": e["标题"], "类型": e["类型"], "提示词": e["提示词"],
                "预期结果": e["预期结果"], "标签": e["标签"] or "", "优先级": e["优先级"],
                "rounds": {},
            })
            d["rounds"][rnd] = {
                "结论": concl, "why": why, "回复": rec["reply"] or "",
                "oracle": rec.get("oracle", {}), "elapsed_s": rec.get("elapsed_s"),
                "exit_code": rec.get("exit_code"),
            }
    # 顺序：A 卷 1..53，B 卷 B1..B10
    keys = sorted(by_key, key=lambda k: (k.startswith("B"), by_key[k]["n"]))
    results_html = {}
    score_rows = []
    missing = []
    for k in keys:
        d = by_key[k]
        rounds = []
        for r in (1, 2, 3):
            if r in d["rounds"]:
                rounds.append({"结论": d["rounds"][r]["结论"], "回复": d["rounds"][r]["回复"]})
            else:
                rounds.append({"结论": "", "回复": ""})
                missing.append((k, r))
        results_html[d["key"]] = {
            "标题": d["标题"], "类型": d["类型"], "提示词": d["提示词"],
            "预期结果": d["预期结果"], "标签": d["标签"], "优先级": d["优先级"],
            "轮次": rounds,
        }
        score_rows.append({
            "id": d["key"], "type": d["类型"], "expected": d["预期结果"],
            "tags": d["标签"], "title": d["标题"],
            "rounds": [x["结论"] for x in rounds],
        })
    with open(os.path.join(HERE, "results-all.json"), "w", encoding="utf-8") as f:
        json.dump(results_html, f, ensure_ascii=False, indent=1)
    a_rows = [r for r in score_rows if not str(r["id"]).startswith("B")]
    b_rows = [r for r in score_rows if str(r["id"]).startswith("B")]
    with open(os.path.join(HERE, "score-input-a.json"), "w", encoding="utf-8") as f:
        json.dump({"skill_name": "kb-media-extractor", "results": a_rows}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(HERE, "score-input-b.json"), "w", encoding="utf-8") as f:
        json.dump({"skill_name": "kb-media-extractor", "results": b_rows}, f, ensure_ascii=False, indent=1)
    print(f"[ok] A 卷 {len(a_rows)} 条 → score-input-a.json；B 卷 {len(b_rows)} 条 → score-input-b.json")
    if missing:
        print(f"[warn] 缺轮次 {len(missing)} 处：{missing[:12]}{' …' if len(missing) > 12 else ''}")
    else:
        print("[ok] 三条轮次齐全，无缺漏")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
