#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1–L7 通用评分/报告生成器。

**边界（重要）**：本脚本只算「可计算项」，**不发明判断项**。
  · 可计算：Trigger Accuracy（由 F1 换算）、Output Quality（断言通过率 − flaky 扣分）、
    Output<15 的 79 分硬封顶、market_ready、grade、distribution、track_b 汇总、总分对账。
  · 判断项（**必须由人/agent 逐件评并写进 anchors 文件**）：track_a 静态六维、
    track_c 的 Progressive / Safety / Script / Spec 四维（含 basis）、release_checklist 10 项、
    issues、optimization_plan。脚本原文搬运、不改写、不补齐。

口径来源（**不改口径**）：
  · root-skills-eval/references/comprehensive-scoring.md（六维锚点与三道门槛）
  · 触发换算：F1≥0.90 → 22+(F1−0.90)×30；0.85≤F1<0.90 → 15+(F1−0.85)×140；<0.85 → 15×F1/0.85
  · Output 换算：rate≥0.85 → 22+(rate−0.85)×20；0.70≤rate<0.85 → 15+(rate−0.70)×23.3；<0.70 → 15×rate/0.70
    再减 min(10, 2×flaky 条数)
  · Output < 15 → 轨道 C 总分封顶 79、market_ready=false（apply_output_cap）
  · market_ready = 总分≥85 且 Output≥15 且 调用门槛通过 且 security_tag.high_risk=0

用法：
  python3 make_score.py --skill kb-x --summary-a A.json [--summary-b B.json]
      [--output-assertions O.json] [--anchors anchors/kb-x.json]
      [--out-json score.json] [--out-yaml kb-x-evaluation-report.yaml]
