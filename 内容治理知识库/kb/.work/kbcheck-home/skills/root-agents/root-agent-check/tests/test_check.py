"""root-agent-check · 公开 seam 回归测试

seam：CLI 进程边界。测试只通过子进程调用 check，断言 stdout JSON 与
memory/growth.json 的内容。

设计要点：全部用现场构造的确定性夹具。家族根里没有预置样例包，
「真实端到端」那条也改成现场造：creater 造包 → eval 真跑一遍 → 拿评测器
产出的真 score.json。本机无模型端点，所以真跑的结果恒为全员无作答，
只能用来验证 `insufficient_evidence` 这一条路径。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
CHECK = WORKSPACE / "root-agents" / "root-agent-check" / "agent.py"
# ── 夹具：现场用家族自己的 creater + eval 造一个真实端到端包 ──
# 本文件声明的原则是「夹具全部现场构造，不依赖仓库内既有包」；
# 原来指向仓库内预置样例包的常量违背了这条原则，这里改回现场构造。
FAMILY = Path(__file__).resolve().parents[2]


def _build_real_package(root):
    """creater 造包 → eval 真跑一遍 → 目标包里落一份评测器产出的真 evals/score.json。"""
    req = {
        "name": "fixture-real-agent",
        "task_types": ["fact_qa", "reasoning", "multi_turn",
                       "instruction", "rag", "safety"],
        "tools": [{"name": "search_kb", "description": "检索知识库"}],
        "purpose": "check 回归用的真实端到端夹具（本机无模型端点）",
        "target_dir": str(root),
        "force": True,
    }
    proc = subprocess.run(
        [sys.executable, str(FAMILY / "root-agent-creater" / "agent.py")],
        input=json.dumps(req), capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("fixture build failed: %s\n%s" % (proc.stdout, proc.stderr))
    pkg = Path(root) / req["name"]
    ev = subprocess.run(
        [sys.executable, str(FAMILY / "root-agent-eval" / "agent.py")],
        input=json.dumps({"agent_dir": str(pkg)}), capture_output=True, text=True,
        timeout=900)
    # eval 的非零退出码说的是「被测对象的判定」（本机恒 degraded_fail），
    # 不是工具自己跑没跑成；判据是 evals/score.json 有没有落盘。
    if not (pkg / "evals" / "score.json").is_file():
        raise RuntimeError("fixture eval produced no score.json\nstdout: %s\nstderr: %s"
                           % (ev.stdout[:2000], ev.stderr[:2000]))
    return pkg


_FIXTURE_ROOT = tempfile.mkdtemp(prefix="rank-check-fixture-")
REAL_PACKAGE = _build_real_package(_FIXTURE_ROOT)

AGENT_YAML = """name: {name}
version: "0.1.0"
stage: create
interface: cli
run: python3 agent.py
input: stdin-json
profile: general
task_types:
  - fact_qa
tools: []
env:
  API_KEY: ${{managed}}
