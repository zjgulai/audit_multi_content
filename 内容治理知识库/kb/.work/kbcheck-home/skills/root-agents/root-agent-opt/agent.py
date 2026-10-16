#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""root-agent-opt · 优化型 agent（创建-验证-优化 的收尾环节）

契约（见 ../refs/agent-contract.yaml）：
    interface: cli
    run:       python3 agent.py
    input:     stdin-json  —— {"agent_dir":"...", "score_path":"...", "copy_dir":"...",
                              "max_iterations":3}
    output:    stdout-json —— 优化报告摘要

三条铁律：
  1. 修复只改副本，源只读（所有写入只发生在 copy_dir 下）
  2. 回归通过才放行（留出集门禁 + 判定强度门禁）
  3. 封顶轮数，超限如实标「修复失败」

核心立场：**只做能由证据决定、且效果可复测的修复。**
不可自动修的类别明确交还人工，绝不为了「有产出」而瞎改。

五仓库取值与取舍：
  - anthropics/claude-code · openai/codex → 按错误证据做最小修复、修复后必须复跑
  - claude-agent-sdk-typescript          → 派生子 agent 做修复的隔离思想（副本 + 独立进程）
  - THUDM/AgentRL                        → 多轮迭代 + 每轮重测
  - SWE-bench/SWE-smith                  → 防过拟合：留出集门禁 + 拒绝自动拟合用例
  不取：RL 训练、合成数据生成、LLM 驱动补丁 —— 本机无模型端点与训练栈，不具备条件。
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT_AGENTS = HERE.parents[0]
EVAL_AGENT = ROOT_AGENTS / "root-agent-eval" / "agent.py"

KIND = "root-agent-opt"
STAGE = "optimize"
DEFAULT_MAX_ITERATIONS = 3
REEVAL_TIMEOUT = 600

NON_PASS_OUTCOMES = ("fail", "error", "inconclusive")

# 作答为空：契约层缺陷，可自动补兜底作答（不假装回答了问题）
EMPTY_ANSWER_MARKERS = (
    "answer 为空",
    "answer_empty",
    "未给出作答内容",
    "answer 为空或缺失",
)

# 环境级标记：出现即说明任何代码改动都无法修复（缺模型端点等）
ENVIRONMENT_MARKERS = (
    "llm_unavailable",
    "缺模型端点",
    "环境缺少模型",
)

ANSWER_FIELD_NAME = "answer"
FALLBACK_ANSWER = "（未生成作答内容）"

STUB_MARKER = "raise NotImplementedError"


# ---------------------------------------------------------------- 输出

# 安全守卫：拒绝把产物写进根目录 / 系统目录（安全题「危险操作」「路径权限越界」）
UNSAFE_TARGET_ROOTS = ("/etc", "/private/etc", "/usr", "/bin", "/sbin",
                       "/System", "/Library", "/dev", "/proc", "/boot",
                       "/root", "/cores")


def is_unsafe_target(target_dir):
    """目标目录落在根目录或系统目录时返回 True。

    历史缺陷：不校验写入目录，传 "/etc" 会直接 mkdir / 复制，抛未捕获异常。
    """
    try:
        resolved = Path(target_dir).expanduser().resolve()
    except (OSError, RuntimeError):
        return True
    text = str(resolved)
    if text == "/":
        return True
    return any(text == root or text.startswith(root + "/")
               for root in UNSAFE_TARGET_ROOTS)


def paths_overlap(source, copy_dir):
    """copy_dir 与源包重叠就返回 True。

    重叠有三种，三种都违反「修复只改副本」：
      · 相等        —— 副本就是源包本身；
      · copy_dir 是源的祖先 —— 删副本等于把源包一起删；
      · copy_dir 是源的后代 —— 把整包复制进自己内部，源目录被写。
    make_copy 是「先 rmtree 再 copytree」，所以前两种会**先删掉源包**，
    随后 copytree 找不到源、抛 FileNotFoundError。

    历史缺陷：唯一守卫是 is_unsafe_target，它只拦根目录与系统目录，
    copy_dir 传成源包本身时源包被删净（实测：目录空了、stdout 0 字节、
    stderr 是 copytree 的 FileNotFoundError）。
    """
    try:
        src = Path(source).resolve()
        dst = Path(copy_dir).resolve()
    except (OSError, RuntimeError):
        return True
    if src == dst:
        return True
    return src in dst.parents or dst in src.parents

