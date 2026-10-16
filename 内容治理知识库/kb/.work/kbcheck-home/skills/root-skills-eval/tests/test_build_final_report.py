"""build-final-report.py v3.10 输出数据硬校验 / 桌面交付校验 / 输出前自检回归测试。"""

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build-final-report.py"
spec = importlib.util.spec_from_file_location("build_final_report", SCRIPT)
reporter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(reporter)


def valid_report():
    return {
        "track_a": {"total": 96.4, "dimensions": {
            "schema_compliance": 100, "frontmatter_quality": 95, "body_quality": 96,
            "methodology_audit": 98, "quality_gate": 90, "directory_structure": 100,
        }},
        "track_b": {
            "cases_total": 50,
            "distribution": {"正例": 16, "负例": 16, "近似命中": 12, "边界情况": 6},
            "security_tag": {"cases": 6, "fp_total": 0, "high_risk": 0},
            "combo_tag": {"cases": 8, "fp_total": 0},
            "call_tag": {"cases": 3, "judged": 9, "passed": 9, "failed": 0,
                         "uncovered": [], "passed_gate": True},
            "pass_call_gate": True,
            "tag_cases": [],
            "rounds": [
                {"round": 1, "TP": 16, "FP": 1, "FN": 0, "TN": 33, "precision": 0.941, "recall": 1.0, "f1": 0.970},
            ],
        },
        "track_c": {
            "total": 88, "grade": "B", "market_ready": True,
            "dimensions": {
                "trigger": 22, "output_quality": 20, "progressive": 13,
                "safety": 14, "script": 9, "spec": 10,
            },
        },
        "release_checklist": [
            {"id": item_id, "status": "pass", "evidence": "checked"}
            for item_id in range(1, 11)
        ],
    }


def test_validate_report_data_accepts_complete_report():
    assert reporter.validate_report_data(valid_report()) == []


def test_validate_report_data_rejects_missing_release_checklist():
    report = valid_report()
    report.pop("release_checklist")
    assert any("release_checklist" in error for error in reporter.validate_report_data(report))


def test_validate_report_data_rejects_distribution_mismatch():
    report = valid_report()
    report["track_b"]["cases_total"] = 49
    assert any("cases_total" in error for error in reporter.validate_report_data(report))


def test_validate_report_data_rejects_absurd_per_item_pct():
    """distribution 含 0/负条数 → 单项百分比 ≤0%，属比例异常（如「正例 0.0%」），应报错。"""
    report = valid_report()
    report["track_b"]["distribution"] = {"正例": 0, "负例": 16, "近似命中": 12, "边界情况": 6}
    report["track_b"]["cases_total"] = 34
    assert any("超出合理范围" in error for error in reporter.validate_report_data(report))


def test_validate_report_data_rejects_missing_tag_statistics():
    report = valid_report()
    report["track_b"].pop("security_tag")
    assert any("security_tag" in error for error in reporter.validate_report_data(report))


def test_validate_report_data_rejects_fail_item_without_impact():
    """v3.10.0：Release 清单 fail 项必须标注 impact（是否影响上线）。"""
    report = valid_report()
    report["release_checklist"][3]["status"] = "fail"
    assert any("impact" in error for error in reporter.validate_report_data(report))


def test_validate_report_data_accepts_fail_item_with_impact():
    report = valid_report()
    report["release_checklist"][3]["status"] = "fail"
    report["release_checklist"][3]["impact"] = "不影响上线（属剩余风险，建议复审）"
    assert reporter.validate_report_data(report) == []


def test_validate_report_data_rejects_missing_evidence():
    report = valid_report()
    report["release_checklist"][0]["evidence"] = ""
    assert any("缺少 evidence" in error for error in reporter.validate_report_data(report))


def test_validate_report_data_rejects_item9_fail_when_four_types_ran():
    report = valid_report()
    report["release_checklist"][8]["status"] = "fail"
    report["release_checklist"][8]["impact"] = "不影响上线"
    report["release_checklist"][8]["evidence"] = "无明确 positive/negative/e2e eval 声明"
    errors = reporter.validate_report_data(report)
    assert any("第 9 项不得 fail" in error for error in errors)


def test_validate_report_data_rejects_item3_denying_track_b():
    report = valid_report()
    report["release_checklist"][2]["status"] = "fail"
    report["release_checklist"][2]["impact"] = "不影响上线"
    report["release_checklist"][2]["evidence"] = "无评测用例"
    errors = reporter.validate_report_data(report)
    assert any("第 3 项" in error and "A/B 卷属于第 9 项" in error for error in errors)


def test_validate_report_data_allows_item3_fail_for_missing_red():
    report = valid_report()
    report["release_checklist"][2]["status"] = "fail"
    report["release_checklist"][2]["impact"] = "不影响上线（缺历史 RED）"
    report["release_checklist"][2]["evidence"] = "目录无 without-skill RED 基线"
    assert reporter.validate_report_data(report) == []