"""


def run_check(request, timeout=300):
    """memory_dir 必须显式传入：测试间共享真实记忆目录会互相污染
    （实测踩到：前一个测试立的规则让后一个测试的模式提前达标）。"""
    proc = subprocess.run(
        [sys.executable, str(CHECK)],
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


def make_target(root, name, cases, verdict="fail", environment_degraded=False):
    """现场构造一个带 evals/score.json 的目标包。字段形状照抄 root-agent-eval 产出。"""
    pkg = Path(root) / name
    (pkg / "evals").mkdir(parents=True, exist_ok=True)
    (pkg / "agent.yaml").write_text(AGENT_YAML.format(name=name), encoding="utf-8")
    counts = {"total": len(cases)}
    for key in ("eligible", "na", "pass", "fail", "error", "inconclusive"):
        counts[key] = 0
    for case in cases:
        outcome = case["outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome != "na":
            counts["eligible"] += 1
    doc = {
        "agent": name,
        "agent_dir": str(pkg),
        "threshold": 0.6,
        "verdict": verdict,
        "verdict_confidence": "normal",
        "environment_degraded": environment_degraded,
        "environment_notes": [],
        "scores": {"pass_rate": None, "coverage": 1.0, "total_score": None},
        "counts": counts,
        "formula": "pass_rate=pass/decisive",
        "dimensions": {},
        "cases": cases,
    }
    (pkg / "evals" / "score.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pkg


def case(case_id, outcome, strength="real", detail="", dimension="fact_qa"):
    return {
        "id": case_id,
        "dimension": dimension,
        "difficulty": "L1",
        "outcome": outcome,
        "assessment_strength": strength,
        "detail": detail,
        "exit_code": 0,
        "duration_ms": 1,
        "unresolved_expectations": [],
    }


def read_memory(memory_dir):
    return json.loads((Path(memory_dir) / "growth.json").read_text(encoding="utf-8"))


class InsufficientEvidence(unittest.TestCase):
    """故事 5、9：没有决定性证据时绝不能声称成长。

    这正是本机真实情况：环境缺模型端点，全部用例 inconclusive。
    把它报成 grew 或 degraded，就是把环境问题误报成能力变化。
    """

    def test_all_environment_blocked_is_insufficient_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_target(tmp, "env-blocked-agent", [
                case("c1", "inconclusive", strength="structural",
                     detail="agent 未给出作答内容（answer 为空或缺失）"),
                case("c2", "inconclusive", strength="structural",
                     detail="agent 未给出作答内容（answer 为空或缺失）"),
            ], verdict="inconclusive", environment_degraded=True)

            code, stdout, stderr = run_check({
                "targets": [str(Path(tmp) / "env-blocked-agent")],
                "run_id": "run-A",
                "memory_dir": tmp,
            })
            self.assertEqual(code, 0, f"证据不足是合法结论，应退出码 0。stderr:\n{stderr}")
            result = parse_stdout(stdout)

            self.assertEqual(result["growth_verdict"], "insufficient_evidence")
            self.assertEqual(result["counts"]["decisive_cases"], 0)
            self.assertEqual(result["counts"]["environment_blocked_cases"], 2)

    def test_no_targets_is_insufficient_evidence_not_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _ = run_check(
                {"targets": [], "run_id": "run-empty", "memory_dir": tmp})
        self.assertEqual(code, 0, "没有目标不是失败")
        result = parse_stdout(stdout)
        self.assertEqual(result["growth_verdict"], "insufficient_evidence")

    def test_real_package_is_insufficient_evidence(self):
        """真实端到端：现场造的包经评测器真跑一遍，本机全员无作答，只能得出证据不足。

        这条同时钉住两件事：check 能读懂评测器真产出的 score.json 形状，
        且无作答不算成长证据——报成 grew / degraded 就是把环境问题当能力变化。
        """
        self.assertTrue((REAL_PACKAGE / "evals" / "score.json").is_file(),
                        "夹具包必须带着评测器真产出的 score.json")
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_check({
                "targets": [str(REAL_PACKAGE)],
                "run_id": "run-real",
                "memory_dir": tmp,
            })
            self.assertEqual(code, 0, f"stderr:\n{stderr}")
            result = parse_stdout(stdout)
            self.assertEqual(result["growth_verdict"], "insufficient_evidence",
                             f"报告：{result}")


class SingleOccurrenceDoesNotBecomeRule(unittest.TestCase):
    """故事 2：单次观察不立规则。这道门槛是「不编造成长」的第一道防线。"""

    def test_one_occurrence_goes_to_pending_not_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_target(tmp, "single-agent", [
                case("c1", "fail", detail="NotImplementedError 工具 search_kb 未实现"),
            ])
            code, stdout, _ = run_check({
                "targets": [str(Path(tmp) / "single-agent")],
                "run_id": "run-single-1",
                "memory_dir": tmp,
            })
            self.assertEqual(code, 0, stdout)
            result = parse_stdout(stdout)

            self.assertEqual(result["new_rules"], [],
                             f"单次观察不得立规则：{result['new_rules']}")
            self.assertEqual(len(result["pending_patterns"]), 1,
                             f"应记入待复现：{result['pending_patterns']}")
            pending = result["pending_patterns"][0]
            self.assertEqual(pending["occurrences"], 1)
            self.assertIn("新证据", pending["note"],
                          f"应说清门槛要的是新证据（不是多跑几轮）：{pending}")
            self.assertEqual(pending["occurrences"], 1,
                             "一份证据就是一份，不能按 run 数虚增")


class RepeatedPatternBecomesRule(unittest.TestCase):
    """故事 3、4：同一模式拿到**两份不同证据**后才立规则，记忆跨轮累积。

    注意「独立复现」的定义（第二版修正）：数的是**证据指纹**，不是 run 次数。
    同一份 score.json 换个 run_id 重读一遍，证据指纹一样 → 不算第二次复现。
    """

    def test_second_evidence_from_another_target_creates_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_a = make_target(tmp, "repeat-agent-a", [
                case("c1", "fail", detail="NotImplementedError 工具 search_kb 未实现"),
            ])
            pkg_b = make_target(tmp, "repeat-agent-b", [
                case("c1", "fail", detail="NotImplementedError 工具 search_kb 未实现"),
            ])

            code1, out1, _ = run_check({
                "targets": [str(pkg_a)], "run_id": "run-repeat-1",
                "memory_dir": tmp})
            self.assertEqual(code1, 0, out1)
            first = parse_stdout(out1)
            self.assertEqual(first["new_rules"], [])

            code2, out2, _ = run_check({
                "targets": [str(pkg_b)], "run_id": "run-repeat-2",
                "memory_dir": tmp})
            self.assertEqual(code2, 0, out2)
            second = parse_stdout(out2)

            self.assertEqual(len(second["new_rules"]), 1,
                             f"两个包上复现同一模式应立规则：{second['new_rules']}")
            rule = second["new_rules"][0]
            self.assertGreaterEqual(rule["occurrences"], 2,
                                    "独立证据数应 ≥ 门槛")
            self.assertEqual(len(rule["evidence_keys"]), rule["occurrences"],
                             "证据指纹数与复现次数必须一致")
            self.assertIn("run-repeat-1", rule["evidence_runs"])
            self.assertIn("run-repeat-2", rule["evidence_runs"])
            self.assertTrue(rule["statement"], "规则必须有语句")

            # 故事 4：记忆跨轮累积
            mem = read_memory(tmp)
            run_ids = [r["run_id"] for r in mem["runs"]]
            self.assertIn("run-repeat-1", run_ids)
            self.assertIn("run-repeat-2", run_ids)
            self.assertGreaterEqual(len(mem["rules"]), 1, "规则应持久化在记忆里")

    def test_same_evidence_reread_is_not_a_reproduction(self):
        """反例钉子：score.json 一个字节不改、只换 run_id，不得立规则、不得判 grew。

        历史缺陷（实测）：复现次数按 run_id 个数数，于是同一份评分文件被读第二遍
        就算「复现 2 次」，凭空立规则并把 growth_verdict 报成 grew。
        """
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_target(tmp, "same-evidence-agent", [
                case("c1", "fail", detail="NotImplementedError 工具 search_kb 未实现"),
            ])
            score_before = (pkg / "evals" / "score.json").read_bytes()

            _, out1, _ = run_check({"targets": [str(pkg)], "run_id": "run-x1",
                                    "memory_dir": tmp})
            r1 = parse_stdout(out1)
            self.assertEqual(r1["new_rules"], [])

            # 内容一字未改，只换 run_id
            self.assertEqual(score_before,
                             (pkg / "evals" / "score.json").read_bytes())
            _, out2, _ = run_check({"targets": [str(pkg)], "run_id": "run-x2",
                                    "memory_dir": tmp})
            r2 = parse_stdout(out2)

            self.assertEqual(r2["new_rules"], [],
                             f"同一份证据重读不得立规则：{r2['new_rules']}")
            self.assertNotEqual(r2["growth_verdict"], "grew",
                                "同一份证据重读不得判 grew")
            self.assertEqual(len(r2["pending_patterns"]), 1,
                             f"应仍停在待复现：{r2['pending_patterns']}")
            pending = r2["pending_patterns"][0]
            self.assertEqual(pending["occurrences"], 1,
                             "同一份证据只算 1 份，不能因换 run_id 变成 2")
            self.assertIn("新证据", pending["note"],
                          f"应说清需要的是新证据：{pending['note']}")
            # 记忆仍然只增不减：两轮记录都在
            mem = read_memory(tmp)
            self.assertEqual(len(mem["runs"]), 2)

    def test_same_run_id_is_idempotent(self):
        """故事 14：同一 run_id 重复提交不得重复计数。"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_target(tmp, "idem-agent", [
                case("c1", "fail", detail="NotImplementedError 工具未实现"),
            ])
            run_check({"targets": [str(pkg)], "run_id": "run-idem",
                       "memory_dir": tmp})
            run_check({"targets": [str(pkg)], "run_id": "run-idem",
                       "memory_dir": tmp})
            mem = read_memory(tmp)
            same = [r for r in mem["runs"] if r["run_id"] == "run-idem"]
            self.assertEqual(len(same), 1,
                             f"同一 run_id 只应有一条记录：{len(same)} 条")


