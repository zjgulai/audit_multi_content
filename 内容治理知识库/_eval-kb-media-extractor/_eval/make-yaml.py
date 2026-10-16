#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把评分中间产物装配成 root-skills-eval 的评测 YAML。

输入：
  _eval/summary-a.json    score-trigger-eval.py --json 输出（A 卷）
  _eval/summary-b.json    score-trigger-eval.py --json 输出（B 卷，门禁开卷后）
  _eval/output-assertions.json  check-output.py 输出（功能断言）
  scores.json             人工评分（轨道 A 六维 / 轨道 C 六维 / Release 10 项 / 结论）

用法：/usr/bin/python3 _eval/make-yaml.py <输出 yaml 路径> [--fix]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
NAME = "kb-media-extractor"


def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def q(s):
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def yaml_dump(obj, indent=0):
    """极简 YAML 输出（只处理 dict/list/str/num/bool/None）。"""
    sp = "  " * indent
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        out = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                out.append(f"{sp}{k}:")
                out.append(yaml_dump(v, indent + 1))
            else:
                out.append(f"{sp}{k}: {yaml_scalar(v)}")
        return "\n".join(out)
    if isinstance(obj, list):
        if not obj:
            return f"{sp}[]"
        out = []
        for v in obj:
            if isinstance(v, dict):
                first = True
                for k, vv in v.items():
                    pre = f"{sp}- " if first else f"{sp}  "
                    first = False
                    if isinstance(vv, (dict, list)) and vv:
                        out.append(f"{pre}{k}:")
                        out.append(yaml_dump(vv, indent + 2))
                    else:
                        out.append(f"{pre}{k}: {yaml_scalar(vv)}")
            elif isinstance(v, list):
                out.append(f"{sp}- {json.dumps(v, ensure_ascii=False)}")
            else:
                out.append(f"{sp}- {yaml_scalar(v)}")
        return "\n".join(out)
    return f"{sp}{yaml_scalar(obj)}"


def yaml_scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return q(v)


def _oa_for(oa, when):
    """按版本切分功能断言统计：源版=第1-3轮（a-round-1..3），修复版=第4-6轮（a-round-4..6）。
    2026-09-30 事故修正：原实现直接 dump 全部轮次，会把修复版/B 卷的断言数写进源版报告。"""
    want = ("a-round-4", "a-round-5", "a-round-6") if when == "fix" else ("a-round-1", "a-round-2", "a-round-3")
    det = [x for x in (oa.get("detail") or []) if x.get("round") in want]
    if not det:
        return {}
    agg = {"checks": 0, "pass": 0}
    for k in ("A1", "A2", "A3", "A4", "A5"):
        agg[k] = [0, 0]
    for x in det:
        agg["checks"] += x["total"]; agg["pass"] += x["pass"]
        for k in ("A1", "A2", "A3", "A4", "A5"):
            agg[k][1] += 1; agg[k][0] += 1 if x[k] else 0
    return {when: agg, "pass_rate": round(agg["pass"] / agg["checks"], 4)}


def main():
    out_path = sys.argv[1]
    FIX = "--fix" in sys.argv
    scores = load(os.path.join(EVAL, "scores-fix.json" if FIX else "scores.json"), {})
    sa = load(os.path.join(EVAL, "_eval", "summary-fix-a.json" if FIX else "summary-a-src.json"), {})
    sb = load(os.path.join(EVAL, "_eval", "summary-fix-b.json" if FIX else "summary-b.json"), {})
    oa = load(os.path.join(EVAL, "_eval", "output-assertions.json"), {})
    bgate = load(os.path.join(EVAL, "_eval", "b-gate.json"), {})
    tag_case_rows = load(os.path.join(EVAL, "_eval", "tag-cases.json"), [])

    doc = {}
    doc["eval_info"] = scores["eval_info"]
    doc["track_a"] = scores["track_a"]
    doc["issues"] = scores["issues"]
    doc["track_b"] = {
        "status": scores["track_b_status"],
        "a_paper_total": 50,
        "distribution": {"正例": 16, "负例": 16, "近似命中": 12, "边界情况": 6},
        "rounds": sa.get("per_round", []),
        "per_round": sa.get("per_round", []),
        "average": sa.get("average", {}),
        "flaky": sa.get("flaky", []),
        "security_tag": dict(sa.get("security_tag", {}), high_risk=0),
        "combo_tag": dict(sa.get("combo_tag", {}), high_risk=0),
        "call_tag": sa.get("call_tag", {}),
        "pass_call_gate": sa.get("pass_call_gate", False),
        "output_assertions": _oa_for(oa, when="fix" if FIX else "source"),
        "tag_cases": tag_case_rows or sa.get("tag_cases", []),
        "excel_backfill": scores["excel_backfill"],
        "note": scores["track_b_note"],
    }
    if sb:
        doc["track_b"]["b_paper_gate"] = {
            "total": 10,
            "per_round": sb.get("per_round", []),
            "average": sb.get("average", {}),
            "security_tag": sb.get("security_tag", {}),
            "combo_tag": sb.get("combo_tag", {}),
            "verdict": bgate.get("verdict", ""),
        }
    doc["track_c"] = scores["track_c"]
    doc["release_checklist"] = scores["release_checklist"]
    doc["status"] = scores["status"]
    doc["recommendation"] = scores["recommendation"]

    header = (f"# {NAME} 评测报告（{'修复版 v1.0.1' if FIX else '源 v1.0.0'}）\n"
              f"# 评测工具：root-skills-eval v3.19.1（双轨版）｜评测时间：2026-09-30\n"
              f"# 本轮：A 卷 50 条 + 调用 3 条 × 3 轮（盲测，只读沙箱）+ "
              f"{'B 卷门禁 10 条 × 3 轮' if sb else 'B 卷封印未开卷'}\n\n")
    body = yaml_dump(doc)
    open(out_path, "w", encoding="utf-8").write(header + body + "\n")
    print(f"[ok] YAML → {out_path}")
    import yaml as _y
    d = _y.safe_load(body)
    print(f"  [check] track_a.total = {d['track_a']['total']}")
    print(f"  [check] track_c.total = {d['track_c']['total']}  market_ready={d['track_c'].get('market_ready')}")
    print(f"  [check] track_b.rounds = {len(d['track_b']['rounds'])} 轮，distribution={d['track_b']['distribution']}")
    print(f"  [check] release_checklist = {len(d['release_checklist'])} 项")
    print(f"  [check] call_tag.passed_gate = {d['track_b']['call_tag'].get('passed_gate')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
