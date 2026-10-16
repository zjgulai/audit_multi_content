import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.product_fact_queue import approved_facts, build_queue, product_fact_gate, record_approval


class ProductFactQueueTests(unittest.TestCase):
    def setUp(self):
        self.seed = {
            "knowledge_version": "k1",
            "products": [{
                "sku": "SKU-1", "model": "M5", "product_line": "吸奶器", "region": "US",
                "verified_facts": [{"fact": "three modes", "value": 3, "source_id": "MOM-M5-PRODUCT"}],
                "claims_requiring_evidence_or_owner_approval": ["painless pumping"],
                "source_refs": [{"source_id": "MOM-M5-PRODUCT", "url": "https://momcozy.com/m5", "locator": "features"}],
            }]
        }
        self.sources = {"manifest_version": "m1", "sources": [{"source_id": "M5-PRODUCT", "fetch_status": "fetched", "snapshot_sha256": "hash"}]}

    def test_build_resolves_mom_source_ids_and_requires_approval(self):
        policy = {
            "approval_policy_version": "p1",
            "matrix": {"verified_fact": ["product"], "objective_or_comparative_claim": ["product", "legal"], "health_safety_efficacy_claim": ["product", "legal", "medical"]},
            "health_safety_efficacy_tokens": ["painless"]
        }
        queue = build_queue(self.seed, self.sources, {"roles": {"product": "产品负责人", "legal": "法务", "medical": "医学顾问"}}, policy)
        self.assertEqual(len(queue["entries"]), 2)
        self.assertEqual(queue["entries"][0]["evidence_status"], "evidence_ready")
        self.assertEqual(queue["entries"][0]["status"], "pending_product_owner")
        self.assertEqual(queue["entries"][0]["approval_route"][0]["owner_label"], "产品负责人")
        self.assertEqual(queue["approval_policy_version"], "p1")

    def test_all_required_roles_must_approve_claim(self):
        queue = build_queue(self.seed, self.sources)
        claim = next(e for e in queue["entries"] if e["kind"] == "claim_phrase")
        record_approval(queue, claim["fact_id"], decision="approved", actor="p", role="product")
        self.assertEqual(claim["status"], "pending_product_legal_review")
        record_approval(queue, claim["fact_id"], decision="approved", actor="l", role="legal", approved_wording="Use only with approved substantiation.")
        record_approval(queue, claim["fact_id"], decision="approved", actor="m", role="medical")
        self.assertEqual(claim["status"], "approved")
        self.assertEqual(len(approved_facts(queue)), 1)

    def test_unfetched_source_cannot_be_approved(self):
        sources = {"manifest_version": "m1", "sources": [{"source_id": "M5-PRODUCT", "fetch_status": "failed"}]}
        queue = build_queue(self.seed, sources)
        fact = queue["entries"][0]
        self.assertEqual(fact["status"], "evidence_gap")
        record_approval(queue, fact["fact_id"], decision="approved", actor="p", role="product")
        self.assertEqual(fact["status"], "evidence_gap")

    def test_pending_fact_blocks_product_support(self):
        queue = build_queue(self.seed, self.sources, {"roles": {"product": "产品负责人", "legal": "法务", "medical": "医学顾问"}})
        result = product_fact_gate(queue, "SKU-1", "three modes")
        self.assertEqual(result["decision"], "REVIEW")
        self.assertFalse(result["eligible_for_product_fact_support"])


if __name__ == "__main__":
    unittest.main()
