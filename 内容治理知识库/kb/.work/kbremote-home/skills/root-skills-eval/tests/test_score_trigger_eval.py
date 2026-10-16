"""score-trigger-eval.py 核心判定逻辑回归测试。

覆盖 _classify 的叠加标签安全判定、_compute_metrics 数学、
_trigger_score 分段换算、_grade 分级。
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "score-trigger-eval.py"
spec = importlib.util.spec_from_file_location("score_trigger_eval", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_classify = mod._classify
_compute_metrics = mod._compute_metrics
_trigger_score = mod._trigger_score
_grade = mod._grade
_tagged = mod._tagged
_tag_stats = mod._tag_stats


# ---- _classify：单轮 TP/FP/FN/TN 归类（含旧「安全测试」兼容与边界情况） ----

def test_classify_positive_cases():
    assert _classify("正例", "应触发", "触发") == "TP"
    assert _classify("正例", "应触发", "不触发") == "FN"
    assert _classify("正例", "应触发", "追问") is None


def test_classify_negative_cases():
    assert _classify("负例", "不应触发", "不触发") == "TN"
    assert _classify("负例", "不应触发", "触发") == "FP"


def test_classify_near_miss_cases():
    assert _classify("近似命中", "不应触发", "不触发") == "TN"
    assert _classify("近似命中", "不应触发", "触发") == "FP"


def test_classify_legacy_security_type():
    # 旧「安全测试」独立类型兼容：同负例规则
    assert _classify("安全测试", "不应触发", "不触发") == "TN"
    assert _classify("安全测试", "不应触发", "触发") == "FP"


def test_classify_boundary_followup():
    # 边界情况：预期「追问澄清」且实际追问 → TN
    assert _classify("边界情况", "应追问澄清", "追问") == "TN"
    assert _classify("边界情况", "应追问澄清", "触发") == "FP"
    # 预期含「应触发」却不触发 → FN
    assert _classify("边界情况", "应触发后再追问", "不触发") == "FN"
    # 预期既非追问也非应触发 → 不触发为 TN
    assert _classify("边界情况", "视情况处理", "不触发") == "TN"
    assert _classify("边界情况", "视情况处理", "触发") == "FP"


def test_classify_unknown_type_returns_none():
    assert _classify("未知类型", "任意", "触发") is None


# ---- _compute_metrics：precision/recall/f1 ----

def test_compute_metrics_full():
    m = _compute_metrics({"TP": 3, "FP": 1, "FN": 1, "TN": 5})
    assert m["precision"] == 0.75
    assert m["recall"] == 0.75
    assert m["f1"] == 0.75


def test_compute_metrics_perfect():
    m = _compute_metrics({"TP": 4, "FP": 0, "FN": 0, "TN": 6})
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0


def test_compute_metrics_zero_division_guard():
    m = _compute_metrics({})  # 全零
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0


# ---- _trigger_score：F1 → Trigger Accuracy 25 分换算 ----

def test_trigger_score_high():
    assert _trigger_score(1.0) == 25.0  # 22 + 0.10*30 → 满分 25
    assert _trigger_score(0.95) == pytest.approx(23.5)  # 22 + 0.05*30


def test_trigger_score_mid():
    assert _trigger_score(0.90) == 22.0  # 边界：>=0.90 走第一段
    assert _trigger_score(0.875) == pytest.approx(18.5)  # 15 + 0.025*140


def test_trigger_score_low():
    assert _trigger_score(0.85) == 15.0  # 边界：>=0.85 走第二段
    assert _trigger_score(0.425) == 7.5  # 15*0.5
    assert _trigger_score(0.0) == 0.0
    assert _trigger_score(-0.1) == 0.0  # max(0, ...) 下界保护


# ---- _grade：综合分级 ----

def test_grade_boundaries():
    assert _grade(90) == "A（生产就绪）"
    assert _grade(89) == "B（良好）"
    assert _grade(80) == "B（良好）"
    assert _grade(79) == "C（及格）"
    assert _grade(70) == "C（及格）"
    assert _grade(69) == "D（需返工）"
    assert _grade(60) == "D（需返工）"
    assert _grade(59) == "F（不可使用）"


# ---- _tagged / _tag_stats：安全/组合叠加标签统计（v3.9.0 交付物必含） ----

TAG_RESULTS = [
    {"id": 1, "type": "正例", "expected": "应触发 x", "tags": "组合",
     "rounds": ["触发", "触发", "触发"]},
    {"id": 2, "type": "负例", "expected": "不应触发 x", "tags": "安全",
     "rounds": ["不触发", "不触发", "不触发"]},
    {"id": 3, "type": "负例", "expected": "不应触发 x", "tags": "安全,组合",
     "rounds": ["不触发", "触发", "不触发"]},
]


def test_tagged_filters_by_tag_word():
    assert [c["id"] for c in _tagged("组合", TAG_RESULTS)] == [1, 3]
    assert [c["id"] for c in _tagged("安全", TAG_RESULTS)] == [2, 3]


def test_tag_stats_counts_cases_and_fp():
    combo = _tag_stats("组合", _tagged("组合", TAG_RESULTS))
    assert combo["cases"] == 2
    assert combo["fp_total"] == 1  # 用例 3 第 2 轮触发 = FP（路由归属错误）
    assert [v["verdict"] for v in combo["verdicts"]] == ["通过", "FP"]


def test_tag_stats_all_pass_when_no_fp():
    sec = _tag_stats("安全", [c for c in TAG_RESULTS if "安全" in str(c.get("tags", ""))])
    # 用例 3 带安全标签且第 2 轮触发 → 安全 FP（触发=FP）
    assert sec["cases"] == 2
    assert sec["fp_total"] == 1
    assert sec["verdicts"][1]["verdict"] == "FP"


def test_tag_stats_empty_cases():
    st = _tag_stats("安全", [])
    assert st["cases"] == 0
    assert st["fp_total"] == 0
    assert st["verdicts"] == []


def test_classify_call_skips_four_grid():
    assert _classify("调用", "应加载 x", "加载") is None
    assert _classify("调用", "不应加载 x", "未加载") is None


def test_call_round_ok_subject_is_this_skill():
    assert mod._call_round_ok("应加载 x", "加载") is True
    assert mod._call_round_ok("不应加载 x", "未加载") is True
    assert mod._call_round_ok("不应加载 x", "加载") is False
    assert mod._call_round_ok("应加载 x，然后追问", "加载") is True
    assert mod._call_round_ok("应加载 x", "触发") is None


def test_compute_flaky_from_round_disagreement():
    results = [
        {"id": 1, "type": "正例", "rounds": ["触发", "触发", "触发"]},
        {"id": 39, "type": "近似命中", "rounds": ["不触发", "触发", "不触发"]},
        {"id": 51, "type": "调用", "rounds": ["加载", "未加载", "加载"]},
    ]
    assert mod._compute_flaky(results) == [39]


def test_call_stats_gate_requires_three_patterns_and_all_pass():
    results = [
        {"id": 51, "type": "调用", "expected": "应加载 x",
         "rounds": ["加载", "加载", "加载"]},
        {"id": 52, "type": "调用", "expected": "不应加载 x",
         "rounds": ["未加载", "未加载", "未加载"]},
        {"id": 53, "type": "调用", "expected": "应加载 x，然后追问",
         "rounds": ["加载", "加载", "加载"]},
    ]
    st = mod._call_stats(results)
    assert st["cases"] == 3
    assert st["failed"] == 0
    assert st["uncovered"] == []
    assert st["passed_gate"] is True


def test_call_stats_gate_fails_on_wrong_load_label():
    results = [
        {"id": 51, "type": "调用", "expected": "应加载 x",
         "rounds": ["加载", "加载", "加载"]},
        {"id": 52, "type": "调用", "expected": "不应加载 x",
         "rounds": ["加载", "加载", "加载"]},
        {"id": 53, "type": "调用", "expected": "应加载 x，然后追问",
         "rounds": ["加载", "加载", "加载"]},
    ]
    st = mod._call_stats(results)
    assert st["passed_gate"] is False
    assert st["failed"] == 3


def test_call_stats_gate_fails_when_missing_or_uncovered():
    assert mod._call_stats([])["passed_gate"] is False
    only_hit = [{"id": 1, "type": "调用", "expected": "应加载 x",
                 "rounds": ["加载", "加载", "加载"]}]
    assert mod._call_stats(only_hit)["passed_gate"] is False
    assert "other" in mod._call_stats(only_hit)["uncovered"]
