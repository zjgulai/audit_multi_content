"""root-agent-eval · 扩展静态检查（与 doctor 的 D 组同源）回归测试

seam：CLI 进程边界。夹具全部现场构造，不依赖仓库内既有包。

三条口径是本文件的钉子：

  1. **能力门控**：无状态、单 agent 的包，`state_contract` 与 `collab_contract`
     必须是 0 命中 —— 不适用不是扣分项；但两项仍要逐项出现在表里（不适用 ≠ 不存在）。
  2. **干净包不掉分**：最小健康夹具的 `static_score` 仍是 1.0、`static_issues` 仍是 []，
     新增检测不许把健康包判成缺陷。
  3. **跨成员口径一致**：同一份缺陷包，doctor 与 eval 必须报出同一批问题。
     这条钉子是给未来改单边口径的人准备的：谁只改一边，本文件立刻红。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
EVAL = WORKSPACE / "root-agents" / "root-agent-eval" / "agent.py"
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
  - id: answer
    name: 业务答复
    format: text
    acceptance: 直接回答用户的问题
tools: []
env:
  API_KEY: ${{managed}}
"""

AGENT_PY = '''#!/usr/bin/env python3
import json
import sys

raw = sys.stdin.read()
request = json.loads(raw) if raw.strip() else {}
print(json.dumps({"ok": True, "answer": "pong"}, ensure_ascii=False))
'''

PROMPT = "# 提示词\n\n回答业务问题。\n"

# 子 agent / 兄弟包夹具路径**运行时拼接**：源码里不留连续的 `subagents/…/agent.py`
# 字面量。doctor 扫本包时会把这段夹具路径当成「eval 自己引用的子 agent」（它的能力
# 检测排除 tests/，但一旦有人把单边口径改回去就会踩到），所以路径一律拼出来。
SUBAGENT_DIR = "sub" + "agents/refund"
SUBAGENT_ENTRY = SUBAGENT_DIR + "/agent.py"
# 别的 agent 包的入口（文档只贴路径用）与兄弟包入口（代码里真去调用用）
FOREIGN_ENTRY = "root-agent" + "-creater/agent.py"
SIBLING_PKG = "refund" + "-agent"
SIBLING_ENTRY = ".." + "/" + SIBLING_PKG + "/agent.py"

# 一条结构期望全部满足的用例：缺陷夹具的判定不受用例结论影响（静态检查独立计分）
SMOKE_CASES = [{"id": "c-1", "dimension": "fact_qa", "difficulty": "L1",
                "tool_required": [], "input": {"question": "ping"},
                "expect": {"ok": True}}]

# 检查项 → 单次扣分（照 root-agent-eval 的 STATIC_CHECK_ITEMS）。
# 写在这里是为了钉住口径：改扣分额度必须同时改这张表。
DEDUCTIONS = {
    "dangling_refs": 10,
    "placeholder_left": 10,
    "hardcoded_path": 10,
    "unbounded_loop": 10,
    "undeclared_tool_ref": 5,
    "state_contract": 10,
    "collab_contract": 10,
}

# doctor 的 D 组 check id ↔ eval 的静态检查 id：同源检测项在两环里的名字
DOCTOR_IDS = {
    "dangling_refs": "instructions.dangling_refs",
    "placeholder_left": "instructions.placeholders",
    "hardcoded_path": "deps.hardcoded_path",
    "unbounded_loop": "flow.loop_bound",
    "state_contract": "state.declared",
    "collab_contract": "collab.handoff_declared",
}


def run_eval(pkg, generate=False, timeout=180):
    proc = subprocess.run(
        [sys.executable, str(EVAL)],
        input=json.dumps({"agent_dir": str(pkg), "generate": generate},
                         ensure_ascii=False),
        capture_output=True, text=True, timeout=timeout)
    return proc


def eval_result(proc):
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"eval stdout 不是合法 JSON（{exc}）。前 500 字符：\n{proc.stdout[:500]}\n"
            f"stderr：\n{proc.stderr[:500]}") from exc


def run_doctor(pkg, skip_instantiate=True):
    """跑 doctor 的 CLI。skip_instantiate：本文件只对 D 组口径，不重复测实例化。"""
    proc = subprocess.run(
        [sys.executable, str(DOCTOR)],
        input=json.dumps({"agent_dir": str(pkg),
                          "skip_instantiate": bool(skip_instantiate)},
                         ensure_ascii=False),
        capture_output=True, text=True, timeout=180)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"doctor stdout 不是合法 JSON（{exc}）。前 500 字符：\n{proc.stdout[:500]}\n"
            f"stderr：\n{proc.stderr[:500]}") from exc