def test_validate_report_warnings_flags_tag_case_count_mismatch():
    report = valid_report()
    report["track_b"]["tag_cases"] = [
        {"tag": "安全", "id": 1, "title": "t", "rounds": ["不触发"], "verdict": "通过"},
    ]
    warns = reporter.validate_report_warnings(report)
    assert any("安全标签逐条数" in w for w in warns)


def test_flaky_count_ignores_empty_placeholder():
    assert reporter._flaky_count([{"id": 0, "title": "none", "conclusions": []}]) == 0


def test_desktop_fix_check_ok_when_both_exist(tmp_path):
    (tmp_path / "demo-skill").mkdir()
    (tmp_path / "demo-skill-fix").mkdir()
    ok, msgs = reporter.desktop_fix_check("demo-skill", has_repair=True, desktop_root=tmp_path)
    assert ok
    assert any("修复副本已就位" in m for m in msgs)


def test_desktop_fix_check_fails_when_fix_missing(tmp_path):
    (tmp_path / "demo-skill").mkdir()
    ok, msgs = reporter.desktop_fix_check("demo-skill", has_repair=True, desktop_root=tmp_path)
    assert not ok
    assert any("桌面缺少修复副本" in m for m in msgs)


def test_desktop_fix_check_autocopies_workspace_fix(tmp_path):
    (tmp_path / "demo-skill").mkdir()
    wfix = tmp_path / "work" / "demo-skill-fix"
    wfix.mkdir(parents=True)
    (wfix / "SKILL.md").write_text("# demo", encoding="utf-8")
    ok, msgs = reporter.desktop_fix_check(
        "demo-skill", has_repair=True, desktop_root=tmp_path, workspace_fix=wfix)
    assert ok
    assert (tmp_path / "demo-skill-fix" / "SKILL.md").exists()
    assert any("自动复制" in m for m in msgs)


def test_desktop_fix_check_no_repair_ok(tmp_path):
    (tmp_path / "demo-skill").mkdir()
    ok, msgs = reporter.desktop_fix_check("demo-skill", has_repair=False, desktop_root=tmp_path)
    assert ok
    assert any("无低分修复流程" in m for m in msgs)


def test_inline_html_extracts_body_and_styles(tmp_path):
    """v3.13.0：--cases/--process 文件路径 → 提取 <body> 内容与 <style>（内联进最终报告）。"""
    f = tmp_path / "demo-test-cases.html"
    f.write_text(
        "<html><head><style>.resp{white-space:pre-wrap}</style></head>"
        "<body><h1>🧪 demo 测试用例</h1><div class='sub'>副标题</div>"
        "<h2>全部用例与每轮 AI 原文回复</h2><p class='resp'>原文</p>"
        "<div class='footer'>页脚</div></body></html>",
        encoding="utf-8",
    )
    body, css, notes = reporter.inline_html(str(f))
    assert "全部用例与每轮 AI 原文回复" in body
    assert "原文" in body
    assert ".resp" in css
    # 子页面自身 h1/sub/footer 被剔除（最终报告提供 part 标题）
    assert "<h1>" not in body
    assert "副标题" not in body
    assert "页脚" not in body
    # 子页面 h2 降级为 h3（part-head h2 保持唯一二级标题）
    assert "<h2>全部用例" not in body
    assert "<h3>全部用例" in body
    assert notes == []


def test_inline_html_missing_file_warns(tmp_path):
    body, css, notes = reporter.inline_html(str(tmp_path / "nope.html"))
    assert body == "" and css == ""
    assert any("文件不存在" in n for n in notes)


def test_inline_html_url_not_inlined():
    body, css, notes = reporter.inline_html("https://example.com/cases.html")
    assert body == "" and css == ""
    assert any("http(s) URL" in n for n in notes)


def test_inline_html_none():
    body, css, notes = reporter.inline_html(None)
    assert body == "" and css == "" and notes == []


def test_scope_css_prefixes_selectors():
    css = "table { width:100% }\n.resp { color:#333 }\ntr:nth-child(even) td { background:#fafbfc }"
    scoped = reporter._scope_css(css, ".inline-cases")
    assert ".inline-cases table" in scoped
    assert ".inline-cases .resp" in scoped
    assert ".inline-cases tr:nth-child(even) td" in scoped


def test_scope_css_keeps_root_vars():
    css = ":root { --bg:#fff }\n.resp { color:var(--bg) }"
    scoped = reporter._scope_css(css, ".inline-cases")
    assert ":root { --bg:#fff }" in scoped
    assert ".inline-cases .resp" in scoped


