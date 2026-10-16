import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.product_fact_integration import apply_product_fact_gates
from core.review_text import run as run_text


class ProductFactIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"sku": "SKU-1"}
        self.queue = {
            "entries": [{
                "fact_id": "F1", "sku": "SKU-1", "kind": "verified_fact", "fact": "three modes",
                "status": "pending_product_owner", "evidence_status": "evidence_ready",
                "approval_route": [{"role": "product", "owner_label": "产品负责人"}],
            }]
        }

    def test_pending_fact_becomes_review_finding(self):
        findings, gates = apply_product_fact_gates(self.payload, [{"text": "This pump has three modes", "location": "caption"}], self.queue)
        self.assertEqual(gates[0]["decision"], "REVIEW")
        self.assertEqual(findings[0]["risk_type"], "产品事实审批")

    def test_unmatched_text_has_no_gate(self):
        findings, gates = apply_product_fact_gates(self.payload, [{"text": "Wearable pump", "location": "caption"}], self.queue)
        self.assertEqual(findings, [])
        self.assertEqual(gates, [])

    def test_missing_sku_skips_gate(self):
        findings, gates = apply_product_fact_gates({}, [{"text": "three modes"}], self.queue)
        self.assertEqual(findings, [])
        self.assertEqual(gates, [])

    def test_text_pipeline_uses_real_pending_queue(self):
        payload = {
            "review_id": "FACT-1", "content_id": "TEXT-1", "product_line": "吸奶器",
            "sku": "BP078-GR00BA-A", "channel": "TikTok", "content_type": "text", "content_version": "v1",
            "input_manifest": {"status": "ready", "sha256": "h1"},
            "coverage": {"text": "complete", "image": "not_applicable", "audio": "not_applicable", "video": "not_applicable", "ocr": "not_applicable", "asr": "not_applicable", "keyframes": "not_applicable"},
            "risk_items": [], "version_gate": {"reviewed_hash": "h1", "release_hash": "h1"},
        }
        result = run_text(payload, "Our pump has three modes")
        self.assertEqual(result["decision"], "REVIEW")
        self.assertTrue(any(item["risk_type"] == "产品事实审批" for item in result["risk_items"]))


if __name__ == "__main__":
    unittest.main()
