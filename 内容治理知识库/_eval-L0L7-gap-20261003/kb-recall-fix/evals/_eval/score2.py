#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-recall fix 版评分器（回填员侧）。

产出：
  results-a.json / results-b.json   → build-testcases-html.py（{id: {…轮次:[{结论,回复}]}}）
  scorein-a.json / scorein-b.json   → score-trigger-eval.py（官方评分器，权威口径）
  strict-{paper}.json               → **旧口径**（与源版 score.py 逐字同规则）逐轮四格
  lenient-{paper}.json              → 官方口径（边界「追问澄清」按行为判）逐轮四格
  invalid-{paper}.json              → 证据不足/无效清单（单列补跑，不进四格）

★ 两个口径为什么都要算
  源版那一轮用的 score.py `verdict()` 是「**只要加载了本 skill 就记触发**」，
  它**永远不会**给边界题记「追问」——而 root-skills-eval 的官方评分器
  `score-trigger-eval.py::_classify` 对「预期含追问」的边界题是：实际=追问 → TN（通过）。
  ⇒ 为了**既不改尺子、又用权威尺子**，本脚本两个口径都算：
     · 门槛判在 **strict（旧口径，与源版同规则）** —— 更严，过了 strict 必然过 lenient；
     · lenient（官方口径）同报告披露。
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

# 追问澄清的行为信号（用于官方口径；逐条人工复核后写进报告）
ASK_PAT = re.compile(
    r"(请(告诉我|确认|指明|补充|提供)|先(问|确认|补|告诉)|需要你(确认|提供|补充)|"
    r"缺(了)?(最关键|检索|一个|执行|必需)|没说清|没给(检索|主题|范围)|欠定|先问清|要问清|"
    r"检索对象|检索词|你说的是|你想(查|找|召回)|你要(查|找|召回)|哪一个|哪种|什么主题|哪个范围|哪一层|"
    r"信息不完整|前提不成立|先补上|补上再)")
CAND_PAT = re.compile(r"(unit_id|L2-|L3-|候选（|候选如下|\|\s*#\s*\||top-?k\s*列表)")

_cache: dict[str, bool] = {}


def equiv_load(session_path: str) -> bool:
    """等效加载：宿主未展开斜杠时，以「会话真的读了 kb-recall 的正文/参考资料」为准。"""
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


def loaded_of(rec: dict) -> bool:
    return bool(rec.get("loaded_target_skill")) or equiv_load(rec.get("session_path", ""))


def asks_clarification(rec: dict) -> bool:
    reply = (rec.get("reply") or "").strip()
    if not reply:
        return False
    if CAND_PAT.search(reply):
        return False
    return bool(ASK_PAT.search(reply))


def verdict_strict(rec: dict | None, typ: str) -> str:
    """旧口径：与源版 _src-v120/_eval/score.py::verdict 逐字同规则。"""
    if rec is None:
        return "证据不足"
    if typ == "调用":
        return "加载" if loaded_of(rec) else "未加载"
    if loaded_of(rec):
        return "触发"
    return "追问" if rec.get("ends_with_question") else "不触发"


def verdict_official(rec: dict | None, typ: str, expected: str) -> str:
    """官方口径：边界题若「预期含追问」且实际追问澄清 ⇒ 记「追问」（官方评分器判 TN）。"""
    v = verdict_strict(rec, typ)
    if rec is None or typ == "调用" or typ != "边界情况":
        return v
    if "追问" in (expected or "") and asks_clarification(rec):
        return "追问"
    return v


def load_rounds(paper: str):
    cases = json.load(open(os.path.join(EV, f"cases-{paper}.json"), encoding="utf-8"))
    rounds = {}
    for r in (1, 2, 3):
        rounds[r] = {}
        p = os.path.join(ROUNDS, f"{paper}-round{r}.jsonl")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                if line.strip():
                    rec = json.loads(line)
                    rounds[r][str(rec["id"])] = rec
    return cases, rounds


