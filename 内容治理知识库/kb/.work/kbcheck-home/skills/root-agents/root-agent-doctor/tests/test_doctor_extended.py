"""root-agent-doctor · D 组扩展检查回归测试（六项：职责/指令/依赖/流程/状态/协作）

seam：CLI 进程边界。夹具全部现场构造，不依赖仓库内既有包。

两条口径是本文件的钉子：
  1. **能力门控**：无状态、单 agent 的包，`state.*` 与 `collab.*` 必须是 skipped，
     既不能 fail，也不能出现在 blockings/warnings 里 —— 不因缺少记忆或协作配置扣分；
  2. **真有能力就得有约定**：检测到状态写入或子 agent 引用之后，缺声明就是 fail。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
DOCTOR = WORKSPACE / "root-agents" / "root-agent-doctor" / "agent.py"

MANIFEST = """name: {name}
version: "0.1.0"
interface: cli
run: python3 agent.py
input: stdin-json
profile: general
task_types:
  - fact_qa
deliverables:
  - id: report
    name: 分析报告
    format: md
    acceptance: 可直接发给业务方
tools: []
env:
  API_KEY: ${{managed}}
"""

AGENT_PY = '''#!/usr/bin/env python3
import json
import sys

raw = sys.stdin.read()
request = json.loads(raw) if raw.strip() else {}
print(json.dumps({{"ok": True, "answer": "pong", "echo": request.get("question")}},
                 ensure_ascii=False))
'''

PROMPT = "# 提示词\n\n回答业务问题。\n"


def run_doctor(pkg, skip_instantiate=True):
    payload = {"agent_dir": str(pkg), "skip_instantiate": bool(skip_instantiate)}
    proc = subprocess.run([sys.executable, str(DOCTOR)],
                          input=json.dumps(payload, ensure_ascii=False),
                          capture_output=True, text=True, timeout=180)
    return proc.returncode, json.loads(proc.stdout)


def check_by_id(result, check_id):
    for item in result.get("checks", []):
        if item.get("id") == check_id:
            return item
    raise AssertionError(
        f"报告缺少 check {check_id!r}。实际含：{[c.get('id') for c in result.get('checks', [])]}")


def make_package(root, name, manifest=None, agent_py=AGENT_PY, prompt=PROMPT, extra=None):
    pkg = Path(root) / name
    (pkg / "prompts").mkdir(parents=True)
    (pkg / "tests").mkdir(parents=True)
    (pkg / "agent.yaml").write_text(
        manifest if manifest is not None else MANIFEST.format(name=name),
        encoding="utf-8")
    if agent_py is not None:
        (pkg / "agent.py").write_text(agent_py, encoding="utf-8")
    (pkg / "prompts" / "system.md").write_text(prompt, encoding="utf-8")
    (pkg / "tests" / "smoke.json").write_text('{"cases": []}\n', encoding="utf-8")
    for rel, content in (extra or {}).items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return pkg


class StatelessSingleAgentIsNotPenalized(unittest.TestCase):
    """第 10、11 项按实际能力启用：没能力就不查、不扣分。"""

    def test_state_and_collab_are_skipped_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "plain-agent")
            code, result = run_doctor(pkg)

            self.assertEqual(result["verdict"], "healthy")
            self.assertEqual(code, 0)

            state_ids = ("state.declared", "state.isolation",
                         "state.lifecycle", "state.concurrency")
            collab_ids = ("collab.refs_exist", "collab.handoff_declared",
                          "collab.bounds")
            for cid in state_ids + collab_ids:
                item = check_by_id(result, cid)
                self.assertEqual(item["status"], "skipped",
                                 f"{cid} 对无状态单 agent 必须是 skipped")
                self.assertIn("不适用", item["detail"])
                self.assertIn("扣分", item["detail"])

            blocked = [b["id"] for b in result["blockings"]]
            warned = " ".join(result["warnings"])
            for cid in state_ids + collab_ids:
                self.assertNotIn(cid, blocked, f"{cid} 不该阻断无状态单 agent")
                self.assertNotIn(cid, warned, f"{cid} 不该进 warnings")

    def test_plain_package_has_no_blockings(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "plain-two")
            _, result = run_doctor(pkg)
            self.assertEqual(result["blockings"], [],
                             f"最小健康包不该有阻断项：{result['blockings']}")


class StateCapabilityGating(unittest.TestCase):
    """有状态就得写清位置与隔离键；声明齐全后放行。"""

    AGENT_WITH_STATE = '''#!/usr/bin/env python3
import json
import sys

MEMORY_FILE = "growth.json"


def main():
    raw = sys.stdin.read()
    request = json.loads(raw) if raw.strip() else {}
    (__import__("pathlib").Path(".") / MEMORY_FILE).write_text(raw, encoding="utf-8")
    print(json.dumps({"ok": True, "answer": "pong", "echo": request.get("question")},
                     ensure_ascii=False))


main()
'''

    STATE_BLOCK = """state:
  path: memory/growth.json
  scope: 家族级
  key: run_id
  cleanup: 不自动清理，换 run_id 即开新一轮
  concurrency: 单进程追加写
