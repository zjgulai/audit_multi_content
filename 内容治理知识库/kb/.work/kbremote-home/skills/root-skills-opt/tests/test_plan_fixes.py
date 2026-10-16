"""plan-fixes.py（修复计划生成 + 训练纪律参数）单元测试。"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def load_script(name: str):
    """按文件路径加载带连字符的脚本（plan-fixes.py → 模块名 plan_fixes）。"""
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plan_fixes = load_script("plan-fixes")


def make_report(tmp_path, n_issues=8):
    """生成最小合法评估报告 YAML。"""
    issues = [{"severity": "error" if i % 3 == 0 else "warning",
               "field": f"field-{i}", "message": f"问题 {i}",
               "fix_type": "schema_compliance" if i % 2 == 0 else "content_quality"}
              for i in range(1, n_issues + 1)]
    report = {
        "skill_info": {"name": "demo-skill"},
        "eval_info": {"skill_name": "demo-skill"},
        "scores": {"total": 78.0},
        "issues": issues,
        "optimization_plan": [
            {"priority": "P0", "field": "description", "action": "优化触发词",
             "type": "description_optimization"},
        ],
        "status": "below_target",
    }
    p = tmp_path / "report.yaml"
    p.write_text("", encoding="utf-8")
    # 用 yaml 序列化（pytest 环境应已有 PyYAML；没有则手动写）
    try:
        import yaml
        p.write_text(yaml.safe_dump(report, allow_unicode=True), encoding="utf-8")
    except ImportError:
        p.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return p


class TestFingerprint:
    def test_stable_and_distinct(self):
        f1 = plan_fixes.fingerprint("description", "优化触发词")
        f2 = plan_fixes.fingerprint("description", "优化触发词")
        f3 = plan_fixes.fingerprint("description", "优化触发词X")
        assert f1 == f2
        assert f1 != f3
        assert len(f1) == 12


class TestBuildPlan:
    def test_merges_issues_and_plan(self, tmp_path):
        rep = plan_fixes.load_report(make_report(tmp_path))
        plan = plan_fixes.build_plan(rep, "info")
        assert len(plan) == 9  # 8 issues + 1 optimization_plan

    def test_min_severity_filters(self, tmp_path):
        rep = plan_fixes.load_report(make_report(tmp_path))
        plan = plan_fixes.build_plan(rep, "error")
        # 8 issues 中 error 的约 3 条 + optimization_plan P0→error 1 条
        assert len(plan) <= 4
        assert all(it["severity"] == "error" for it in plan)

    def test_plan_priority_order(self, tmp_path):
        rep = plan_fixes.load_report(make_report(tmp_path))
        plan = plan_fixes.build_plan(rep, "error")
        # optimization_plan(P0) 排最前
        assert plan[0]["source"] == "plan"


class TestOptState:
    def test_budget_truncation(self, tmp_path):
        rep = plan_fixes.load_report(make_report(tmp_path))
        plan = plan_fixes.build_plan(rep, "info")
        result = plan_fixes.apply_opt_state(plan, None, None)
        assert len(result["plan"]) == len(plan)

    def test_rejected_exclusion(self, tmp_path):
        rep = plan_fixes.load_report(make_report(tmp_path))
        plan = plan_fixes.build_plan(rep, "info")
        fp = plan_fixes.fingerprint("field-2", "问题 2")
        result = plan_fixes.apply_opt_state(plan, {fp}, None)
        assert len(result["excluded"]) == 1
        assert all(plan_fixes.fingerprint(it["field"], it["message"]) != fp
                   for it in result["plan"])

    def test_training_log_reorder(self, tmp_path):
        rep = plan_fixes.load_report(make_report(tmp_path))
        plan = plan_fixes.build_plan(rep, "info")
        # schema_compliance 有效 → 该类型修复应排前
        log = [{"round": 1, "fix_type": "schema_compliance", "outcome": "effective"},
               {"round": 1, "fix_type": "content_quality", "outcome": "ineffective"}]
        result = plan_fixes.apply_opt_state(plan, None, log)
        first_types = [it["fix_type"] for it in result["plan"]]
        assert first_types[0] == "schema_compliance"

    def test_load_opt_state_missing(self, tmp_path):
        assert plan_fixes.load_opt_state(tmp_path / "nope.yaml") == {}


class TestEffectiveTrackC:
    def test_output_low_caps_88_to_79(self):
        report = {
            "issues": [],
            "track_c": {
                "total": 88,
                "dimensions": {"output_quality": 12},
            },
        }
        eff = plan_fixes.effective_track_c(report)
        assert eff["total"] == 79
        assert eff["total_before_cap"] == 88
        assert eff["meets_repair_exit"] is False
        assert eff["market_ready"] is False
        assert eff["below_repair_enter"] is True

    def test_output_pass_keeps_88(self):
        report = {
            "issues": [],
            "track_c": {
                "total": 88,
                "dimensions": {"output_quality": 16},
            },
        }
        eff = plan_fixes.effective_track_c(report)
        assert eff["total"] == 88
        assert eff["meets_repair_exit"] is True
        assert eff["market_ready"] is True

    def test_call_gate_fail_blocks_even_if_88(self):
        report = {
            "issues": [],
            "track_b": {"call_tag": {"cases": 3, "failed": 3, "judged": 9,
                                     "uncovered": [], "passed_gate": False}},
            "track_c": {
                "total": 88,
                "dimensions": {"output_quality": 16},
            },
        }
        eff = plan_fixes.effective_track_c(report)
        assert eff["total"] == 88
        assert eff["market_ready"] is False
        assert eff["meets_repair_exit"] is False
        assert eff["below_repair_enter"] is True

    def test_missing_call_tag_does_not_block_old_yaml(self):
        report = {
            "issues": [],
            "track_c": {
                "total": 88,
                "dimensions": {"output_quality": 16},
            },
        }
        eff = plan_fixes.effective_track_c(report)
        assert eff["market_ready"] is True
        assert eff["meets_repair_exit"] is True

    def test_error_caps_even_if_output_ok(self):
        report = {
            "issues": [{"severity": "error", "field": "x", "message": "e"}],
            "track_c": {"total": 90, "dimensions": {"output_quality": 20}},
        }
        eff = plan_fixes.effective_track_c(report)
        assert eff["total"] == 79
        assert eff["meets_repair_exit"] is False
        assert eff["market_ready"] is False

    def test_missing_output_not_exit(self):
        report = {"issues": [], "track_c": {"total": 88}}
        eff = plan_fixes.effective_track_c(report)
        assert eff["meets_repair_exit"] is False
        assert eff["below_repair_enter"] is True

    def test_already_capped_yaml(self):
        report = {
            "issues": [],
            "track_c": {
                "total": 79,
                "total_before_cap": 88,
                "dimensions": {"output_quality": 12},
            },
        }
        eff = plan_fixes.effective_track_c(report)
        assert eff["total"] == 79
        assert eff["total_before_cap"] == 88
        assert eff["meets_repair_exit"] is False

    def test_low_total_stays_f_not_raised(self):
        report = {
            "issues": [],
            "track_c": {"total": 50, "dimensions": {"output_quality": 10}},
        }
        eff = plan_fixes.effective_track_c(report)
        assert eff["total"] == 50
        assert eff["meets_repair_exit"] is False


class TestReleaseChecklistPlan:
    def test_item10_fail_enters_skill_fix(self):
        report = {
            "issues": [],
            "release_checklist": [
                {"id": 10, "status": "fail", "evidence": "无 lifecycle",
                 "impact": "不影响上线"},
            ],
        }
        plan = plan_fixes.build_plan(report, "warning")
        assert any(it["fix_type"] == "lifecycle" and it["source"] == "release_checklist"
                   for it in plan)

    def test_item9_fail_with_track_b_is_rejudge_not_new_files(self):
        report = {
            "issues": [],
            "track_b": {
                "distribution": {"正例": 8, "负例": 8, "近似命中": 6, "边界情况": 3},
                "rounds": [{"round": 1, "TP": 8, "FP": 0, "FN": 0, "TN": 17}],
            },
            "release_checklist": [
                {"id": 9, "status": "fail", "evidence": "tests 未声明",
                 "impact": "不影响上线"},
            ],
        }
        plan = plan_fixes.build_plan(report, "warning")
        hits = [it for it in plan if it["source"] == "release_rejudge"]
        assert len(hits) == 1
        assert "必须 pass" in hits[0]["message"] or "改为 pass" in hits[0]["message"]
        assert hits[0]["fix_type"] == "release_rejudge"

    def test_pass_items_skipped(self):
        report = {
            "issues": [],
            "release_checklist": [
                {"id": 10, "status": "pass", "evidence": "已有维护段"},
            ],
        }
        plan = plan_fixes.build_plan(report, "warning")
        assert plan == []