def doctor_check(result, check_id):
    for item in result.get("checks", []):
        if item.get("id") == check_id:
            return item
    raise AssertionError(
        f"doctor 报告缺 check {check_id!r}，实际含 "
        f"{[c.get('id') for c in result.get('checks', [])]}")


def make_pkg(root, name, agent_py=AGENT_PY, prompt=PROMPT, manifest=None, extra=None):
    """现场造包：agent.py / agent.yaml / prompts/system.md / tests/smoke.json。"""
    pkg = Path(root) / name
    (pkg / "prompts").mkdir(parents=True)
    (pkg / "tests").mkdir(parents=True)
    (pkg / "agent.yaml").write_text(
        manifest if manifest is not None else MANIFEST.format(name=name),
        encoding="utf-8")
    if agent_py is not None:
        (pkg / "agent.py").write_text(agent_py, encoding="utf-8")
    (pkg / "prompts" / "system.md").write_text(prompt, encoding="utf-8")
    (pkg / "tests" / "smoke.json").write_text(
        json.dumps({"agent": name, "cases": SMOKE_CASES}, ensure_ascii=False),
        encoding="utf-8")
    for rel, content in (extra or {}).items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return pkg


class ExtendedItemsHit(unittest.TestCase):
    """七项新检查各一条命中用例：造缺陷包 → 该 id 命中且扣分。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def items_of(self, pkg):
        proc = run_eval(pkg)
        self.assertEqual(proc.returncode, 0,
                         f"评测应正常退出：\n{proc.stdout[:600]}\n{proc.stderr[:600]}")
        result = eval_result(proc)
        return ({i["id"]: i for i in result["scores"]["static_checks"]}, result)

    def assert_hit(self, items, check_id):
        item = items[check_id]
        self.assertGreater(item["hit_count"], 0,
                           f"{check_id} 应命中，实际 {item['hit_count']} 处：{item}")
        self.assertGreater(item["deducted"], 0, f"{check_id} 应扣分：{item}")
        self.assertEqual(item["deduction_per_hit"], DEDUCTIONS[check_id],
                         f"{check_id} 的单次扣分口径变了")
        for hit in item["hits"]:
            self.assertTrue(hit.get("file"), f"{check_id} 的命中缺 file：{hit}")
            self.assertTrue(hit.get("detail"), f"{check_id} 的命中缺 detail：{hit}")

    def assert_clean(self, items, check_id):
        item = items[check_id]
        self.assertEqual(item["hit_count"], 0,
                         f"{check_id} 不该命中：{item['hits']}")
        self.assertEqual(item["deducted"], 0)

    # ---------------------------------------------------------------- 1 悬空引用

    def test_dangling_ref_hits_and_resolved_ref_is_clean(self):
        pkg = make_pkg(self.root, "dangling",
                       prompt="# 提示词\n\n模板见 templates/report.md。\n")
        items, result = self.items_of(pkg)
        self.assert_hit(items, "dangling_refs")
        self.assertIn("templates/report.md",
                      items["dangling_refs"]["hits"][0]["detail"])
        self.assertEqual(result["scores"]["static_score"], 0.9,
                         "一处悬空引用扣 10 分静态分")

        # 引用真的落地之后不能再报 —— 否则这项退化成「只要提到路径就扣分」
        ok = make_pkg(self.root, "dangling-ok",
                      prompt="# 提示词\n\n模板见 templates/report.md。\n",
                      extra={"templates/report.md": "# 模板\n"})
        items_ok, _ = self.items_of(ok)
        self.assert_clean(items_ok, "dangling_refs")

    def test_artifact_dirs_and_tests_are_not_references(self):
        """产物目录里的路径与 tests/ 下的题面素材都不判悬空。"""
        pkg = make_pkg(self.root, "artifact-refs", extra={
            "notes.json": '{"hint": "产物见 outputs/report.md"}\n',
            "tests/scenario.json": '{"material": "见 knowledge/missing.md"}\n',
            "memory/notes.md": "# 记忆\n\n{{STALE_SLOT}}\n",
        })
        items, result = self.items_of(pkg)
        self.assert_clean(items, "dangling_refs")
        self.assert_clean(items, "placeholder_left")
        self.assertEqual(result["scores"]["static_issues"], [],
                         f"产物目录不是被测方的缺陷：{result['scores']['static_issues']}")

    # ---------------------------------------------------------------- 2 占位符

    def test_placeholder_hits_but_code_fence_is_exempt(self):
        prompt = ("# 提示词\n\n署名用 {{BRAND_NAME}}。\n\n"
                  "```jinja\n{{ 这是示例模板 }}\n```\n")
        pkg = make_pkg(self.root, "placeholder", prompt=prompt)
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "placeholder_left")
        hits = " ".join(h["file"] for h in items["placeholder_left"]["hits"])
        self.assertIn("system.md:3", hits, "第 3 行的占位符必须报出来")
        self.assertEqual(items["placeholder_left"]["hit_count"], 1,
                         f"代码块里的模板示例不算未替换占位符：{hits}")

    def test_placeholder_in_legacy_syntax_hits(self):
        pkg = make_pkg(self.root, "placeholder-legacy",
                       prompt="# 提示词\n\n报告标题：{% TITLE %}\n")
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "placeholder_left")

    # ---------------------------------------------------------------- 3 硬编码主目录

    def test_hardcoded_home_path_hits(self):
        # 运行时拼接：源码里不留连续的个人主目录字面量，
        # 否则本包自己的路径扫描会命中这段夹具源码（与 doctor 的测试同一手法）
        home = "/Use" "rs/lute/Desktop/project/data.xlsx"
        agent_py = AGENT_PY.replace(
            'print(json.dumps',
            f'DATA = "{home}"\nprint(json.dumps')
        pkg = make_pkg(self.root, "hardcoded-path", agent_py=agent_py)
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "hardcoded_path")
        self.assertIn("agent.py", items["hardcoded_path"]["hits"][0]["file"])

    # ---------------------------------------------------------------- 4 无界循环

    def test_unbounded_loop_hits_and_bounded_loop_is_clean(self):
        looping = AGENT_PY.replace(
            "raw = sys.stdin.read()",
            "def spin():\n    while True:\n        pass\n\n\nraw = sys.stdin.read()")
        pkg = make_pkg(self.root, "unbounded", agent_py=looping)
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "unbounded_loop")

        bounded = AGENT_PY.replace(
            "raw = sys.stdin.read()",
            "def spin():\n    while True:\n        break\n\n\nraw = sys.stdin.read()")
        ok = make_pkg(self.root, "bounded", agent_py=bounded)
        items_ok, _ = self.items_of(ok)
        self.assert_clean(items_ok, "unbounded_loop")

    # ---------------------------------------------------------------- 5 未声明工具

    def test_undeclared_tool_ref_hits_and_declared_tool_is_clean(self):
        pkg = make_pkg(self.root, "ghost-tool",
                       prompt="# 提示词\n\n先用 `ghost_kb` 工具检索，再作答。\n")
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "undeclared_tool_ref")
        self.assertIn("ghost_kb", items["undeclared_tool_ref"]["hits"][0]["detail"])

        # 工具真在契约里声明（并有实现文件）之后不该再报
        declared = MANIFEST.format(name="real-tool").replace(
            "tools: []",
            "tools:\n  - name: kb_search\n    description: 检索知识库\n    schema: {}")
        ok = make_pkg(self.root, "real-tool", manifest=declared,
                      prompt="# 提示词\n\n先用 `kb_search` 工具检索，再作答。\n",
                      extra={"tools/kb_search.py":
                             "def call(**kwargs):\n    return {\"ok\": True}\n"})
        items_ok, _ = self.items_of(ok)
        self.assert_clean(items_ok, "undeclared_tool_ref")

    # ---------------------------------------------------------------- 6 状态约定

    STATEFUL_AGENT_PY = '''#!/usr/bin/env python3
import json
import sys
from pathlib import Path

MEMORY_FILE = "growth.json"


def main():
    raw = sys.stdin.read()
    Path(MEMORY_FILE).write_text(raw, encoding="utf-8")
    print(json.dumps({"ok": True, "answer": "pong"}, ensure_ascii=False))


main()
'''

    STATE_BLOCK = """state:
  path: memory/growth.json
  key: run_id
