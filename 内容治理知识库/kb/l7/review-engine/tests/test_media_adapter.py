import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.media_adapter import apply_extraction, extraction_request, text_segments, validate_extraction


class MediaAdapterTests(unittest.TestCase):
    def test_request_is_provider_neutral(self):
        request = extraction_request({"content_type": "video", "sha256": "h1", "source_ref": "clip.mp4"})
        self.assertEqual(request["content_hash"], "h1")
        self.assertIn("adaptive_keyframes", request["tasks"])
        self.assertTrue(request["safety"]["no_final_decision"])

    def test_incomplete_extraction_cannot_complete_coverage(self):
        manifest = {"content_type": "video", "sha256": "h1", "coverage": {}}
        output = apply_extraction(manifest, {"provider": "mock", "provider_version": "0", "content_hash": "h1", "status": "partial"})
        self.assertEqual(output["status"], "extraction_incomplete")
        self.assertEqual(output["coverage"]["keyframes"], "incomplete")

    def test_hash_mismatch_fails(self):
        manifest = {"content_type": "image", "sha256": "h1", "coverage": {}}
        output = apply_extraction(manifest, {"provider": "mock", "provider_version": "0", "content_hash": "h2", "status": "complete"})
        self.assertEqual(output["status"], "failed")
        self.assertIn("content_hash_mismatch", output["extraction"]["errors"])

    def test_complete_video_requires_status_fields_and_artifacts(self):
        manifest = {"content_type": "video", "sha256": "h1", "coverage": {}}
        output = apply_extraction(manifest, {
            "provider": "offline",
            "provider_version": "1",
            "content_hash": "h1",
            "status": "complete",
            "keyframes": [{"timecode": "00:01", "observation": "pump"}],
            "asr_status": "complete",
            "ocr_status": "complete",
            "keyframes_status": "complete",
            "transcript": [{"text": "safe for baby", "timecode": "00:01"}],
        })
        self.assertEqual(output["status"], "ready")
        self.assertEqual(output["coverage"]["video"], "complete")
        self.assertEqual(text_segments({"transcript": [{"text": "hello"}], "ocr": []})[0]["kind"], "asr")

    def test_complete_video_without_keyframe_status_stays_incomplete(self):
        errors = validate_extraction(
            {"content_type": "video", "sha256": "h1"},
            {"provider": "offline", "provider_version": "1", "content_hash": "h1", "status": "complete", "keyframes": []},
        )
        self.assertIn("invalid:asr_status", errors)

    def test_visual_observation_can_feed_claim_gate(self):
        segments = text_segments({"observations": [{"observation": "8 bottles", "region": "center"}]})
        self.assertEqual(segments[0]["kind"], "observation")
        self.assertEqual(segments[0]["text"], "8 bottles")


if __name__ == "__main__":
    unittest.main()
