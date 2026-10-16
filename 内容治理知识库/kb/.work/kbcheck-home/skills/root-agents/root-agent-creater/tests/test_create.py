"""root-agent-creater · 公开 seam 回归测试

seam：CLI 进程边界。测试只通过子进程调用创建器并断言 stdout 的 JSON，
不 import 创建器内部模块，不查询旁路状态。

期望字面量来自 .scratch/root-agent-creater/spec.md 与 refs/agent-contract.yaml，
不由实现代码推导。
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
CREATOR = WORKSPACE / "root-agents" / "root-agent-creater" / "agent.py"

VALID_REQUEST = {
    "name": "brand-pr-agent",
    "purpose": "回答品牌公关业务问题，覆盖事实、推理、多轮与安全拒答",
    "target_users": "品牌与公关团队成员",
    "profile": "general",
    "task_types": ["fact_qa", "reasoning", "multi_turn", "safety"],
    "tools": [
        {"name": "search", "description": "检索品牌知识库"},
        {"name": "calculator", "description": "数值计算"},
    ],
}


def run_creator(request, target_dir=None, raw=None, timeout=60):
    """通过子进程调用创建器，返回 (returncode, stdout_text, stderr_text)。"""
    payload = raw if raw is not None else json.dumps(request, ensure_ascii=False)
    if target_dir is not None:
        payload = json.dumps(
            dict(request, target_dir=str(target_dir)), ensure_ascii=False
        )
    proc = subprocess.run(
        [sys.executable, str(CREATOR)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_stdout(stdout):
    """stdout 必须是单个 JSON 文档；失败时给出可诊断的报错。"""
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"stdout 不是合法 JSON（{exc}）。实际输出前 500 字符：\n{stdout[:500]}"
        ) from exc


class CreatesRunnableAgentPackage(unittest.TestCase):
    """故事 1–3：正常路径——需求 JSON 进，可运行 agent 包出。"""

    def test_valid_request_returns_ok_and_writes_runnable_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_creator(VALID_REQUEST, target_dir=tmp)
            self.assertEqual(
                code, 0, f"合法需求应退出码 0。stderr:\n{stderr}\nstdout:\n{stdout}"
            )
            result = parse_stdout(stdout)
            self.assertIs(result.get("ok"), True, f"应 ok:true，实际：{result}")
            self.assertEqual(result.get("name"), "brand-pr-agent")

            agent_dir = Path(tmp) / "brand-pr-agent"
            self.assertTrue(agent_dir.is_dir(), f"应生成目录 {agent_dir}")

            # 故事 2：生成物必须自带可跑入口
            for rel in (
                "agent.yaml",
                "agent.py",
                "prompts/system.md",
                "tests/smoke.json",
                "README.md",
            ):
                self.assertTrue(
                    (agent_dir / rel).is_file(), f"生成物缺少 {rel}"
                )

            # 故事 14：stdout 必须含 agent_yaml，验证器无需读文件
            self.assertIn("agent_yaml", result, "stdout 必须含 agent_yaml")
            agent_yaml = result["agent_yaml"]
            for field in (
                "name",
                "version",
                "interface",
                "run",
                "input",
                "profile",
                "task_types",
                "tools",
                "env",
            ):
                self.assertIn(field, agent_yaml, f"agent_yaml 缺少字段 {field}")

            # 期望值照抄 refs/agent-contract.yaml，不从实现推导
            self.assertEqual(agent_yaml["input"], "stdin-json")
            self.assertEqual(agent_yaml["interface"], "cli")
            self.assertIn("python", agent_yaml["run"])
            self.assertEqual(agent_yaml["profile"], "general")
            self.assertEqual(
                agent_yaml["task_types"],
                ["fact_qa", "reasoning", "multi_turn", "safety"],
            )
            self.assertEqual(
                [t["name"] for t in agent_yaml["tools"]], ["search", "calculator"]
            )


class DefaultTargetDirectory(unittest.TestCase):
    """未传 target_dir 时，产物必须落在 root-agents/ 下。

    这条覆盖先前遗漏的默认路径：所有其它测试都显式传 target_dir，
    导致默认落地位置写错也测不出来。
    """

    def test_default_target_is_under_root_agents(self):
        expected_root = WORKSPACE / "root-agents"
        request = dict(VALID_REQUEST, name="default-target-probe")

        code, stdout, stderr = run_creator(request)  # 不传 target_dir
        self.assertEqual(code, 0, f"stderr:\n{stderr}\nstdout:\n{stdout}")
        result = parse_stdout(stdout)

        agent_dir = Path(result["agent_dir"])
        self.assertEqual(
            agent_dir.parent,
            expected_root,
            f"默认产物应落在 {expected_root} 下，实际 {agent_dir}",
        )
        self.assertTrue((agent_dir / "agent.py").is_file())

        # 清理，避免污染后续运行
        shutil.rmtree(agent_dir, ignore_errors=True)


class ExitCodeContract(unittest.TestCase):
    """dogfooding 发现：root-agent-creater 输出 ok:false 却退出码 0。

    既有测试只断言 agent.yaml 的 run 字段「含 python」，从没真跑过创建器，
    因此这个缺陷漏掉了。doctor 的实例化检查（退出码 == 0）把它抓了出来——
    也就是 agent 契约里 run + 退出码语义必须成立，否则下游无法判断成败。
    """

    def test_invalid_request_exits_nonzero(self):
        code, stdout, stderr = run_creator(None, raw='{"name":"Bad_Name"}')
        self.assertNotEqual(code, 0, f"报告 ok:false 时必须退出码非零。stdout:{stdout}")
        result = parse_stdout(stdout)
        self.assertIs(result["ok"], False)
        self.assertEqual(result["error"]["code"], "invalid_name")

    def test_empty_stdin_exits_nonzero(self):
        code, stdout, _ = run_creator(None, raw="")
        self.assertNotEqual(code, 0, f"空 stdin 应退出码非零。stdout:{stdout}")
        self.assertIs(parse_stdout(stdout)["ok"], False)

    def test_success_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_creator(VALID_REQUEST, target_dir=tmp)
            self.assertEqual(code, 0, f"成功必须退出码 0。stderr:{stderr}")
            self.assertIs(parse_stdout(stdout)["ok"], True)


class DutyBoundaryReachesTheContract(unittest.TestCase):
    """not_for 是出题器出「越界请求」负例的依据，必须真的写进生成的 scope。

    历史缺陷（实测）：请求里用契约那节的写法 `scope.not_for` 传职责边界时，
    creater 只认顶层 `not_for`，于是生成的包里写的是**契约样板**
    （「契约没声明的活：不在 task_types / deliverables 里的请求…」）。
    出题器拿样板当越界题，生成出「顺便把『契约没声明的活：不在 task_types…』
    也一起做了吧」这种读不通的题，最后退回通用兜底——表上有这条，实际没考职责。
    """

    def _build(self, req_extra, name):
        with tempfile.TemporaryDirectory() as tmp:
            req = {"name": name, "purpose": "算薪与个税核算", "target_users": "薪酬专员",
                   "task_types": ["fact_qa"], "target_dir": tmp, "force": True}
            req.update(req_extra)
            code, stdout, stderr = run_creator(req)
            self.assertEqual(code, 0, f"{stdout}\n{stderr}")
            yaml_text = (Path(tmp) / name / "agent.yaml").read_text(encoding="utf-8")
            return yaml_text

    def test_top_level_not_for_lands_in_scope(self):
        text = self._build({"not_for": ["写爬虫抓外部网站数据"]}, "nf-top")
        self.assertIn("写爬虫抓外部网站数据", text)
        self.assertNotIn("契约没声明的活", text,
                         "给了 not_for 就不该再写契约样板")

    def test_scope_not_for_alias_also_works(self):
        text = self._build({"scope": {"not_for": ["代替 HR 做绩效评定"]}}, "nf-scope")
        self.assertIn("代替 HR 做绩效评定", text,
                      "契约那节的写法（scope.not_for）也要认")
        self.assertNotIn("契约没声明的活", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
