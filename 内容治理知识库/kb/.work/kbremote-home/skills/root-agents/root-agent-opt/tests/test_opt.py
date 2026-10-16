"""root-agent-opt · 公开 seam 回归测试

seam：CLI 进程边界。测试只通过子进程调用优化器，断言 stdout JSON、退出码、
副本内容，以及**源包逐字节未变**。

设计要点：全部用现场构造的确定性夹具。真实包在本机恒为全员无作答
（无模型端点），无法用来验证「改进」路径。
家族根里没有预置样例包，夹具一律现场构造——本文件因此不持有任何
指向仓库内既有包的常量。
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
OPT = WORKSPACE / "root-agents" / "root-agent-opt" / "agent.py"
EVAL = WORKSPACE / "root-agents" / "root-agent-eval" / "agent.py"

AGENT_YAML = """name: {name}
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
    description: 检索知识库
    schema: {{}}
env:
  API_KEY: ${{managed}}
"""

# 回答 = 问题回显 → 满足 must_contain，用于可改进夹具
ECHO_AGENT_PY = '''#!/usr/bin/env python3
import json
import sys

request = json.loads(sys.stdin.read() or "{}")
print(json.dumps({{"ok": True, "answer": request.get("question", ""),
                  "tools_declared": ["search_kb"]}}, ensure_ascii=False))
'''

# 回答固定且不含关键词 → 满足不了 must_contain，用于 content 类夹具
WRONG_AGENT_PY = '''#!/usr/bin/env python3
import json
print(json.dumps({"ok": True, "answer": "抱歉，我不清楚"},
                 ensure_ascii=False))
'''

# 工具桩：call() 抛 NotImplementedError
STUB_TOOL_PY = '''# -*- coding: utf-8 -*-
"""search_kb · 工具桩"""

TOOL_NAME = "search_kb"


def call(**kwargs):
    raise NotImplementedError("工具 search_kb 尚未实现")
'''

FILLED_TOOL_PY = '''# -*- coding: utf-8 -*-
"""search_kb · 工具实现"""

TOOL_NAME = "search_kb"


def call(**kwargs):
    return {}
'''

# 输出 answer 恒为 null —— 违背 agent.yaml 的 stdin-json「必有作答」协议。
# 这正是创建器生成的 agent 在本机无模型端点时的真实行为。
NULL_ANSWER_AGENT_PY = '''#!/usr/bin/env python3
import json

print(json.dumps({"ok": True, "answer": None, "warnings": ["llm_unavailable"]},
                 ensure_ascii=False))
'''

# 输出 answer 有值但不含关键词 —— 内容级问题，不可自动修
CONST_ANSWER_AGENT_PY = '''#!/usr/bin/env python3
import json

print(json.dumps({"ok": True, "answer": "抱歉，我不清楚"},
                 ensure_ascii=False))
'''


def run_opt(request, generate=None, timeout=600):
    if generate is not None:
        request = dict(request, generate=generate)
    proc = subprocess.run(
        [sys.executable, str(OPT)],
        input=json.dumps(request, ensure_ascii=False),
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


def fingerprint(root):
    return {str(f.relative_to(root)): (f.stat().st_mtime_ns,
                                       hashlib.sha256(f.read_bytes()).hexdigest())
            for f in sorted(Path(root).rglob("*"))
            if f.is_file() and "__pycache__" not in f.parts and "evals" not in f.parts}


def make_package(root, name, agent_py=ECHO_AGENT_PY, tool_py=None):
    pkg = Path(root) / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "agent.py").write_text(agent_py, encoding="utf-8")
    (pkg / "agent.yaml").write_text(AGENT_YAML.format(name=name), encoding="utf-8")
    (pkg / "prompts").mkdir(exist_ok=True)
    (pkg / "prompts" / "system.md").write_text("# 提示词\n", encoding="utf-8")
    (pkg / "tests").mkdir(exist_ok=True)
    (pkg / "tests" / "smoke.json").write_text(
        json.dumps({"agent": name, "cases": []}, ensure_ascii=False), encoding="utf-8")
    if tool_py is not None:
        (pkg / "tools").mkdir(exist_ok=True)
        (pkg / "tools" / "search_kb.py").write_text(tool_py, encoding="utf-8")
    return pkg


def write_score(pkg, cases, verdict="fail", environment_degraded=False):
    """写一份 score.json，字段形状照抄 root-agent-eval 的真实产出。"""
    counts = {"total": len(cases)}
    for key in ("eligible", "na", "pass", "fail", "error", "inconclusive"):
        counts[key] = 0
    for case in cases:
        outcome = case["outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome != "na":
            counts["eligible"] += 1
    doc = {
        "agent": pkg.name,
        "agent_dir": str(pkg),
        "threshold": 0.6,
        "verdict": verdict,
        "verdict_confidence": "normal",
        "environment_degraded": environment_degraded,
        "environment_notes": [],
        "scores": {"pass_rate": None, "coverage": 1.0, "total_score": None,
                   "dimension_score": None},
        "counts": counts,
        "formula": "pass_rate=pass/decisive where decisive=eligible-inconclusive; "
                   "coverage=eligible/total; total_score=pass_rate*coverage",
        "dimensions": {},
        "cases": cases,
    }
    path = pkg / "evals"
    path.mkdir(exist_ok=True)
    (path / "score.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path / "score.json"


def case(case_id, outcome, strength="real", detail="", dimension="fact_qa",
         difficulty="L1", exit_code=0):
    return {
        "id": case_id,
        "dimension": dimension,
        "difficulty": difficulty,
        "outcome": outcome,
        "assessment_strength": strength,
        "detail": detail,
        "exit_code": exit_code,
        "duration_ms": 10,
        "unresolved_expectations": [],
    }


class NoActionableCases(unittest.TestCase):
    """故事 1、12：无可优化项是合法结论，绝不制造假修复。

    这正是真实包当前的状态：20 条全 inconclusive（本机无模型端点）。
    """

    def test_all_inconclusive_yields_no_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "inconclusive-agent")
            write_score(pkg, [
                case("c1", "inconclusive", strength="structural",
                     detail="agent 未给出作答内容（answer 为空或缺失）"),
                case("c2", "inconclusive", strength="structural",
                     detail="agent 未给出作答内容（answer 为空或缺失）"),
            ], verdict="inconclusive", environment_degraded=True)

            before = fingerprint(pkg)
            code, stdout, stderr = run_opt({"agent_dir": str(pkg)})
            self.assertEqual(code, 0, f"无可优化项应退出码 0。stderr:\n{stderr}")
            result = parse_stdout(stdout)

            self.assertEqual(result["verdict"], "no_actionable")
            self.assertEqual(result["rounds"], 0, "无可优化项不应进入迭代")
            self.assertEqual(
                result["patches_applied_total"], 0,
                "无可优化项绝不允许打补丁",
            )
            self.assertEqual(
                sorted(before.keys()), sorted(fingerprint(pkg).keys()),
                "源包不得被改动",
            )
            self.assertEqual(before, fingerprint(pkg), "源包内容必须逐字节未变")

    def test_already_passing_yields_no_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "passing-agent")
            write_score(pkg, [case("c1", "pass")], verdict="pass")
            code, stdout, _ = run_opt({"agent_dir": str(pkg)})
            self.assertEqual(code, 0)
            self.assertEqual(parse_stdout(stdout)["verdict"], "no_actionable")

    def test_environment_cause_stated_explicitly(self):
        """环境级问题必须显式说明「任何代码改动都无法修复」。"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "env-agent")
            write_score(pkg, [case("c1", "inconclusive", strength="structural")],
                        verdict="inconclusive", environment_degraded=True)
            _, stdout, _ = run_opt({"agent_dir": str(pkg)})
            result = parse_stdout(stdout)
            blob = json.dumps(result, ensure_ascii=False)
            self.assertIn("环境", blob)
            self.assertTrue(
                "无法修复" in blob or "无法通过代码改动" in blob
                or "不可自动修" in blob,
                f"应说明环境级问题不可自动修：{blob[:800]}",
            )