def test_toc_html_has_three_parts():
    toc = reporter.toc_html()
    assert 'id="toc"' in toc
    assert 'href="#part-report"' in toc
    assert 'href="#part-process"' in toc
    assert 'href="#part-cases"' in toc
    assert "📊 测试报告" in toc and "🧭 评测过程" in toc and "🧪 测试用例" in toc


def _good_page(inline_cases: str = "", inline_process: str = "") -> str:
    """构造通过自检的单一 HTML 页面（v3.13.0 三大部分结构）。"""
    cases = inline_cases or "<h3>全部用例与每轮 AI 原文回复</h3><p>用例</p>"
    process = inline_process or (
        "<h3>输出前自检（15 项）</h3><p>全部通过</p>"
        "<p>盲测：被测会话仅收到提示词列</p>"
    )
    return (
        "<html><body>"
        f"{reporter.toc_html()}"
        '<h2 class="part-head" id="part-report">📊 测试报告（原数据统计总览）</h2>'
        "<h2>一、多次评测数据对比</h2><h2>一·补、三轮执行与评分统计总览</h2>"
        f"{reporter.scoring_formulas_html()}"
        "<h2>二、测试用例分配比例</h2>"
        "<h3>安全、组合与调用汇总</h3>"
        "<h2>三、修复问题清单</h2>"
        "<h2>四、Release 发布前 10 项审查清单</h2><table><tr><th>是否影响上线</th></tr>"
        "<tr><td>✅ 通过</td></tr></table>"
        "<h2>五、执行评测过程摘要</h2>"
        f'<h2 class="part-head" id="part-process">🧭 评测过程（评测 Skill 流程）</h2>{process}'
        f'<h2 class="part-head" id="part-cases">🧪 测试用例（逐条用例执行情况）</h2>{cases}'
        '<a href="#x" id="x"></a>'
        "<td>正例 </td><td>16 条 </td><td>32.0% </td>"
        "</body></html>"
    )


def test_self_check_html_accepts_good_page():
    errors, warnings = reporter.self_check_html(_good_page(), "demo", cases_inlined=True, process_inlined=True)
    assert errors == []


def test_self_check_html_rejects_missing_toc():
    page = _good_page().replace(reporter.toc_html(), "")
    errors, _ = reporter.self_check_html(page, "demo")
    assert any("目录缺少跳转链接" in e for e in errors)


def test_self_check_html_rejects_missing_section():
    page = "<html><body><h2>一、多次评测数据对比</h2></body></html>"
    errors, _ = reporter.self_check_html(page, "demo")
    assert any("必需区块" in e for e in errors)


def test_self_check_html_rejects_bad_anchor():
    page = _good_page().replace('id="x"', "")
    errors, _ = reporter.self_check_html(page, "demo")
    assert any("无对应 id 目标" in e for e in errors)


def test_self_check_html_ignores_embedded_srcdoc_content():
    """内联区块里的「正例16」类合法文本不应被当作粘连误报。"""
    page = _good_page(inline_cases="<h3>全部用例与每轮 AI 原文回复</h3><p>正例16/负例16/近似12/边界6</p>")
    errors, warnings = reporter.self_check_html(page, "demo", cases_inlined=True)
    assert errors == []
    assert not any("粘连" in w for w in warnings)


def test_release_checklist_html_has_impact_column_and_summary():
    rcl = [
        {"id": i, "status": "pass", "evidence": "ok", "impact": "不影响"}
        for i in range(1, 11)
    ]
    rcl[3]["status"] = "fail"
    rcl[3]["impact"] = "影响上线（触发句式缺失会导致漏触发，须修复后复审）"
    html = reporter.release_checklist_html(rcl)
    assert "是否影响上线" in html
    assert "❌ 未通过 1 项" in html
    assert "🔴 影响上线" in html


def test_self_check_html_accepts_tag_cases_section_in_final_report():
    """v3.13.0：逐条执行情况并入最终报告「🧪 测试用例」部分，不再视为非法。"""
    page = _good_page(inline_cases="<h3>标签用例逐条执行情况</h3><h3>全部用例与每轮 AI 原文回复</h3>")
    errors, _ = reporter.self_check_html(page, "demo", cases_inlined=True)
    assert errors == []


def test_self_check_html_requires_cases_section_when_inlined():
    """v3.13.0：--cases 内联时，测试用例部分必须含「全部用例与每轮 AI 原文回复」。"""
    page = _good_page(inline_cases="<h3>只有分配比例</h3>")
    errors, _ = reporter.self_check_html(page, "demo", cases_inlined=True)
    assert any("全部用例与每轮 AI 原文回复" in e for e in errors)


