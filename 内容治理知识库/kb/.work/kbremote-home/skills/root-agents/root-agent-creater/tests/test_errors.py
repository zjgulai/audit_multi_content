"""root-agent-creater · 错误路径与离线退化回归测试

seam：CLI 进程边界。期望字面量来自 .scratch/root-agent-creater/spec.md 的故事 4–13。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
CREATOR = WORKSPACE / "root-agents" / "root-agent-creater" / "agent.py"

VALID_REQUEST = {
    "name": "brand-pr-agent",
    "purpose": "回答品牌公关业务问题",
    "profile": "general",
    "task_types": ["fact_qa", "safety"],
    "tools": [{"name": "search", "description": "检索品牌知识库"}],
}


def run_creator(request, target_dir=None, raw=None, timeout=60):
    if raw is not None:  # 注意：raw="" 也是「显式传了原始串」
        payload = raw
    else:
        body = dict(request)
        if target_dir is not None:
            body["target_dir"] = str(target_dir)
        payload = json.dumps(body, ensure_ascii=False)
    proc = subprocess.run(
        [sys.executable, str(CREATOR)],
        input=payload,
        capture_output=True,
        text=True,
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


class RejectsBadInput(unittest.TestCase):
    """故事 4–8：输入不合规时必须结构化失败，且不留半截产物。"""

    def assert_fails_with(self, label, payload, error_code, raw=None, **extra_expected):
        proc_dir = tempfile.mkdtemp()
        returncode, stdout, stderr = run_creator(payload, target_dir=proc_dir, raw=raw)
        self.assertNotEqual(returncode, 0, f"应退出码非零。stdout:\n{stdout}")
        result = parse_stdout(stdout)
        self.assertIs(result.get("ok"), False)
        self.assertEqual(result["error"]["code"], error_code, f"实际：{result['error']}")
        for key, value in extra_expected.items():
            self.assertEqual(result["error"].get(key), value)
        # 不留半截产物
        leftovers = list(Path(proc_dir).iterdir())
        self.assertEqual(leftovers, [], f"失败时不应留下产物：{leftovers}")

    def test_malformed_json_is_invalid_input(self):
        self.assert_fails_with("malformed-json", None, "invalid_input",
                               raw="{这不是 JSON")

    def test_empty_stdin_is_invalid_input(self):
        self.assert_fails_with("empty-stdin", None, "invalid_input", raw="")

    def test_missing_name_is_missing_field(self):
        request = {k: v for k, v in VALID_REQUEST.items() if k != "name"}
        self.assert_fails_with("missing_field", request, "missing_field", field="name")

    def test_non_kebab_name_is_invalid_name(self):
        request = dict(VALID_REQUEST, name="Brand_PR_Agent")
        self.assert_fails_with("invalid_name", request, "invalid_name", field="name")

    def test_unknown_dimension_is_rejected(self):
        request = dict(VALID_REQUEST, task_types=["fact_qa", "telepathy"])
        self.assert_fails_with(
            "unknown_dimension", request, "unknown_dimension", field="task_types"
        )

    def test_tool_required_not_declared_is_unknown_tool(self):
        request = dict(VALID_REQUEST, tool_required=["nonexistent-tool"])
        self.assert_fails_with("unknown_tool", request, "unknown_tool",
                               tool="nonexistent-tool")


class TargetDirectoryGuard(unittest.TestCase):
    """故事 10：同名目录默认拒绝覆盖，force 才覆盖。"""

    def test_existing_target_is_rejected_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _ = run_creator(VALID_REQUEST, target_dir=tmp)
            self.assertEqual(code, 0, stdout)

            code2, stdout2, _ = run_creator(VALID_REQUEST, target_dir=tmp)
            self.assertNotEqual(code2, 0, "第二次应拒绝覆盖")
            result = parse_stdout(stdout2)
            self.assertEqual(result["error"]["code"], "target_exists")

            code3, stdout3, _ = run_creator(
                dict(VALID_REQUEST, force=True), target_dir=tmp
            )
            self.assertEqual(code3, 0, f"force:true 应允许覆盖。stdout:\n{stdout3}")


class OfflineDegradation(unittest.TestCase):
    """故事 12：没有模型端点也必须产出完整结构，只加 warning。"""

    def test_missing_llm_endpoint_still_produces_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "HOME": tmp,
                # 故意不注入 ROOT_AGENT_LLM_*
            }
            body = json.dumps(dict(VALID_REQUEST, target_dir=tmp), ensure_ascii=False)
            proc = subprocess.run(
                [sys.executable, str(CREATOR)],
                input=body,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, f"stderr:\n{proc.stderr}")
            result = json.loads(proc.stdout)
            self.assertIs(result["ok"], True)
            self.assertIn("llm_unavailable", result["warnings"])

            prompt = (Path(tmp) / "brand-pr-agent" / "prompts" / "system.md")
            self.assertTrue(prompt.is_file(), "退化路径仍须产出 system.md")
            text = prompt.read_text(encoding="utf-8")
            # 硬约束必须注入（VoltAgent issue #300 的反面教训）
            self.assertIn("N/A", text, "必须注入「数不出来就写 N/A」的硬约束")


class GeneratedAgentIsRunnable(unittest.TestCase):
    """故事 2：生成物必须真的能跑，而不是只有文件存在。"""

    def test_generated_agent_runs_via_stdin_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _ = run_creator(VALID_REQUEST, target_dir=tmp)
            self.assertEqual(code, 0, stdout)

            agent_py = Path(tmp) / "brand-pr-agent" / "agent.py"
            env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": tmp}
            proc = subprocess.run(
                [sys.executable, str(agent_py)],
                input=json.dumps({"question": "测试问题"}, ensure_ascii=False),
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
            self.assertEqual(
                proc.returncode, 0,
                f"生成物必须可跑。stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}",
            )
            result = json.loads(proc.stdout)
            self.assertIs(result["ok"], True)
            self.assertIn("llm_unavailable", result.get("warnings", []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