"""

    def test_stateful_without_declaration_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "stateful-nodecl", agent_py=self.AGENT_WITH_STATE)
            code, result = run_doctor(pkg)

            self.assertEqual(result["verdict"], "unhealthy")
            self.assertNotEqual(code, 0)
            item = check_by_id(result, "state.declared")
            self.assertEqual(item["status"], "fail")
            self.assertIn("MEMORY_FILE", item["detail"])
            self.assertEqual(check_by_id(result, "state.isolation")["status"], "fail")

    def test_in_memory_context_constant_is_not_state(self):
        """`CONTEXT = {}` 这种内存变量不是状态能力 —— 别把无状态的包判成有状态。"""
        agent_py = AGENT_PY.replace(
            "raw = sys.stdin.read()",
            "CONTEXT = {}\nraw = sys.stdin.read()")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "in-memory-context", agent_py=agent_py)
            _, result = run_doctor(pkg)
            self.assertEqual(check_by_id(result, "state.declared")["status"], "skipped")
            self.assertEqual(result["verdict"], "healthy")

    def test_path_valued_state_constant_is_state(self):
        """名字不像状态、值是状态文件路径 —— 也算状态能力。"""
        agent_py = AGENT_PY.replace(
            "raw = sys.stdin.read()",
            'CACHE = "/tmp/agent-cache.json"\nraw = sys.stdin.read()')
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "path-state", agent_py=agent_py)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "state.declared")
            self.assertEqual(item["status"], "fail")
            self.assertIn("CACHE", item["detail"])

    def test_stateful_with_declaration_is_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = MANIFEST.format(name="stateful-decl") + self.STATE_BLOCK
            pkg = make_package(tmp, "stateful-decl", manifest=manifest,
                               agent_py=self.AGENT_WITH_STATE)
            code, result = run_doctor(pkg)

            self.assertEqual(result["verdict"], "healthy",
                             f"blockings={result['blockings']}")
            self.assertEqual(code, 0)
            self.assertEqual(check_by_id(result, "state.declared")["status"], "pass")
            self.assertEqual(check_by_id(result, "state.isolation")["status"], "pass")
            self.assertIn("run_id", check_by_id(result, "state.isolation")["detail"])


class CollabCapabilityGating(unittest.TestCase):
    """派子 agent 就得写清交接；单 agent 一律 skipped。"""

    def test_dangling_subagent_reference_fails(self):
        prompt = "# 提示词\n\n把明细交给 subagents/refund/agent.py 汇总。\n"
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "collab-dangling", prompt=prompt)
            code, result = run_doctor(pkg)

            self.assertEqual(result["verdict"], "unhealthy")
            self.assertEqual(check_by_id(result, "collab.refs_exist")["status"], "fail")
            self.assertIn("subagents/refund/agent.py",
                          check_by_id(result, "collab.refs_exist")["detail"])
            self.assertEqual(check_by_id(result, "collab.handoff_declared")["status"],
                             "fail")

    def test_declared_handoff_with_existing_subagent_passes(self):
        prompt = "# 提示词\n\n把明细交给 subagents/refund/agent.py 汇总。\n"
        manifest = MANIFEST.format(name="collab-ok") + """handoff:
  to: subagents/refund
  input:
    - 订单明细
  output:
    - 退款结论
  bounds:
    max_depth: 1
