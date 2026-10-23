#!/usr/bin/env python3
"""Verify that absent historical advice never becomes an invented reject rule."""
import importlib.util
from pathlib import Path

review = (Path(__file__).resolve().parents[1] / "l7/skills/kb-content-review/scripts/review.py")
spec = importlib.util.spec_from_file_location("kb_review_history_advice", review)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot load {review}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

cases = [
    ({"kind": "replace", "replacement": "请改成明确的安全睡眠建议"}, "取自源记录的建议原文"),
    ({"kind": "none"}, "源记录未提供具体修改建议；此条仅为相似历史参考，不构成禁止或打回依据"),
    ({}, "源记录未提供具体修改建议；此条仅为相似历史参考，不构成禁止或打回依据"),
]
for action, expected in cases:
    actual = module.history_action_advice_note(action)
    assert actual == expected, (action, actual, expected)
    print("  ✅", actual)
print(f"history_advice_selftest PASS ({len(cases)}/{len(cases)})")