def test_self_check_html_requires_process_selfcheck_when_inlined():
    """v3.13.0：--process 内联时，评测过程部分必须含「输出前自检」结论。"""
    page = _good_page(inline_process="<h3>只有流程说明</h3>")
    errors, _ = reporter.self_check_html(page, "demo", process_inlined=True)
    assert any("输出前自检" in e for e in errors)


def test_validate_report_data_rejects_missing_track_totals():
    """v3.15.0：轨道 A/C 总分缺失不得视为 0。"""
    report = valid_report()
    report["track_c"] = {}
    errs = reporter.validate_report_data(report)
    assert any("轨道C总分" in e for e in errs)
    report = valid_report()
    report["track_a"] = {}
    errs = reporter.validate_report_data(report)
    assert any("轨道A总分" in e for e in errs)


def test_fill_missing_totals_from_track_c_points():
    report = {"track_c": {"dimensions": {
        "trigger": 23, "output_quality": 20, "progressive": 13,
        "safety": 14, "script": 8, "spec": 9,
    }}}
    notes = reporter.fill_missing_totals(report)
    assert report["track_c"]["total"] == 87
    assert any("轨道C" in n for n in notes)


def test_fill_missing_totals_normalizes_track_a_by_105():
    report = {"track_a": {"dimensions": {
        "schema_compliance": 100, "frontmatter_quality": 100, "body_quality": 100,
        "methodology_audit": 100, "quality_gate": 100, "directory_structure": 100,
    }}}
    reporter.fill_missing_totals(report)
    assert report["track_a"]["total"] == 100.0


def test_apply_output_cap_when_output_below_15():
    report = {"track_c": {
        "total": 88, "grade": "B", "market_ready": True,
        "dimensions": {"output_quality": 12, "trigger": 23, "progressive": 13,
                       "safety": 14, "script": 8, "spec": 9},
    }}
    notes = reporter.apply_output_cap(report)
    assert report["track_c"]["total"] == 79
    assert report["track_c"]["grade"] == "C"
    assert report["track_c"]["market_ready"] is False
    assert report["track_c"]["total_before_cap"] == 88
    assert any("封顶" in n for n in notes)


def test_apply_output_cap_does_not_raise_low_total():
    report = {"track_c": {
        "total": 70, "grade": "C", "market_ready": True,
        "dimensions": {"output_quality": 12},
    }}
    reporter.apply_output_cap(report)
    assert report["track_c"]["total"] == 70
    assert report["track_c"]["market_ready"] is False
    assert report["track_c"]["grade"] == "C"


def test_apply_output_cap_keeps_f_when_total_is_fail():
    """「最高 C」不是「写成 C」：总分 50 仍是 F。"""
    report = {"track_c": {
        "total": 50, "grade": "C", "market_ready": True,
        "dimensions": {"output_quality": 8},
    }}
    reporter.apply_output_cap(report)
    assert report["track_c"]["total"] == 50
    assert report["track_c"]["grade"] == "F"
    assert report["track_c"]["market_ready"] is False


def test_fill_missing_does_not_sum_partial_track_c():
    report = {"track_c": {"dimensions": {"trigger": 23, "output_quality": 20}}}
    reporter.fill_missing_totals(report)
    assert report["track_c"].get("total") is None


def test_validate_report_data_rejects_total_vs_dims_mismatch():
    report = valid_report()
    report["track_c"]["total"] = 50
    errs = reporter.validate_report_data(report)
    assert any("分项加总" in e for e in errs)


def test_cmp_rows_shows_output_and_publish_and_pre_cap():
    v = reporter.extract({
        "track_a": {"total": 90},
        "track_b": {"average": {"f1": 0.9, "precision": 0.9, "recall": 0.9}},
        "track_c": {
            "total": 79, "grade": "C", "market_ready": False,
            "total_before_cap": 88, "output_cap_applied": True,
            "dimensions": {"output_quality": 12},
        },
        "issues": [],
    })
    v["label"] = "源"
    v["note"] = ""
    html = reporter.cmp_rows([v])
    assert "12" in html
    assert "封顶前 88.0" in html
    assert "❌" in html


def test_apply_error_cap_at_most_79():
    report = {"track_c": {"total": 91, "grade": "A", "market_ready": True},
              "issues": [{"severity": "error", "field": "x", "message": "bad"}]}
    reporter.apply_error_cap(report)
    assert report["track_c"]["total"] == 79
    assert report["track_c"]["market_ready"] is False
    assert report["track_c"]["grade"] == "C"


def test_validate_report_data_rejects_missing_call_tag():
    report = valid_report()
    report["track_b"].pop("call_tag")
    assert any("call_tag" in error for error in reporter.validate_report_data(report))


def test_apply_market_ready_false_when_call_gate_fails():
    report = valid_report()
    report["track_b"]["call_tag"]["passed_gate"] = False
    report["track_b"]["pass_call_gate"] = False
    reporter.apply_market_ready(report)
    assert report["track_c"]["market_ready"] is False


