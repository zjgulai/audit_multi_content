import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.product_fact_approval import apply_event, make_event, rebuild_library
from core.product_fact_queue import build_queue


class ProductFactApprovalTests(unittest.TestCase):
    def setUp(self):
        seed = {
            "knowledge_version": "k1",
            "products": [{
                "sku": "SKU-1", "model": "M5", "product_line": "吸奶器", "region": "US",
                "verified_facts": [{"fact": "three modes", "value": 3}],
                "claims_requiring_evidence_or_owner_approval": [],
                "source_refs": [{"source_id": "M5-PRODUCT", "url": "https://momcozy.com/m5", "locator": "features"}],
            }]
        }
        sources = {"manifest_version": "m1", "sources": [{"source_id": "M5-PRODUCT", "fetch_status": "fetched", "snapshot_sha256": "hash"}]}
        self.queue = build_queue(seed, sources)

    def test_approval_rebuilds_active_library(self):
        fact_id = self.queue["entries"][0]["fact_id"]
        event = make_event(fact_id, decision="approved", actor="product-owner", role="product")
        apply_event(self.queue, event)
        library = rebuild_library(self.queue)
        self.assertEqual(library["status"], "active")
        self.assertEqual(library["approved_facts"][0]["value"], 3)

    def test_duplicate_event_is_idempotent(self):
        fact_id = self.queue["entries"][0]["fact_id"]
        event = make_event(fact_id, decision="approved", actor="product-owner", role="product")
        apply_event(self.queue, event)
        apply_event(self.queue, event)
        self.assertEqual(len(self.queue["processed_event_ids"]), 1)
        self.assertEqual(len(self.queue["entries"][0]["approvals"]), 1)

    def test_empty_queue_rebuild_stays_approval_required(self):
        library = rebuild_library({"entries": []})
        self.assertEqual(library["status"], "approval_required")
        self.assertEqual(library["approved_facts"], [])


if __name__ == "__main__":
    unittest.main()
