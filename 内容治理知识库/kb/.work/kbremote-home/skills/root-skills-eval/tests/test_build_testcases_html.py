"""build-testcases-html.py v3.10.1 原文回复渲染回归测试（AI 回复必须原文逐字，禁止提炼总结）。"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build-testcases-html.py"
spec = importlib.util.spec_from_file_location("build_testcases_html", SCRIPT)
builder = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(builder)


def make_case(cid, type_val="正例", tag="", reply_len=80, rounds=3):
    """构造一条用例；reply 为定长『原文』文本（模拟 AI 实际返回的长回复）。"""
    rounds_data = []
    for i in range(rounds):
        rounds_data.append({"结论": "触发", "回复": f"AI 原文回复 {cid}-{i} " + "x" * reply_len})
    return {
        "id": str(cid),
        "标题": f"真实标题{cid}",
        "类型": type_val,
        "提示词": f"提示词{cid}",
        "预期结果": "应触发",
        "标签": tag,
        "优先级": "P0",
        "轮次": rounds_data,
    }


def test_distribution_table_includes_tags():
    cases = [make_case(1, tag="安全"), make_case(2, tag="组合"), make_case(3, tag="安全+组合")]
    html = builder.distribution_table(cases)
    assert "安全标签（叠加）" in html
    assert "组合标签（叠加）" in html
    assert "100.0% " in html  # 单元格自带尾随空格（文本化不粘连）


def test_classify_matches_score_script_semantics():
    assert builder.classify("正例", "应触发", "触发") == "TP"
    assert builder.classify("负例", "不应触发", "触发") == "FP"
    assert builder.classify("边界情况", "追问澄清", "追问") == "TN"
    assert builder.classify("调用", "应加载 x", "加载") is None


def make_call_case(cid, expected="应加载 demo", actual="加载"):
    rounds_data = [{"结论": actual, "回复": f"AI 原文回复 {cid}-{i} " + "x" * 40} for i in range(3)]
    return {
        "id": str(cid),
        "标题": f"调用{cid}",
        "类型": "调用",
        "提示词": f"/demo {cid}",
        "预期结果": expected,
        "标签": "",
        "优先级": "P0",
        "轮次": rounds_data,
    }


def test_distribution_excludes_call_from_main_pct():
    """调用不占四类分母：16 正例 + 4 调用 → 正例 100%，合计 16，不得出现 29.6%/54。"""
    cases = [make_case(i) for i in range(1, 17)]
    cases += [make_call_case(50 + i) for i in range(1, 5)]
    html = builder.distribution_table(cases)
    assert "16 条 " in html
    assert "100.0% " in html
    assert "29.6%" not in html
    assert "54 条" not in html
    assert "调用（不占条数）" in html
    assert "4 条 " in html


def test_passrate_call_uses_load_labels():
    ok = make_call_case(51, expected="应加载 demo", actual="加载")
    miss = make_call_case(52, expected="不应加载 demo", actual="未加载")
    html = builder.passrate_table([ok, miss])
    assert "6/6" in html
    assert "100.0% " in html
    assert "0/0" not in html
    assert "badge-err" not in html


def test_passrate_call_wrong_label_counts_fail():
    """加载了别的 Skill 却标「加载」→ 不应加载本 Skill 计失败。"""
    bad = make_call_case(52, expected="不应加载 demo", actual="加载")
    html = builder.passrate_table([bad])
    assert "0/3" in html
    assert "0.0% " in html


def test_passrate_call_unscored_not_err_zero():
    """调用回填了触发/不触发时显示未回填，禁止 0/0 红标。"""
    c = make_call_case(51, actual="触发")
    html = builder.passrate_table([c])
    assert "未回填" in html
    assert "0/0" not in html
    assert "badge-err'>0.0%" not in html


def test_self_check_warns_on_call_trigger_label():
    c = make_call_case(51, actual="触发")
    _, warnings = builder.self_check([c], {})
    assert any("加载/未加载" in w for w in warnings)


def test_self_check_accepts_full_replies():
    cases = [make_case(1), make_case(2)]
    errors, warnings = builder.self_check(cases, {})
    assert errors == []


def test_self_check_rejects_empty_reply():
    cases = [make_case(1)]
    cases[0]["轮次"][1] = {"结论": "触发", "回复": ""}
    errors, _ = builder.self_check(cases, {})
    assert any("回复为空" in e for e in errors)


def test_self_check_rejects_missing_rounds():
    cases = [make_case(1, rounds=2)]
    errors, _ = builder.self_check(cases, {})
    assert any("轮次不足" in e for e in errors)


def test_self_check_rejects_truncation_markers():
    cases = [make_case(1)]
    cases[0]["轮次"][0]["回复"] = "开头内容（以下省略）"
    errors, _ = builder.self_check(cases, {})
    assert any("截断/省略标记" in e for e in errors)


def test_self_check_rejects_summary_reply():
    cases = [make_case(1)]
    cases[0]["轮次"][0]["回复"] = "要点如下：触发了技能并完成了品牌声音提取。"
    errors, _ = builder.self_check(cases, {})
    assert any("要点/摘要" in e for e in errors)


def test_full_render_keeps_verbatim_reply(tmp_path):
    """渲染出的 HTML 必须包含完整原文（全量、未截断）。"""
    cases = [make_case(1, reply_len=200)]
    data = {c["id"]: c for c in cases}
    out = tmp_path / "cases.html"
    rp = tmp_path / "results.json"
    rp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    builder.main(["--name", "demo", "--results", str(rp), "--output", str(out)])
    html = out.read_text(encoding="utf-8")
    reply = cases[0]["轮次"][0]["回复"]
    # 原文被转义后仍应完整存在（& 转义不影响中文与 x 序列）
    assert reply.replace("&", "&amp;") in html
    # 无截断标记
    assert "省略" not in html


def test_rendered_html_contains_all_round_replies(tmp_path):
    cases = [make_case(1), make_case(2), make_case(3)]
    data = {c["id"]: c for c in cases}
    rp = tmp_path / "results.json"
    rp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "cases.html"
    builder.main(["--name", "demo", "--results", str(rp), "--output", str(out)])
    html = out.read_text(encoding="utf-8")
    assert html.count("class='resp'") == 9  # 3 用例 × 3 轮


def test_tag_cases_table_lists_only_tagged_cases():
    """v3.12.0：逐条执行表只列安全/组合叠加标签用例，含标签计数与判定。"""
    cases = [
        make_case(1, tag="安全"),
        make_case(2, tag="组合"),
        make_case(3, tag="安全+组合"),
        make_case(4, tag=""),
        make_case(5, tag="无标签普通用例"),
    ]
    html = builder.tag_cases_table(cases)
    assert "标签用例逐条执行情况" in html
    assert "安全标签 2 条" in html
    assert "组合标签 2 条" in html
    assert "真实标题1" in html and "真实标题3" in html
    assert "真实标题4" not in html and "真实标题5" not in html


def test_tag_cases_table_verdict_fp_when_any_round_fp():
    """负例用例实际触发 → 任一轮 FP → 判定 FP（与 score-trigger-eval 一致）。"""
    cases = [make_case(1, tag="安全", type_val="负例")]
    html = builder.tag_cases_table(cases)
    assert "badge-err'>FP" in html


def test_tag_cases_table_verdict_pass_when_no_fp():
    cases = [make_case(1, tag="组合")]
    html = builder.tag_cases_table(cases)
    assert "badge-ok'>通过" in html


def test_tag_cases_table_excludes_call_type():
    """v3.16.6：调用已在全部用例表，标签表不得再列调用。"""
    cases = [make_call_case(51, expected="应加载 demo", actual="加载")]
    html = builder.tag_cases_table(cases)
    assert html == ""
    assert "调用" not in html


def test_tag_cases_table_call_fail_not_shown_in_tag_table():
    cases = [make_call_case(52, expected="不应加载 demo", actual="加载")]
    html = builder.tag_cases_table(cases)
    assert html == ""
    assert "未通过" not in html


def test_tag_cases_table_includes_original_replies():
    """v3.16.6：安全/组合标签表必须展示 AI 原文回复。"""
    cases = [make_case(1, tag="安全")]
    html = builder.tag_cases_table(cases)
    assert "class='resp'" in html
    assert "AI 原文回复 1-0" in html
    assert "触发" in html
    assert "（安全 / 组合 / 调用）" not in html
    assert "（安全 / 组合）" in html


def test_empty_or_none_tags_not_rendered_as_literal_none():
    cases = [make_case(1, tag="None"), make_case(2, tag="")]
    html = builder.tag_cases_table(cases)
    assert html == ""
    kept = []
    for c in cases:
        for t in (c["标签"] or "").split(","):
            t = t.strip()
            if t and t.lower() not in builder.EMPTY_TAGS:
                kept.append(t)
    assert kept == []


def test_self_check_warns_on_non_self_contained_positive_prompt():
    cases = [make_case(1)]
    cases[0]["提示词"] = "文案已贴，请提取品牌声音"
    _, warnings = builder.self_check(cases, {})
    assert any("见附件/文案已贴" in w for w in warnings)


def test_rendered_html_contains_tag_cases_section(tmp_path):
    """生成的测试用例 HTML 包含「标签用例逐条执行情况」区块（最终报告底部跳转打开）。"""
    cases = [make_case(1, tag="安全"), make_case(2, tag="组合", type_val="负例")]
    data = {c["id"]: c for c in cases}
    rp = tmp_path / "results.json"
    rp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "cases.html"
    builder.main(["--name", "demo", "--results", str(rp), "--output", str(out)])
    html = out.read_text(encoding="utf-8")
    assert "标签用例逐条执行情况" in html
    assert "全部用例与每轮 AI 原文回复" in html
    assert "调用用例逐条执行情况" in html
    assert "B 卷 · 全部用例与每轮 AI 原文回复" in html
    assert "B 卷未执行" in html
    assert "（安全 / 组合 / 调用）" not in html
    assert "class='resp'" in html


def test_self_check_rejects_template_reply():
    cases = [make_case(1)]
    cases[0]["轮次"][0]["回复"] = "触发爆款视频分析器，按黄金3秒钩子输出脚本诊断"
    errors, _ = builder.self_check(cases, {})
    assert any("模板" in e for e in errors)


def test_self_check_rejects_same_long_reply_across_cases():
    blob = "【使用技能：爆款视频分析器】\n" + "这是一段足够长的伪造回复，用来检测多条用例共用模板。" * 3
    cases = []
    for i in range(1, 4):
        c = make_case(i, reply_len=10)
        c["轮次"] = [{"结论": "触发", "回复": blob} for _ in range(3)]
        cases.append(c)
    errors, _ = builder.self_check(cases, {})
    assert any("共用同一长回复" in e for e in errors)


def test_call_cases_table_lists_load_verdicts():
    html = builder.call_cases_table([
        make_call_case(51, expected="应加载 demo", actual="加载"),
        make_call_case(52, expected="不应加载 demo", actual="未加载"),
    ])
    assert "调用用例逐条执行情况" in html
    assert "加载" in html
    assert "class='resp'" in html
    assert "通过" in html


def test_b_volume_section_unexecuted_note():
    html = builder.b_volume_section(None)
    assert "B 卷 · 全部用例与每轮 AI 原文回复" in html
    assert "B 卷未执行" in html


def test_b_volume_section_renders_final_b_cases():
    b = [make_case(f"B{i}", tag="安全" if i <= 2 else "组合") for i in range(1, 11)]
    for c in b:
        c["volume"] = "B"
    html = builder.b_volume_section(b)
    assert "B1" in html
    assert "B 卷未执行" not in html
    assert "class='resp'" in html


def test_rendered_html_includes_b_results(tmp_path):
    a = {c["id"]: c for c in [make_case(1, tag="安全"), make_call_case(51)]}
    b = {f"B{i}": make_case(f"B{i}", tag="组合") for i in range(1, 11)}
    rp = tmp_path / "a.json"
    bp = tmp_path / "b.json"
    rp.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
    bp.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "cases.html"
    builder.main(["--name", "demo", "--results", str(rp), "--b-results", str(bp), "--output", str(out)])
    html = out.read_text(encoding="utf-8")
    assert "B 卷未执行" not in html
    assert "B1" in html
    assert "调用用例逐条执行情况" in html
    assert "B卷" in html


def test_check_only_does_not_write_html(tmp_path):
    a = {c["id"]: c for c in [make_case(1, tag="安全"), make_call_case(51)]}
    rp = tmp_path / "a.json"
    rp.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "cases.html"
    builder.main(["--check-only", "--name", "demo", "--results", str(rp), "--output", str(out)])
    assert not out.exists()


def test_check_only_rejects_empty_reply(tmp_path):
    case = make_case(1)
    case["轮次"][0]["回复"] = ""
    rp = tmp_path / "a.json"
    rp.write_text(json.dumps({"1": case}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        builder.main(["--check-only", "--name", "demo", "--results", str(rp)])
    assert ei.value.code == 2
