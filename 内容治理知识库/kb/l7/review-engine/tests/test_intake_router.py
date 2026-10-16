import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.intake_router import load_batch, manifest_from_source, normalize_batch


class IntakeRouterTests(unittest.TestCase):
    def test_text_manifest_has_hash(self):
        result = manifest_from_source({"kind": "text", "value": "hello"}, content_id="T1")
        self.assertEqual(result["content_type"], "text")
        self.assertEqual(len(result["sha256"]), 64)

    def test_url_is_pending_fetch(self):
        result = manifest_from_source({"kind": "url", "url": "https://momcozy.com/products/example"}, content_id="U1")
        self.assertEqual(result["status"], "url_pending_fetch")

    def test_batch_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            path.write_text(json.dumps([{"content_id": "B1", "text": "hello", "channel": "TikTok"}]), encoding="utf-8")
            rows = normalize_batch(path)
            self.assertEqual(rows[0]["content_id"], "B1")
            self.assertEqual(rows[0]["channel"], "TikTok")


if __name__ == "__main__":
    unittest.main()
