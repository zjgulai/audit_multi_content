#!/usr/bin/env python3
"""Regression controls for the L7 image review fail-closed gate.

Run from the knowledge-base root:
    python3 kb/l8/image_skill_gate_selftest.py

No DSH calls, Feishu writes, or knowledge-base mutations are performed.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


KB = Path(__file__).resolve().parents[1]
ENTRY = KB / "l7/review-engine/core/with_kb_evidence.py"
SPEC = importlib.util.spec_from_file_location("with_kb_evidence_gate_selftest", ENTRY)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("cannot load %s" % ENTRY)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> int:
    passed = 0
    with tempfile.TemporaryDirectory(prefix="image-skill-gate-") as td:
        image = Path(td) / "source.png"
        image.write_bytes(b"synthetic readable image fixture")
        good = Namespace(decision_owner="图片安全审查", image=[str(image)],
                         allow_decision_owner_mismatch=False)

        def check(label, cond):
            nonlocal passed
            if not cond:
                raise AssertionError(label)
            passed += 1
            print("  ✅", label)

        missing = Namespace(decision_owner="图片安全审查", image=None,
                             allow_decision_owner_mismatch=False)
        check("missing --image rejects", MODULE.image_skill_gate(missing).get("reason_code")
              == "image_source_missing")

        unreadable = Namespace(decision_owner="图片安全审查", image=[str(Path(td) / "absent.png")],
                               allow_decision_owner_mismatch=False)
        check("unreadable original rejects", MODULE.image_skill_gate(unreadable).get("reason_code")
              == "image_source_unreadable")

        ready = (0, {"skills": [{"path": "/skills/图片安全审查"}]})
        # ★ 2026-10-27：dsh 0.2.x **只给 `$DSH_SESSION_ID`**（不再给 `$DSH_SESSION_JSONL`）⇒ 闸门
        #   不再「环境变量为空就先判死」，而是把日志位置交给唯一解析口
        #   （`verify_skill_loaded::resolve_session_path`）。所以这一格必须**两个变量都清**，
        #   才算真正的「没有会话」；并把解析那一调钉成 rc=5（untested）—— 那正是它真找不到时的返回。
        with patch.dict(os.environ, {}, clear=False):
            for _k in ("DSH_SESSION_JSONL", "DSH_SESSION_ID"):
                os.environ.pop(_k, None)
            with patch.object(MODULE, "_json_tool",
                              side_effect=[ready, (5, {"verdict": "untested"})]):
                result = MODULE.image_skill_gate(good)
        check("missing DSH session rejects", not result["ok"]
              and result.get("reason_code") == "skill_session_unverified")

        # ★ 新增（2026-10-27）：只有 `$DSH_SESSION_ID` 时**不许提前拒** —— 迁移到新版后，
        #   每一张图片单都走这个形状；这条一坏，图片单会全变 NEEDS_INPUT（当天 2 单实证）。
        _bak = {k: os.environ.get(k) for k in ("DSH_SESSION_JSONL", "DSH_SESSION_ID")}
        try:
            os.environ.pop("DSH_SESSION_JSONL", None)
            os.environ["DSH_SESSION_ID"] = "session-968579f1-b2d5-4e62-8b0f-533159a67bff"
            with patch.object(MODULE, "_json_tool",
                              side_effect=[ready, (0, {"verdict": "loaded", "calls": 2})]):
                result = MODULE.image_skill_gate(good)
        finally:
            for _k, _v in _bak.items():
                if _v is None:
                    os.environ.pop(_k, None)
                else:
                    os.environ[_k] = _v
        check("id-only env (dsh 0.2.x) is not rejected up-front", result["ok"]
              and (result.get("load") or {}).get("verdict") == "loaded")

        with patch.dict(os.environ, {"DSH_SESSION_JSONL": str(Path(td) / "session.jsonl")}, clear=False):
            with patch.object(MODULE, "_json_tool", side_effect=[ready, (5, {"reason": "unreadable"})]):
                result = MODULE.image_skill_gate(good)
        check("unreadable DSH session rejects", not result["ok"]
              and result.get("reason_code") == "skill_session_unverified")

        with patch.dict(os.environ, {"DSH_SESSION_JSONL": str(Path(td) / "session.jsonl")}, clear=False):
            with patch.object(MODULE, "_json_tool", side_effect=[ready, (0, {"verdict": "loaded", "calls": 1})]):
                result = MODULE.image_skill_gate(good)
        check("readable original plus observed skill call passes", result["ok"]
              and (result.get("load") or {}).get("calls") == 1)

        with patch.dict(os.environ, {"DSH_SESSION_JSONL": str(Path(td) / "session.jsonl")}, clear=False):
            with patch.object(MODULE, "_json_tool", return_value=(3, {"error": "not ready"})):
                result = MODULE.image_skill_gate(good)
        check("skill not ready rejects", not result["ok"]
              and result.get("reason_code") == "skill_not_ready")

    print("image_skill_gate selftest PASS (%d/7)" % passed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