class MissingScoreIsPreconditionError(unittest.TestCase):
    """故事 11：没有 score.json 时明确报错，不猜。"""

    def test_missing_score_is_precondition_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "no-score-agent")
            code, stdout, _ = run_opt({"agent_dir": str(pkg)})
            self.assertNotEqual(code, 0)
            result = parse_stdout(stdout)
            self.assertIs(result["ok"], False)
            self.assertEqual(result["error"]["code"], "score_missing")


class StructuralPatch(unittest.TestCase):
    """故事 4：结构性缺陷（工具桩未实现）可由确定性规则修复。"""

    def test_tool_stub_is_filled_in_copy_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "stub-agent", tool_py=STUB_TOOL_PY)
            write_score(pkg, [
                case("c-stub", "fail", detail="NotImplementedError: 工具 search_kb 尚未实现"),
            ])
            before = fingerprint(pkg)

            code, stdout, stderr = run_opt({"agent_dir": str(pkg)})
            result = parse_stdout(stdout)

            self.assertTrue(result["patches_applied_total"] >= 1,
                            f"应填充工具桩：{result.get('patches')}")
            patch = result["patches"][0]
            self.assertEqual(patch["rule"], "fill_tool_stub")
            self.assertEqual(patch["evidence_case_id"], "c-stub")

            copy_dir = Path(result["copy_dir"])
            filled = (copy_dir / "tools" / "search_kb.py").read_text(encoding="utf-8")
            self.assertNotIn("raise NotImplementedError", filled,
                             "副本里的工具桩应被填充")
            self.assertTrue((copy_dir / "tools" / "search_kb.py.orig").is_file(),
                            "原文件必须备份为 .orig 以便审计")

            # 铁律 1：源包只读
            self.assertEqual(before, fingerprint(pkg),
                             "源包必须逐字节未变，改动只落在副本")

    def test_provenance_written_in_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "prov-agent", tool_py=STUB_TOOL_PY)
            write_score(pkg, [case("c1", "fail",
                                   detail="NotImplementedError 工具未实现")])
            _, stdout, _ = run_opt({"agent_dir": str(pkg)})
            result = parse_stdout(stdout)
            prov = Path(result["copy_dir"]) / "opt" / "_fix_provenance.json"
            self.assertTrue(prov.is_file(), "副本需带来源记录")
            doc = json.loads(prov.read_text(encoding="utf-8"))
            self.assertEqual(doc["source_agent_dir"], str(pkg.resolve()))
            self.assertTrue(doc["source_readonly"])


