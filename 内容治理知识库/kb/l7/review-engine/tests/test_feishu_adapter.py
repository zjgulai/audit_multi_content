import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.feishu_adapter import build_outbound, normalize_inbound, write_fallback


class FeishuAdapterTests(unittest.TestCase):
    def setUp(self):
        self.result = {
            "review_id": "R-1", "content_id": "AD-1", "content_version": "v2", "decision": "REVIEW",
            "confidence": 0.78, "summary": "需要人工复核", "next_action": "转法务和医学复核",
            "next_owners": ["法务", "医学顾问"], "sla": {"target": "4 business hours"},
            "version_gate": {"reviewed_hash": "h1", "release_hash": "h1"}, "risk_items": []
        }

    def test_inbound_maps_fields_and_preserves_sender(self):
        payload = normalize_inbound({"event_id": "e1", "source": "feishu-group", "sender_id": "u1", "fields": {"content_id": "AD-1", "sku": "SKU-1"}})
        self.assertEqual(payload["review_id"], "e1")
        self.assertEqual(payload["sku"], "SKU-1")
        self.assertEqual(payload["submission"]["sender_id"], "u1")

    def test_outbound_contains_role_mentions_and_table_patch(self):
        outbound = build_outbound(self.result, report_url="https://report.local/r1")
        self.assertEqual(outbound["idempotency_key"], "R-1:v2")
        self.assertEqual(outbound["mentions"][0]["status"], "role_placeholder")
        self.assertEqual(outbound["table_patch"]["sla_target"], "4 business hours")
        self.assertIn("{{role:legal}}", outbound["chat_message"])

    def test_fallback_write_is_idempotent(self):
        outbound = build_outbound(self.result)
        with tempfile.TemporaryDirectory() as directory:
            first = write_fallback(outbound, directory)
            second = write_fallback(outbound, directory)
            self.assertEqual(first["status"], "written")
            self.assertEqual(second["status"], "duplicate")
            self.assertTrue(Path(first["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
