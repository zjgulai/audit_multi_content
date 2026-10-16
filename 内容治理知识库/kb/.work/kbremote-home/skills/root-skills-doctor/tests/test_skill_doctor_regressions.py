#!/usr/bin/env python3
"""Regression tests for skill-doctor.py validator integration."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DOCTOR_PATH = REPO_ROOT / "root-skills/root-skills-doctor/scripts/skill-doctor.py"

# 修正：优先用本 skill 目录下的 skill-doctor.py（支持 root-skills 结构）
_SKILL_ROOT = Path(__file__).resolve().parents[1]
_LOCAL_DOCTOR = _SKILL_ROOT / "scripts/skill-doctor.py"
if _LOCAL_DOCTOR.exists():
    DOCTOR_PATH = _LOCAL_DOCTOR


def load_doctor_module():
    spec = importlib.util.spec_from_file_location("skill_doctor", DOCTOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


DOCTOR_MODULE = load_doctor_module()


class SkillDoctorRegressionTests(unittest.TestCase):
    def write_skill(self, root: Path) -> Path:
        skill_dir = root / "fixture-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: fixture-skill
description: This skill should be used when testing doctor regression behavior.
complexity: complex
---

# Fixture Skill

Read `references/missing.md` before use.
""",
            encoding="utf-8",
        )
        return skill_dir

    def test_validator_warnings_are_mapped_to_doctor_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = self.write_skill(Path(tmp))
            doctor = DOCTOR_MODULE.SkillDoctor(dry_run=True)

            issues = doctor.scan(skill_dir)

        issue_codes = {issue.code for issue in issues}
        self.assertIn("D004", issue_codes)
        self.assertIn("V_WARN", issue_codes)

    def test_validator_execution_failure_is_visible(self):
        original_run = DOCTOR_MODULE.subprocess.run

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, 2, stdout="", stderr="boom")

        DOCTOR_MODULE.subprocess.run = fake_run
        try:
            doctor = DOCTOR_MODULE.SkillDoctor(dry_run=True)
            doctor._run_validator(Path("fixture-skill"))
        finally:
            DOCTOR_MODULE.subprocess.run = original_run

        issue_codes = {issue.code for issue in doctor.issues}
        self.assertIn("V_RUN", issue_codes)

    def test_chinese_name_matching_dir_skips_d102(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "品牌声音提取器"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: 品牌声音提取器
description: 当用户需要提取品牌声音时使用本技能。
---

# 品牌声音提取器
""",
                encoding="utf-8",
            )
            doctor = DOCTOR_MODULE.SkillDoctor(dry_run=True)
            issues = doctor.scan(skill_dir)

        issue_codes = {issue.code for issue in issues}
        self.assertNotIn("D101", issue_codes)
        self.assertNotIn("D102", issue_codes)

    def test_shared_import_is_warning_not_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = self.write_skill(Path(tmp))
            scripts = skill_dir / "scripts"
            scripts.mkdir()
            (scripts / "run.py").write_text(
                "#!/usr/bin/env python3\nfrom skills._shared.llm_pipeline import run\n",
                encoding="utf-8",
            )
            doctor = DOCTOR_MODULE.SkillDoctor(dry_run=True)
            issues = doctor.scan(skill_dir)

        shared = [i for i in issues if i.code == "D115"]
        self.assertTrue(shared)
        self.assertEqual(shared[0].severity, "warning")


if __name__ == "__main__":
    unittest.main()
