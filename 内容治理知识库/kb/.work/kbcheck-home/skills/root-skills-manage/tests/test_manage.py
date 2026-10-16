"""manage.py 核心逻辑回归测试。

覆盖 _member_skill_version、cmd_route 路由、cmd_check 一致性（含 schema 单一事实来源校验）。
"""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manage.py"
spec = importlib.util.spec_from_file_location("manage", SCRIPT)
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


def _fake_registry():
    return {
        "family": "root-skills",
        "members": [
            {"name": "root-skills-creator", "role": "create", "status": "active",
             "path": "../../root-skills-creator", "depends_on": ["root-skills-eval", "root-skills-opt"]},
            {"name": "root-skills-manage", "role": "manage", "status": "active",
             "path": "..", "depends_on": []},
            {"name": "root-skills-doctor", "role": "diagnose", "status": "active",
             "path": "../../root-skills-doctor", "depends_on": ["root-skills-creator"]},
            {"name": "root-skills-eval", "role": "evaluate", "status": "active",
             "path": "../../root-skills-eval", "depends_on": ["root-skills-doctor"]},
            {"name": "root-skills-opt", "role": "optimize", "status": "active",
             "path": "../../root-skills-opt",
             "depends_on": ["root-skills-eval", "root-skills-doctor", "root-skills-creator"]},
        ],
    }


# ---- _member_skill_version：解析 frontmatter version ----

def test_member_skill_version(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\nname: demo\nversion: 2.3.1\n---\n正文\n", encoding="utf-8"
    )
    assert manage._member_skill_version(tmp_path) == "2.3.1"


def test_member_skill_version_missing(tmp_path):
    assert manage._member_skill_version(tmp_path) is None


# ---- cmd_route：请求 → 家族成员路由 ----

def test_route_diagnose(monkeypatch, capsys):
    monkeypatch.setattr(manage, "_load_registry", _fake_registry)
    manage.cmd_route("修复 skill 目录结构")
    assert "root-skills-doctor" in capsys.readouterr().out


def test_route_diagnose_skill_structure(monkeypatch, capsys):
    monkeypatch.setattr(manage, "_load_registry", _fake_registry)
    manage.cmd_route("修复 skill 结构")
    assert "root-skills-doctor" in capsys.readouterr().out


def test_route_optimize(monkeypatch, capsys):
    monkeypatch.setattr(manage, "_load_registry", _fake_registry)
    manage.cmd_route("根据评估报告优化这个 skill")
    assert "root-skills-opt" in capsys.readouterr().out


def test_route_evaluate(monkeypatch, capsys):
    monkeypatch.setattr(manage, "_load_registry", _fake_registry)
    manage.cmd_route("评估这个 skill 的质量")
    assert "root-skills-eval" in capsys.readouterr().out


def test_route_create(monkeypatch, capsys):
    monkeypatch.setattr(manage, "_load_registry", _fake_registry)
    manage.cmd_route("创建一个新的 skill")
    assert "root-skills-creator" in capsys.readouterr().out


def test_route_manage(monkeypatch, capsys):
    monkeypatch.setattr(manage, "_load_registry", _fake_registry)
    manage.cmd_route("查看家族成员列表")
    assert "root-skills-manage" in capsys.readouterr().out


def test_route_unclear(monkeypatch, capsys):
    monkeypatch.setattr(manage, "_load_registry", _fake_registry)
    manage.cmd_route("随便说点什么")
    assert "无法明确路由" in capsys.readouterr().out


# ---- cmd_check：一致性校验 + schema 单一事实来源校验（真实家族） ----

def test_check_family_consistent():
    # 直接跑真实家族的 check，验证注册表一致且 schema 三副本 md5 一致
    assert manage.cmd_check() == 0



def _write_registry_fixture(tmp_path):
    family = tmp_path / "root-skills"
    registry_path = family / "root-skills-manage" / "registry" / "skills.json"
    registry_path.parent.mkdir(parents=True)

    member_specs = [
        ("root-skills-creator", "4.1.1", "create", ["root-skills-eval", "root-skills-opt"]),
        ("root-skills-manage", "1.0.1", "manage", []),
        ("root-skills-doctor", "2.0.2", "diagnose", ["root-skills-creator"]),
        ("root-skills-eval", "3.8.1", "evaluate", ["root-skills-doctor"]),
        (
            "root-skills-opt",
            "3.4.1",
            "optimize",
            ["root-skills-eval", "root-skills-doctor", "root-skills-creator"],
        ),
    ]
    members = []
    for name, version, role, dependencies in member_specs:
        skill_dir = family / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\nversion: \"{version}\"\n"
            "description: fixture\n---\nbody\n",
            encoding="utf-8",
        )
        members.append(
            {
                "name": name,
                "path": ".." if name == "root-skills-manage" else f"../../{name}",
                "status": "active",
                "version": version,
                "role": role,
                "description": "fixture",
                "depends_on": dependencies,
            }
        )

    for name in ("root-skills-creator", "root-skills-eval", "root-skills-opt"):
        refs = family / name / "references"
        refs.mkdir()
        (refs / "universal-skill-schema.md").write_text("same", encoding="utf-8")

    data = {
        "family": "root-skills",
        "root_dir": "../..",
        "version": "2.0.1",
        "updated_at": "2026-08-31",
        "members": members,
    }
    registry_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return registry_path, data


def test_check_rejects_version_drift(tmp_path, monkeypatch, capsys):
    registry_path, data = _write_registry_fixture(tmp_path)
    data["members"][0]["version"] = "9.9.9"
    registry_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(manage, "REGISTRY", registry_path)

    assert manage.cmd_check() == 1
    assert "版本不一致" in capsys.readouterr().out


def test_check_rejects_unregistered_dependency(tmp_path, monkeypatch, capsys):
    registry_path, data = _write_registry_fixture(tmp_path)
    data["members"][0]["depends_on"].append("root-skills-missing")
    registry_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(manage, "REGISTRY", registry_path)

    assert manage.cmd_check() == 1
    assert "依赖未登记" in capsys.readouterr().out


def test_check_rejects_path_escape(tmp_path, monkeypatch, capsys):
    registry_path, data = _write_registry_fixture(tmp_path)
    data["members"][4]["path"] = "../../../outside"
    registry_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(manage, "REGISTRY", registry_path)

    assert manage.cmd_check() == 1
    assert "路径逃出家族根目录" in capsys.readouterr().out


def test_register_rejects_invalid_name_and_escape(tmp_path, monkeypatch):
    registry_path, _ = _write_registry_fixture(tmp_path)
    monkeypatch.setattr(manage, "REGISTRY", registry_path)

    assert manage.cmd_register("Bad_Name", "../../new-skill", "create", "") == 1
    assert manage.cmd_register("new-skill", "../../../outside", "create", "") == 1