# 本轮的自主步数：一步 = 一次「想一下 → 动一下」的完整回合。
STEPS = []


def step(action, summary):
    STEPS.append({"n": len(STEPS) + 1, "action": action, "summary": summary})


def emit(obj, exit_code):
    # 过程字段：本轮自主步数（契约 refs/agent-contract.yaml 的 `steps`）。
    # 确定性 agent 没有 tool-calling 循环，按**顶层动作**记真做了的事；
    # 没有工具就不写 tool_calls（契约明说：别拿空数组冒充「调用了 0 次」）。
    obj = dict(obj)
    obj.setdefault("steps", STEPS)
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    sys.stdout.flush()
    sys.exit(exit_code)


def fail(code, message, **extra):
    error = {"code": code, "message": message}
    error.update({k: v for k, v in extra.items() if v is not None})
    emit({"ok": False, "agent": KIND, "stage": STAGE, "error": error,
          "reply": message, "warnings": []}, 1)


# ---------------------------------------------------------------- 归类

def syntax_ok(source_text):
    """语法自检。补丁落盘前必须过这一关——实测曾因括号没补够而写坏副本。"""
    import ast
    try:
        ast.parse(source_text)
        return True, None
    except SyntaxError as exc:
        return False, f"{exc.msg}（第 {exc.lineno} 行）"


def classify(case, package_dir):
    """把一条非 pass 用例归类。返回 (kind, patch_rule_or_None, evidence)。

    kind ∈ content | environment | structural
    content     —— 作答内容不合期望。改提示词去拟合用例是过拟合，交还人工。
    environment —— 环境缺模型端点等。任何代码改动都无法修复。
    structural  —— 实现缺陷（如工具桩未实现）。可由确定性规则打补丁。
    """
    outcome = case.get("outcome")
    detail = case.get("detail") or ""
    strength = case.get("assessment_strength")

    if outcome == "inconclusive":
        return "environment", None, detail

    # 「作答为空」是契约层缺陷（违背 stdin-json「必有作答」协议），不是内容缺陷，
    # 也不是环境缺陷。它与环境问题的区别很关键：
    #   - 环境问题（无模型端点）→ 任何代码改动都无法修复
    #   - 作答为空            → 可补兜底作答，使协议达标（不假装回答了问题）
    if any(marker in detail for marker in EMPTY_ANSWER_MARKERS):
        return "structural", "ensure_answer_field", detail

    if any(marker in detail for marker in ENVIRONMENT_MARKERS):
        return "environment", None, detail

    if outcome in ("fail", "error"):
        # 结构性可修：输出显示存在抛 NotImplementedError 的工具桩
        blob = detail
        if STUB_MARKER in blob or "NotImplementedError" in blob:
            return "structural", "fill_tool_stub", blob
        # 其余失败都是作答内容层面的
        return "content", None, detail

    return "content", None, detail


def analyze(score_doc, package_dir):
    """归类可优化项。

    **优先消费评测报告的归因结果**（`evals/report.json` 的 `remediation_plan`），
    没有报告时才回退到自己的用例归类。

    为什么必须以报告为准：工具桩这类结构性缺陷在用例全 inconclusive（无模型端点）
    时不会出现在任何失败用例上——只靠 score.json 归类会让「可自动修」恒为 0，
    五环的修复环节被架空。实测踩到过。
    """
    from_report = None
    report_path = Path(package_dir) / "evals" / "report.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            plan = report.get("remediation_plan") or {}
            from_report = plan
        except (json.JSONDecodeError, OSError):
            from_report = None

    if from_report is not None:
        actionable, human_review, environment = [], [], []
        for entry in from_report.get("auto_fixable") or []:
            if not entry.get("patch_rule"):
                continue
            actionable.append({
                "id": (entry.get("case_ids") or [None])[0],
                "outcome": "static",
                "kind": "structural",
                "patch_rule": entry["patch_rule"],
                "evidence": (entry.get("message") or "")[:400],
                "source": "eval-report",
            })
        for entry in from_report.get("needs_human_review") or []:
            human_review.append({
                "id": (entry.get("case_ids") or [None])[0],
                "outcome": "fail", "kind": entry.get("kind") or "content",
                "patch_rule": None,
                "evidence": (entry.get("message") or "")[:400],
                "source": "eval-report",
            })
        for entry in from_report.get("environment_blocked") or []:
            environment.append({
                "id": (entry.get("case_ids") or [None])[0],
                "outcome": "inconclusive", "kind": "environment",
                "patch_rule": None,
                "evidence": (entry.get("message") or "")[:400],
                "source": "eval-report",
            })
        if actionable or human_review or environment:
            return actionable, human_review, environment

    cases = score_doc.get("cases") or []
    actionable, human_review, environment = [], [], []
    for case in cases:
        outcome = case.get("outcome")
        if outcome == "pass":
            continue
        if outcome == "na":
            continue
        kind, rule, evidence = classify(case, package_dir)
        entry = {
            "id": case.get("id"),
            "outcome": outcome,
            "kind": kind,
            "patch_rule": rule,
            "evidence": (evidence or "")[:400],
        }
        if kind == "structural" and rule:
            actionable.append(entry)
        elif kind == "environment":
            environment.append(entry)
        else:
            human_review.append(entry)
    return actionable, human_review, environment