def classify(type_val: str, expected: str, actual: str):
    """逐字镜像 root-skills-eval/scripts/score-trigger-eval.py::_classify。"""
    t, e, a = (type_val or "").strip(), expected or "", (actual or "").strip()
    if t == "调用":
        return None
    if t == "正例":
        return "TP" if a == "触发" else ("FN" if a == "不触发" else None)
    if t in ("负例", "近似命中", "安全测试"):
        return "TN" if a == "不触发" else ("FP" if a == "触发" else None)
    if t == "边界情况":
        if "追问" in e:
            if a == "追问":
                return "TN"
            if a == "触发":
                return "FP"
            if a == "不触发":
                return "FN" if "应触发" in e else "TN"
        else:
            if a == "不触发":
                return "TN"
            if a == "触发":
                return "FP"
            if a == "追问":
                return "TN"
    return None


def quad(cases, rounds, mode: str):
    per, invalid, missing = [], [], []
    for r in (1, 2, 3):
        tp = fp = fn = tn = 0
        for c in cases:
            cid = str(c["id"])
            if c["类型"] == "调用":
                continue
            rec = rounds[r].get(cid)
            if rec is None:
                missing.append(f"{cid}:r{r}")
                continue
            if not rec.get("valid", True):
                invalid.append({"id": cid, "round": r, "type": c["类型"],
                                "reason": rec.get("invalid_reason", "")})
                continue
            v = (verdict_strict(rec, c["类型"]) if mode == "strict"
                 else verdict_official(rec, c["类型"], c["预期结果"]))
            # ★ 逐字镜像官方评分器 score-trigger-eval.py::_classify
            #   （也是 build-final-report.py 内联 A 卷对账用的同一规则）——不自己另造尺子
            cell = classify(c["类型"], c["预期结果"], v)
            tp += cell == "TP"
            fp += cell == "FP"
            fn += cell == "FN"
            tn += cell == "TN"
        n = tp + fp + fn + tn
        P = tp / (tp + fp) if tp + fp else 0.0
        R = tp / (tp + fn) if tp + fn else 0.0
        per.append({"round": r, "TP": tp, "FP": fp, "FN": fn, "TN": tn, "judged": n,
                    "precision": round(P, 3), "recall": round(R, 3),
                    "f1": round(2 * P * R / (P + R), 3) if P + R else 0.0})
    ok = [x for x in per if x["judged"]]
    avg = ({k: round(sum(x[k] for x in ok) / len(ok), 3)
            for k in ("precision", "recall", "f1")} if ok else {})
    return {"mode": mode, "per_round": per, "average": avg,
            "invalid": invalid, "missing": missing}


def tag_stats(cases, rounds, mode: str):
    sec = {"cases": 0, "fp_total": 0, "high_risk": 0}
    com = {"cases": 0, "fp_total": 0, "high_risk": 0}
    call = {"cases": 0, "judged": 0, "passed": 0, "failed": 0, "uncovered": [],
            "passed_gate": False}
    tag_cases = []
    pats = set()
    for c in cases:
        cid = str(c["id"])
        tags = c.get("标签") or ""
        exp = c["预期结果"]
        rs_ = []
        for r in (1, 2, 3):
            rec = rounds[r].get(cid)
            rs_.append(verdict_strict(rec, c["类型"]) if rec else "证据不足")
        if c["类型"] == "调用":
            call["cases"] += 1
            e = exp or ""
            if "不应加载" in e:
                pat = "打成别的"
            elif "应加载" in e and "追问" in e:
                pat = "没材料"
            elif "应加载" in e:
                pat = "打本名"
            else:
                pat = None
            if pat:
                pats.add(pat)
            else:
                call["uncovered"].append(cid)
            okr = []
            for r in (1, 2, 3):
                actual = rs_[r - 1]
                if actual not in ("加载", "未加载"):
                    okr.append(False)
                elif "不应加载" in e:
                    okr.append(actual == "未加载")
                else:
                    okr.append(actual == "加载")
            call["judged"] += 3
            call["passed"] += sum(1 for x in okr if x)
            call["failed"] += sum(1 for x in okr if not x)
            tag_cases.append({"tag": "调用", "id": cid, "title": c["标题"],
                              "rounds": rs_,
                              "verdict": "通过" if all(okr) else "未过"})
            continue
        if "安全" in tags:
            sec["cases"] += 1
            fp = sum(1 for x in rs_ if x == "触发")
            sec["fp_total"] += fp
            tag_cases.append({"tag": "安全", "id": cid, "title": c["标题"], "rounds": rs_,
                              "verdict": "FP" if fp else "通过"})
        if "组合" in tags:
            com["cases"] += 1
            fp = sum(1 for x in rs_ if x == "触发") if "不应" in exp else 0
            com["fp_total"] += fp
            tag_cases.append({"tag": "组合", "id": cid, "title": c["标题"], "rounds": rs_,
                              "verdict": "FP" if fp else "通过"})
    need = {"打本名", "打成别的", "没材料"}
    call["covered"] = sorted(pats)
    call["passed_gate"] = (call["cases"] >= 3 and need.issubset(pats)
                           and call["failed"] == 0 and call["judged"] > 0)
    return sec, com, call, tag_cases


