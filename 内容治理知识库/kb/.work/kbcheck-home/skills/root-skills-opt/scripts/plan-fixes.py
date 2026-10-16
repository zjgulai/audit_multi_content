#!/usr/bin/env python3
"""
plan-fixes.py - 从 root-skills-eval 评估报告生成修复计划

读取 YAML 评估报告（issues + optimization_plan + release_checklist），输出按优先级排序的
修复计划清单（stdout 文本或 JSON），供 root-skills-opt 执行修复前预览。

借鉴 microsoft/SkillOpt 训练纪律的扩展参数：
    --budget N            编辑预算：每轮最多输出 N 条修复（默认 0=不限）
    --rejected-edits PATH 拒绝编辑缓冲：排除已验证无效的修复（.opt-state/rejected-edits.yaml）
    --training-log PATH   跨轮元记忆：有效修复类型提前、无效类型延后（.opt-state/training-log.yaml）

用法:
    python3 scripts/plan-fixes.py path/to/evaluation-report.yaml
    python3 scripts/plan-fixes.py path/to/report.yaml --format json
    python3 scripts/plan-fixes.py path/to/report.yaml --min-severity warning
    python3 scripts/plan-fixes.py path/to/report.yaml --budget 5 \\
        --rejected-edits ../{skill}-fix/.opt-state/rejected-edits.yaml \\
        --training-log ../{skill}-fix/.opt-state/training-log.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}
PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}

# 与 eval v3.16.0 三道门槛对齐：达标只看封顶后轨道 C，不得把 YAML 原文总分当成已达标。
REPAIR_ENTER = 85
OUTPUT_QUALITY_PASS = 15
TRACK_C_OUTPUT_CAP = 79
MARKET_READY_MIN = 80

# Release 清单：可改 SKILL.md 的 fail → 进修复批次；1/3/9 只复判，不编造 RED/评测文件。
RELEASE_SKILL_FIX = {
    2: ("warning", "description",
        "补齐何时不用/相邻不触发场景", "content_quality"),
    4: ("warning", "description",
        "首句改为触发时机（当用户…时使用），触发词前置", "description_optimization"),
    5: ("warning", "description",
        "description 改为用户会说的意图/触发词，而非功能列表", "description_optimization"),
    6: ("warning", "body",
        "删通用背景，只留行为规则/gotcha/读取条件", "content_quality"),
    7: ("warning", "body",
        "正文写明 references/assets/scripts 的读取条件；无 runtime 则不要改",
        "progressive_disclosure"),
    8: ("warning", "body",
        "补安全边界：注入/密钥/危险命令/越权整体拒绝", "safety"),
    10: ("warning", "body",
        "补维护与退役：gotcha 优先、递增 version、更新 last_updated、写明停用条件"
        "（description 注明停用并保留目录；不要写 manage 家族注册表）",
        "lifecycle"),
}
RELEASE_REJUDGE = {
    1: ("warning", "release_checklist",
        "按 release-checklist「评测已有 Skill」复判第 1 项；本轮触发门槛已过则 pass；"
        "禁止用「通用能力」打发，禁止为过本项删 Skill",
        "release_rejudge"),
    3: ("warning", "release_checklist",
        "第 3 项只判 Iron Law RED。本轮 A/B 卷属于第 9 项。"
        "评已有 Skill 缺历史 RED 时保持 fail+不影响上线；禁止补造 without-skill 基线文件",
        "release_rejudge"),
    9: ("warning", "release_checklist",
        "本轮 A 卷已有正例/负例/近似/边界且已执行则第 9 项必须 pass；"
        "禁止因 tests/ 未在正文声明而 fail；禁止新造评测文件凑数",
        "release_rejudge"),
}
FOUR_TYPE_KEYS = ("正例", "负例", "近似命中", "边界情况")


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, dict):
        for k in ("score", "value", "total"):
            if k in v:
                return _num(v[k])
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _output_quality(tc: dict):
    if not isinstance(tc, dict):
        return None
    dims = tc.get("dimensions") if isinstance(tc.get("dimensions"), dict) else {}
    for key in ("output_quality", "output", "Output Quality"):
        if key in dims:
            n = _num(dims[key])
            if n is not None:
                return n
    return _num(tc.get("output_quality"))


def _call_gate_ok(report: dict) -> bool:
    """调用门槛。缺 call_tag / pass_call_gate = 旧 YAML，不挡修复退出。

    新报告里 passed_gate=false 或三种斜杠路径未齐 → 不可发布、不能退出修复。
    """
    tb = report.get("track_b") if isinstance(report, dict) else None
    if not isinstance(tb, dict):
        return True
    has_gate = "pass_call_gate" in tb
    ct = tb.get("call_tag")
    if ct is None and not has_gate:
        return True
    if tb.get("pass_call_gate") is False:
        return False
    if not isinstance(ct, dict):
        return not has_gate
    if int(ct.get("cases") or 0) < 3:
        return False
    if ct.get("uncovered"):
        return False
    if "passed_gate" in ct:
        return bool(ct.get("passed_gate"))
    return int(ct.get("failed") or 0) == 0 and int(ct.get("judged") or 0) > 0


def effective_track_c(report: dict) -> dict:
    """封顶后的轨道 C。YAML 88 + Output 12 → 有效 79，未达修复退出线 85。

    达标条件：封顶后总分 ≥ 85 且 Output ≥ 15 且无 error；若 YAML 含调用门槛则必须通过。
    Output 缺失不得视为及格，因此不能退出修复。旧 YAML 无 call_tag 不挡。
    """
    tc = report.get("track_c") if isinstance(report.get("track_c"), dict) else {}
    raw = _num(tc.get("total_before_cap"))
    displayed = _num(tc.get("total"))
    if raw is None:
        raw = displayed
    if raw is None:
        raw = _num((report.get("scores") or {}).get("total"))
    out = _output_quality(tc)
    issues = report.get("issues") or []
    has_error = any(
        isinstance(i, dict) and str(i.get("severity", "")).lower() == "error"
        for i in issues
    )

    total = raw
    notes: list[str] = []
    if total is not None:
        if out is not None and out < OUTPUT_QUALITY_PASS and total > TRACK_C_OUTPUT_CAP:
            notes.append(
                f"Output Quality {out}/25 < {OUTPUT_QUALITY_PASS} → {total} 封顶为 {TRACK_C_OUTPUT_CAP}"
            )
            total = float(TRACK_C_OUTPUT_CAP)
        elif out is not None and out < OUTPUT_QUALITY_PASS:
            notes.append(
                f"Output Quality {out}/25 < {OUTPUT_QUALITY_PASS} → market_ready=false（不抬分）"
            )
        if has_error and total > TRACK_C_OUTPUT_CAP:
            notes.append(f"存在 error 级静态问题 → {total} 封顶为 {TRACK_C_OUTPUT_CAP}")
            total = float(TRACK_C_OUTPUT_CAP)
        elif has_error:
            notes.append("存在 error 级静态问题 → market_ready=false")

    output_ok = out is not None and out >= OUTPUT_QUALITY_PASS
    call_ok = _call_gate_ok(report)
    if not call_ok:
        notes.append("调用门槛未过 → market_ready=false，不能退出修复（不能调用就不能上线）")
    market_ready = (
        total is not None
        and total >= MARKET_READY_MIN
        and output_ok
        and not has_error
        and call_ok
    )
    meets_repair_exit = (
        total is not None
        and total >= REPAIR_ENTER
        and output_ok
        and not has_error
        and call_ok
    )
    return {
        "total": total,
        "total_before_cap": raw,
        "output_quality": out,
        "has_error": has_error,
        "market_ready": market_ready,
        "meets_repair_exit": meets_repair_exit,
        "below_repair_enter": not meets_repair_exit,
        "notes": notes,
    }


def _track_b_four_types_executed(report: dict) -> bool:
    tb = report.get("track_b") if isinstance(report.get("track_b"), dict) else {}
    dist = tb.get("distribution") or {}
    if not isinstance(dist, dict):
        return False
    try:
        if not all(int(dist.get(k) or 0) > 0 for k in FOUR_TYPE_KEYS):
            return False
    except (TypeError, ValueError):
        return False
    rounds = tb.get("rounds") or []
    if isinstance(rounds, list) and any(isinstance(r, dict) for r in rounds):
        return True
    avg = tb.get("average") if isinstance(tb.get("average"), dict) else {}
    return avg.get("f1") is not None


def _release_checklist_items(report: dict) -> list[dict]:
    """把 release_checklist 的 fail 收进修复计划（可补改 Skill；1/3/9 只复判）。"""
    rcl = report.get("release_checklist") or []
    if not isinstance(rcl, list):
        return []
    four_ok = _track_b_four_types_executed(report)
    out: list[dict] = []
    for it in rcl:
        if not isinstance(it, dict) or it.get("status") != "fail":
            continue
        try:
            item_id = int(it.get("id"))
        except (TypeError, ValueError):
            continue
        if item_id in RELEASE_SKILL_FIX:
            sev, field, message, fix_type = RELEASE_SKILL_FIX[item_id]
            source = "release_checklist"
        elif item_id in RELEASE_REJUDGE:
            sev, field, message, fix_type = RELEASE_REJUDGE[item_id]
            source = "release_rejudge"
            if item_id == 9 and four_ok:
                message = (
                    "本轮 A 卷四类已执行：第 9 项改为 pass，不要改 SKILL.md、不要新造评测文件"
                )
        else:
            continue
        evidence = str(it.get("evidence") or "").strip()
        if evidence:
            message = f"{message}（原判：{evidence}）"
        out.append({
            "source": source,
            "severity": sev,
            "field": field,
            "message": message,
            "fix_type": fix_type,
            "priority": 1,
        })
    return out


def load_report(path: Path) -> dict:
    """读取评估报告 YAML；无 PyYAML 时给出明确错误。"""
    if yaml is None:
        sys.stderr.write("[error] 需要 PyYAML：python3 -m pip install pyyaml\n")
        sys.exit(1)
    if not path.exists():
        sys.stderr.write(f"[error] 报告不存在: {path}\n")
        sys.exit(1)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        sys.stderr.write(f"[error] 报告 YAML 解析失败: {exc}\n")
        sys.exit(1)
    if not isinstance(data, dict) or "issues" not in data:
        sys.stderr.write("[error] 报告缺少 issues 字段，不是有效的评估报告\n")
        sys.exit(1)
    return data


def fingerprint(field: str, message: str) -> str:
    """修复项稳定指纹：field|message 的 SHA-1 前 12 位，用于拒绝缓冲去重。"""
    raw = f"{field}|{message}".strip().lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def load_opt_state(path: Path) -> dict:
    """读取 .opt-state 下的 YAML/JSON 状态文件；缺失或损坏时返回空结构。"""
    if yaml is None or not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def build_plan(report: dict, min_severity: str) -> list[dict]:
    """合并 issues、optimization_plan 与 release_checklist fail 项。"""
    min_rank = SEVERITY_RANK.get(min_severity, 0)
    # optimization_plan 无 severity 字段：按优先级映射（P0→error / P1→warning / P2→info）
    plan_sev_of_prio = {"P0": "error", "P1": "warning", "P2": "info"}
    plan: list[dict] = []
    for it in report.get("issues", []):
        sev = str(it.get("severity", "info")).lower()
        if SEVERITY_RANK.get(sev, 2) > min_rank:
            continue
        plan.append({
            "source": "issue",
            "severity": sev,
            "field": str(it.get("field", "")),
            "message": str(it.get("message", "")),
            "fix_type": str(it.get("fix_type", "")),
            "priority": PRIORITY_RANK.get(str(it.get("priority", "P1")).upper(), 1),
        })
    for p in report.get("optimization_plan", []):
        prio = str(p.get("priority", "P1")).upper()
        sev = plan_sev_of_prio.get(prio, "info")
        if SEVERITY_RANK.get(sev, 2) > min_rank:
            continue
        plan.append({
            "source": "plan",
            "severity": sev,
            "field": str(p.get("field", "")),
            "message": str(p.get("action", "")),
            "fix_type": str(p.get("type", "")),
            "priority": PRIORITY_RANK.get(prio, 1),
        })
    for item in _release_checklist_items(report):
        if SEVERITY_RANK.get(item.get("severity", "info"), 2) > min_rank:
            continue
        plan.append(item)
    plan.sort(key=lambda x: (x["priority"], SEVERITY_RANK.get(x["severity"], 2)))
    for item in plan:
        item.pop("priority", None)
    return plan


def apply_opt_state(plan: list[dict], rejected: set[str] | None,
                    training_log: list[dict] | None) -> dict:
    """应用拒绝缓冲与元记忆：返回 {plan, excluded, reordered}。"""
    excluded: list[dict] = []
    kept: list[dict] = []
    if rejected:
        for item in plan:
            fp = fingerprint(item.get("field", ""), item.get("message", ""))
            (excluded if fp in rejected else kept).append(item)
    else:
        kept = plan

    reordered = 0
    if training_log:
        # 统计每种 fix_type 的净效果（effective 记 +1，ineffective/regression 记 -1）
        effect: dict[str, int] = {}
        for entry in training_log:
            ft = str(entry.get("fix_type", ""))
            outcome = str(entry.get("outcome", "")).lower()
            if not ft:
                continue
            effect[ft] = effect.get(ft, 0) + (1 if outcome == "effective" else -1)
        if effect:
            kept.sort(key=lambda x: (
                -effect.get(x.get("fix_type", ""), 0),  # 净效果大的优先
                SEVERITY_RANK.get(x.get("severity", 2)),
            ))
            reordered = sum(1 for x in kept if effect.get(x.get("fix_type", ""), 0) != 0)
    return {"plan": kept, "excluded": excluded, "reordered": reordered}


def main() -> None:
    parser = argparse.ArgumentParser(description="从评估报告生成修复计划")
    parser.add_argument("report", type=Path, help="评估报告 YAML 路径")
    parser.add_argument("--format", choices=("text", "json"), default="text",
                        help="输出格式（默认 text）")
    parser.add_argument("--min-severity", choices=("error", "warning", "info"),
                        default="warning", help="最低严重度（默认 warning）")
    parser.add_argument("--budget", type=int, default=0,
                        help="编辑预算：每轮最多输出 N 条修复（默认 0=不限）")
    parser.add_argument("--rejected-edits", type=Path, default=None,
                        help="拒绝编辑缓冲 YAML/JSON（.opt-state/rejected-edits.yaml）")
    parser.add_argument("--training-log", type=Path, default=None,
                        help="跨轮元记忆 YAML/JSON（.opt-state/training-log.yaml）")
    args = parser.parse_args()

    report = load_report(args.report)
    plan = build_plan(report, args.min_severity)

    rejected: set[str] | None = None
    if args.rejected_edits:
        state = load_opt_state(args.rejected_edits)
        rejected = {str(r.get("fingerprint", "")) for r in state.get("rejected_edits", [])
                    if r.get("fingerprint")}

    training_log: list[dict] | None = None
    if args.training_log:
        state = load_opt_state(args.training_log)
        training_log = state.get("training_log", [])

    filtered = apply_opt_state(plan, rejected, training_log)
    plan = filtered["plan"]
    excluded = filtered["excluded"]

    budget = args.budget if args.budget > 0 else len(plan)
    truncated = len(plan) - budget if len(plan) > budget else 0
    plan = plan[:budget]

    if args.format == "json":
        print(json.dumps({
            "skill": report.get("eval_info", {}).get("skill_name", ""),
            "track_c": effective_track_c(report),
            "items": plan,
            "stats": {
                "total": len(plan) + truncated + len(excluded),
                "excluded_rejected": len(excluded),
                "truncated_budget": truncated,
                "budget": args.budget,
            },
        }, ensure_ascii=False, indent=2))
        return

    name = report.get("eval_info", {}).get("skill_name", Path(args.report).stem)
    print(f"== 修复计划: {name}（{len(plan)} 项）==")
    eff = effective_track_c(report)
    if eff["total"] is not None:
        cap_note = ""
        if (eff["total_before_cap"] is not None
                and eff["total"] != eff["total_before_cap"]):
            cap_note = f"（封顶前 {eff['total_before_cap']}）"
        out_s = f"{eff['output_quality']}/25" if eff["output_quality"] is not None else "缺失"
        gate = ("已达修复退出线 ≥85" if eff["meets_repair_exit"]
                else f"未达修复退出线 {REPAIR_ENTER}（继续修）")
        print(f"  [track_c] 封顶后 {eff['total']}{cap_note}，Output {out_s} → {gate}")
        for n in eff["notes"]:
            print(f"    · {n}")
    else:
        print("  [track_c] 缺少轨道 C 总分，按未达标继续修")
    if excluded:
        print(f"  [rejected] 已排除拒绝缓冲中的 {len(excluded)} 项（验证无效，不再重复提议）")
    if truncated:
        print(f"  [budget] 编辑预算 {args.budget} 条：本轮截断 {truncated} 项，留待下轮")
    if not plan:
        print("  无待修复项 ✅")
        return
    for i, item in enumerate(plan, 1):
        sev = item["severity"].upper()
        field = item["field"] or "-"
        print(f"  {i}. [{sev}] {field}")
        print(f"     {item['message']}")
        if item.get("fix_type"):
            print(f"     修复类型: {item['fix_type']}")


if __name__ == "__main__":
    main()