class AnswerFieldPatch(unittest.TestCase):
    """answer 恒为 null 违背契约协议 → 结构性可修，且修完可复测出改进。

    夹具要点（第一版设计错了，这里说明修正）：
    - score.json 里的用例 id 必须与复测时真实存在的用例 id 一致，否则
      holdout 门禁会因「用例消失」误判为退步。早期版本往副本里塞了假 id
      （c-hold / c-null），复测时这些 id 不存在 → 直接判 regressed。
    - 用 generate=False 关掉生成用例，使用例集只剩自带 smoke 用例，可控可断言。
    """

    # 自带 smoke 用例：一条初始就通过（作留出集），一条初始失败（待修）
    SMOKE = {
        "agent": "null-answer-agent",
        "cases": [
            {"id": "keep-pass", "dimension": "fact_qa", "difficulty": "L1",
             "tool_required": [],
             "input": {"question": "任意问题"},
             "expect": {"ok": True}},
            {"id": "needs-answer", "dimension": "fact_qa", "difficulty": "L1",
             "tool_required": [],
             "input": {"question": "任意问题"},
             "expect": {"answer_non_empty": True}},
        ],
    }

    def _prepare(self, tmp, name="null-answer-agent"):
        pkg = make_package(tmp, name, agent_py=NULL_ANSWER_AGENT_PY)
        (pkg / "tests" / "smoke.json").write_text(
            json.dumps(self.SMOKE, ensure_ascii=False), encoding="utf-8")
        # 基线：keep-pass 通过（real），needs-answer 因作答为空失败
        write_score(pkg, [
            case("keep-pass", "pass", strength="real", detail="1 条期望全部满足"),
            case("needs-answer", "fail", strength="structural",
                 detail="agent 未给出作答内容（answer 为空或缺失），无法判定能力"),
        ])
        return pkg

    def test_null_answer_patch_fixes_protocol_but_never_claims_improvement(self):
        """补兜底只修协议，不得当成能力改进。

        历史缺陷（实测）：`ensure_answer_field` 往输出里塞一个占位 answer
        （"（未生成作答内容）"），评测器把「answer 非空」当内容证据，于是
        degraded_fail(0/34) 复测变成 pass(34/34)、evidence_strength=strong、
        release_ready=true —— 一台没有模型端点的机器上，一个完全不会作答的
        agent 被自家修复环节洗成了「可发布」。

        现口径：占位作答**不算内容**（评测器四处判定点一致），所以这条补丁
        照打（协议达标）、源包只读、副本带补丁，但**结论不得是 improved**。
        """
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._prepare(tmp)
            before = fingerprint(pkg)

            code, stdout, stderr = run_opt({"agent_dir": str(pkg)}, generate=False)
            result = parse_stdout(stdout)

            # 补丁照打：规则正确命中，且真的落到了副本里
            self.assertEqual(result["patches"][0]["rule"], "ensure_answer_field")
            copy_dir = Path(result["copy_dir"])
            patched = (copy_dir / "agent.py").read_text(encoding="utf-8")
            self.assertIn("_ensure_answer_field", patched)
            self.assertIn("ensure_answer_field", patched)

            # 关键钉子：占位作答不得制造「改进」
            self.assertNotEqual(result["verdict"], "improved",
                                f"补兜底不得判改进：{result.get('verdict')}")
            self.assertNotEqual(code, 0, "未改进应退出码 1")
            self.assertEqual(result["improved_cases"], [],
                             f"不得有用例因占位作答转好：{result.get('improved_cases')}")

            # 铁律 1：源包只读
            self.assertEqual(before, fingerprint(pkg), "源包必须逐字节未变")

    def test_provenance_written_in_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._prepare(tmp, "prov-agent")
            _, stdout, _ = run_opt({"agent_dir": str(pkg)}, generate=False)
            result = parse_stdout(stdout)
            prov = Path(result["copy_dir"]) / "opt" / "_fix_provenance.json"
            self.assertTrue(prov.is_file(), "副本需带来源记录")
            doc = json.loads(prov.read_text(encoding="utf-8"))
            self.assertEqual(doc["source_agent_dir"], str(pkg.resolve()))
            self.assertTrue(doc["source_readonly"])

    def test_optimization_report_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._prepare(tmp, "report-agent")
            _, stdout, _ = run_opt({"agent_dir": str(pkg)}, generate=False)
            result = parse_stdout(stdout)
            report = Path(result["copy_dir"]) / "opt" / "optimization.json"
            self.assertTrue(report.is_file(), "应产出 optimization.json")
            doc = json.loads(report.read_text(encoding="utf-8"))
            for key in ("verdict", "rounds", "patches", "before", "after",
                        "holdout_baseline", "honest_limitations",
                        "requires_human_review", "environment_blocked"):
                self.assertIn(key, doc, f"报告缺少字段 {key}")
            self.assertTrue(doc["honest_limitations"])


