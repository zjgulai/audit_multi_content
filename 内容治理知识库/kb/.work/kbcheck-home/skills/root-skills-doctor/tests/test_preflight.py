import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "doctor-preflight.py"


def _skill_md(body: str = "## 正文\n\n一些内容\n") -> str:
    return (
        "---\n"
        "name: fixture-skill\n"
        "description: |\n"
        "  当用户请求特定操作时使用本技能。\n"
        "  触发词：特定操作。\n"
        'version: "1.0.0"\n'
        'complexity: "standard"\n'
        "compatibility:\n"
        '  dsh: { status: "native" }\n'
        "---\n\n# Fixture Skill\n\n" + body
    )


def _make_source(tmp: Path) -> Path:
    src = tmp / "src"
    a = src / "skillA"
    a.mkdir(parents=True)
    (a / "SKILL.md").write_text(
        "---\n"
        "name: skillA\n"
        "description: 用于做某事的功能描述。\n"   # 故意：非触发句式 + 缺 license/last_updated
        'version: "1.0.0"\n'
        "---\n\n# SkillA\n\n正文\n", encoding="utf-8")
    (a / "notes.md").write_bytes(b"abc\xff\xfebad")  # 坏编码
    (a / "scripts").mkdir()
    (a / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")

    b = src / "skillB"
    inner = b / "skillB"
    inner.mkdir(parents=True)
    (inner / "SKILL.md").write_text(_skill_md(), encoding="utf-8")
    return src


def test_dry_run_does_not_write(tmp_path):
    src = _make_source(tmp_path)
    out = tmp_path / "prepared"
    r = subprocess.run([sys.executable, str(SCRIPT), str(src), "--out", str(out), "--dry-run"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "dry-run" in r.stdout
    assert not out.exists()


def test_apply_fixes_copies_and_keeps_source(tmp_path):
    src = _make_source(tmp_path)
    before = {p.name: p.read_bytes() for p in src.rglob("*") if p.is_file()}
    out = tmp_path / "prepared"
    r = subprocess.run([sys.executable, str(SCRIPT), str(src), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    # 源只读
    after = {p.name: p.read_bytes() for p in src.rglob("*") if p.is_file()}
    assert before == after

    sa = out / "skillA" / "SKILL.md"
    txt = sa.read_text(encoding="utf-8")
    assert "license: MIT" in txt
    assert "last_updated:" in txt
    assert "## Safety Boundaries" in txt and "安全边界" in txt
    assert "## Error Handling" in txt and "错误处理" in txt
    (out / "skillA" / "notes.md").read_text(encoding="utf-8")  # 编码已修

    assert (out / "skillB" / "SKILL.md").exists()          # 嵌套已展平
    assert not (out / "skillB" / "skillB").exists()
    report = out / "preflight-report.yaml"
    assert report.exists() and "skillA" in report.read_text(encoding="utf-8")