"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "collab-ok", manifest=manifest, prompt=prompt,
                               extra={"subagents/refund/agent.py": "# 子 agent\n"})
            code, result = run_doctor(pkg)

            self.assertEqual(result["verdict"], "healthy",
                             f"blockings={result['blockings']}")
            self.assertEqual(code, 0)
            self.assertEqual(check_by_id(result, "collab.refs_exist")["status"], "pass")
            self.assertEqual(check_by_id(result, "collab.handoff_declared")["status"],
                             "pass")
            self.assertEqual(check_by_id(result, "collab.bounds")["status"], "pass")

    def test_docs_only_path_reference_is_not_collab_capability(self):
        """文档里只贴一行别的 agent 包的用法，不是协作能力。

        历史误报：业务包 README 写「用法：python3 …/root-agent-creater/agent.py」，
        被当成派子 agent，进而要求 handoff 声明、判 unhealthy。
        路径引用与交接动作是两件事。
        """
        readme = ("# 目录说明\n\n本包的目录结构参考了 "
                  "subagents/refund/agent.py 的写法。\n")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "docs-only-ref", extra={
                "README.md": readme,
                "subagents/refund/agent.py": "# 参考实现\n"})
            _, result = run_doctor(pkg)
            for cid in ("collab.refs_exist", "collab.handoff_declared", "collab.bounds"):
                self.assertEqual(check_by_id(result, cid)["status"], "skipped",
                                 f"{cid} 对「文档只贴路径」的包应判不适用")
            self.assertEqual(result["verdict"], "healthy",
                             f"blockings={result['blockings']}")

    def test_code_reference_to_sibling_agent_is_capability(self):
        """代码里真去执行别的 agent 包 —— 这才是协作能力。"""
        agent_py = AGENT_PY.replace(
            "raw = sys.stdin.read()",
            'import subprocess\n'
            'subprocess.run([sys.executable, "../root-agent-eval/agent.py"])\n'
            'raw = sys.stdin.read()')
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "code-collab", agent_py=agent_py)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "collab.handoff_declared")
            self.assertEqual(item["status"], "fail")
            self.assertIn("handoff", item["detail"])

    def test_declared_handoff_to_missing_sibling_fails(self):
        manifest = MANIFEST.format(name="collab-ghost") + """handoff:
  to: ghost-sub-agent
  input:
    - 请求
  output:
    - 结论
"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "collab-ghost", manifest=manifest)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "collab.refs_exist")
            self.assertEqual(item["status"], "fail")
            self.assertIn("ghost-sub-agent", item["detail"])

    def test_external_handoff_target_is_not_judged(self):
        """外部服务名/宿主调度器名不判存在性 —— 共置与否不是这个包能决定的。"""
        manifest = MANIFEST.format(name="collab-external") + """handoff:
  to: 公司调度平台
  input:
    - 请求
  output:
    - 结论
  bounds:
    max_depth: 1
"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "collab-external", manifest=manifest)
            _, result = run_doctor(pkg)
            self.assertEqual(check_by_id(result, "collab.refs_exist")["status"], "pass")
            self.assertEqual(result["verdict"], "healthy")


class InstructionChecks(unittest.TestCase):
    """第 5 项：占位符、悬空引用、点名未声明的工具。"""

    def test_placeholder_fails_but_code_fence_is_exempt(self):
        prompt = ("# 提示词\n\n署名用 {{BRAND_NAME}}。\n\n"
                  "```jinja\n{{ 这是示例模板 }}\n```\n")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "placeholder", prompt=prompt)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "instructions.placeholders")
            self.assertEqual(item["status"], "fail")
            self.assertIn("system.md:3", item["detail"])
            self.assertNotIn(":6", item["detail"],
                             "代码块里的模板示例不该算未替换占位符")

    def test_dangling_ref_fails_and_existing_ref_passes(self):
        bad = "# 提示词\n\n模板见 templates/report.md。\n"
        good = "# 提示词\n\n模板见 templates/report.md。\n"
        with tempfile.TemporaryDirectory() as tmp:
            bad_pkg = make_package(tmp, "ref-bad", prompt=bad)
            _, result = run_doctor(bad_pkg)
            item = check_by_id(result, "instructions.dangling_refs")
            self.assertEqual(item["status"], "fail")
            self.assertIn("templates/report.md", item["detail"])

            good_pkg = make_package(tmp, "ref-good", prompt=good,
                                    extra={"templates/report.md": "# 模板\n"})
            _, result = run_doctor(good_pkg)
            self.assertEqual(check_by_id(result, "instructions.dangling_refs")["status"],
                             "pass")

    def test_prompt_naming_undeclared_tool_warns(self):
        prompt = "# 提示词\n\n先用 `ghost_kb` 工具检索，再作答。\n"
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "tool-ref", prompt=prompt)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "instructions.tool_refs")
            self.assertEqual(item["level"], "warn")
            self.assertEqual(item["status"], "fail")
            self.assertIn("ghost_kb", item["detail"])
            self.assertEqual(result["verdict"], "healthy",
                             "工具点名是 warn 级，不该阻断")