"""

    def test_stateful_without_state_declaration_hits_and_declared_passes(self):
        pkg = make_pkg(self.root, "stateful-nodecl",
                       agent_py=self.STATEFUL_AGENT_PY)
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "state_contract")
        details = " ".join(h["detail"] for h in items["state_contract"]["hits"])
        self.assertIn("MEMORY_FILE", details, "证据要说清是哪个常量")

        declared = MANIFEST.format(name="stateful-decl") + self.STATE_BLOCK
        ok = make_pkg(self.root, "stateful-decl", agent_py=self.STATEFUL_AGENT_PY,
                      manifest=declared)
        items_ok, _ = self.items_of(ok)
        self.assert_clean(items_ok, "state_contract")

    def test_state_declared_without_key_still_hits(self):
        """有位置没隔离：不同任务共用一个状态文件，先写后读会互相污染。"""
        manifest = MANIFEST.format(name="stateful-nokey") + "state:\n  path: memory/growth.json\n"
        pkg = make_pkg(self.root, "stateful-nokey", agent_py=self.STATEFUL_AGENT_PY,
                       manifest=manifest)
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "state_contract")
        details = " ".join(h["detail"] for h in items["state_contract"]["hits"])
        self.assertIn("key", details)

    # ---------------------------------------------------------------- 7 协作约定

    COLLAB_PROMPT = "# 提示词\n\n把明细交给 " + SUBAGENT_ENTRY + " 汇总。\n"

    COLLAB_BLOCK = ("handoff:\n  to: " + SUBAGENT_DIR
                    + "\n  input:\n    - 订单明细\n  output:\n    - 退款结论\n")

    def test_subagent_ref_hits_both_dangling_and_collab(self):
        """指令面写了不存在的子 agent：悬空引用与缺交接约定各算各的。"""
        pkg = make_pkg(self.root, "collab-dangling", prompt=self.COLLAB_PROMPT)
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "dangling_refs")
        self.assertIn(SUBAGENT_ENTRY,
                      items["dangling_refs"]["hits"][0]["detail"])
        self.assert_hit(items, "collab_contract")

    def test_collab_declared_with_handoff_is_clean(self):
        manifest = MANIFEST.format(name="collab-ok") + self.COLLAB_BLOCK
        pkg = make_pkg(self.root, "collab-ok", prompt=self.COLLAB_PROMPT,
                       manifest=manifest,
                       extra={SUBAGENT_ENTRY: "# 子 agent\n"})
        items, _ = self.items_of(pkg)
        self.assert_clean(items, "collab_contract")
        self.assert_clean(items, "dangling_refs")

    def test_handoff_missing_output_hits(self):
        manifest = MANIFEST.format(name="collab-partial") + (
            "handoff:\n  to: " + SUBAGENT_DIR + "\n  input:\n    - 订单明细\n")
        pkg = make_pkg(self.root, "collab-partial", prompt=self.COLLAB_PROMPT,
                       manifest=manifest,
                       extra={SUBAGENT_ENTRY: "# 子 agent\n"})
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "collab_contract")
        self.assertIn("output",
                      items["collab_contract"]["hits"][0]["detail"])

    # ------------------------------- 8 路径证据只认代码配置面 / 交接对象存在性

    def test_doc_path_reference_alone_is_not_collab_capability(self):
        """文档只贴一行别的 agent 入口路径，是出处说明，不是协作能力。

        路径**存在**（不存在的那些归 dangling_refs 管），所以这里只测一件事：
        指令面引用路径不再被当成「在派子 agent」，不该要求 handoff。
        """
        pkg = make_pkg(self.root, "doc-path-only",
                       prompt="# 提示词\n\n回答业务问题。\n",
                       extra={
                           "README.md": ("# doc-path-only\n\n生成方式见 "
                                         + FOREIGN_ENTRY + "。\n"),
                           FOREIGN_ENTRY: "# 别的 agent\n",
                       })
        items, _ = self.items_of(pkg)
        self.assert_clean(items, "collab_contract")
        self.assert_clean(items, "dangling_refs")

    def test_code_face_subprocess_call_is_collab_capability(self):
        """代码里真去 subprocess 调别的 agent 包 → 有协作能力，缺 handoff 就扣分。

        兄弟包**存在**（同级目录），所以这条测的不是「文件找不到」，而是
        「代码面的路径引用本身就是协作能力证据」。
        """
        sibling = Path(self.root) / SIBLING_PKG
        sibling.mkdir(parents=True)
        (sibling / "agent.py").write_text("# 兄弟包\n", encoding="utf-8")
        agent_py = '''#!/usr/bin/env python3
import json
import sys

CALLEE = "%s"


def delegate():
    # 真的会去调兄弟包。夹具不调用它，避免用例执行期真把别的 agent 拉起来。
    import subprocess
    subprocess.run([sys.executable, CALLEE], check=False)


raw = sys.stdin.read()
request = json.loads(raw) if raw.strip() else {}
print(json.dumps({"ok": True, "answer": "pong"}, ensure_ascii=False))
''' % SIBLING_ENTRY
        pkg = make_pkg(self.root, "code-path", agent_py=agent_py)
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "collab_contract")
        details = " ".join(h["detail"] for h in items["collab_contract"]["hits"])
        self.assertIn(SIBLING_PKG, details, "证据要说清是哪个文件引用了谁")
        self.assert_clean(items, "dangling_refs")

    def test_handoff_to_missing_sibling_hits(self):
        """交接对象不存在：to/input/output 写全了也扣分（照 doctor 的 collab.refs_exist）。"""
        manifest = MANIFEST.format(name="collab-ghost") + (
            "handoff:\n  to: ghost-sub-agent\n  input:\n    - 请求\n"
            "  output:\n    - 结论\n")
        pkg = make_pkg(self.root, "collab-ghost", manifest=manifest)
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "collab_contract")
        details = " ".join(h["detail"] for h in items["collab_contract"]["hits"])
        self.assertIn("ghost-sub-agent", details)
        self.assertIn("交接对象不存在", details)

    def test_external_handoff_target_is_not_judged(self):
        """外部服务名 / 宿主调度器名不判存在性——共置与否不是这个包能决定的。"""
        manifest = MANIFEST.format(name="collab-external") + (
            "handoff:\n  to: 公司调度平台\n  input:\n    - 请求\n"
            "  output:\n    - 结论\n")
        pkg = make_pkg(self.root, "collab-external", manifest=manifest)
        items, _ = self.items_of(pkg)
        self.assert_clean(items, "collab_contract")

    def test_handoff_verb_in_instruction_face_is_collab_capability(self):
        """指令面用「交接」这个动词点名子 agent → 算协作能力（动词表含交接）。"""
        pkg = make_pkg(self.root, "prose-verb",
                       prompt="# 提示词\n\n结论交接给子 agent 汇总。\n")
        items, _ = self.items_of(pkg)
        self.assert_hit(items, "collab_contract")
        self.assertIn("交接", items["collab_contract"]["hits"][0]["detail"])


class CapabilityGating(unittest.TestCase):
    """能力门控：没有状态、没有协作的包，不被这两项扣分，但两项仍要在表里。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_stateless_single_agent_is_not_penalized(self):
        pkg = make_pkg(self._tmp.name, "plain-agent")
        proc = run_eval(pkg)
        self.assertEqual(proc.returncode, 0,
                         f"评测应正常退出：\n{proc.stdout[:600]}\n{proc.stderr[:600]}")
        result = eval_result(proc)
        scores = result["scores"]
        items = {i["id"]: i for i in scores["static_checks"]}

        for check_id in ("state_contract", "collab_contract"):
            self.assertIn(check_id, items, "不适用 ≠ 不存在：逐项表里必须有这一项")
            self.assertEqual(items[check_id]["hit_count"], 0,
                             f"无状态单 agent 不该因缺配置扣分：{items[check_id]}")
        self.assertEqual(scores["static_score"], 1.0,
                         "干净包静态分必须满分")
        self.assertEqual(scores["static_issues"], [],
                         "干净包不该有任何静态 issue")

    def test_in_memory_context_constant_is_not_state(self):
        """`CONTEXT = {}` 这种内存变量不是状态能力（照 doctor 的口径）。"""
        agent_py = AGENT_PY.replace("raw = sys.stdin.read()",
                                    "CONTEXT = {}\nraw = sys.stdin.read()")
        pkg = make_pkg(self._tmp.name, "in-memory-context", agent_py=agent_py)
        proc = run_eval(pkg)
        result = eval_result(proc)
        items = {i["id"]: i for i in result["scores"]["static_checks"]}
        self.assertEqual(items["state_contract"]["hit_count"], 0,
                         f"内存里的 CONTEXT 不是状态能力：{items['state_contract']}")


