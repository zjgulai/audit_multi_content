import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.report_memory import render_markdown, write_report


class ReportMemoryTests(unittest.TestCase):
    def test_markdown_groups_risks(self):
        """★★ 2026-10-19（Owner：「报告要同步 卡上 12 类呀，**整个知识库都要同步**」）。

        分组轴从 **A2 四维**（`risk_category`）换成 **A3 12 类**（`taxonomy_category`）。
        这条用例的**防护意图一个字没改**：分组标题必须是「分类」，而且没给的条目
        **不许编一个类**（落 `未归类` 兜底），证据 id 照旧在。
        """
        result = {"review_id": "R1", "decision": "REVIEW", "risk_items": [
            {"risk_id": "1", "risk_type": "合规", "taxonomy_category": "合规与受监管宣称",
             "taxonomy_subcategory": "生理功效与效果承诺", "priority_tier": "P0", "severity": "high",
             "location": "caption", "reason": "需确认", "suggestion": "补证据", "evidence_id": "E1"},
            # 反向对照用的第二条：**没有** `taxonomy_category` ⇒ 只能落兜底类
            {"risk_id": "2", "risk_type": "合规", "priority_tier": "P1", "severity": "low",
             "location": "caption", "reason": "需确认", "suggestion": "补证据", "evidence_id": "E2"}]}
        markdown = render_markdown(result)
        self.assertIn("### 合规与受监管宣称", markdown, "没按 A3 12 类分组")
        self.assertIn("### 未归类", markdown, "没给分类的条目应落 `未归类` 兜底，而不是被编进某一类")
        self.assertNotIn("### 合规\n", markdown, "分组标题又变成四维的「合规」了")
        self.assertIn("E1", markdown)

    def test_write_report_creates_json_and_markdown(self):
        result = {"review_id": "R2", "decision": "PASS", "risk_items": []}
        with tempfile.TemporaryDirectory() as directory:
            paths = write_report(result, directory)
            self.assertTrue(Path(paths["json_path"]).is_file())
            self.assertTrue(Path(paths["markdown_path"]).is_file())
            self.assertEqual(json.loads(Path(paths["json_path"]).read_text())["review_id"], "R2")

    def test_history_rule_is_distinct_from_current_material_and_links_source(self):
        markdown = render_markdown({"review_id": "R3", "decision": "REVIEW", "risk_items": [{
            "risk_id": "N-1.317", "risk_type": "负面样本", "location": "图片",
            "history_rule_text": "这个质感好像不对。避免太靠图片下方。",
            "history_attribution": "该记录的历史意见（未指定图号）",
            "evidence": {"l0_entry_url": "https://example.test/record"},
        }], "decision_trace": {"image_identity": {
            "checked": True, "detected": 1, "added": 0, "upgraded": 1,
            "hits": [{"article_no": "N-1.317", "record_id": "recA", "attribution": "subject"}],
        }}})
        self.assertIn("历史规则意见（非本素材原文", markdown)
        self.assertIn("这个质感好像不对。避免太靠图片下方。", markdown)
        self.assertIn("https://example.test/record", markdown)
        self.assertIn("原文/观察：未提供", markdown)
        self.assertIn("图片身份层：已检查；检测 1 条，新增 0 条，升级 1 条", markdown)
        self.assertIn('"article_no": "N-1.317"', markdown)

    def test_full_source_analysis_and_advice_are_rendered_as_history(self):
        markdown = render_markdown({"review_id": "R4", "decision": "REVIEW", "risk_items": [{
            "risk_id": "N-1.312", "risk_type": "负面样本", "location": "图 1",
            "history_record_id": "recA", "history_scope": "record_level",
            "history_analysis": "【问题要点】\n1. 错误示范面板：婴儿侧睡。\n2. 正确建议：仰睡。",
            "history_advice": "同房不同床，宝宝睡独立婴儿床。",
            "evidence": {"l0_entry_url": "https://example.test/record"},
        }]})
        self.assertIn("历史审核完整分析（来源记录 recA", markdown)
        self.assertIn("错误示范面板：婴儿侧睡", markdown)
        self.assertIn("历史源建议（来源记录 recA", markdown)
        self.assertIn("同房不同床，宝宝睡独立婴儿床。", markdown)
        self.assertIn("https://example.test/record", markdown)


if __name__ == "__main__":
    unittest.main()
