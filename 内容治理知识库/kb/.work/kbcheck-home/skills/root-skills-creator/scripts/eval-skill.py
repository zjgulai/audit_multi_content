#!/usr/bin/env python3
"""
eval-skill.py - Skill 评测编排工具（DSH 化）

生成 with/without 评测任务清单、校验评测集、聚合 grading 结果输出 benchmark。

用法:
    python scripts/eval-skill.py validate evals.json
        校验评测集格式，输出每条 eval 的断言数与警告。

    python scripts/eval-skill.py tasks evals.json --out tasks.json
        生成评测任务清单（每条 eval 生成 with_skill / without_skill 两个任务），
        供 agent 并行派发给 subagent 执行。

    python scripts/eval-skill.py aggregate <workspace>/iteration-N --out benchmark.json
        扫描迭代目录下的所有 grading.json，聚合出 benchmark.json（pass_rate/time/tokens + delta）。

    python scripts/eval-skill.py summary benchmark.json
        打印 benchmark 的人类可读摘要。

约定:
    grading.json 由执行 subagent 按 references/schemas.md 的格式写入
    <run-dir>/grading.json。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


def _load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------

def cmd_validate(evals_path: Path) -> int:
    data = _load_json(evals_path)
    evals = data.get("evals", [])
    if not evals:
        print(f"[error] {evals_path}: evals 列表为空")
        return 1

    errors = 0
    for e in evals:
        problems = []
        if "prompt" not in e or not e.get("prompt"):
            problems.append("缺 prompt")
        if "expectations" not in e or not e.get("expectations"):
            problems.append("缺 expectations（断言）")
        if "id" not in e:
            problems.append("缺 id")
        if "expected_output" not in e or not e.get("expected_output"):
            problems.append("缺 expected_output")
        if problems:
            errors += 1
            print(f"[error] eval#{e.get('id', '?')}: {', '.join(problems)}")
        else:
            n = len(e["expectations"])
            print(f"[ok] eval#{e['id']} {e.get('name', '')}: {n} 条断言")

    if errors:
        print(f"[result] {errors} 条 eval 不完整，请按 references/schemas.md 补齐")
        return 1
    print(f"[result] 评测集合法：{len(evals)} 条 eval")
    return 0


# --------------------------------------------------------------------------
# tasks
# --------------------------------------------------------------------------

def cmd_tasks(evals_path: Path, out_path: Path) -> int:
    data = _load_json(evals_path)
    evals = data.get("evals", [])
    tasks = []
    for e in evals:
        for cfg in ("with_skill", "without_skill"):
            tasks.append({
                "eval_id": e.get("id"),
                "eval_name": e.get("name", f"eval-{e.get('id')}"),
                "configuration": cfg,
                "prompt": e.get("prompt"),
                "files": e.get("files", []),
                "expectations": e.get("expectations", []),
                "output_dir": f"iteration-N/eval-{e.get('id')}/{cfg}/outputs",
            })
    _write_json(out_path, {"skill_name": data.get("skill_name"), "tasks": tasks})
    print(f"[result] 生成 {len(tasks)} 个评测任务（{len(evals)} 条 eval × 2 配置）→ {out_path}")
    return 0


# --------------------------------------------------------------------------
# aggregate
# --------------------------------------------------------------------------

def _mean(vals):
    return statistics.mean(vals) if vals else 0.0


def _stddev(vals):
    return statistics.stdev(vals) if len(vals) > 1 else 0.0


def _delta_str(with_val, without_val):
    d = with_val - without_val
    return f"{d:+.2f}"


def cmd_aggregate(iteration_dir: Path, out_path: Path) -> int:
    if not iteration_dir.is_dir():
        print(f"[error] {iteration_dir} 不是目录")
        return 1

    runs = []
    per_cfg = {"with_skill": [], "without_skill": []}

    for grading in sorted(iteration_dir.rglob("grading.json")):
        g = _load_json(grading)
        # 从路径推断 eval_id 与 configuration，例如 eval-1/with_skill/grading.json
        parts = grading.parts
        cfg = "without_skill"
        eval_id = None
        eval_name = grading.parent.name
        for p in parts:
            if p in ("with_skill", "without_skill"):
                cfg = p
            if p.startswith("eval-"):
                eval_id = p
        summary = g.get("summary", {})
        timing = g.get("timing", {})
        metrics = g.get("execution_metrics", {})
        run = {
            "eval_id": eval_id,
            "eval_name": eval_name,
            "configuration": cfg,
            "result": {
                "pass_rate": summary.get("pass_rate", 0.0),
                "passed": summary.get("passed", 0),
                "failed": summary.get("failed", 0),
                "total": summary.get("total", 0),
                "time_seconds": timing.get("total_duration_seconds", 0.0),
                "tokens": metrics.get("total_tool_calls", 0),
                "errors": metrics.get("errors_encountered", 0),
            },
        }
        runs.append(run)
        per_cfg.setdefault(cfg, []).append(run)

    def _agg(key):
        return {
            "mean": round(_mean([r["result"][key] for r in runs if r["configuration"] == "with_skill"]), 3),
            "stddev": round(_stddev([r["result"][key] for r in runs if r["configuration"] == "with_skill"]), 3),
            "without_mean": round(_mean([r["result"][key] for r in runs if r["configuration"] == "without_skill"]), 3),
        }

    ws = [r["result"]["pass_rate"] for r in runs if r["configuration"] == "with_skill"]
    wos = [r["result"]["pass_rate"] for r in runs if r["configuration"] == "without_skill"]

    benchmark = {
        "metadata": {
            "skill_name": "unknown",
            "timestamp": "",
            "evals_run": sorted({r["eval_id"] for r in runs if r["eval_id"]}),
            "runs_per_configuration": 1,
        },
        "runs": runs,
        "run_summary": {
            "with_skill": {
                "pass_rate": {"mean": round(_mean(ws), 3), "stddev": round(_stddev(ws), 3)},
                "time_seconds": {"mean": round(_mean([r["result"]["time_seconds"] for r in runs if r["configuration"] == "with_skill"]), 1)},
                "tokens": {"mean": round(_mean([r["result"]["tokens"] for r in runs if r["configuration"] == "with_skill"]), 1)},
            },
            "without_skill": {
                "pass_rate": {"mean": round(_mean(wos), 3), "stddev": round(_stddev(wos), 3)},
                "time_seconds": {"mean": round(_mean([r["result"]["time_seconds"] for r in runs if r["configuration"] == "without_skill"]), 1)},
                "tokens": {"mean": round(_mean([r["result"]["tokens"] for r in runs if r["configuration"] == "without_skill"]), 1)},
            },
            "delta": {
                "pass_rate": _delta_str(_mean(ws), _mean(wos)),
                "time_seconds": _delta_str(
                    _mean([r["result"]["time_seconds"] for r in runs if r["configuration"] == "with_skill"]),
                    _mean([r["result"]["time_seconds"] for r in runs if r["configuration"] == "without_skill"]),
                ),
                "tokens": _delta_str(
                    _mean([r["result"]["tokens"] for r in runs if r["configuration"] == "with_skill"]),
                    _mean([r["result"]["tokens"] for r in runs if r["configuration"] == "without_skill"]),
                ),
            },
        },
        "notes": [],
    }

    _write_json(out_path, benchmark)
    print(f"[result] 聚合 {len(runs)} 个运行 → {out_path}")
    print(f"  pass_rate  with={benchmark['run_summary']['with_skill']['pass_rate']['mean']}  without={benchmark['run_summary']['without_skill']['pass_rate']['mean']}  delta={benchmark['run_summary']['delta']['pass_rate']}")
    return 0


# --------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------

def cmd_summary(benchmark_path: Path) -> int:
    b = _load_json(benchmark_path)
    rs = b.get("run_summary", {})
    print("== Benchmark 摘要 ==")
    print(f"  pass_rate : with={rs['with_skill']['pass_rate']['mean']}±{rs['with_skill']['pass_rate']['stddev']}  without={rs['without_skill']['pass_rate']['mean']}±{rs['without_skill']['pass_rate']['stddev']}  delta={rs['delta']['pass_rate']}")
    print(f"  time(s)   : with={rs['with_skill']['time_seconds']['mean']}  without={rs['without_skill']['time_seconds']['mean']}  delta={rs['delta']['time_seconds']}")
    print(f"  tokens    : with={rs['with_skill']['tokens']['mean']}  without={rs['without_skill']['tokens']['mean']}  delta={rs['delta']['tokens']}")
    for note in b.get("notes", []):
        print(f"  note: {note}")
    return 0


# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Skill 评测编排工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_v = sub.add_parser("validate", help="校验评测集")
    p_v.add_argument("evals", type=Path)

    p_t = sub.add_parser("tasks", help="生成评测任务清单")
    p_t.add_argument("evals", type=Path)
    p_t.add_argument("--out", type=Path, default=Path("tasks.json"))

    p_a = sub.add_parser("aggregate", help="聚合 grading 为 benchmark")
    p_a.add_argument("iteration_dir", type=Path)
    p_a.add_argument("--out", type=Path, default=Path("benchmark.json"))

    p_s = sub.add_parser("summary", help="打印 benchmark 摘要")
    p_s.add_argument("benchmark", type=Path)

    args = parser.parse_args()

    if args.command == "validate":
        sys.exit(cmd_validate(args.evals))
    elif args.command == "tasks":
        sys.exit(cmd_tasks(args.evals, args.out))
    elif args.command == "aggregate":
        sys.exit(cmd_aggregate(args.iteration_dir, args.out))
    elif args.command == "summary":
        sys.exit(cmd_summary(args.benchmark))


if __name__ == "__main__":
    main()
