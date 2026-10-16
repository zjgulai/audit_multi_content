#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把盲测轮次结果（rounds/*.jsonl）汇成两用的结果 JSON：

  results-a.json / results-b.json   → build-testcases-html.py（{id: {…轮次:[{结论,回复}]}}）
  scorein-a.json / scorein-b.json   → score-trigger-eval.py（{skill_name, results:[{…rounds:[str]}]}）

判定口径（mechanical，公开可复现）：
  触发   = 该轮被测会话**加载了 kb-recall**（skill 工具调用或 skill 正文注入）
  追问   = 未加载 kb-recall，且最终回复以澄清性追问收尾
  不触发 = 未加载且未追问
  调用类 = 加载 / 未加载（主语是本 skill）
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
ROUNDS = os.path.join(EV, "rounds")
NAME = "kb-recall"

SKILL_FILE_PAT = re.compile(r"\.dsh/skills/kb-recall(/|\b)|kb-recall/(SKILL\.md|references|scripts)")

_cache: dict[str, bool] = {}


def equiv_load(session_path: str) -> bool:
    """等效加载：宿主未展开斜杠时，以「会话真的读了 kb-recall 的正文/参考资料」为准。

    返回 (True/False)；证据 = tool/call 参数里出现 kb-recall 的 SKILL.md / references / scripts 路径。
    """
    if not session_path or not os.path.exists(session_path):
        return False
    if session_path in _cache:
        return _cache[session_path]
    ok = False
    try:
        for e in rs.read_events(session_path):
            if e.get("type") != "tool/call":
                continue
            s = json.dumps(e.get("data") or {}, ensure_ascii=False)
            if SKILL_FILE_PAT.search(s):
                ok = True
                break
    except Exception:  # noqa: BLE001
        ok = False
    _cache[session_path] = ok
    return ok


def verdict(rec: dict | None, typ: str) -> str:
    if rec is None:
        return ""
    if typ == "调用":
        loaded = bool(rec.get("loaded_target_skill")) or equiv_load(rec.get("session_path", ""))
        return "加载" if loaded else "未加载"
    if rec.get("loaded_target_skill"):
        return "触发"
    return "追问" if rec.get("ends_with_question") else "不触发"


def build(paper: str):
    cases = json.load(open(os.path.join(EV, f"cases-{paper}.json"), encoding="utf-8"))
    rounds = {}
    for r in (1, 2, 3):
        p = os.path.join(ROUNDS, f"{paper}-round{r}.jsonl")
        rounds[r] = {}
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                if line.strip():
                    rec = json.loads(line)
                    rounds[r][str(rec["id"])] = rec
    wide, narrow = {}, {}
    missing = []
    for c in cases:
        cid = str(c["id"])
        rt, concl = [], []
        for r in (1, 2, 3):
            rec = rounds[r].get(cid)
            if rec is None:
                missing.append(f"{paper}:{cid}:r{r}")
            v = verdict(rec, c["类型"])
            concl.append(v)
            rt.append({"结论": v, "回复": (rec or {}).get("reply", ""),
                       "session": (rec or {}).get("session_path", ""),
                       "exit": (rec or {}).get("exit_code")})
        wide[cid] = {"标题": c["标题"], "类型": c["类型"], "提示词": c["提示词"],
                     "预期结果": c["预期结果"], "标签": c["标签"], "优先级": c["优先级"],
                     "轮次": rt}
        narrow[cid] = {"id": cid, "title": c["标题"], "type": c["类型"],
                       "expected": c["预期结果"], "tags": c["标签"], "pin": c["优先级"],
                       "rounds": concl}
    json.dump(wide, open(os.path.join(EV, f"results-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"skill_name": NAME, "results": list(narrow.values())},
              open(os.path.join(EV, f"scorein-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return missing


def lenient_stats(paper: str):
    """辅助口径（仅供报告披露，不进门槛）：边界情况若「加载了本 skill 但先追问澄清」，记「追问」而非「触发」。"""
    cases = json.load(open(os.path.join(EV, f"cases-{paper}.json"), encoding="utf-8"))
    per = []
    for r in (1, 2, 3):
        p = os.path.join(ROUNDS, f"{paper}-round{r}.jsonl")
        rows = {}
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                if line.strip():
                    rec = json.loads(line)
                    rows[str(rec["id"])] = rec
        tp = fp = fn = tn = 0
        for c in cases:
            rec = rows.get(str(c["id"]))
            if rec is None or c["类型"] == "调用":
                continue
            loaded = rec.get("loaded_target_skill")
            asks = rec.get("ends_with_question")
            strict = "触发" if loaded else ("追问" if asks else "不触发")
            if c["类型"] == "边界情况" and "追问" in c["预期结果"] and loaded and asks:
                v = "追问"
            else:
                v = strict
            if c["类型"] == "正例":
                tp += v == "触发"; fn += v != "触发"
            else:
                fp += v == "触发"; tn += v != "触发"
        P = tp / (tp + fp) if tp + fp else 0
        R = tp / (tp + fn) if tp + fn else 0
        per.append({"round": r, "TP": tp, "FP": fp, "FN": fn, "TN": tn,
                    "precision": round(P, 3), "recall": round(R, 3),
                    "f1": round(2 * P * R / (P + R), 3) if P + R else 0.0})
    avg = {k: round(sum(x[k] for x in per) / len(per), 3) for k in ("precision", "recall", "f1")} if per else {}
    out = {"paper": paper, "note": "辅助口径：边界情况「加载后先追问」记追问；不进门槛、不替代主口径",
           "per_round": per, "average": avg}
    json.dump(out, open(os.path.join(EV, f"lenient-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="a")
    a = ap.parse_args()
    miss = []
    for p in (["a", "b"] if a.paper == "all" else [a.paper]):
        miss += build(p)
        print(p, lenient_stats(p)["average"])
    print("缺轮次：", miss if miss else "无")
    return 0


if __name__ == "__main__":
    sys.exit(main())
