import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.source_manifest import build_manifest, canonical_url, fetch_source


class _FakeHeaders:
    def get_content_type(self):
        return "text/html"


class _FakeResponse:
    status = 200
    headers = _FakeHeaders()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return b"<html><title>Momcozy</title><body>safe text</body></html>"


class SourceManifestTests(unittest.TestCase):
    def test_canonical_url_removes_tracking_query_and_rejects_other_hosts(self):
        self.assertEqual(canonical_url("https://momcozy.com/p?a=1#x"), "https://momcozy.com/p")
        with self.assertRaises(ValueError):
            canonical_url("https://example.com/p")

    def test_build_manifest_keeps_discovery_only_status(self):
        result = build_manifest({"candidates": [{"candidate_id": "M5", "url": "https://momcozy.com/m5", "model": "M5"}]})
        self.assertEqual(result["status"], "discovery_only")
        self.assertEqual(result["sources"][0]["approval_status"], "discovery_only")

    def test_fetch_failure_is_recorded_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            result = fetch_source({"source_id": "BAD", "canonical_url": "https://example.com/not-allowed"}, directory, timeout=1)
            self.assertEqual(result["fetch_status"], "failed")
            self.assertTrue(result["fetch_error"])

    @patch("core.source_manifest.urlopen", return_value=_FakeResponse())
    def test_fetch_writes_hashable_raw_and_text_snapshots(self, _urlopen):
        with tempfile.TemporaryDirectory() as directory:
            result = fetch_source({"source_id": "M5", "canonical_url": "https://momcozy.com/m5"}, directory)
            self.assertEqual(result["fetch_status"], "fetched")
            self.assertTrue(Path(result["snapshot_path"]).is_file())
            self.assertTrue(Path(result["text_snapshot_path"]).is_file())
            self.assertEqual(result["title"], "Momcozy")


if __name__ == "__main__":
    unittest.main()
