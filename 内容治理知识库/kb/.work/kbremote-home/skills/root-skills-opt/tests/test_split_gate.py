"""split-gate.py（留出验证门）单元测试。"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def load_script(name: str):
    """按文件路径加载带连字符的脚本（split-gate.py → 模块名 split_gate）。"""
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


split_gate = load_script("split-gate")


def make_cases(n=50, seed_rounds=0):
    """生成 n 条标准触发用例（正例/负例/近似/边界/安全混合）。"""
    types = ["正例", "负例", "近似命中", "边界情况", "安全测试"]
    results = []
    for i in range(1, n + 1):
        t = types[i % len(types)]
        if t == "正例":
            expected = f"应触发 skill-{i}"
            rounds = ["触发"] * 3
        elif t == "安全测试":
            expected = f"不应触发（安全拒绝）{i}"
            rounds = ["不触发"] * 3
        else:
            expected = f"不应触发 {i}"
            rounds = ["不触发"] * 3
        results.append({"id": i, "type": t, "expected": expected, "rounds": rounds})
    return results


class TestSplit:
    def test_deterministic_split(self):
        cases = make_cases()
        g1, h1, gid1, hid1 = split_gate.split_cases(cases, seed=42, holdout_ratio=0.2)
        g2, h2, gid2, hid2 = split_gate.split_cases(cases, seed=42, holdout_ratio=0.2)
        assert gid1 == gid2 and hid1 == hid2
        assert g1 == g2 and h1 == h2

    def test_split_counts(self):
        cases = make_cases(50)
        g, h, gid, hid = split_gate.split_cases(cases, seed=42, holdout_ratio=0.2)
        assert len(g) == 40 and len(h) == 10
        assert len(gid | hid) == 50

    def test_split_differs_across_seed(self):
        cases = make_cases(50)
        _, _, gid1, _ = split_gate.split_cases(cases, seed=42, holdout_ratio=0.2)
        _, _, gid2, _ = split_gate.split_cases(cases, seed=7, holdout_ratio=0.2)
        assert gid1 != gid2

    def test_case_key_fallback_index(self):
        cases = [{"type": "正例", "expected": "x", "rounds": ["触发"] * 3}]
        assert split_gate.case_key(cases[0], 3) == "3"


class TestMetrics:
    def test_perfect_f1(self):
        cases = make_cases(50)
        m = split_gate.metrics_for(cases)
        assert m["f1"] == 1.0
        assert m["precision"] == 1.0 and m["recall"] == 1.0

    def test_classify_basic(self):
        assert split_gate._classify("正例", "应触发 x", "触发") == "TP"
        assert split_gate._classify("正例", "应触发 x", "不触发") == "FN"
        assert split_gate._classify("负例", "不应触发", "不触发") == "TN"
        assert split_gate._classify("安全测试", "不应触发", "触发") == "FP"

    def test_metrics_known_f1(self):
        # 5 正例 + 5 负例，其中 1 个正例 FN → P=1.0, R=0.8, F1=0.888...
        cases = ([{"id": i, "type": "正例", "expected": "触发", "rounds": ["触发"] * 3}
                  for i in range(1, 5)]
                 + [{"id": 5, "type": "正例", "expected": "触发", "rounds": ["不触发"] * 3}]
                 + [{"id": i, "type": "负例", "expected": "不触发", "rounds": ["不触发"] * 3}
                    for i in range(6, 11)])
        m = split_gate.metrics_for(cases)
        assert m["recall"] == pytest.approx(0.8, abs=0.001)
        assert m["precision"] == pytest.approx(1.0, abs=0.001)


class TestGate:
    def test_verdicts(self):
        assert split_gate.gate_verdict(0.90, 0.85) == "improved"
        assert split_gate.gate_verdict(0.85, 0.90) == "regressed"
        assert split_gate.gate_verdict(0.852, 0.85) == "held"  # 容差内持平
        assert split_gate.gate_verdict(0.85, None) == "no-baseline"

    def test_baseline_roundtrip(self, tmp_path):
        results = {"skill_name": "demo", "results": make_cases(50)}
        rj = tmp_path / "results.json"
        rj.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
        baseline = tmp_path / "gate-baseline.json"

        # 基线写入
        data = split_gate._load_json(rj)
        g, h, _, _ = split_gate.split_cases(data["results"], 42, 0.2)
        hm = split_gate.metrics_for(h)
        baseline.write_text(json.dumps({"holdout_f1": hm["f1"]}), encoding="utf-8")

        base = json.loads(baseline.read_text(encoding="utf-8"))
        assert split_gate.gate_verdict(hm["f1"], base["holdout_f1"]) in ("held", "improved")