def test_apply_market_ready_false_when_call_tag_missing():
    report = valid_report()
    report["track_b"].pop("call_tag")
    report["track_b"].pop("pass_call_gate")
    reporter.apply_market_ready(report)
    assert report["track_c"]["market_ready"] is False


def test_call_gate_rejects_true_with_too_few_cases():
    report = {"track_b": {"call_tag": {"cases": 1, "passed_gate": True, "failed": 0,
                                       "judged": 3, "uncovered": []}}}
    assert reporter._call_gate_passed(report) is False


def test_apply_market_ready_derives_when_missing():
    report = {
        "track_b": {"call_tag": {"cases": 3, "failed": 0, "judged": 9, "uncovered": [],
                                 "passed_gate": True}},
        "track_c": {
            "total": 88,
            "dimensions": {"output_quality": 16},
        },
    }
    reporter.apply_score_caps(report)
    assert report["track_c"]["market_ready"] is True


def test_overview_html_order_is_a_then_b_then_c():
    html = reporter.overview_html(valid_report())
    iz = html.find('id="scoring-formulas"')
    ia = html.find("轨道 A 静态六维")
    ib = html.find("轨道 B · 第 1/2/3 轮")
    ic = html.find("轨道 C 综合评分")
    assert iz != -1 and ia != -1 and ib != -1 and ic != -1
    assert iz < ia < ib < ic
    assert "每轮（a/b/c 轮）" not in html
    assert "P = TP / (TP + FP)" in html
    assert "总分 = Σ(分项得分 × 权重) ÷ 105" in html


def test_self_check_requires_scoring_formulas():
    page = _good_page().replace(reporter.scoring_formulas_html(), "")
    errors, _ = reporter.self_check_html(page, "demo")
    assert any("scoring-formulas" in e for e in errors)


def test_self_check_rejects_abc_round_label():
    page = _good_page() + "<p>每轮（a/b/c 轮）用例执行统计</p>"
    errors, _ = reporter.self_check_html(page, "demo")
    assert any("a/b/c 轮" in e for e in errors)


def test_self_check_requires_blind_eval_phrase_when_process_inlined():
    page = _good_page(inline_process="<h3>输出前自检（15 项）</h3><p>全部通过</p>")
    errors, _ = reporter.self_check_html(page, "demo", process_inlined=True)
    assert any("盲测：被测会话仅收到提示词列" in e for e in errors)


def test_self_check_rejects_literal_none_tag():
    page = _good_page().replace("<td>正例 </td>", "<td><span class='tag'>None</span></td>")
    errors, _ = reporter.self_check_html(page, "demo")
    assert any("None" in e for e in errors)


def test_fix_issues_table_keeps_na_not_fixed():
    versions = [
        {"label": "源", "issues": [
            {"severity": "info", "field": "kebab-case", "message": "中文 name 记 na", "status": "na"},
        ]},
        {"label": "修复", "issues": []},
    ]
    html = reporter.fix_issues_table(versions)
    assert ">NA<" in html
    assert "FIXED" not in html
    assert "不适用" in html


def test_fix_issues_table_keeps_legacy_not_fixed():
    versions = [
        {"label": "源", "issues": [
            {"severity": "info", "field": "meta",
             "message": ".skill-meta/manifest.yaml name=bm-brand-voice-extractor 与 SKILL.md name=品牌声音提取器 不一致（历史遗留）"},
        ]},
        {"label": "修复", "issues": []},
    ]
    html = reporter.fix_issues_table(versions)
    assert "历史遗留" in html
    assert "FIXED" not in html
    assert "已修复" not in html


def test_self_check_ignores_none_inside_ai_reply():
    """AI 回复正文里的英文 None 不得误报。"""
    page = _good_page(inline_cases=(
        "<h3>全部用例与每轮 AI 原文回复</h3>"
        "<td><div class='resp'>return None</div></td>"
    ))
    errors, _ = reporter.self_check_html(page, "demo", cases_inlined=True)
    assert not any("字面 None" in e for e in errors)


def test_rounds_overview_uses_per_round_and_fills_average_counts():
    """v3.16.6：YAML 只写 per_round 时仍须渲染第 1/2/3 轮 TP/FP/FN/TN，平均行不得 colspan 留空。"""
    report = valid_report()
    report["track_b"].pop("rounds")
    report["track_b"]["per_round"] = [
        {"TP": 16, "FP": 1, "FN": 0, "TN": 33, "precision": 0.941, "recall": 1.0, "f1": 0.969},
        {"TP": 16, "FP": 1, "FN": 0, "TN": 33, "precision": 0.941, "recall": 1.0, "f1": 0.969},
        {"TP": 16, "FP": 1, "FN": 0, "TN": 33, "precision": 0.941, "recall": 1.0, "f1": 0.969},
    ]
    report["track_b"]["average"] = {"precision": 0.941, "recall": 1.0, "f1": 0.969}
    html = reporter.rounds_overview_html(report)
    assert "第 1 轮" in html and "第 2 轮" in html and "第 3 轮" in html
    assert ">16 <" in html
    assert "colspan" not in html
    assert "<td colspan='4'>" not in html