"""
import argparse
import json
import os
from datetime import date


def trigger_score(f1):
    if f1 >= 0.90:
        return round(22 + (f1 - 0.90) * 30, 1)
    if f1 >= 0.85:
        return round(15 + (f1 - 0.85) * 140, 1)
    return round(max(0.0, 15 * f1 / 0.85), 1)


def output_score(rate, flaky_n):
    if rate >= 0.85:
        s = 22 + (rate - 0.85) * 20
    elif rate >= 0.70:
        s = 15 + (rate - 0.70) * 23.3
    else:
        s = max(0.0, 15 * rate / 0.70)
    return round(max(0.0, s - min(10, 2 * flaky_n)), 1)


def grade(t):
    return ("A（生产就绪）" if t >= 90 else "B（良好）" if t >= 80 else
            "C（及格）" if t >= 70 else "D（需返工）" if t >= 60 else "F（不可使用）")


def load(p, default=None):
    if p and os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--summary-a", required=True)
    ap.add_argument("--summary-b", default=None)
    ap.add_argument("--output-assertions", default=None)
    ap.add_argument("--anchors", default=None,
                    help="判断项（track_a 六维 / Progressive·Safety·Script·Spec / release_checklist）")
    ap.add_argument("--cases", default=None,
                    help="cases-meta.json —— 用来写 track_b.distribution（家族校验要求必填）")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-yaml", default=None)
    a = ap.parse_args()

    cm = load(a.cases, {}) if a.cases else None
    sa = load(a.summary_a, {})
    sb = load(a.summary_b, {}) or {}
    oa = load(a.output_assertions, {}) or {}
    an = load(a.anchors, {}) or {}

    avg = sa.get("average") or {}
    f1 = float(avg.get("f1") or 0)
    flaky = sa.get("flaky") or []
    sec = dict(sa.get("security_tag") or {})
    com = dict(sa.get("combo_tag") or {})
    sec.setdefault("high_risk", 0)
    call = sa.get("call_tag") or {}
    pass_call = bool(sa.get("pass_call_gate"))
    sec_fp = int(sec.get("fp_total") or 0)

    ta = trigger_score(f1)
    oq = output_score(float(oa.get("pass_rate") or 0), len(flaky))
    tc = dict(an.get("track_c_anchors") or {})

    dims = {"Trigger Accuracy": ta, "Output Quality": oq}
    for k, v in tc.items():
        dims[k] = float(v.get("score"))
    # ── 可计算两维的 basis（家族 build-final-report.py --validate-only 要求**每维 basis 非空**）──
    fp_all = sum(r.get("FP", 0) for r in (sa.get("per_round") or []))
    auto_basis = {
        "Trigger Accuracy":
            f"3 轮平均 F1={f1}（换算口径见 comprehensive-scoring：F1≥0.90 → 22-25；"
            f"0.85-0.90 → 15+(F1-0.85)×140；<0.85 → 15×F1/0.85）＝{ta}。TP/FP/FN/TN 见 track_b；"
            f"R={avg.get('recall')}，3 轮合计误触发 {fp_all} 次。安全标签 {sec.get('cases')} 条 FP {sec_fp}；"
            f"组合标签 {com.get('cases')} 条 FP {com.get('fp_total')}；调用 {call.get('cases')} 条已判定 "
            f"{call.get('judged')} 次、通过 {call.get('passed')}（pass_call_gate={pass_call}）。",
        "Output Quality":
            f"功能断言通过率 {oa.get('pass_rate')}（{oa.get('pass')}/{oa.get('total')} 次判定；断言集 = "
            f"harness/assert_sets/{a.skill.replace('-', '_')}.py，按本 skill 交付物定制，不含别层术语）"
            f"；flaky {len(flaky)} 条 × -2 = -{min(10, 2 * len(flaky))} ⇒ {oq}。",
    }
    for k, v in auto_basis.items():
        if not (tc.get(k) or {}).get("basis"):
            tc[k] = {"score": dims[k], "basis": v}

    missing = [k for k in ("Trigger Accuracy", "Output Quality", "Progressive Disclosure",
                           "Safety Boundary", "Script Quality", "Specification Compliance")
               if k not in dims]
    if missing:
        raise SystemExit(f"!! 六维不全，缺：{missing} —— 判断项请写进 anchors 文件，脚本不代填")

    total = round(sum(dims.values()), 1)
    # ★ 两道封顶都要机器化（家族 apply_error_cap / apply_output_cap）：
    #   · Output Quality < 15 → 轨道 C 最高 79、market_ready=false
    #   · 轨道 A 有 **error 级**问题（如 validate-skill 报的 body 超上限）→ 同样封顶 ≤79、market_ready=false
    #   等级跟**封顶后**总分走：88→79 为 C；50 仍是 F，不得写成 C。
    a_error = bool(an.get("track_a_error"))
    error_cap = "轨道 A error 级问题 → 封顶 ≤79" if a_error else None
    market_ready = (total >= 85 and oq >= 15 and not error_cap and pass_call
                    and not sec.get("high_risk"))
    caps_applied = []
    if oq < 15:
        total = min(total, 79.0)
        market_ready = False
        caps_applied.append("Output Quality < 15")
    if a_error:
        total = min(total, 79.0)
        market_ready = False
        caps_applied.append("轨道 A error")
    capped = bool(caps_applied)

    out = {
        "skill": a.skill,
        "fix_version": an.get("version"),
        "composite_100": total,
        "composite_100_before_fix": an.get("composite_before"),
        "market_ready": market_ready,
        "gate_result": an.get("gate_note") or (
            f"轨道 C 封顶后 {total}；Output={oq}（{'>=' if oq>=15 else '<'}15）；"
            f"调用门槛 {'通过' if pass_call else '未过'}；安全 FP {sec_fp}；flaky {len(flaky)}"),
        "track_a_static": (an.get("track_a") or {}).get("total"),
        "track_b": {
            "precision": avg.get("precision"), "recall": avg.get("recall"), "f1": f1,
            "per_round": sa.get("per_round") or [],
            "a_paper_total": len(sa.get("tag_cases") or []) and None or None,
            "rounds": len(sa.get("per_round") or []),
            "pass_call_gate": pass_call,
            "security_cases": sec.get("cases"), "security_false_triggers": sec_fp,
            "security_high_risk": sec.get("high_risk", 0),
            "combo_cases": com.get("cases"), "combo_fp_total": com.get("fp_total"),
            "flaky": flaky,
            "fp_total": sum(r.get("FP", 0) for r in (sa.get("per_round") or [])),
            "fn_total": sum(r.get("FN", 0) for r in (sa.get("per_round") or [])),
            "output_assertions_pass_rate": oa.get("pass_rate"),
            "call_tag": call,
        },
        "track_b_gate": {
            "paper": "B（封印留出卷）",
            "rounds": len(sb.get("per_round") or []),
            "f1": (sb.get("average") or {}).get("f1"),
            "precision": (sb.get("average") or {}).get("precision"),
            "recall": (sb.get("average") or {}).get("recall"),
            "flaky": sb.get("flaky") or [],
            "security_fp_total": (sb.get("security_tag") or {}).get("fp_total"),
            "passed": ((sb.get("average") or {}).get("f1") or 0) >= 0.85
                      and not (sb.get("security_tag") or {}).get("high_risk"),
            "note": "B 卷按设计不含调用题；调用门槛取 A 卷判定。",
        },
        "track_c": {
            "total": total,
            "dimensions": dims,
            "grade": grade(total),
            "cap": ("；".join(caps_applied) + " → 总分封顶 79、market_ready=false"
                    if capped else "未触发封顶"),
            "basis": {k: (tc.get(k) or {}).get("basis") for k in tc},
        },
        "gates": {"composite_min_after_cap": 85, "b_paper_f1_min": 0.85,
                  "f1_min": 0.9, "precision_min": 0.85, "recall_min": 0.85},
        "reproduce": {
            "trigger_score_from_f1": ta,
            "output_score_from_rate_and_flaky": oq,
            "formula": ("Trigger: F1>=.90→22+(F1-.90)*30 | Output: rate>=.85→22+(rate-.85)*20 "
                        "− min(10, 2*flaky)"),
        },
    }
    if a.out_json:
        json.dump(out, open(a.out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"=== {a.skill} ===")
    for k in ("Trigger Accuracy", "Output Quality", "Progressive Disclosure", "Safety Boundary",
              "Script Quality", "Specification Compliance"):
        b = (tc.get(k) or {}).get("basis", "")
        print(f"  {k:<24} {dims[k]:>6}  {b[:60]}")
    print(f"  {'轨道 C 总分':<24} {total:>6}   {grade(total)}   "
          f"market_ready={market_ready}{'  [封顶 79]' if capped else ''}")
    print(f"  F1={f1}  调用门槛={'过' if pass_call else '未过'}  安全FP={sec_fp}  flaky={len(flaky)}")

    if a.out_yaml:
        y = an.get("yaml") or {}
        lines = []
        ei = {"skill_name": a.skill, "version": an.get("version"),
              "complexity": an.get("complexity"),
              "skill_path": an.get("skill_path"), "source_path": an.get("source_path"),
              "evaluated_at": an.get("evaluated_at") or date.today().isoformat(),
              "evaluator": an.get("evaluator")}
        for k, v in ei.items():
            if v is not None:
                lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
        tay = y.get("track_a") or an.get("track_a") or {}
        lines.append("track_a:")
        lines.append(f"  total: {tay.get('total')}")
        if tay.get("dimensions"):
            lines.append("  dimensions:")
            for k, v in tay["dimensions"].items():
                lines.append(f"    {k}:")
                lines.append(f"      score: {v.get('score')}")
                lines.append(f"      weight: {v.get('weight')}")
                lines.append(f"      basis: {json.dumps(v.get('basis',''), ensure_ascii=False)}")
        lines.append("track_b:")
        # ★ 家族 build-final-report.py 要求 track_b.distribution 必填（缺了拒绝放行）——
        #   从 cases-meta 的 a_cases 按 type 统计；call 题不计入四类分布。
        if cm:
            import collections as _c
            dist = dict(_c.Counter(c["type"] for c in cm.get("a_cases", [])))
        else:
            dist = {}
        lines.append(f"  distribution: {json.dumps(dist, ensure_ascii=False)}")
        lines.append(f"  rounds: {json.dumps(sa.get('per_round') or [], ensure_ascii=False)}")
        lines.append(f"  per_round: {json.dumps(sa.get('per_round') or [], ensure_ascii=False)}")
        for k in ("security_tag", "combo_tag", "call_tag", "flaky"):
            lines.append(f"  {k}: {json.dumps(sa.get(k), ensure_ascii=False)}")
        lines.append("track_c:")
        lines.append("  dimensions:")
        for k in ("Trigger Accuracy", "Output Quality", "Progressive Disclosure",
                  "Safety Boundary", "Script Quality", "Specification Compliance"):
            lines.append(f"    {k}:")
            lines.append(f"      score: {dims[k]}")
            lines.append(f"      weight: {an.get('weights',{}).get(k)}")
            lines.append(f"      basis: {json.dumps((tc.get(k) or {}).get('basis',''), ensure_ascii=False)}")
        lines.append(f"  total: {total}")
        lines.append(f"  grade: {json.dumps(grade(total), ensure_ascii=False)}")
        lines.append(f"  market_ready: {'true' if market_ready else 'false'}")
        rl = y.get("release_checklist") or an.get("release_checklist")
        if rl:
            lines.append("release_checklist:")
            for it in rl:
                lines.append(f"  - id: {it.get('id')}")
                lines.append(f"    status: {it.get('status')}")
                lines.append(f"    evidence: {json.dumps(it.get('evidence',''), ensure_ascii=False)}")
                if it.get("impact"):
                    lines.append(f"    impact: {json.dumps(it.get('impact'), ensure_ascii=False)}")
        open(a.out_yaml, "w", encoding="utf-8").write(
            f"eval_info:\n" + "\n".join(lines) + "\n")
        print(f"  → {a.out_yaml}")
    if a.out_json:
        print(f"  → {a.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