class CrossMemberAgreement(unittest.TestCase):
    """跨成员口径一致：同一份缺陷包，doctor 与 eval 必须报出同一批问题。

    这条用例是给「以后只改一边」准备的：谁把单边口径改了，这里立刻红。
    """

    def test_doctor_and_eval_report_the_same_defects(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 个人主目录路径运行时拼接：源码里不留连续字面量，
            # 否则家族自检的路径扫描会命中这段夹具源码
            home = "/Use" "rs/lute/Desktop/project/data.xlsx"
            worker_py = ("DATA_ROOT = \"%s\"\n\n\n"
                         "def spin():\n    while True:\n        pass\n" % home)
            prompt = ("# 提示词\n\n模板见 templates/report.md。\n\n"
                      "署名用 {{BRAND_NAME}}。\n")
            pkg = make_pkg(tmp, "cross-member", prompt=prompt,
                           extra={"worker.py": worker_py})

            doctor_result = run_doctor(pkg)
            proc = run_eval(pkg)
            result = eval_result(proc)
            items = {i["id"]: i for i in result["scores"]["static_checks"]}

            # 一一对上：doctor 哪个 check 报 fail，eval 对应的 id 就得命中。
            # 状态/协作两项在这份夹具上没有能力，另行由 CapabilityGating 覆盖。
            shared = {eval_id: doctor_id for eval_id, doctor_id in DOCTOR_IDS.items()
                      if eval_id not in ("state_contract", "collab_contract")}
            self.assertEqual(len(shared), 4, "四类确定性缺陷都要在对照表里")
            for eval_id, doctor_id in sorted(shared.items()):
                item = doctor_check(doctor_result, doctor_id)
                self.assertEqual(item["status"], "fail",
                                 f"doctor 该报 {doctor_id}：{item}")
                self.assertGreater(items[eval_id]["hit_count"], 0,
                                   f"eval 该报 {eval_id}：{items[eval_id]}")

    def test_collab_capability_caliber_matches_doctor(self):
        """协作能力门控逐例对照：文档贴路径 / 代码真调用 / 交接对象存不存在。

        这四处是 2026-09-16 那次口径修订的全部边界——只改一边就会红。
        表里给的是两边各自的 check 状态与命中数，不是「doctor 一项对 eval 一项」
        （doctor 把「引用落地」单列成 collab.refs_exist，eval 并进 collab_contract）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            # 同级目录放一个真的兄弟包：代码里的调用路径能落地，
            # 这样「代码面路径 = 协作能力」与「文件找不到」两件事不会混在一起
            sibling = Path(tmp) / SIBLING_PKG
            sibling.mkdir(parents=True)
            (sibling / "agent.py").write_text("# 兄弟包\n", encoding="utf-8")

            doc_only = make_pkg(
                tmp, "caliber-doc",
                prompt="# 提示词\n\n回答业务问题。\n",
                extra={"README.md": ("# caliber-doc\n\n生成方式见 " + FOREIGN_ENTRY
                                     + "。\n"),
                       FOREIGN_ENTRY: "# 别的 agent\n"})
            code_call = make_pkg(
                tmp, "caliber-code",
                agent_py=AGENT_PY.replace(
                    "raw = sys.stdin.read()",
                    'CALLEE = "%s"\nraw = sys.stdin.read()' % SIBLING_ENTRY))
            ghost = make_pkg(
                tmp, "caliber-ghost",
                manifest=MANIFEST.format(name="caliber-ghost") + (
                    "handoff:\n  to: ghost-sub-agent\n  input:\n    - 请求\n"
                    "  output:\n    - 结论\n"))
            external = make_pkg(
                tmp, "caliber-external",
                manifest=MANIFEST.format(name="caliber-external") + (
                    "handoff:\n  to: 公司调度平台\n  input:\n    - 请求\n"
                    "  output:\n    - 结论\n"))

            def eval_hits(pkg):
                result = eval_result(run_eval(pkg))
                items = {i["id"]: i for i in result["scores"]["static_checks"]}
                return items["collab_contract"]["hit_count"]

            # 场景 / 夹具 / doctor handoff_declared / doctor refs_exist / eval 命中数
            cases = [
                ("文档只贴路径", doc_only, "skipped", "skipped", 0),
                ("代码真调兄弟包", code_call, "fail", "pass", 1),
                ("交接对象 ghost-sub-agent", ghost, "pass", "fail", 1),
                ("交接对象是外部服务名", external, "pass", "pass", 0),
            ]
            for label, pkg, want_declared, want_refs, want_hits in cases:
                doctor_result = run_doctor(pkg)
                for check_id, want in (("collab.handoff_declared", want_declared),
                                       ("collab.refs_exist", want_refs)):
                    item = doctor_check(doctor_result, check_id)
                    self.assertEqual(item["status"], want,
                                     f"{label}：doctor 的 {check_id} 应为 {want}，"
                                     f"实际 {item['status']}（{item['detail'][:80]}）")
                hits = eval_hits(pkg)
                self.assertEqual(hits, want_hits,
                                 f"{label}：eval 的 collab_contract 命中数应为 "
                                 f"{want_hits}，实际 {hits}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