class ContentFailGoesToHuman(unittest.TestCase):
    """故事 5：作答内容不合期望 → 交还人工，绝不自动改提示词。"""

    def test_content_failure_requires_human_review_and_no_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "content-agent", agent_py=CONST_ANSWER_AGENT_PY)
            write_score(pkg, [
                case("c-content", "fail", detail="应包含 '品牌' 但未出现"),
            ])
            before = fingerprint(pkg)

            code, stdout, _ = run_opt({"agent_dir": str(pkg)})
            result = parse_stdout(stdout)

            self.assertEqual(result["patches_applied_total"], 0,
                             f"内容级问题不得自动打补丁：{result.get('patches')}")
            reviews = result["requires_human_review"]
            self.assertEqual(len(reviews), 1, f"应记入人工审阅：{reviews}")
            self.assertEqual(reviews[0]["id"], "c-content")
            self.assertEqual(reviews[0]["kind"], "content")
            self.assertIn("品牌", reviews[0]["evidence"])
            self.assertNotEqual(result["verdict"], "improved")
            self.assertEqual(before, fingerprint(pkg), "源包必须逐字节未变")
            # 无可自动修项 → no_actionable → 按规格退出码 0
            # （「没有需要修的东西」是合法结论，把它当失败会诱导制造假改进）
            self.assertEqual(result["verdict"], "no_actionable")
            self.assertEqual(code, 0)


