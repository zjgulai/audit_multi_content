"""build-html-report.py 兼容性与安全回归测试。"""

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build-html-report.py"
spec = importlib.util.spec_from_file_location("build_html_report", SCRIPT)
reporter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(reporter)


def test_inline_allows_http_and_local_links():
    rendered = reporter.inline("[web](https://example.com) [local](report.html)")
    assert 'href="https://example.com"' in rendered
    assert 'href="report.html"' in rendered


def test_inline_rejects_active_content_schemes():
    rendered = reporter.inline(
        "[xss](javascript:alert(1)) [payload](data:text/html;base64,AAAA)"
    )
    assert 'href="javascript:' not in rendered
    assert 'href="data:' not in rendered


def test_list_is_closed_before_following_heading():
    rendered = reporter.md_to_html("- item\n## Next")
    assert rendered.index("</ul>") < rendered.index("<h2>Next</h2>")


def test_build_smoke():
    report = {
        "eval_info": {
            "skill_name": "demo-skill",
            "eval_date": "2026-08-31",
            "eval_tool": "root-skills-eval",
            "eval_tool_version": "3.9.1",
        },
        "track_a": {"total": 100, "status": "excellent", "dimensions": {}},
        "track_b": {
            "cases_total": 25,
            "average": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            "rounds": [],
            "pass_enterprise_gate": True,
        },
        "track_c": {
            "total": 95,
            "grade": "A",
            "market_ready": True,
            "dimensions": {},
        },
        "issues": [],
        "recommendation": {"verdict": "ready"},
        "release_checklist": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = tmp_path / "input-report.json"
        output_path = tmp_path / "report.html"
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

        probe = """
import subprocess
import sys
from pathlib import Path
script, source, output = sys.argv[1:]
subprocess.run([sys.executable, script, source, "--output", output], check=True)
html = Path(output).read_text(encoding="utf-8")
assert "demo-skill" in html and "F1=1.0" in html and "</html>" in html
"""
        subprocess.run(
            [sys.executable, "-c", probe, str(SCRIPT), str(report_path), str(output_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        assert output_path.exists()