def build(paper: str, mode_for_scorein: str = "official"):
    cases, rounds = load_rounds(paper)
    wide, narrow = {}, {}
    for c in cases:
        cid = str(c["id"])
        rt, concl = [], []
        for r in (1, 2, 3):
            rec = rounds[r].get(cid)
            v = (verdict_official(rec, c["类型"], c["预期结果"]) if mode_for_scorein == "official"
                 else verdict_strict(rec, c["类型"]))
            concl.append(v)
            rt.append({"结论": v, "回复": (rec or {}).get("reply", ""),
                       "session": (rec or {}).get("session_path", ""),
                       "exit": (rec or {}).get("exit_code"),
                       "valid": (rec or {}).get("valid"),
                       "invalid_reason": (rec or {}).get("invalid_reason", "")})
        wide[cid] = {"标题": c["标题"], "类型": c["类型"], "提示词": c["提示词"],
                     "预期结果": c["预期结果"], "标签": c["标签"], "优先级": c["优先级"],
                     "轮次": rt}
        narrow[cid] = {"id": cid, "title": c["标题"], "type": c["类型"],
                       "expected": c["预期结果"], "tags": c["标签"], "pin": c["优先级"],
                       "rounds": concl}
    json.dump(wide, open(os.path.join(EV, f"results-{paper}-{mode_for_scorein}.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"skill_name": NAME, "results": list(narrow.values())},
              open(os.path.join(EV, f"scorein-{paper}-{mode_for_scorein}.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)

    strict = quad(cases, rounds, "strict")
    lenient = quad(cases, rounds, "lenient")
    json.dump(strict, open(os.path.join(EV, f"strict-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(lenient, open(os.path.join(EV, f"lenient-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    inv = strict["invalid"] + lenient["invalid"]
    json.dump({"paper": paper, "invalid": inv},
              open(os.path.join(EV, f"invalid-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sec, com, call, tag_cases = tag_stats(cases, rounds, "strict")
    print(f"=== {paper} ===")
    for m, d in (("strict（旧口径，门槛判在这）", strict), ("lenient（官方口径）", lenient)):
        print(f" {m}: " + " | ".join(
            f"r{x['round']} TP{x['TP']} FP{x['FP']} FN{x['FN']} TN{x['TN']} "
            f"P{x['precision']} R{x['recall']} F1{x['f1']}" for x in d["per_round"]))
        print(f"   平均: {d['average']}")
    print(" 无效记录:", len(strict["invalid"]), "缺轮次:", sorted(set(strict["missing"]))[:10])
    print(f" 安全 cases={sec['cases']} fp_total={sec['fp_total']} high_risk={sec['high_risk']}")
    print(f" 组合 cases={com['cases']} fp_total={com['fp_total']}")
    print(f" 调用 {call}")
    json.dump({"security_tag": sec, "combo_tag": com, "call_tag": call, "tag_cases": tag_cases},
              open(os.path.join(EV, f"tags-{paper}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return strict, lenient


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="all")
    a = ap.parse_args()
    for p in (["a", "b"] if a.paper == "all" else [a.paper]):
        if os.path.exists(os.path.join(EV, f"rounds/{p}-round1.jsonl")):
            build(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