# ---------------------------------------------------------------- 副本

def make_copy(source, copy_dir):
    """完整拷贝源包到副本。不复用源的 evals/ ——优化后必须重新评测。

    调用方（main）已在入口拦重叠路径；这里再守一道：本函数是「先删后拷」，
    一旦被别处以重叠路径调到，删掉的就是源包本身，没有第二次机会。
    """
    source, copy_dir = Path(source), Path(copy_dir)
    if paths_overlap(source, copy_dir):
        raise ValueError(
            "copy_dir 与源包重叠，拒绝删除/覆盖：source=%s copy_dir=%s"
            % (source, copy_dir))
    if copy_dir.exists():
        shutil.rmtree(copy_dir)
    shutil.copytree(
        source, copy_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"),
    )
    return copy_dir


def write_provenance(copy_dir, source, patches):
    doc = {
        "generated_by": KIND,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_agent_dir": str(Path(source).resolve()),
        "source_readonly": True,
        "patches": patches,
        "note": "本副本由 root-agent-opt 生成。源包全程只读，任何改动只发生在这里。",
    }
    path = Path(copy_dir) / "opt"
    path.mkdir(exist_ok=True)
    (path / "_fix_provenance.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path / "_fix_provenance.json"


# ---------------------------------------------------------------- 补丁规则

def patch_fill_tool_stub(copy_dir, entry):
    """规则 fill_tool_stub：把抛 NotImplementedError 的工具桩替换为最小实现。

    只在有证据（用例失败原因指向该桩）时执行，保持函数签名不变，
    并在文件头注明需人工补真实实现。绝不引入任何密钥。
    """
    tools_dir = Path(copy_dir) / "tools"
    if not tools_dir.is_dir():
        return None
    for tool_file in sorted(tools_dir.glob("*.py")):
        if tool_file.stem == "__init__":
            continue
        text = tool_file.read_text(encoding="utf-8")
        if STUB_MARKER not in text:
            continue
        backup = tool_file.with_suffix(".py.orig")
        if not backup.exists():
            backup.write_text(text, encoding="utf-8")
        filled = (
            '# -*- coding: utf-8 -*-\n'
            f'"""{tool_file.stem} · 工具实现（由 root-agent-opt 填充最小实现）\n\n'
            '注意：这里只是让 call() 不再抛 NotImplementedError 的最小实现，\n'
            '返回空结果。**真实实现需人工补齐**，否则 agent 的回答质量不会提升。\n'
            '凭证一律从 env 读，禁止硬编码。\n"""\n\n'
            f'TOOL_NAME = "{tool_file.stem}"\n\n\n'
            'def call(**kwargs):\n'
            '    return {}\n'
        )
        tool_file.write_text(filled, encoding="utf-8")
        return {
            "rule": "fill_tool_stub",
            "file": str(tool_file.relative_to(copy_dir)),
            "backup": str(backup.relative_to(copy_dir)),
            "evidence_case_id": entry["id"],
            "reason": entry["evidence"][:200],
        }
    return None


def patch_ensure_answer_field(copy_dir, entry):
    """规则 ensure_answer_field：让回答带非空 answer 字段。

    只做**协议达标**：当 answer 为 null 或缺失时补一个明确标注的兜底作答。
    它绝不假装回答了问题——兜底文案会写清「未生成作答内容」。
    真实作答质量取决于模型端点与提示词内容，那是人工与模型的事。

    预期副作用（报告必须说明）：这会让 eval 的 assessment_strength 由
    structural 变为 real，成绩不可与优化前直接横比。判定强度门禁只拦下降、
    不拦上升；真正防虚报的是报告说明与留出集门禁。
    """
    target = Path(copy_dir) / "agent.py"
    if not target.is_file():
        return None
    text = target.read_text(encoding="utf-8")

    if "ensure_answer_field" in text:
        return None                                   # 已打过，避免重复

    # 锚点：必须能找到 answer 字段出现的位置，否则不猜着改。
    # 两种常见写法都接受：JSON 键 "answer": ... 或 Python 变量 answer = ...
    answer_key_json = f'"{ANSWER_FIELD_NAME}"'  + ":"
    answer_var_assign = f'{ANSWER_FIELD_NAME}' + " = "
    if answer_key_json not in text and answer_var_assign not in text:
        return None

    backup = target.with_suffix(".py.orig")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")

    helper_lines = [
        'def _ensure_answer_field(payload):',
        '    """由 root-agent-opt 注入：保证 answer 字段存在且非空（协议达标）。',
        '',
        '    注意：这只是让输出满足契约，并不代表回答了问题。',
        '    """',
        '    if isinstance(payload, dict):',
        '        value = payload.get("answer")',
        '        if not isinstance(value, str) or not value.strip():',
        f'            payload["answer"] = "{FALLBACK_ANSWER}"',
        '            warnings = payload.get("warnings")',
        '            if isinstance(warnings, list):',
        '                warnings.append("answer_fallback")',
        '    return payload',
        '',
        '',
    ]
    text = "\n".join(helper_lines) + text

    # 把 print(json.dumps(...)) 改造成：
    #     print(json.dumps(_ensure_answer_field(json.loads(json.dumps(...)))))
    # 即「算完原结果 → 先序列化再用 json.loads 还原成 dict → 补 answer 字段 → 再序列化」。
    # 为什么绕这一圈：直接内插包装层会打乱原有的函数实参与关键字参数边界
    # （实测两次踩到：一次括号数不对，一次吃掉 json.dumps 的调用括号）。
    # 用 json.loads(json.dumps(...)) 做边界隔离，不触碰内层结构的任何一个字符。
    chars = list(text)
    opens = [i for i in range(len(chars))
             if text.startswith("print(json.dumps(", i)]
    if not opens:
        return None

    for pos in reversed(opens):              # 从后往前改，前面的下标不失效
        depth = 0
        close_at = None
        scan = pos + len("print(")
        while scan < len(chars):
            if chars[scan] == "(":
                depth += 1
            elif chars[scan] == ")":
                depth -= 1
                if depth == 0:
                    close_at = scan
                    break
            scan += 1
        if close_at is None:
            return None                      # 括号不配对，不猜着改

        # 定位 json.dumps( 的调用括号
        inner_open = chars.index("(", pos + len("print(json.dumps"))
        inner_close = None
        depth = 0
        for scan in range(inner_open, close_at + 1):
            if chars[scan] == "(":
                depth += 1
            elif chars[scan] == ")":
                depth -= 1
                if depth == 0:
                    inner_close = scan
                    break
        if inner_close is None:
            return None

        segment = "".join(chars[inner_open + 1:inner_close])
        replacement = (f"_ensure_answer_field(json.loads(json.dumps({segment})))")
        chars[inner_open + 1:inner_close] = list(replacement)

    lines = "".join(chars)

    patched_text = lines
    ok, problem = syntax_ok(patched_text)
    if not ok:
        # 实测踩到过：括号没补够导致副本无法解析。绝不落盘坏补丁。
        return None
    target.write_text(patched_text, encoding="utf-8")
    return {
        "rule": "ensure_answer_field",
        "file": str(target.relative_to(copy_dir)),
        "backup": str(backup.relative_to(copy_dir)),
        "evidence_case_id": entry["id"],
        "reason": entry["evidence"][:200],
        "expected_side_effect": (
            "让 assessment_strength 由 structural 变为 real；"
            "成绩不可与优化前直接横比"
        ),
    }


PATCH_RULES = {
    "fill_tool_stub": patch_fill_tool_stub,
    "ensure_answer_field": patch_ensure_answer_field,
}


def apply_patches(copy_dir, actionable):
    applied = []
    for entry in actionable:
        rule = entry.get("patch_rule")
        handler = PATCH_RULES.get(rule)
        if handler is None:
            continue
        record = handler(copy_dir, entry)
        if record:
            applied.append(record)
    return applied


# ---------------------------------------------------------------- 复测

def reevaluate(copy_dir, threshold=None, generate=None):
    """通过 root-agent-eval 的子进程重新评测副本。不重新实现评测逻辑。

    generate 必须透传：调用方用 generate=False 限定用例集时，复测也必须一致，
    否则改进对比会拿两套不同用例集比较（实测踩到：复测多出 13 条生成用例）。
    """
    request = {"agent_dir": str(Path(copy_dir).resolve()), "stage": "all"}
    if threshold is not None:
        request["threshold"] = threshold
    if generate is not None:
        request["generate"] = generate
    proc = subprocess.run(
        [sys.executable, str(EVAL_AGENT)],
        input=json.dumps(request, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=REEVAL_TIMEOUT,
    )
    if proc.returncode not in (0, 1):     # eval 用 1 表示 fail/degraded_fail
        return None, f"复测失败：eval 退出码 {proc.returncode}；{proc.stderr[:300]}"
    try:
        summary = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return None, f"复测输出非 JSON：{exc}"

    score_path = Path(copy_dir) / "evals" / "score.json"
    if not score_path.is_file():
        return None, f"复测未产出 score.json：{score_path}"
    try:
        score = json.loads(score_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"复测 score.json 非法：{exc}"
    return {"summary": summary, "score": score}, None


def gate_check(holdout, after_map, strength_before, strength_after):
    """两道放行门禁（纯逻辑，便于直接验证）。

    返回 (verdict, detail)：verdict ∈ ok | regressed

    门禁一（留出集）：优化前 pass 的用例，优化后必须仍 pass。
        防的是「修好 A 弄坏 B」。
    门禁二（判定强度）：real 判定的用例数不得下降。
        防的是靠消除 inconclusive、只过结构期望来虚报提升——
        这个漏洞在第三阶段真实出现过（全 null 回答曾拿满分 1.0）。
    """
    holdout_broken = sorted(cid for cid in holdout
                            if after_map.get(cid) != "pass")
    if holdout_broken:
        return "regressed", {
            "holdout_broken": holdout_broken,
            "gate": "holdout 门禁被违反：优化前通过的用例在优化后不再通过",
        }
    if strength_after < strength_before:
        return "regressed", {
            "holdout_broken": [],
            "strength_dropped": [strength_before, strength_after],
            "gate": "判定强度门禁被违反：real 判定数下降，属虚报提升",
        }
    return "ok", {"holdout_broken": []}


def outcome_map(score_doc):
    return {c.get("id"): c.get("outcome") for c in (score_doc.get("cases") or [])}


def real_strength_count(score_doc):
    return sum(1 for c in (score_doc.get("cases") or [])
               if c.get("assessment_strength") == "real")


# ---------------------------------------------------------------- 主流程

def main():
    raw = sys.stdin.read()
    if not raw.strip():
        fail("invalid_input", "stdin 为空，需要 {\"agent_dir\": \"...\"}")
    step("read_request", "读 stdin 请求")
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail("invalid_input", f"输入不是合法 JSON：{exc}")
    if not isinstance(request, dict):
        fail("invalid_input", "输入必须是 JSON 对象")

    agent_dir_raw = request.get("agent_dir")
    if not agent_dir_raw or not isinstance(agent_dir_raw, str):
        fail("missing_field", "缺少必填字段 agent_dir", field="agent_dir")

    agent_dir = Path(agent_dir_raw).expanduser()
    if not agent_dir.is_absolute():
        agent_dir = (Path.cwd() / agent_dir).resolve()
    if not agent_dir.is_dir():
        fail("agent_dir_missing", f"agent_dir 不存在或不是目录：{agent_dir}")

    score_path = request.get("score_path")
    score_path = (Path(score_path).expanduser() if score_path
                  else agent_dir / "evals" / "score.json")
    if not score_path.is_absolute():
        score_path = (Path.cwd() / score_path).resolve()
    if not score_path.is_file():
        fail("score_missing",
             f"缺少评分文件，请先跑 root-agent-eval：{score_path}",
             field=str(score_path))

    try:
        score_doc = json.loads(score_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail("score_invalid", f"score.json 不是合法 JSON：{exc}")

    try:
        max_iterations = int(request.get("max_iterations", DEFAULT_MAX_ITERATIONS))
    except (TypeError, ValueError):
        fail("invalid_input", "max_iterations 必须是整数")
    if max_iterations < 0:
        fail("invalid_input", "max_iterations 不能为负")

    copy_dir = request.get("copy_dir")
    copy_dir = (Path(copy_dir).expanduser() if copy_dir
                else agent_dir.parent / f"{agent_dir.name}-fix")
    if not copy_dir.is_absolute():
        copy_dir = (Path.cwd() / copy_dir).resolve()
    if is_unsafe_target(copy_dir):
        fail("unsafe_copy_dir",
             f"copy_dir 指向根目录或系统目录，拒绝写入：{copy_dir}",
             field=str(copy_dir))
    if paths_overlap(agent_dir, copy_dir):
        # 路径别名必须先拦：make_copy 先删后拷，重叠时删的就是被测源包本身。
        fail("copy_dir_overlaps_source",
             f"copy_dir 与被测包重叠，拒绝执行（修复只改副本）："
             f"被测包 {agent_dir}，副本 {copy_dir}",
             field=str(copy_dir))

    actionable, human_review, environment = analyze(score_doc, agent_dir)
    step("read_score", "读 %s 并对每条缺陷做归因分派"
         % score_path.name)
    step("triage", "可自动修 %d 条 / 需人工审阅 %d 条 / 环境阻塞 %d 条"
         % (len(actionable), len(human_review), len(environment)))
    before_score = score_doc

    base = {
        "ok": True,
        "agent": KIND,
        "kind": KIND,
        "stage": STAGE,
        "target": score_doc.get("agent") or agent_dir.name,
        "source_agent_dir": str(agent_dir),
        "source_readonly": True,
        "copy_dir": str(copy_dir),
        "score_path": str(score_path),
        "actionable": actionable,
        "requires_human_review": human_review,
        "environment_blocked": environment,
    }

    # ── 无可优化项：合法结论，绝不制造假修复 ──
    if not actionable:
        reason = "评分中没有任何可自动修复的结构性缺陷"
        if environment and not human_review:
            reason = ("全部非通过用例都是环境级问题（本机无模型端点，作答为空），"
                      "任何代码改动都无法修复")
        elif environment:
            reason = ("无结构性缺陷；剩余问题中环境级不可自动修，"
                      "内容级需人工审阅提示词")
        base.update({
            "verdict": "no_actionable",
            "rounds": 0,
            "reason": reason,
            "patches_applied_total": 0,
            "patches": [],
            "before": {
                "verdict": before_score.get("verdict"),
                "counts": before_score.get("counts"),
                "scores": before_score.get("scores"),
            },
            "after": None,
            "honest_limitations": honest_limitations(),
            "warnings": ["无可自动修项，故未创建副本：不制造无意义的产物"],
        })
        base["copy_dir"] = None          # 不建副本，也不写报告到不存在的目录
        base["reply"] = ("不用修：%s 的评分里没有可自动修复的结构性缺陷"
                         "（需人工审阅 %d 项、环境阻塞 %d 项）。"
                         % (agent_dir.name, len(human_review), len(environment)))
        emit(base, 0)

    # ── 有可优化项：建副本 → 迭代补丁 → 复测 ──
    # 副本只在确实要动手时才建（实测踩到：no_actionable 也建了副本，污染仓库）
    make_copy(agent_dir, copy_dir)

    holdout = {cid for cid, outcome in outcome_map(before_score).items()
               if outcome == "pass"}
    baseline_real = real_strength_count(before_score)

    rounds = []
    final_verdict = "not_improved_capped"
    all_patches = []
    last_round = None

    for index in range(1, max_iterations + 1):
        patches = apply_patches(copy_dir, actionable)
        all_patches.extend(patches)
        write_provenance(copy_dir, agent_dir, all_patches)

        if not patches:
            final_verdict = "no_improvement"
            rounds.append({
                "round": index,
                "patches_applied": [],
                "note": "本轮未找到可应用的补丁规则",
            })
            break

        evaluated, error = reevaluate(copy_dir, score_doc.get("threshold"),
                                      generate=request.get("generate"))
        if error:
            rounds.append({"round": index, "patches_applied": patches,
                           "error": error})
            final_verdict = "no_improvement"
            break

        after_score = evaluated["score"]
        after_map = outcome_map(after_score)

        strength_after = real_strength_count(after_score)
        improved = sorted(cid for cid, outcome in after_map.items()
                          if outcome == "pass"
                          and outcome_map(before_score).get(cid) != "pass")

        gate_verdict, gate_detail = gate_check(
            holdout, after_map, baseline_real, strength_after)

        record = {
            "round": index,
            "patches_applied": patches,
            "after_verdict": after_score.get("verdict"),
            "after_counts": after_score.get("counts"),
            "after_scores": after_score.get("scores"),
            "holdout_broken": gate_detail.get("holdout_broken", []),
            "strength_before": baseline_real,
            "strength_after": strength_after,
            "improved_cases": improved,
        }

        if gate_verdict == "regressed":
            record["gate"] = gate_detail["gate"]
            rounds.append(record)
            last_round = record
            final_verdict = "regressed"
            break

        if improved:
            record["gate"] = "两道门禁均通过"
            rounds.append(record)
            last_round = record
            final_verdict = "improved"
            break

        record["gate"] = "无用例转好"
        rounds.append(record)
        last_round = record
        final_verdict = "not_improved_capped" if index >= max_iterations else "no_improvement"

    baseline_map = outcome_map(before_score)
    after_status = last_round.get("after_counts") if last_round else None

    base.update({
        "verdict": final_verdict,
        "rounds": len(rounds),
        "patches_applied_total": len(all_patches),
        "patches": all_patches,
        "rounds_detail": rounds,
        "before": {
            "verdict": before_score.get("verdict"),
            "counts": before_score.get("counts"),
            "scores": before_score.get("scores"),
        },
        "after": ({"verdict": last_round.get("after_verdict"),
                   "counts": after_status,
                   "scores": last_round.get("after_scores")}
                  if last_round else None),
        "holdout_baseline": sorted(holdout),
        "improved_cases": (last_round or {}).get("improved_cases", []),
        "honest_limitations": honest_limitations(),
        "warnings": [],
    })
    # 源包只读自查（报告里明确写出）
    base["reply"] = ("修复完成：结论 %s。可自动修 %d 项、需人工审阅 %d 项、"
                     "环境阻塞 %d 项；修复副本在 %s。"
                     % (final_verdict, len(actionable), len(human_review),
                        len(environment), copy_dir))
    base["warnings"].append("源包全程只读：所有改动只落在副本目录")
    if final_verdict == "no_improvement":
        base["warnings"].append(
            "复测后没有用例转好：可能是补丁只是消除了结构缺陷，"
            "而作答质量取决于模型端点与提示词内容，需人工审阅 requires_human_review"
        )
    write_report(copy_dir, base)
    emit(base, 0 if final_verdict == "improved" else 1)


def honest_limitations():
    return [
        "未做 RL 训练（AgentRL 语义）：需要模型端点、训练栈与大量算力，本机不具备。",
        "未做合成数据生成（SWE-smith 语义）：需要模型生成多样题目；"
        "且若用同一模型生成又用其判分，会形成自证循环。已改以「留出集门禁」"
        "落实其防过拟合取向。",
        "未做 LLM 驱动的补丁生成（Claude Code / Codex 的 fix 语义）：本机无模型端点。"
        "未来接入模型时，补丁仍须过两道门禁与 doctor 体检。",
        "不自动改提示词语义：改提示词让某个 must_contain 通过是针对测试集过拟合，"
        "不是提升能力。内容级问题交还人工。",
    ]


def write_report(copy_dir, doc):
    path = Path(copy_dir) / "opt"
    path.mkdir(parents=True, exist_ok=True)
    (path / "optimization.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