class CapabilityLadderHonesty(unittest.TestCase):
    """故事 6：能力阶梯绝不允许在无证据时标 achieved。"""

    def test_rl_and_synthetic_data_are_blocked_with_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_target(tmp, "ladder-agent", [case("c1", "pass")])
            _, stdout, _ = run_check({
                "targets": [str(Path(tmp) / "ladder-agent")],
                "run_id": "run-ladder", "memory_dir": tmp})
            result = parse_stdout(stdout)
            levels = {lvl["level"]: lvl for lvl in result["ladder"]["levels"]}

            self.assertIn(3, levels, f"阶梯应含 level 3：{levels.keys()}")
            self.assertIn(4, levels)
            self.assertEqual(levels[3]["state"], "blocked",
                             "无模型端点时合成数据生成必须 blocked")
            self.assertEqual(levels[4]["state"], "blocked",
                             "无训练栈时 RL 训练必须 blocked")
            for level in (3, 4):
                self.assertTrue(levels[level].get("requires"),
                                f"blocked 必须写明缺什么条件：{levels[level]}")
                self.assertTrue(levels[level].get("evidence"),
                                f"blocked 必须写明如何确认：{levels[level]}")

    def test_achieved_levels_have_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_target(tmp, "ladder2-agent", [case("c1", "pass")])
            _, stdout, _ = run_check({
                "targets": [str(Path(tmp) / "ladder2-agent")],
                "run_id": "run-ladder2", "memory_dir": tmp})
            result = parse_stdout(stdout)
            for lvl in result["ladder"]["levels"]:
                if lvl["state"] == "achieved":
                    self.assertTrue(lvl.get("evidence"),
                                    f"achieved 必须给出证据：{lvl}")