class DependencyChecks(unittest.TestCase):
    """第 7 项：硬编码个人路径、未声明环境变量、第三方依赖。"""

    def test_comment_ref_in_agent_yaml_is_not_flagged(self):
        """契约注释里写出处不算引用 —— creater 生成的包首行就是这么写的。

        历史缺陷：不区分注释，把「本文件遵循 refs/agent-contract.yaml」当成悬空
        引用，于是 creater 造出来的健康包被判 unhealthy（实测踩到）。
        """
        manifest = ("# 由 root-agent-creater 生成，契约见 refs/agent-contract.yaml\n"
                    + MANIFEST.format(name="comment-ref"))
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "comment-ref", manifest=manifest)
            _, result = run_doctor(pkg)
            self.assertEqual(check_by_id(result, "deps.refs_exist")["status"], "pass")
            self.assertEqual(result["verdict"], "healthy")

    def test_script_ref_to_missing_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "script-ref",
                               extra={"setup.sh": "#!/bin/sh\nbash scripts/init.sh\n"})
            _, result = run_doctor(pkg)
            item = check_by_id(result, "deps.refs_exist")
            self.assertEqual(item["status"], "fail")
            self.assertIn("scripts/init.sh", item["detail"])

    def test_artifact_dir_ref_is_not_judged(self):
        """产物目录里的路径是运行时生成的，不判悬空。"""
        manifest = MANIFEST.format(name="artifact-ref") + "deps:\n  outputs:\n    - evals/score.json\n"
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "artifact-ref", manifest=manifest)
            _, result = run_doctor(pkg)
            self.assertEqual(check_by_id(result, "deps.refs_exist")["status"], "pass")

    def test_hardcoded_home_path_fails(self):
        # 运行时拼接：避免这段夹具源码本身成为 doctor 自检命中的硬编码路径
        home = "/Use" "rs/lute/Desktop/project/data.xlsx"
        agent_py = AGENT_PY.replace('request.get("question")', f'"{home}"')
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "hardcoded", agent_py=agent_py)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "deps.hardcoded_path")
            self.assertEqual(item["status"], "fail")
            self.assertIn("agent.py", item["detail"])

    def test_undeclared_env_warns_and_declared_env_passes(self):
        agent_py = AGENT_PY.replace(
            "import sys",
            'import os\nimport sys\n\nTOKEN = os.environ.get("MY_AGENT_TOKEN")\n')
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "env-undeclared", agent_py=agent_py)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "deps.env_declared")
            self.assertEqual(item["level"], "warn")
            self.assertEqual(item["status"], "fail")
            self.assertIn("MY_AGENT_TOKEN", item["detail"])

            manifest = MANIFEST.format(name="env-declared").replace(
                "  API_KEY: ${managed}", "  API_KEY: ${managed}\n  MY_AGENT_TOKEN: ${managed}")
            pkg2 = make_package(tmp, "env-declared", manifest=manifest, agent_py=agent_py)
            _, result2 = run_doctor(pkg2)
            self.assertEqual(check_by_id(result2, "deps.env_declared")["status"], "pass")

    def test_third_party_import_without_manifest_warns(self):
        agent_py = AGENT_PY.replace("import sys", "import sys\nimport yaml  # 第三方\n")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "third-party", agent_py=agent_py)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "deps.third_party")
            self.assertEqual(item["level"], "warn")
            self.assertEqual(item["status"], "fail")
            self.assertIn("yaml", item["detail"])


