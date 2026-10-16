import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.report_memory import render_markdown, write_report


class ReportMemoryTests(unittest.TestCase):
    def test_markdown_groups_risks(self):
        result = {"review_id": "R1", "decision": "REVIEW", "risk_items": [{"risk_id": "1", "risk_type": "合规", "priority_tier": "P0", "severity": "high", "location": "caption", "reason": "需确认", "suggestion": "补证据", "evidence_id": "E1"}]}
        markdown = render_markdown(result)
        self.assertIn("### 合规", markdown)
        self.assertIn("E1", markdown)

    def test_write_report_creates_json_and_markdown(self):
        result = {"review_id": "R2", "decision": "PASS", "risk_items": []}
        with tempfile.TemporaryDirectory() as directory:
            paths = write_report(result, directory)
            self.assertTrue(Path(paths["json_path"]).is_file())
            self.assertTrue(Path(paths["markdown_path"]).is_file())
            self.assertEqual(json.loads(Path(paths["json_path"]).read_text())["review_id"], "R2")


if __name__ == "__main__":
    unittest.main()