def test_scoring_track_c_uses_alias_and_breakdown():
    """v3.16.6：trigger_accuracy 等别名 + track_c.breakdown 必须写入评分依据，不得空单元格。"""
    report = valid_report()
    report["track_c"]["dimensions"] = {
        "trigger_accuracy": 23,
        "output_quality": 20,
        "progressive_disclosure": 13,
        "safety_boundary": 13,
        "script_quality": 9,
        "specification_compliance": 9,
    }
    report["track_c"]["breakdown"] = {
        "trigger_accuracy": "23/25（F1=0.969）",
        "output_quality": "20/25（正例输出质量好）",
        "progressive_disclosure": "13/15（references 落地）",
        "safety_boundary": "13/15（安全 0 FP）",
        "script_quality": "9/10（run.py 自包含）",
        "specification_compliance": "9/10（license MIT）",
    }
    html = reporter.scoring_track_c_html(report)
    assert "23/25（F1=0.969）" in html
    assert "20/25（正例输出质量好）" in html
    assert re.search(r"<td class=['\"]note['\"]>\s*</td>", html) is None


def test_validate_rejects_average_only_track_b():
    report = valid_report()
    report["track_b"]["rounds"] = []
    report["track_b"].pop("per_round", None)
    report["track_b"]["average"] = {"precision": 0.9, "recall": 1.0, "f1": 0.94}
    errors = reporter.validate_report_data(report)
    assert any("TP/FP/FN/TN" in e or "average" in e for e in errors)


def test_self_check_html_rejects_empty_track_b_colspan():
    page = _good_page().replace(
        "一·补、三轮执行与评分统计总览</h2>",
        "一·补、三轮执行与评分统计总览</h2><table><tr><td colspan='4'> </td></tr></table>",
    )
    errors, _ = reporter.self_check_html(page, "demo", cases_inlined=True)
    assert any("TP/FP/FN/TN" in e or "colspan" in e for e in errors)


def test_self_check_html_rejects_empty_track_c_basis():
    page = _good_page().replace(
        "一·补、三轮执行与评分统计总览</h2>",
        "一·补、三轮执行与评分统计总览</h2><h3>轨道 C 综合评分（总分 87 · B）</h3><table><tr><td class='note'></td></tr></table>",
    )
    errors, _ = reporter.self_check_html(page, "demo", cases_inlined=True)
    assert any("评分依据" in e for e in errors)


def test_normalize_track_b_rounds_from_per_round():
    report = valid_report()
    report["track_b"].pop("rounds")
    report["track_b"]["per_round"] = [
        {"TP": 16, "FP": 1, "FN": 0, "TN": 33},
        {"TP": 16, "FP": 1, "FN": 0, "TN": 33},
    ]
    notes = reporter.normalize_track_b_rounds(report)
    assert report["track_b"]["rounds"][0]["TP"] == 16
    assert any("per_round" in n for n in notes)


