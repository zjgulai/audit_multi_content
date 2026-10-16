"""root-skills-batch-driver 回归测试（Iron Law RED 场景）。

覆盖：scan 幂等与分桶、timeout 映射、heartbeat 判 stale、
record 状态/事件/attempts、summary 聚合与 score 归档。
"""

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"

# 脚本名带连字符，无法直接 import；按文件路径加载为模块
_spec = importlib.util.spec_from_file_location("batch_driver", SCRIPTS / "batch-driver.py")
bd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bd)


def _mk_skill(root: Path, name: str) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    return d


class TestTimeout(unittest.TestCase):
    def test_complex_maps_to_25(self):
        self.assertEqual(bd.timeout_for("complex"), 25)

    def test_standard_and_simple_map_to_15(self):
        self.assertEqual(bd.timeout_for("standard"), 15)
        self.assertEqual(bd.timeout_for("simple"), 15)

    def test_unknown_falls_back_to_15(self):
        self.assertEqual(bd.timeout_for("weird"), 15)
        self.assertEqual(bd.timeout_for(None), 15)


class TestScan(unittest.TestCase):
    def test_scan_discovers_only_skill_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mk_skill(root, "a-skill")
            _mk_skill(root, "b-skill")
            (root / "not-a-skill").mkdir()
            self.assertEqual(bd.scan_skills(root), ["a-skill", "b-skill"])

    def test_scan_is_idempotent_and_marks_removed_as_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mk_skill(root, "a-skill")
            state_path = root / "state" / "batch-progress.json"
            r = bd._dispatch({"action": "scan", "skills_dir": str(root),
                              "state_path": str(state_path)})
            self.assertTrue(r["ok"])
            self.assertEqual(r["pending"], ["a-skill"])

            # 第二次 scan 不重复、不丢状态
            r2 = bd._dispatch({"action": "scan", "skills_dir": str(root),
                               "state_path": str(state_path)})
            self.assertEqual(r2["pending"], ["a-skill"])

            # 移除 skill 后 scan → skipped
            os.remove(root / "a-skill" / "SKILL.md")
            r3 = bd._dispatch({"action": "scan", "skills_dir": str(root),
                               "state_path": str(state_path)})
            self.assertEqual(r3["total"], 0)
            self.assertEqual(r3["skipped"], ["a-skill"])


class TestHeartbeat(unittest.TestCase):
    def test_empty_dir_not_stale(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            r = bd._dispatch({"action": "heartbeat",
                              "progress_dir": str(root / "empty")})
            self.assertTrue(r["ok"])
            self.assertIsNone(r["latest_mtime"])
            self.assertFalse(r["stale"])

    def test_recent_file_not_stale(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "results.json").write_text("{}", encoding="utf-8")
            r = bd._dispatch({"action": "heartbeat",
                              "progress_dir": str(root), "timeout_minutes": 15})
            self.assertTrue(r["ok"])
            self.assertFalse(r["stale"])
            self.assertGreaterEqual(r["seconds_idle"], 0)

    def test_old_file_is_stale(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "results.json"
            f.write_text("{}", encoding="utf-8")
            old = time.time() - 3600  # 1 小时前
            os.utime(f, (old, old))
            r = bd._dispatch({"action": "heartbeat",
                              "progress_dir": str(root), "timeout_minutes": 15})
            self.assertTrue(r["ok"])
            self.assertTrue(r["stale"])


class TestRecordAndSummary(unittest.TestCase):
    def test_record_running_increments_attempts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mk_skill(root, "a-skill")
            state_path = root / "state" / "batch-progress.json"
            bd._dispatch({"action": "scan", "skills_dir": str(root),
                          "state_path": str(state_path)})
            bd._dispatch({"action": "record", "state_path": str(state_path),
                          "skill": "a-skill", "status": "running",
                          "complexity": "complex"})
            st = bd.load_state(state_path)
            self.assertEqual(st["skills"]["a-skill"]["attempts"], 1)
            self.assertEqual(st["skills"]["a-skill"]["timeout_minutes"], 25)

    def test_summary_aggregates_score_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mk_skill(root, "a-skill")
            _mk_skill(root, "b-skill")
            state_path = root / "state" / "batch-progress.json"
            bd._dispatch({"action": "scan", "skills_dir": str(root),
                          "state_path": str(state_path)})
            bd._dispatch({"action": "record", "state_path": str(state_path),
                          "skill": "a-skill", "status": "done", "score": 91})
            # b-skill 无 state score，但有 evals/score.json
            evals = root / "b-skill" / "evals"
            evals.mkdir(parents=True, exist_ok=True)
            (evals / "score.json").write_text(
                json.dumps({"composite_100": 70}), encoding="utf-8")
            bd._dispatch({"action": "record", "state_path": str(state_path),
                          "skill": "b-skill", "status": "done"})

            r = bd._dispatch({"action": "summary", "state_path": str(state_path),
                              "skills_dir": str(root)})
            self.assertTrue(r["ok"])
            s = r["batch_summary"]
            self.assertEqual(s["total_skills"], 2)
            self.assertEqual(s["evaluated"], 2)
            self.assertEqual(s["passed"], 1)
            self.assertEqual(s["failed"], 1)

    def test_repeat_attempt_marked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mk_skill(root, "a-skill")
            state_path = root / "state" / "batch-progress.json"
            bd._dispatch({"action": "scan", "skills_dir": str(root),
                          "state_path": str(state_path)})
            bd._dispatch({"action": "record", "state_path": str(state_path),
                          "skill": "a-skill", "status": "running"})
            bd._dispatch({"action": "record", "state_path": str(state_path),
                          "skill": "a-skill", "status": "stuck",
                          "event_type": "timeout", "note": "无进展超时"})
            bd._dispatch({"action": "record", "state_path": str(state_path),
                          "skill": "a-skill", "status": "running",
                          "event_type": "restart"})
            r = bd._dispatch({"action": "summary", "state_path": str(state_path),
                              "skills_dir": str(root)})
            self.assertIn("a-skill", r["batch_summary"]["repeat_attempt_skills"])


class TestErrors(unittest.TestCase):
    def test_unknown_action(self):
        r = bd._dispatch({"action": "nope"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"]["code"], "unknown_action")

    def test_missing_skills_dir(self):
        r = bd._dispatch({"action": "scan", "skills_dir": "/no/such/dir",
                          "state_path": "/tmp/x.json"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"]["code"], "FileNotFoundError")


if __name__ == "__main__":
    unittest.main()
