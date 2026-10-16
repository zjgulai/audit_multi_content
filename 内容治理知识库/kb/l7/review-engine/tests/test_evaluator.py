import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.evaluator import evaluate


class EvaluatorTests(unittest.TestCase):
    def test_metrics_keep_denominators(self):
        result = evaluate([
            {"expected_decision": "PASS", "actual_decision": "PASS"},
            {"expected_decision": "BLOCK", "actual_decision": "REVIEW", "p0_should_hit": True, "p0_hit": False},
            {"expected_decision": "REVIEW", "actual_decision": "REVIEW"},
            {"expected_decision": "REVIEW", "actual_decision": "PASS"}
        ])
        self.assertEqual(result["sample_count"], 4)
        self.assertEqual(result["three_state_accuracy"], 0.5)
        self.assertEqual(result["p0_miss_rate"], 1.0)
        self.assertEqual(result["denominators"]["predicted_pass"], 2)


if __name__ == "__main__":
    unittest.main()