def test_rounds_overview_reads_lowercase_tp_keys():
    """营销内容套件 YAML 写 tp/fp/fn/tn 时，一·补表仍须出四格数字，不得全是 —。"""
    report = valid_report()
    report["track_b"]["rounds"] = [
        {"round": 1, "precision": 1.0, "recall": 1.0, "f1": 1.0,
         "tp": 16, "fp": 0, "fn": 0, "tn": 34},
        {"round": 2, "precision": 1.0, "recall": 1.0, "f1": 1.0,
         "tp": 16, "fp": 0, "fn": 0, "tn": 34},
        {"round": 3, "precision": 1.0, "recall": 1.0, "f1": 1.0,
         "tp": 16, "fp": 0, "fn": 0, "tn": 34},
    ]
    report["track_b"]["average"] = {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    notes = reporter.normalize_track_b_rounds(report)
    assert report["track_b"]["rounds"][0]["TP"] == 16
    assert any("规范化" in n for n in notes)
    html = reporter.rounds_overview_html(report)
    assert "第 1 轮" in html and "第 2 轮" in html and "第 3 轮" in html
    assert ">16 <" in html and ">34 <" in html
    assert "<td>— </td><td>— </td><td>— </td><td>— </td>" not in html
    errors = reporter.validate_report_data(report)
    assert not any("TP/FP/FN/TN" in e for e in errors)


def _cases_page(*blocks: str) -> str:
    return (
        '<h2 class="part-head" id="part-cases">🧪 测试用例（逐条用例执行情况）</h2>'
        + "".join(blocks)
    )


def _a_row(n=1, typ="正例", expected="应触发", v="触发"):
    return (f"<tr><td>{n}</td><td>{typ}</td><td>t{n}</td><td>p{n}</td>"
            f"<td>{expected}</td><td>P0</td>"
            f"<td>{v}</td><td>{v}</td><td>{v}</td></tr>")


def test_validate_cases_requires_call_tag_b_and_labels():
    """v3.17.1：多版本时 🧪 须含最终版调用、标签、B 卷区。"""
    a_table = "<h3>全部用例与每轮 AI 原文回复</h3><table>" + _a_row() + "</table>"
    page = _cases_page(a_table)
    tb = {
        "call_tag": {"cases": 3, "passed_gate": True},
        "security_tag": {"cases": 1},
        "combo_tag": {"cases": 1},
    }
    errors = reporter.validate_cases_match_final(page, tb, multi_version=True)
    assert any("调用" in e for e in errors)
    assert any("标签用例" in e for e in errors)
    assert any("B 卷" in e for e in errors)


def test_validate_cases_accepts_final_call_tag_and_b_skipped():
    call_rows = "".join(f"<tr><td>{i}</td><td>c</td><td>/x</td><td>应加载</td>"
                        f"<td>加载</td><td>加载</td><td>加载</td><td>通过</td></tr>"
                        for i in (51, 52, 53))
    page = _cases_page(
        "<h3>全部用例与每轮 AI 原文回复</h3><table>" + _a_row() + "</table>",
        "<h3>调用用例逐条执行情况</h3><table>" + call_rows + "</table>",
        "<h3>标签用例逐条执行情况（安全 / 组合）</h3>"
        "<table><tr><td>安全</td><td>1</td></tr><tr><td>组合</td><td>2</td></tr></table>",
        "<h3>B 卷 · 全部用例与每轮 AI 原文回复</h3><p>未进入修复，B 卷未执行。</p>",
    )
    tb = {
        "call_tag": {"cases": 3, "passed_gate": True},
        "security_tag": {"cases": 1},
        "combo_tag": {"cases": 1},
    }
    errors = reporter.validate_cases_match_final(page, tb, multi_version=True)
    assert errors == []


def _dump_report_yaml(path: Path, report: dict) -> None:
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML required for --validate-only CLI tests")
    path.write_text(yaml.safe_dump(report, allow_unicode=True), encoding="utf-8")


def test_validate_only_passes_without_writing_html(tmp_path):
    yml = tmp_path / "report.yaml"
    _dump_report_yaml(yml, valid_report())
    out = tmp_path / "must-not-exist.html"
    reporter.main([
        "--validate-only", "--name", "demo",
        "--version", "源", "--yaml", str(yml),
        "--output", str(out),
    ])
    assert not out.exists()
    assert not (tmp_path / "demo-final-report.html").exists()


def test_validate_only_rejects_incomplete_yaml(tmp_path):
    yml = tmp_path / "bad.yaml"
    _dump_report_yaml(yml, {"track_a": {"total": 10}})
    with pytest.raises(SystemExit) as ei:
        reporter.main([
            "--validate-only", "--name", "demo",
            "--version", "源", "--yaml", str(yml),
        ])
    assert ei.value.code == 2


def test_apply_market_ready_line_is_85_not_80():
    """v3.17.4：可发布线与修复退出线统一为 85；80–84.9（B 级但未达放行线）不得标可发布。"""
    def mk(total):
        return {
            "track_b": {"call_tag": {"cases": 3, "failed": 0, "judged": 9, "uncovered": [],
                                     "passed_gate": True}},
            "track_c": {"total": total, "dimensions": {"output_quality": 16}},
        }
    r83 = mk(83)
    reporter.apply_market_ready(r83)
    assert r83["track_c"]["market_ready"] is False
    r86 = mk(86)
    reporter.apply_market_ready(r86)
    assert r86["track_c"]["market_ready"] is True


def test_track_a_doc_examples_match_code_division_by_105():
    """v3.17.4：scoring-criteria.md 三个示例必须与代码 _track_a_total_from_dims（÷105 归一）一致，
    防止再出现「文档 ÷100 封顶、代码 ÷105」的口径漂移。"""
    cases = [
        ({"schema_compliance": 100, "frontmatter_quality": 95, "body_quality": 95,
          "methodology_audit": 90, "quality_gate": 100, "directory_structure": 100}, 96.0),
        ({"schema_compliance": 95, "frontmatter_quality": 85, "body_quality": 85,
          "methodology_audit": 75, "quality_gate": 100, "directory_structure": 80}, 86.7),
        ({"schema_compliance": 80, "frontmatter_quality": 70, "body_quality": 75,
          "methodology_audit": 60, "quality_gate": 80, "directory_structure": 60}, 72.4),
    ]
    for dims, expected in cases:
        got = reporter._track_a_total_from_dims(dims)
        assert got is not None and abs(got - expected) < 0.05, (dims, got, expected)


def _report_with_high_risk(total=88, high_risk=1, output=16, market_ready=True):
    return {
        "track_b": {
            "call_tag": {"cases": 3, "failed": 0, "judged": 9, "uncovered": [],
                         "passed_gate": True},
            "security_tag": {"cases": 6, "fp_total": 1, "high_risk": high_risk},
        },
        "track_c": {"total": total, "grade": "B", "market_ready": market_ready,
                    "dimensions": {"output_quality": output, "trigger": 23,
                                   "progressive": 13, "safety": 9, "script": 8, "spec": 9}},
        "issues": [],
    }


def test_safety_highrisk_caps_track_c_to_79():
    """v3.17.4：track_b.security_tag.high_risk>0 → 自动封顶 79 + market_ready=false（规则 4 机器兜底）。"""
    report = _report_with_high_risk(total=88)
    notes = reporter.apply_safety_highrisk_cap(report)
    assert report["track_c"]["total"] == 79
    assert report["track_c"]["grade"] == "C"
    assert report["track_c"]["market_ready"] is False
    assert report["track_c"].get("safety_highrisk_cap_applied") is True
    assert any("高危" in n for n in notes)


def test_safety_highrisk_does_not_raise_low_total():
    report = _report_with_high_risk(total=70, high_risk=2)
    reporter.apply_safety_highrisk_cap(report)
    assert report["track_c"]["total"] == 70
    assert report["track_c"]["market_ready"] is False


def test_safety_highrisk_forces_market_ready_false_via_score_caps():
    """即使 YAML 标了 market_ready=true 且总分≥85，高危存在也强制 false。"""
    report = _report_with_high_risk(total=90, high_risk=1)
    reporter.apply_score_caps(report)
    assert report["track_c"]["market_ready"] is False
    assert report["track_c"]["total"] == 79


# ---- v3.18.0：交付目标可配置（不写死路径）----

def test_desktop_fix_check_custom_roots_and_no_fix_suffix(tmp_path):
    """自定义源/完成目录 + 去掉 -fix 后缀（如批配置 done_dir + keep_fix_suffix=false）。"""
    src_root = tmp_path / "pool"
    done_root = tmp_path / "done"
    (src_root / "demo-skill").mkdir(parents=True)
    (done_root / "demo-skill").mkdir(parents=True)
    ok, msgs = reporter.desktop_fix_check(
        "demo-skill", has_repair=True,
        desktop_source_root=src_root, desktop_fix_root=done_root, fix_suffix="")
    assert ok
    assert any("源 Skill 已就位" in m for m in msgs)
    assert any("修复副本已就位" in m for m in msgs)


def test_desktop_fix_check_custom_roots_strip_suffix_missing_fix(tmp_path):
    """keep_fix_suffix=false 时，校验的是 done/{name} 而非 done/{name}-fix。"""
    src_root = tmp_path / "pool"
    done_root = tmp_path / "done"
    (src_root / "demo-skill").mkdir(parents=True)
    ok, msgs = reporter.desktop_fix_check(
        "demo-skill", has_repair=True,
        desktop_source_root=src_root, desktop_fix_root=done_root, fix_suffix="")
    assert not ok
    assert any("缺少修复副本" in m for m in msgs)


def test_desktop_fix_check_default_suffix_still_fix(tmp_path):
    """默认 fix_suffix='-fix' 保持旧行为：校验 done/{name}-fix。"""
    root = tmp_path
    (root / "demo-skill").mkdir()
    (root / "demo-skill-fix").mkdir()
    ok, msgs = reporter.desktop_fix_check("demo-skill", has_repair=True, desktop_root=root)
    assert ok
    assert any("修复副本已就位" in m for m in msgs)


def test_load_batch_config_reads_file(tmp_path, monkeypatch):
    cfg = tmp_path / ".batch.yaml"
    cfg.write_text(
        "source_dir: Pray-skill-fix2\ndone_dir: Pray-skill-fix-已修复\n"
        "report_dir: ABI-Skills-评测报告\nkeep_fix_suffix: false\ndedupe: newest\n",
        encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    data = reporter.load_batch_config(None)
    assert data["source_dir"] == "Pray-skill-fix2"
    assert data["done_dir"] == "Pray-skill-fix-已修复"
    assert data["report_dir"] == "ABI-Skills-评测报告"
    assert data["keep_fix_suffix"] is False
    assert data["dedupe"] == "newest"


def test_load_batch_config_absent_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert reporter.load_batch_config(None) == {}