class GateLogic(unittest.TestCase):
    """两道门禁的逻辑必须可直接验证，不依赖构造「必然退化」的补丁。

    说明：早期版本试图用真实补丁构造留出集退化，结果测试本身设计错误
    （往副本塞假用例 id → 复测时 id 不存在 → 误判退化）。
    门禁是纯逻辑，故导出为可测函数直接验证，并用真实补丁验证「通过」路径。
    """

    def test_holdout_violation_detected(self):
        from importlib import util as _util
        spec = _util.spec_from_file_location("optmod", OPT)
        optmod = _util.module_from_spec(spec)
        spec.loader.exec_module(optmod)
        self.assertTrue(hasattr(optmod, "gate_check"),
                        "门禁逻辑应导出为 gate_check 以便直接验证")

        # 留出集里 a 原本 pass，优化后变成 fail → 违反
        verdict, detail = optmod.gate_check(
            holdout={"a", "b"},
            after_map={"a": "fail", "b": "pass"},
            strength_before=5,
            strength_after=5,
        )
        self.assertEqual(verdict, "regressed")
        self.assertIn("a", detail["holdout_broken"])

        # 判定强度下降 → 违反
        verdict2, detail2 = optmod.gate_check(
            holdout={"a"},
            after_map={"a": "pass"},
            strength_before=5,
            strength_after=3,
        )
        self.assertEqual(verdict2, "regressed")
        self.assertIn("strength", str(detail2))

        # 两道门禁都过
        verdict3, _ = optmod.gate_check(
            holdout={"a"},
            after_map={"a": "pass"},
            strength_before=3,
            strength_after=4,
        )
        self.assertEqual(verdict3, "ok")

    def test_holdout_baseline_recorded_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            smoke = {
                "agent": "hb-agent",
                "cases": [
                    {"id": "keep-pass", "dimension": "fact_qa", "difficulty": "L1",
                     "tool_required": [], "input": {"question": "q"},
                     "expect": {"ok": True}},
                    {"id": "needs-answer", "dimension": "fact_qa", "difficulty": "L1",
                     "tool_required": [], "input": {"question": "q"},
                     "expect": {"answer_non_empty": True}},
                ],
            }
            pkg = make_package(tmp, "hb-agent", agent_py=NULL_ANSWER_AGENT_PY)
            (pkg / "tests" / "smoke.json").write_text(
                json.dumps(smoke, ensure_ascii=False), encoding="utf-8")
            write_score(pkg, [
                case("keep-pass", "pass", strength="real"),
                case("needs-answer", "fail", strength="structural",
                     detail="answer 为空，未给出作答内容"),
            ])
            _, stdout, _ = run_opt({"agent_dir": str(pkg)}, generate=False)
            result = parse_stdout(stdout)
            self.assertIn("keep-pass", result["holdout_baseline"],
                          "留出集基线必须记录在报告里以便审计")


class NoCopyWhenNothingToFix(unittest.TestCase):
    """实测发现：无可优化项时也创建了副本目录，污染了仓库（brand-pr-agent-fix/）。

    没有要动的东西就什么都不该留下——包括目录。
    """

    def test_no_actionable_leaves_no_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp, "clean-agent")
            write_score(pkg, [
                case("c1", "inconclusive", strength="structural",
                     detail="agent 未给出作答内容（answer 为空或缺失）"),
            ], verdict="inconclusive", environment_degraded=True)

            code, stdout, _ = run_opt({"agent_dir": str(pkg)})
            result = parse_stdout(stdout)
            self.assertEqual(result["verdict"], "no_actionable")
            self.assertEqual(code, 0)
            self.assertIsNone(result["copy_dir"],
                              "无可优化项时不应有副本目录")
            self.assertFalse((Path(tmp) / "clean-agent-fix").exists(),
                             "无可优化项时不得在磁盘上留下副本")
            # 临时目录里除了源包，不该多出任何东西
            leftovers = sorted(p.name for p in Path(tmp).iterdir())
            self.assertEqual(leftovers, ["clean-agent"],
                             f"不应留下额外产物：{leftovers}")



