import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.offline_review import run


class OfflineReviewTests(unittest.TestCase):
    def test_scans_asr_and_preserves_source_location(self):
        payload = {
            "review_id": "OFF-1",
            "content_id": "VID-1",
            "product_line": "吸奶器",
            "channel": "TikTok",
            "content_type": "video",
            "content_version": "v1",
            "input_manifest": {"status": "ready", "sha256": "h1"},
            "coverage": {},
            "risk_items": [],
            "version_gate": {"reviewed_hash": "h1", "release_hash": "h1"},
        }
        result = run(payload, {
            "provider": "offline",
            "provider_version": "1",
            "content_hash": "h1",
            "status": "complete",
            "asr_status": "complete",
            "ocr_status": "not_applicable",
            "keyframes_status": "complete",
            "keyframes": [{"timecode": "00:12"}],
            "ocr": [],
            "transcript": [{"text": "This pump treats plugged ducts", "timecode": "00:12"}],
        })
        self.assertEqual(result["decision"], "REVIEW")
        self.assertTrue(result["risk_items"][0]["evidence_id"].startswith("OFFLINE:asr:0:"))
        self.assertIn("00:12", result["risk_items"][0]["location"])

    def test_incomplete_offline_result_is_needs_input(self):
        payload = {
            "review_id": "OFF-2", "content_id": "VID-2", "product_line": "Baby Monitor", "channel": "TikTok",
            "content_type": "video", "content_version": "v1", "input_manifest": {"status": "ready", "sha256": "h2"},
            "coverage": {}, "risk_items": [], "version_gate": {"reviewed_hash": "h2", "release_hash": "h2"},
        }
        result = run(payload, {"provider": "offline", "provider_version": "1", "content_hash": "h2", "status": "partial"})
        self.assertEqual(result["decision"], "NEEDS_INPUT")


if __name__ == "__main__":
    unittest.main()