class FlowChecks(unittest.TestCase):
    """第 8 项：无界循环、终止预算。"""

    def test_unbounded_loop_fails(self):
        agent_py = AGENT_PY.replace(
            "raw = sys.stdin.read()",
            "while True:\n    pass\nraw = sys.stdin.read()")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "unbounded", agent_py=agent_py)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "flow.loop_bound")
            self.assertEqual(item["status"], "fail")
            self.assertIn("agent.py", item["detail"])

    def test_bounded_loop_passes(self):
        agent_py = AGENT_PY.replace(
            "raw = sys.stdin.read()",
            "while True:\n    break\nraw = sys.stdin.read()")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "bounded", agent_py=agent_py)
            _, result = run_doctor(pkg)
            self.assertEqual(check_by_id(result, "flow.loop_bound")["status"], "pass")

    def test_limits_declaration_passes(self):
        manifest = MANIFEST.format(name="with-limits") + """limits:
  timeout_s: 120
  max_iterations: 1
"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "with-limits", manifest=manifest)
            _, result = run_doctor(pkg)
            self.assertEqual(check_by_id(result, "flow.limits_declared")["status"], "pass")

    def test_limits_missing_is_warn_not_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "no-limits")
            _, result = run_doctor(pkg)
            item = check_by_id(result, "flow.limits_declared")
            self.assertEqual(item["level"], "warn")
            self.assertEqual(item["status"], "fail")
            self.assertEqual(result["verdict"], "healthy")


class ScopeChecks(unittest.TestCase):
    """第 3 项：职责边界声明与自相矛盾。"""

    def test_missing_scope_is_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "no-scope")
            _, result = run_doctor(pkg)
            item = check_by_id(result, "scope.declared")
            self.assertEqual(item["level"], "warn")
            self.assertEqual(item["status"], "fail")
            self.assertEqual(result["verdict"], "healthy")

    def test_contradictory_scope_fails(self):
        manifest = MANIFEST.format(name="scope-clash") + """scope:
  does:
    - 代发邮件
  not_for:
    - 代发邮件
    - 分析报告
"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "scope-clash", manifest=manifest)
            code, result = run_doctor(pkg)
            item = check_by_id(result, "scope.consistent")
            self.assertEqual(item["status"], "fail")
            self.assertIn("does", item["detail"])
            self.assertIn("deliverables", item["detail"])
            self.assertEqual(result["verdict"], "unhealthy")
            self.assertNotEqual(code, 0)

    def test_clean_scope_passes(self):
        manifest = MANIFEST.format(name="scope-ok") + """scope:
  does:
    - 出一份分析报告
  not_for:
    - 代发邮件
"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "scope-ok", manifest=manifest)
            _, result = run_doctor(pkg)
            self.assertEqual(check_by_id(result, "scope.declared")["status"], "pass")
            self.assertEqual(check_by_id(result, "scope.consistent")["status"], "pass")


class RoutingIsOptional(unittest.TestCase):
    """不参与路由就不查选择条件——skipped，不扣分。"""

    def test_routing_absent_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "no-routing")
            _, result = run_doctor(pkg)
            item = check_by_id(result, "routing.conditions")
            self.assertEqual(item["status"], "skipped")
            self.assertIn("不扣分", item["detail"])

    def test_routing_declared_without_when_fails(self):
        manifest = MANIFEST.format(name="routing-empty") + "routing:\n  when: []\n"
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "routing-empty", manifest=manifest)
            _, result = run_doctor(pkg)
            item = check_by_id(result, "routing.conditions")
            self.assertEqual(item["status"], "fail")
            self.assertEqual(item["level"], "warn")


class StructureFailureSkipsExtended(unittest.TestCase):
    """结构检查没过时，D 组一并记 skipped —— 不级联误报。"""

    def test_broken_manifest_skips_extended_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "broken-manifest",
                               manifest='name: broken\nversion: "0.1.0"\n')
            _, result = run_doctor(pkg)
            self.assertEqual(result["verdict"], "unhealthy")
            for cid in ("scope.declared", "instructions.placeholders",
                        "deps.refs_exist", "flow.loop_bound",
                        "state.declared", "collab.refs_exist"):
                item = check_by_id(result, cid)
                self.assertEqual(item["status"], "skipped", cid)
                self.assertIn("结构检查未通过", item["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