class ConsumesEvalReportFindings(unittest.TestCase):
    """实测发现的链路断裂：opt 从 score.json 自己重新归类，没消费评测报告的归因。

    后果：评测报告已经正确列出「可自动修=1（fill_tool_stub）」，
    但 opt 仍报 no_actionable、零补丁——**五环的修复环节被架空**。
    根因是 opt 只从 fail/error 用例取证据，而工具桩这类结构性缺陷
    在用例全 inconclusive（无模型端点）时不会出现在任何失败用例上。

    修法：opt 优先消费 report.json 的 remediation_plan（评测已做归因），
    没有报告时才回退到自己的用例归类。
    """

    def _make_package_with_stub(self, tmp, name="stub-flow-agent"):
        pkg = make_package(tmp, name, tool_py=STUB_TOOL_PY)
        return pkg

    def test_reads_report_json_remediation_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._make_package_with_stub(tmp)
            # 评测产出：全部 inconclusive（无模型端点），但报告已识别出工具桩
            write_score(pkg, [
                case("c1", "inconclusive", strength="structural",
                     detail="agent 未给出作答内容（answer 为空或缺失）"),
            ], verdict="inconclusive", environment_degraded=True)
            # 同时写一份 report.json（模拟 eval 的真实产出）
            (pkg / "evals" / "report.json").write_text(json.dumps({
                "agent_info": {"agent_name": pkg.name},
                "findings": [
                    {"kind": "environment", "severity": "info",
                     "message": "agent 未给出作答内容", "case_ids": ["c1"],
                     "evidence": [], "patch_rule": None},
                    {"kind": "structural", "severity": "warning",
                     "message": "工具桩未实现：search_kb（tools/search_kb.py）",
                     "case_ids": [], "evidence": [], "patch_rule": "fill_tool_stub"},
                ],
                "remediation_plan": {
                    "auto_fixable": [
                        {"kind": "structural", "case_ids": [],
                         "message": "工具桩未实现：search_kb",
                         "patch_rule": "fill_tool_stub"}
                    ],
                    "needs_human_review": [],
                    "environment_blocked": [
                        {"kind": "environment", "case_ids": ["c1"],
                         "message": "agent 未给出作答内容", "patch_rule": None,
                         "action": "配置模型端点"}
                    ],
                },
            }, ensure_ascii=False), encoding="utf-8")

            code, stdout, stderr = run_opt({"agent_dir": str(pkg)}, generate=False)
            result = parse_stdout(stdout)

            self.assertGreater(
                len(result.get("actionable") or []), 0,
                f"应消费报告的 auto_fixable 桶：{result.get('actionable')}",
            )
            self.assertEqual(result["actionable"][0]["patch_rule"], "fill_tool_stub",
                             f"补丁规则应来自报告：{result['actionable']}")
            self.assertNotEqual(result["verdict"], "no_actionable",
                                "有可自动修项时不得报 no_actionable")
            self.assertGreaterEqual(result["patches_applied_total"], 1,
                                    f"应真的打了补丁：{result.get('patches')}")

    def test_end_to_end_eval_then_opt_applies_patch(self):
        """真实链路：eval 跑出 report.json 后，opt 直接消费它并打补丁。"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._make_package_with_stub(tmp, "e2e-flow-agent")
            EVAL = WORKSPACE / "root-agents" / "root-agent-eval" / "agent.py"
            proc = subprocess.run(
                [sys.executable, str(EVAL)],
                input=json.dumps({"agent_dir": str(pkg), "generate": False}),
                capture_output=True, text=True, timeout=300)
            self.assertTrue((pkg / "evals" / "report.json").is_file(),
                            f"eval 应先产出 report.json。stderr:{proc.stderr[:200]}")

            code, stdout, _ = run_opt({"agent_dir": str(pkg)}, generate=False)
            result = parse_stdout(stdout)
            self.assertGreaterEqual(
                result["patches_applied_total"], 1,
                f"真实链路上 opt 应打补丁。verdict={result['verdict']} "
                f"actionable={len(result.get('actionable') or [])}",
            )
            copy_dir = Path(result["copy_dir"])
            filled = (copy_dir / "tools" / "search_kb.py").read_text(encoding="utf-8")
            self.assertNotIn("raise NotImplementedError", filled,
                             "副本里的工具桩应被填充")


class CopyDirMustNotOverlapSource(unittest.TestCase):
    """故事 13：副本路径与源包重叠时必须拒跑，绝不允许先删后拷删掉源包。

    历史缺陷（实测）：copy_dir 传成源包本身时，make_copy 先 `rmtree(copy_dir)`
    把源包删净，再 `copytree(source, …)` 找不到源、抛 FileNotFoundError；
    进程 stdout 空、退出码 1，源包连同 evals/score.json 一起消失。
    当时唯一的守卫 is_unsafe_target 只拦根目录与系统目录，不拦源目录别名。
    """

    def _fixture(self, tmp, name="alias-agent"):
        pkg = make_package(tmp, name, tool_py=STUB_TOOL_PY)
        write_score(pkg, [
            case("c-stub", "fail", detail="NotImplementedError: 工具 search_kb 尚未实现"),
        ])
        return pkg

    def _assert_rejected(self, pkg, copy_dir, label):
        agent_py_before = (pkg / "agent.py").read_text(encoding="utf-8")
        code, stdout, stderr = run_opt({"agent_dir": str(pkg),
                                        "copy_dir": str(copy_dir)})
        self.assertEqual(code, 1, f"{label}：应判失败并退出码 1。stderr:\n{stderr[:400]}")
        result = parse_stdout(stdout)
        self.assertFalse(result["ok"], f"{label}：应是错误信封，实际 {result}")
        self.assertEqual(result["error"]["code"], "copy_dir_overlaps_source",
                         f"{label}：错误码应是 copy_dir_overlaps_source：{result['error']}")
        self.assertNotIn("Traceback", stderr, f"{label}：不得以未捕获异常收场")
        # 铁律：源包必须还在，且逐字节未变
        self.assertTrue(pkg.is_dir(), f"{label}：源包目录被删了")
        self.assertTrue((pkg / "agent.py").is_file(), f"{label}：源包入口被删了")
        self.assertEqual(agent_py_before, (pkg / "agent.py").read_text(encoding="utf-8"),
                         f"{label}：源包内容被改了")
        self.assertTrue((pkg / "evals" / "score.json").is_file(),
                        f"{label}：源包的 evals/ 被删了")

    def test_copy_dir_equal_to_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._fixture(tmp, "same-dir-agent")
            self._assert_rejected(pkg, pkg, "copy_dir == agent_dir")

    def test_copy_dir_is_source_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._fixture(tmp, "parent-dir-agent")
            self._assert_rejected(pkg, pkg.parent, "copy_dir == agent_dir.parent")

    def test_copy_dir_inside_source_is_rejected(self):
        """副本落在源包内部同样不许：那是往源包里写，源只读被破坏。"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._fixture(tmp, "inner-dir-agent")
            self._assert_rejected(pkg, pkg / "inner-fix", "copy_dir 在源包内部")

    def test_sibling_copy_dir_still_works(self):
        """对照组：正常副本路径不受影响，补丁照打。

        退出码不恒为 0——opt 只在 verdict=improved 时退 0，复测没转好就是 1。
        这里要证明的是「没被重叠守卫误伤」，所以断言的是补丁与副本，不是退出码。
        """
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._fixture(tmp, "sibling-agent")
            _, stdout, stderr = run_opt({"agent_dir": str(pkg)})
            result = parse_stdout(stdout)
            self.assertNotIn("copy_dir_overlaps_source",
                             json.dumps(result, ensure_ascii=False),
                             "正常副本路径被重叠守卫误伤了")
            self.assertGreaterEqual(result["patches_applied_total"], 1,
                                    f"正常路径应照常打补丁：{result.get('patches')}")
            self.assertTrue(Path(result["copy_dir"]).is_dir(), "副本应被建立")
            self.assertNotIn("Traceback", stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