class GrowthAcrossRuns(unittest.TestCase):
    """自动成长的本体：跨轮累积证据 + 成长曲线 + 记忆只增不减。"""

    def test_two_runs_produce_growth_curve_and_persist_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 证据必须来自两个不同的包：同一份评分文件重读不算新证据（第二版规则）
            pkg = make_target(tmp, "curve-agent", [
                case("c1", "fail", detail="NotImplementedError 工具 search_kb 未实现"),
                case("c2", "fail", detail="NotImplementedError 工具 search_kb 未实现"),
            ])
            pkg_b = make_target(tmp, "curve-agent-b", [
                case("c1", "fail", detail="NotImplementedError 工具 search_kb 未实现"),
                case("c2", "fail", detail="NotImplementedError 工具 search_kb 未实现"),
            ])

            _, out1, _ = run_check({"targets": [str(pkg)], "run_id": "run-c1",
                                    "memory_dir": tmp})
            r1 = parse_stdout(out1)
            self.assertEqual(r1["new_rules"], [], "首轮不立规则")
            self.assertEqual(r1["runs_recorded"], 1)

            _, out2, _ = run_check({"targets": [str(pkg_b)], "run_id": "run-c2",
                                    "memory_dir": tmp})
            r2 = parse_stdout(out2)
            # 夹具里是真实判定（strength=real）的 fail 用例 → decisive=2，
            # 且第二轮拿到第二份证据、新立规则 → 正确结论是 grew。
            self.assertEqual(r2["growth_verdict"], "grew",
                             f"有决定性证据且新立规则，应判 grew：{r2['counts']}")
            self.assertGreaterEqual(r2["counts"]["decisive_cases"], 1)
            self.assertEqual(len(r2["new_rules"]), 1, "第二份证据到位即立规则")
            self.assertEqual(r2["runs_recorded"], 2, "记忆应跨轮累积")

            # 第三轮：无新规则 → no_growth（这才是 no_growth 的正确场景）
            _, out3, _ = run_check({"targets": [str(pkg)], "run_id": "run-c3",
                                    "memory_dir": tmp})
            r3 = parse_stdout(out3)
            self.assertEqual(r3["growth_verdict"], "no_growth",
                             "无新规则且无失守时应判 no_growth")
            self.assertEqual(r3["new_rules"], [])

            mem = read_memory(tmp)
            self.assertEqual(len(mem["runs"]), 3)
            self.assertGreaterEqual(len(mem["rules"]), 1)
            # 规则携带完整证据链：两个包 = 两份独立证据
            rule = mem["rules"][0]
            self.assertEqual(rule["occurrences"], 2,
                             f"两份独立证据：{rule['evidence_keys']}")
            self.assertEqual(sorted(rule["evidence_runs"]),
                             ["run-c1", "run-c2"],
                             "证据 run 记的是「哪几轮拿出了不同证据」，"
                             "重读同一份证据的第三轮不算新证据")
            self.assertIn("run-c3", sorted(r["run_id"] for r in mem["runs"]),
                          "记忆仍要记下第三轮")

            # 成长曲线文件存在且含三轮
            md = (Path(tmp) / "growth.md").read_text(encoding="utf-8")
            self.assertIn("成长曲线", md)
            self.assertIn("run-c1", md)
            self.assertIn("run-c2", md)
            self.assertIn("run-c3", md)
            self.assertIn("互不相同的证据", md,
                          "记忆文件里要写明门槛按证据指纹算")

    def test_zero_decisive_evidence_creates_no_rule(self):
        """反例钉子：决定性用例为 0 的轮次，无论跑多少遍都不立规则、不判 grew。

        历史缺陷（实测）：synthesize_rules 先执行且不读 counts，零决定性证据的
        环境报告照样立规则、把能力阶梯标成 achieved；只有 growth_verdict 文案被拦。
        """
        with tempfile.TemporaryDirectory() as tmp:
            make_target(tmp, "zero-evidence-a", [
                case("c1", "inconclusive", strength="structural",
                     detail="agent 未给出作答内容（answer 为空或缺失）"),
            ], verdict="inconclusive", environment_degraded=True)
            make_target(tmp, "zero-evidence-b", [
                case("c1", "inconclusive", strength="structural",
                     detail="agent 未给出作答内容（answer 为空或缺失）"),
            ], verdict="inconclusive", environment_degraded=True)

            for index, name in enumerate(("zero-evidence-a", "zero-evidence-b"), start=1):
                _, out, _ = run_check({
                    "targets": [str(Path(tmp) / name)],
                    "run_id": f"run-zero-{index}", "memory_dir": tmp})
                result = parse_stdout(out)
                self.assertEqual(result["new_rules"], [],
                                 f"决定性证据为 0 不得立规则：{result['new_rules']}")
                self.assertEqual(result["growth_verdict"], "insufficient_evidence")
                self.assertEqual(result["active_rules"], 0)
                self.assertEqual(result["ladder"]["state"], "level0",
                                 "零决定性证据不得晋级能力阶梯")
            mem = read_memory(tmp)
            self.assertEqual(mem["rules"], [], "记忆里不该留下无证据的规则")
            for rule in mem["rules"]:
                self.assertTrue(rule.get("evidence_keys"),
                                "立的每条规则都必须带证据指纹")

    def test_memory_never_shrinks(self):
        """故事 15：记忆只增不减——历史 run 不被覆盖。"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_target(tmp, "shrink-agent", [case("c1", "pass")])
            for index in range(1, 4):
                run_check({"targets": [str(pkg)], "run_id": f"run-s{index}",
                           "memory_dir": tmp})
            mem = read_memory(tmp)
            self.assertEqual(len(mem["runs"]), 3,
                             f"三轮应留下三条记录：{[r['run_id'] for r in mem['runs']]}")

    def test_environment_blocked_run_records_note(self):
        """环境全阻塞时，run 记录里必须写明为什么不给成长结论。"""
        with tempfile.TemporaryDirectory() as tmp:
            make_target(tmp, "env-note-agent", [
                case("c1", "inconclusive", strength="structural",
                     detail="agent 未给出作答内容（answer 为空或缺失）"),
            ], verdict="inconclusive", environment_degraded=True)
            run_check({"targets": [str(Path(tmp) / "env-note-agent")],
                       "run_id": "run-env", "memory_dir": tmp})
            mem = read_memory(tmp)
            run = [r for r in mem["runs"] if r["run_id"] == "run-env"][0]
            self.assertEqual(run["growth_verdict"], "insufficient_evidence")
            self.assertIn("环境", run["note"])
            self.assertTrue(run["note"], "note 必须非空说明原因")


class CorruptMemory(unittest.TestCase):
    """故事 10：记忆损坏时不静默重建。"""

    def test_corrupt_memory_is_reported_and_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "growth.json").write_text("{ 这不是 JSON", encoding="utf-8")
            code, stdout, _ = run_check({
                "targets": [], "run_id": "run-bad", "memory_dir": tmp})
            self.assertNotEqual(code, 0)
            result = parse_stdout(stdout)
            self.assertIs(result["ok"], False)
            self.assertEqual(result["error"]["code"], "memory_corrupt")
            # 原文件必须保留为 .bak，且不被静默覆盖成空记忆
            self.assertTrue((Path(tmp) / "growth.json.bak").is_file(),
                            "损坏的记忆必须备份保留")

    def test_missing_target_recorded_not_failed(self):
        """故事 8：某个目标缺 score.json 时跳过并记明，不整体失败。"""
        with tempfile.TemporaryDirectory() as tmp:
            good = make_target(tmp, "good-agent", [case("c1", "pass")])
            missing = Path(tmp) / "no-score-agent"
            missing.mkdir()

            code, stdout, _ = run_check({
                "targets": [str(good), str(missing)],
                "run_id": "run-mixed", "memory_dir": tmp})
            self.assertEqual(code, 0, "缺 score 的目标不应导致整体失败")
            result = parse_stdout(stdout)
            self.assertEqual(len(result["skipped_targets"]), 1)
            self.assertIn("score.json", result["skipped_targets"][0]["reason"])


class MinimalYamlParserHandlesInlineCollections(unittest.TestCase):
    """dogfooding 发现：本体系自写的最小 YAML 解析器不认内联空集合。

    实测现象：root-agent-check 的 agent.yaml 里写 `targets: []`，doctor 解析成
    字符串 "[]"，于是体检时 check 收到 {"targets": "[]"} → 报「targets 必须是数组」
    → 退出 1 → doctor 判 unhealthy。

    这影响**所有**在 agent.yaml 里用内联 [] / {} 的 agent（creater 的 health.input
    也用了内联 {}）。故在解析器所在处直接验证，而不是绕过去调 agent。
    """

    def _parser(self, path):
        from importlib import util as _util
        spec = _util.spec_from_file_location("mod", path)
        mod = _util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_inline_empty_list_and_map_parse_correctly(self):
        for rel in ("root-agent-doctor/agent.py", "root-agent-eval/agent.py"):
            mod = self._parser(WORKSPACE / "root-agents" / rel)
            parsed = mod.parse_yaml_text(
                "a: []\n"
                "b: {}\n"
                "c:\n"
                "  - x\n"
                "d: plain\n"
                "e: 42\n"
                "f: true\n"
            )
            self.assertEqual(parsed["a"], [], f"{rel}: 空数组应解析为 list")
            self.assertEqual(parsed["b"], {}, f"{rel}: 空映射应解析为 dict")
            self.assertEqual(parsed["c"], ["x"], f"{rel}: 块状列表仍须正常")
            self.assertEqual(parsed["d"], "plain", f"{rel}: 标量仍须正常")
            self.assertEqual(parsed["e"], 42, f"{rel}: 数字应解析为 int")
            self.assertIs(parsed["f"], True, f"{rel}: 布尔应解析为 bool")

    def test_declared_health_probe_payload_parses_as_list(self):
        """把 agent.yaml 的 health 段落交给解析器，targets 必须是 list。"""
        mod = self._parser(WORKSPACE / "root-agents" / "root-agent-doctor" / "agent.py")
        yaml_text = (WORKSPACE / "root-agents" / "root-agent-check"
                     / "agent.yaml").read_text(encoding="utf-8")
        manifest = mod.parse_yaml_text(yaml_text)
        health = manifest.get("health") or {}
        payload = health.get("input") or {}
        self.assertIn("targets", payload, "探针应声明 targets")
        self.assertIsInstance(
            payload["targets"], list,
            f"targets 必须是 list（解析器把内联 [] 当成了字符串）：{payload!r}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
