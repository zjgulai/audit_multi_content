"""root-agent-doctor · 公开 seam 回归测试

seam：CLI 进程边界。测试只通过子进程调用 doctor 并断言 stdout 的 JSON 与退出码，
不 import doctor 内部模块。

期望字面量来自：
  - .scratch/root-agent-doctor/spec.md 的检查清单
  - root-agents/refs/agent-contract.yaml 的十字段
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
DOCTOR = WORKSPACE / "root-agents" / "root-agent-doctor" / "agent.py"
# ── 夹具：现场用家族自己的 creater 造一个健康业务包 ──
# 本文件声明的原则是「夹具全部现场构造，不依赖仓库内既有包」；
# 原来指向仓库内预置样例包的常量违背了这条原则，这里改回现场构造。
FAMILY = Path(__file__).resolve().parents[2]


def _build_healthy_fixture(root):
    req = {
        "name": "fixture-business-agent",
        "task_types": ["fact_qa", "reasoning", "multi_turn",
                       "instruction", "rag", "safety"],
        "tools": [{"name": "search_kb", "description": "检索知识库"}],
        "purpose": "体检/评测用的健康业务包夹具",
        "target_dir": str(root),
        "force": True,
    }
    proc = subprocess.run(
        [sys.executable, str(FAMILY / "root-agent-creater" / "agent.py")],
        input=json.dumps(req), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("fixture build failed: %s\n%s" % (proc.stdout, proc.stderr))
    return Path(root) / req["name"]


_FIXTURE_ROOT = tempfile.mkdtemp(prefix="rank-fixture-")
HEALTHY_PACKAGE = _build_healthy_fixture(_FIXTURE_ROOT)
REAL_PACKAGE = HEALTHY_PACKAGE

# 契约十字段，照抄 root-agents/refs/agent-contract.yaml
CONTRACT_FIELDS = [
    "name",
    "version",
    "interface",
    "run",
    "input",
    "profile",
    "task_types",
    "tools",
    "env",
]

MINIMAL_AGENT_YAML = """name: {name}
version: "0.1.0"
stage: create
interface: cli
run: python3 agent.py
input: stdin-json
profile: general
task_types:
  - fact_qa
tools:
  - name: search_kb
    description: 检索
    schema: {{}}
env:
  API_KEY: ${{managed}}
"""

RUNNABLE_AGENT_PY = '''#!/usr/bin/env python3
import json
import sys

raw = sys.stdin.read()
request = json.loads(raw) if raw.strip() else {}
print(json.dumps({"ok": True, "answer": "pong", "echo": request.get("question")},
                 ensure_ascii=False))
'''


def run_doctor(request, cwd=None, raw=None, timeout=180):
    payload = raw if raw is not None else json.dumps(request, ensure_ascii=False)
    proc = subprocess.run(
        [sys.executable, str(DOCTOR)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_stdout(stdout):
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"stdout 不是合法 JSON（{exc}）。实际输出前 500 字符：\n{stdout[:500]}"
        ) from exc


def check_by_id(result, check_id):
    for item in result.get("checks", []):
        if item.get("id") == check_id:
            return item
    raise AssertionError(
        f"报告缺少 check {check_id!r}。实际含："
        f"{[c.get('id') for c in result.get('checks', [])]}"
    )


def make_package(root, name, manifest=None, agent_py=RUNNABLE_AGENT_PY, extra=None):
    """现场造一个 agent 包，用于畸形用例。"""
    pkg = Path(root) / name
    (pkg / "prompts").mkdir(parents=True)
    (pkg / "tests").mkdir(parents=True)
    (pkg / "tools").mkdir(parents=True)
    (pkg / "agent.yaml").write_text(
        manifest if manifest is not None else MINIMAL_AGENT_YAML.format(name=name),
        encoding="utf-8",
    )
    if agent_py is not None:
        (pkg / "agent.py").write_text(agent_py, encoding="utf-8")
    (pkg / "prompts" / "system.md").write_text("# 提示词\n\n回答业务问题。\n", encoding="utf-8")
    (pkg / "tests" / "smoke.json").write_text(
        json.dumps({"cases": []}, ensure_ascii=False), encoding="utf-8"
    )
    (pkg / "tools" / "search_kb.py").write_text(
        "def call(**kwargs):\n    raise NotImplementedError\n", encoding="utf-8"
    )
    for rel, content in (extra or {}).items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return pkg


def snapshot(pkg):
    """记录包内每个文件的 (相对路径, mtime_ns, sha256)，用于只读性断言。"""
    result = {}
    for path in sorted(Path(pkg).rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result[str(path.relative_to(pkg))] = (stat.st_mtime_ns, digest)
    return result


class HealthyPackage(unittest.TestCase):
    """故事 1：健康包必须判 healthy，且十字段齐全。"""

    def test_real_package_is_healthy(self):
        code, stdout, stderr = run_doctor({"agent_dir": str(HEALTHY_PACKAGE)})
        self.assertEqual(
            code, 0, f"健康包应退出码 0。stderr:\n{stderr}\nstdout:\n{stdout}"
        )
        result = parse_stdout(stdout)

        self.assertIs(result.get("ok"), True)
        self.assertEqual(result.get("verdict"), "healthy")
        self.assertEqual(result.get("agent"), "root-agent-doctor")
        self.assertEqual(result.get("target"), HEALTHY_PACKAGE.name)

        # 契约十字段必须在报告里体现
        fields_check = check_by_id(result, "manifest.fields")
        self.assertEqual(fields_check["status"], "pass")
        for field in CONTRACT_FIELDS:
            self.assertIn(field, fields_check.get("detail", ""))

        # B 组实例化检查必须真的跑过
        self.assertEqual(check_by_id(result, "instantiate.run")["status"], "pass")
        self.assertEqual(check_by_id(result, "instantiate.protocol")["status"], "pass")
        self.assertEqual(check_by_id(result, "instantiate.ok_field")["status"], "pass")

        # 安全扫描必须过
        self.assertEqual(check_by_id(result, "secret.scan")["status"], "pass")
        self.assertEqual(check_by_id(result, "danger.scan")["status"], "pass")


if __name__ == "__main__":
    unittest.main(verbosity=2)
