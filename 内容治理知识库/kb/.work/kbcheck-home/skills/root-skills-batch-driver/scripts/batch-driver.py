#!/usr/bin/env python3
"""
batch-driver.py - root-skills-batch-driver 确定性编排核心

职责边界：只做可机器判定的编排状态机。subagent 的实际启动/监控由驱动会话
（dsh agent）按 SKILL.md 编排；本脚本负责——扫描、心跳（磁盘落盘 mtime）、
无进展超时判定、断点续跑（checkpoint）、事件留痕、汇总。不越权打分、不出题。

统一接口：stdin 传 JSON，stdout 出 JSON，退出码表成败。

actions:
    scan      {"action":"scan","skills_dir":"<绝对或相对路径>","state_path":"<状态文件路径>"}
              → 发现合法 skill（含 SKILL.md），与 checkpoint 合并，返回分桶
    heartbeat {"action":"heartbeat","progress_dir":"<评测产物目录>","timeout_minutes":15}
              → 返回该目录最新落盘 mtime 与 idle 秒数、是否 stale
    record    {"action":"record","state_path":"...","skill":"...","status":"...",
                "note":"...","report_path":null,"score":null}
              → 更新状态 + 追加事件，返回事件序号
    summary   {"action":"summary","state_path":"...","skills_dir":"..."}
              → 聚合为批量汇总（含按 score.json 归档 done 的分数），返回 batch_summary
    timeout   {"action":"timeout","complexity":"complex"}
              → 按复杂度映射无进展超时分钟数（simple/standard=15，complex=25）

硬规则来源：root-skills-eval/references/batch-evaluation.md v3.18.1
    - 无进展超时：默认 15 分钟，complex 100 条用例放宽到 25 分钟
    - 进度以磁盘落盘为准，不凭内存计数
    - 中断/续接/重启事件写入批量摘要留痕
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_VERSION = "1.0"

# 无进展超时（分钟），按复杂度区分；对齐 eval 的 batch-evaluation.md v3.18.1
TIMEOUT_MINUTES = {
    "simple": 15,
    "standard": 15,
    "complex": 25,
}
DEFAULT_TIMEOUT_MINUTES = 15

# 心跳忽略目录：评测过程性字节不会计入“无进展”判据
_IGNORE_PARTS = {"__pycache__", ".git"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _is_skill_dir(d: Path) -> bool:
    """合法 skill = 目录且含 SKILL.md（对齐 eval 批量扫描判定）。"""
    return d.is_dir() and (d / "SKILL.md").is_file()


def timeout_for(complexity: str | None) -> int:
    """按复杂度映射无进展超时分钟数。未知复杂度回退默认 15。"""
    return TIMEOUT_MINUTES.get((complexity or "").lower(), DEFAULT_TIMEOUT_MINUTES)


def scan_skills(skills_dir: str | Path) -> list[str]:
    """发现 skills 目录下所有合法 skill 名，按目录名升序返回。"""
    root = Path(skills_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"skills_dir 不存在或不是目录: {root}")
    return sorted(p.name for p in root.iterdir() if _is_skill_dir(p))


def load_state(state_path: str | Path) -> dict[str, Any]:
    """读取 checkpoint；不存在则返回空骨架。"""
    sp = Path(state_path)
    if sp.is_file():
        return json.loads(sp.read_text(encoding="utf-8"))
    return {
        "version": STATE_VERSION,
        "skills_dir": None,
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
        "skills": {},
        "events": [],
    }


def save_state(state: dict[str, Any], state_path: str | Path) -> None:
    state["updated_at"] = _now_iso()
    sp = Path(state_path)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_event(state: dict[str, Any], skill: str, kind: str, note: str) -> int:
    state.setdefault("events", []).append(
        {"ts": _now_iso(), "skill": skill, "type": kind, "note": note}
    )
    return len(state["events"])


def action_scan(args: dict[str, Any]) -> dict[str, Any]:
    skills_dir = str(args["skills_dir"])
    state_path = str(args["state_path"])
    state = load_state(state_path)

    discovered = scan_skills(skills_dir)
    # checkpoint 合并：保留已知 skill 的历史状态，发现新 skill 记为 pending
    known = state.setdefault("skills", {})
    for name in discovered:
        if name not in known:
            known[name] = {
                "status": "pending",
                "complexity": None,
                "timeout_minutes": DEFAULT_TIMEOUT_MINUTES,
                "started_at": None,
                "last_artifact_mtime": None,
                "attempts": 0,
                "report_path": None,
                "score": None,
            }
    # 目录里已消失的 skill 不再计入待办
    for name in list(known):
        if name not in discovered and known[name].get("status") in ("pending", "running"):
            known[name]["status"] = "skipped"
            _append_event(state, name, "skip", "skill 已从目录移除，跳过")

    state["skills_dir"] = str(Path(skills_dir).resolve())
    save_state(state, state_path)

    buckets = {"pending": [], "running": [], "done": [], "stuck": [], "skipped": []}
    for name in sorted(known):
        st = known[name].get("status", "pending")
        buckets.setdefault(st, []).append(name)

    return {
        "ok": True,
        "total": len(discovered),
        "pending": buckets["pending"],
        "running": buckets["running"],
        "done": buckets["done"],
        "stuck": buckets["stuck"],
        "skipped": buckets["skipped"],
    }


def latest_artifact_mtime(progress_dir: str | Path) -> float | None:
    """目录下（递归）最新落盘 mtime；无任何产物返回 None。"""
    root = Path(progress_dir)
    if not root.is_dir():
        return None
    best: float | None = None
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if _IGNORE_PARTS.intersection(p.parts):
            continue
        m = p.stat().st_mtime
        if best is None or m > best:
            best = m
    return best


def action_heartbeat(args: dict[str, Any]) -> dict[str, Any]:
    progress_dir = str(args["progress_dir"])
    timeout_minutes = int(args.get("timeout_minutes", DEFAULT_TIMEOUT_MINUTES))
    mtime = latest_artifact_mtime(progress_dir)
    now = _now_ts()
    if mtime is None:
        return {
            "ok": True,
            "latest_mtime": None,
            "seconds_idle": None,
            "stale": False,
            "note": "无任何落盘产物（尚未产出，不算无进展超时）",
        }
    idle = now - mtime
    stale = idle > timeout_minutes * 60
    return {
        "ok": True,
        "latest_mtime": mtime,
        "seconds_idle": round(idle, 1),
        "stale": stale,
        "timeout_minutes": timeout_minutes,
    }


def action_record(args: dict[str, Any]) -> dict[str, Any]:
    state_path = str(args["state_path"])
    state = load_state(state_path)
    name = str(args["skill"])
    skills = state.setdefault("skills", {})
    if name not in skills:
        skills[name] = {
            "status": "pending",
            "complexity": None,
            "timeout_minutes": DEFAULT_TIMEOUT_MINUTES,
            "started_at": None,
            "last_artifact_mtime": None,
            "attempts": 0,
            "report_path": None,
            "score": None,
        }
    entry = skills[name]
    status = str(args["status"])
    if status not in {"pending", "running", "done", "stuck", "skipped"}:
        raise ValueError(f"非法 status: {status!r}")

    if status == "running" and entry.get("status") not in ("running",):
        entry["started_at"] = _now_iso()
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        entry["timeout_minutes"] = timeout_for(args.get("complexity"))
    entry["status"] = status

    if args.get("report_path"):
        entry["report_path"] = str(args["report_path"])
    if args.get("score") is not None:
        entry["score"] = args["score"]

    kind = str(args.get("event_type", status))
    seq = _append_event(state, name, kind, str(args.get("note", "")))
    save_state(state, state_path)
    return {"ok": True, "skill": name, "status": status, "event_seq": seq}


def action_timeout(args: dict[str, Any]) -> dict[str, Any]:
    complexity = str(args.get("complexity", ""))
    return {"ok": True, "complexity": complexity, "timeout_minutes": timeout_for(complexity)}


def action_summary(args: dict[str, Any]) -> dict[str, Any]:
    state_path = str(args["state_path"])
    skills_dir = str(args.get("skills_dir", ""))
    state = load_state(state_path)
    skills = state.get("skills", {})

    total = len(skills)
    done = [n for n, e in skills.items() if e.get("status") == "done"]
    running = [n for n, e in skills.items() if e.get("status") == "running"]
    pending = [n for n, e in skills.items() if e.get("status") == "pending"]
    stuck = [n for n, e in skills.items() if e.get("status") == "stuck"]
    skipped = [n for n, e in skills.items() if e.get("status") == "skipped"]

    # done 的分数优先取 state 记录，缺失时读被测 skill 的 evals/score.json 归档
    scores: dict[str, float | None] = {}
    for n in done:
        s = skills[n].get("score")
        if s is not None:
            scores[n] = s
            continue
        candidate = Path(skills_dir) / n / "evals" / "score.json" if skills_dir else None
        if candidate and candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                scores[n] = data.get("composite_100") if isinstance(data, dict) else None
            except (json.JSONDecodeError, OSError):
                scores[n] = None
        else:
            scores[n] = None

    passed = sum(1 for v in scores.values() if isinstance(v, (int, float)) and v >= 85)
    failed = sum(1 for v in scores.values() if isinstance(v, (int, float)) and v < 85)
    unscored = sum(1 for v in scores.values() if v is None)

    # 连续中断留痕：attempts >= 2 的 skill 单独标记（对齐 batch-evaluation.md 第 4 条）
    repeat_attempts = [n for n, e in skills.items() if e.get("attempts", 0) >= 2]

    return {
        "ok": True,
        "batch_summary": {
            "total_skills": total,
            "evaluated": len(done),
            "passed": passed,
            "failed": failed,
            "unscored": unscored,
            "pending": len(pending),
            "running": len(running),
            "stuck": len(stuck),
            "skipped": len(skipped),
            "repeat_attempt_skills": repeat_attempts,
        },
        "events": state.get("events", []),
    }


def _dispatch(args: dict[str, Any]) -> dict[str, Any]:
    action = args.get("action")
    handlers = {
        "scan": action_scan,
        "heartbeat": action_heartbeat,
        "record": action_record,
        "summary": action_summary,
        "timeout": action_timeout,
    }
    if action not in handlers:
        return {"ok": False, "error": {"code": "unknown_action", "action": action}}
    try:
        return handlers[action](args)
    except (KeyError, ValueError, FileNotFoundError, TypeError) as exc:
        return {"ok": False, "error": {"code": type(exc).__name__, "message": str(exc)}}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # 便于人工快速自检：--selftest 不读 stdin
    if "--selftest" in argv:
        return _selftest()

    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"ok": False, "error": {"code": "empty_input"}}, ensure_ascii=False))
        return 1
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": {"code": "bad_json", "message": str(exc)}},
                         ensure_ascii=False))
        return 1
    result = _dispatch(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def _selftest() -> int:
    """最小不变量自检（不进 stdin），供 CI / 手工快速验证。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "a-skill" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
        (root / "a-skill" / "SKILL.md").write_text("---\nname: a-skill\n---\n", encoding="utf-8")
        (root / "b-skill" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
        (root / "b-skill" / "SKILL.md").write_text("---\nname: b-skill\n---\n", encoding="utf-8")
        (root / "not-a-skill").mkdir()

        state_path = root / "state" / "batch-progress.json"
        r = _dispatch({"action": "scan", "skills_dir": str(root), "state_path": str(state_path)})
        assert r["ok"] and r["total"] == 2, r
        assert r["pending"] == ["a-skill", "b-skill"], r

        r = _dispatch({"action": "timeout", "complexity": "complex"})
        assert r["timeout_minutes"] == 25, r
        r = _dispatch({"action": "timeout", "complexity": "standard"})
        assert r["timeout_minutes"] == 15, r

        r = _dispatch({"action": "record", "state_path": str(state_path),
                       "skill": "a-skill", "status": "done", "note": "ok", "score": 90})
        assert r["ok"], r

        r = _dispatch({"action": "summary", "state_path": str(state_path),
                       "skills_dir": str(root)})
        assert r["ok"], r
        s = r["batch_summary"]
        assert s["total_skills"] == 2 and s["evaluated"] == 1 and s["passed"] == 1, s

        # 心跳：空目录无产物 → 不算 stale
        r = _dispatch({"action": "heartbeat", "progress_dir": str(root / "empty")})
        assert r["ok"] and r["stale"] is False, r
    print("selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
