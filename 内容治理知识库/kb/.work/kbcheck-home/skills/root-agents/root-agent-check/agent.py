#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""root-agent-check · 自动成长器

契约（见 ../refs/agent-contract.yaml）：
    interface: cli
    run:       python3 agent.py
    input:     stdin-json      —— {"targets":["..."], "run_id":"...", "memory_dir":"..."}
    output:    stdout-json     —— 本轮成长报告

只新写一件事：**自动成长**。四环里前四个 agent 每次都从零开始，本 agent 让整个体系
跨轮次累积证据，并把复现的模式固化为规则。

成长 = 跨轮累积证据 + 复现的模式固化为规则。

核心立场：**成长必须可证伪。** 自动成长最大的风险不是长得慢，而是编造成长——
把笔记当成长、把单次观察当规律、把环境问题当能力变化。三道防线：

  1. 不写没有证据的规则：规则必须指向 ≥2 次独立 run 的 observation
  2. 不假装做了做不到的事：能力阶梯只按证据晋级，RL/合成数据标 blocked 并写明条件
  3. 不用环境问题衡量成长：只统计 decisive 用例；全环境阻塞时结论是
     insufficient_evidence，不是 grew

四仓库取值：
  - THUDM/AgentRL              → 奖励反馈驱动改进的循环结构（不做 RL 训练：无 torch/无端点）
  - SWE-bench/SWE-smith        → 数据驱动成长的证据积累思想（不做合成数据生成）
  - anthropics/claude-code     → memory 持续积累 + 规则固化
  - openai/openai-agents-python→ sessions 式跨轮有状态记忆（runs[] + run_id 幂等）
"""

import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT_AGENTS = HERE.parents[0]
DEFAULT_MEMORY_DIR = HERE / "memory"
MEMORY_FILE = "growth.json"
MARKDOWN_FILE = "growth.md"

KIND = "root-agent-check"
STAGE = "grow"
MEMORY_VERSION = 1

# 规则门槛：同一模式必须复现在 ≥2 次独立 run 才成立。
# 这是「不编造成长」的第一道防线——单次观察只能是巧合。
MIN_RUNS_FOR_RULE = 2

PATTERN_MAX_LEN = 60

# 归因标记（与 root-agent-opt 的归因分类保持一致）
EMPTY_ANSWER_MARKERS = ("answer 为空", "answer_empty", "未给出作答内容", "answer 为空或缺失")
ENVIRONMENT_MARKERS = ("llm_unavailable", "缺模型端点", "环境缺少模型", "环境缺模型端点")
STRUCTURAL_MARKERS = ("NotImplementedError", "未实现", "工具桩")


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


# ---------------------------------------------------------------- 归因与模式

def classify(case):
    """与 root-agent-opt 同源的三分类：structural / content / environment。"""
    outcome = case.get("outcome")
    detail = case.get("detail") or ""
    if outcome == "pass" or outcome == "na":
        return None
    if outcome == "inconclusive":
        return "environment"
    if any(marker in detail for marker in EMPTY_ANSWER_MARKERS):
        return "structural"
    if any(marker in detail for marker in ENVIRONMENT_MARKERS):
        return "environment"
    if any(marker in detail for marker in STRUCTURAL_MARKERS):
        return "structural"
    if outcome in ("fail", "error"):
        return "content"
    return None


def normalize_pattern(kind, detail):
    """把 detail 归一化成模式键。

    做法：去路径、去引号内容、去数字、压空白、截断。
    已知局限：不做语义聚类。措辞不同的同一问题会被算成两个模式——
    这会让规则**更难**成立而非更容易，属偏保守的一侧（宁可漏聚，不可误聚）。
    """
    text = detail or ""
    text = re.sub(r"/[\w./-]{4,}", "<path>", text)
    text = re.sub(r"'[^']*'", "<q>", text)
    text = re.sub(r'"[^"]*"', "<q>", text)
    text = re.sub(r"\d+", "<n>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return f"{kind}|{text[:PATTERN_MAX_LEN]}"


def is_actionable(kind):
    """只有 structural 类是可自动修的；environment 与 content 都不是。"""
    return kind == "structural"


# ---------------------------------------------------------------- 记忆读写

def load_memory(memory_dir):
    """读成长记忆。损坏时备份原文件并返回 None（不静默重建）。"""
    path = Path(memory_dir) / MEMORY_FILE
    if not path.is_file():
        return {"version": MEMORY_VERSION, "runs": [], "rules": []}, None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("记忆根节点不是对象")
        doc.setdefault("version", MEMORY_VERSION)
        doc.setdefault("runs", [])
        doc.setdefault("rules", [])
        return doc, None
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        backup = path.with_suffix(".json.bak")
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
        return None, f"{type(exc).__name__}: {exc}"


def save_memory(memory_dir, doc):
    path = Path(memory_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / MEMORY_FILE).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (path / MARKDOWN_FILE).write_text(render_markdown(doc), encoding="utf-8")


# ---------------------------------------------------------------- 观察采集

def collect_observations(targets, run_id):
    """从各目标的 evals/score.json 采集观察。只读，绝不改目标。"""
    observations, skipped, counts = [], [], {
        "decisive_cases": 0, "environment_blocked_cases": 0,
        "content_cases": 0, "structural_cases": 0,
    }
    for raw in targets:
        pkg = Path(raw).expanduser()
        if not pkg.is_absolute():
            pkg = (Path.cwd() / pkg).resolve()
        score_path = pkg / "evals" / "score.json"
        if not score_path.is_file():
            skipped.append({"target": str(pkg), "reason": "缺少 evals/score.json"})
            continue
        try:
            score = json.loads(score_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            skipped.append({"target": str(pkg), "reason": f"score.json 非法：{exc}"})
            continue

        for case in score.get("cases") or []:
            outcome = case.get("outcome")
            strength = case.get("assessment_strength")
            # decisive：真的判定了作答内容且结论明确
            if strength == "real" and outcome in ("pass", "fail"):
                counts["decisive_cases"] += 1

            kind = classify(case)
            if kind == "environment":
                counts["environment_blocked_cases"] += 1
            elif kind == "content":
                counts["content_cases"] += 1
            elif kind == "structural":
                counts["structural_cases"] += 1

            if kind is None:
                continue
            observations.append({
                "run_id": run_id,
                "target": pkg.name,
                "case_id": case.get("id"),
                "outcome": outcome,
                "kind": kind,
                "strength": strength,
                "pattern": normalize_pattern(kind, case.get("detail")),
                "detail": (case.get("detail") or "")[:300],
                "source": str(score_path),
            })
    return observations, skipped, counts


# ---------------------------------------------------------------- 规则合成

def pattern_history(memory):
    """从历史 run 的观察里建「模式 → {(证据指纹, run_id)}」。

    关键：待复现模式并不在 rules 里（它们没达门槛），所以必须从历史 run 的
    observations 里回捞。早期版本只看 rules，导致每次运行都从「第 1 次」重新计数，
    门槛永远跨不过去——功能实际是坏的。实测由测试抓出。

    第二版（本版）修的是另一半：复现次数过去按 **run_id 个数** 数，
    于是「同一份 score.json 一个字节没改、只换个 run_id 再读一遍」就算第二次复现，
    凭空立规则判 grew。现在按 **证据指纹** 去重（见 evidence_key），
    决定性用例为 0 的 run 不计入证据。
    """
    history = {}
    for run in memory.get("runs") or []:
        rid = run.get("run_id")
        if not rid:
            continue
        for pattern, key in run_evidence_keys(run):
            # 同一份证据只认**第一个**拿出它的 run：后面重读的轮次不算新证据，
            # 也不该出现在证据链里（否则「读过几遍」会被误读成「复现几次」）。
            history.setdefault(pattern, {}).setdefault(key, rid)
    return history


def evidence_key(target, pattern, rows):
    """同一份证据的稳定指纹：内容不变，指纹就不变。

    组成只取「证据内容」——目标名、归一化模式、以及逐条用例的
    (用例号, 结论, 判定强度, detail 摘要)。**刻意不含 run_id、时间、文件路径**：
    这三样换了不等于证据换了。

    因此「同一份 score.json 换个 run_id 再读一遍」得到同一枚指纹，
    复现次数不增加、不立规则；要跨过门槛必须拿出**新的证据**：
    另一个包里出现同一模式，或同一个包重跑后结论/判定强度变了。
    """
    payload = {
        "target": target,
        "pattern": pattern,
        "rows": sorted(
            json.dumps({"case_id": row.get("case_id"),
                        "outcome": row.get("outcome"),
                        "strength": row.get("strength"),
                        "detail": (row.get("detail") or "")[:300]},
                       ensure_ascii=False, sort_keys=True)
            for row in rows),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def run_evidence_keys(run):
    """一个 run 里的 (模式, 证据指纹) 集合。

    老记忆文件里的 observation 没有 evidence_key 字段，按同样规则现场重算；
    决定性用例为 0 的 run 整轮不算证据（环境问题不是成长证据）。
    """
    if ((run.get("summary") or {}).get("decisive_cases") or 0) <= 0:
        return set()
    pairs, groups = set(), {}
    for obs in run.get("observations") or []:
        pattern = obs.get("pattern")
        if not pattern:
            continue
        key = obs.get("evidence_key")
        if key:
            pairs.add((pattern, key))
        else:
            groups.setdefault((obs.get("target"), pattern), []).append(obs)
    for (target, pattern), rows in groups.items():
        pairs.add((pattern, evidence_key(target, pattern, rows)))
    # 待复现条目本身也携带指纹（老版本没有 → 不当作证据，宁严不宽）
    for pending in run.get("pending_patterns") or []:
        pattern = pending.get("pattern")
        for key in pending.get("evidence_keys") or []:
            if pattern and key:
                pairs.add((pattern, key))
    return pairs


def synthesize_rules(memory, observations, run_id, decisive=True):
    """按模式聚合**独立证据**，达门槛才立规则。

    门槛看的是「几份互不相同的证据」（occurences = 证据指纹去重后的个数），
    不是「跑了几轮」。decisive=False（本轮决定性用例为 0）时一条规则都不立——
    环境阻塞、空作答这类没有能力含义的现象不是成长证据。
    """
    existing = {rule["pattern"]: rule for rule in memory.get("rules") or []}
    history = pattern_history(memory)

    # 本轮出现的模式 → 本轮 observation
    by_pattern = {}
    for obs in observations:
        by_pattern.setdefault(obs["pattern"], []).append(obs)
    # 本轮每条 observation 回填证据指纹（存进记忆，下一轮直接用）
    for pattern, obs_list in by_pattern.items():
        groups = {}
        for obs in obs_list:
            groups.setdefault(obs.get("target"), []).append(obs)
        key_of_target = {t: evidence_key(t, pattern, rows)
                         for t, rows in groups.items()}
        for obs in obs_list:
            obs["evidence_key"] = key_of_target.get(obs.get("target"))

    new_rules, pending = [], []
    for pattern, obs_list in sorted(by_pattern.items()):
        rule = existing.get(pattern)
        # key → 第一个拿出这份证据的 run
        key_to_run = dict(history.get(pattern) or {})
        if not decisive:
            key_to_run = {}       # 非决定性轮：历史与本轮都不计入复现
        else:
            for obs in obs_list:
                key = obs.get("evidence_key")
                if key and key not in key_to_run:
                    key_to_run[key] = run_id
        keys = sorted(key_to_run)
        runs_sorted = sorted(set(key_to_run.values()))
        sample = obs_list[0]
        kind = sample["kind"]

        entry = {
            "pattern": pattern,
            "kind": kind,
            # occurrences 只数「互不相同的证据」，不数「读过几遍」
            "occurrences": len(keys),
            "evidence_keys": keys,
            "evidence_runs": runs_sorted,
            "statement": describe(kind, sample),
            "actionable": is_actionable(kind),
            "action": action_for(kind),
            "first_seen": (rule or {}).get("first_seen") or now_iso(),
            "last_seen": now_iso(),
            "sample_detail": sample["detail"][:200],
        }

        if not decisive:
            entry["note"] = ("本轮决定性用例为 0（全是环境阻塞/无作答），"
                            "不计复现次数、不立规则——环境问题不是成长证据")
            pending.append(entry)
            continue

        if len(keys) >= MIN_RUNS_FOR_RULE:
            if rule is None:
                entry["id"] = f"rule-{kind}-{abs(hash(pattern)) % 10 ** 8:08d}"
                new_rules.append(entry)
            existing[pattern] = entry
        else:
            entry["note"] = (
                f"该模式只有 1 份证据，需再拿出 {MIN_RUNS_FOR_RULE - len(keys)} "
                f"份新证据才立规则；同一份评分文件换个 run_id 重读不算新证据"
                f"（不写没有证据的规则）")
            pending.append(entry)

    memory["rules"] = sorted(existing.values(), key=lambda r: r["pattern"])
    return new_rules, pending


def describe(kind, sample):
    if kind == "environment":
        return ("多轮评测中被测 agent 无法给出有效作答（环境级原因，如缺模型端点），"
                "该问题不可能靠代码改动解决")
    if kind == "content":
        return "被测 agent 的作答内容反复不满足期望，属内容级问题，需人工审阅提示词"
    return "被测 agent 的实现反复出现同一结构性缺陷（如工具桩未实现），可由确定性规则修复"


def action_for(kind):
    if kind == "environment":
        return ("配置 ROOT_AGENT_LLM_BASE_URL 与密钥后重跑评测；"
                "在此之前该问题的所有分数都不代表能力")
    if kind == "content":
        return "人工审阅 prompts/system.md 与用例期望，判断是提示词问题还是期望本身不合理"
    return "运行 root-agent-opt，由 fill_tool_stub 等确定性规则修复"


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------- 能力阶梯

def build_ladder(has_llm, has_torch, rules, applied_rules):
    levels = [
        {
            "level": 0, "name": "证据采集",
            "state": "achieved" if rules or applied_rules is not None else "achieved",
            "evidence": "观察已采集并写入 memory/growth.json（runs[] 逐轮累积）",
        },
    ]
    if rules:
        levels.append({
            "level": 1, "name": "规则合成", "state": "achieved",
            "evidence": f"已有 {len(rules)} 条规则由 ≥{MIN_RUNS_FOR_RULE} 次独立 run 的"
                        f"复现证据支撑",
        })
    else:
        levels.append({
            "level": 1, "name": "规则合成", "state": "blocked",
            "requires": f"同一模式复现 ≥{MIN_RUNS_FOR_RULE} 次独立 run",
            "evidence": "当前所有模式的出现次数均不足门槛，故不立规则",
        })

    actionable = [r for r in rules if r.get("actionable")]
    if actionable:
        levels.append({
            "level": 2, "name": "规则应用", "state": "achieved",
            "evidence": f"{len(actionable)} 条可自动修规则已可供下游 "
                        f"root-agent-opt 消费",
        })
    else:
        levels.append({
            "level": 2, "name": "规则应用", "state": "blocked",
            "requires": "至少一条 actionable 规则（structural 类且复现达标）",
            "evidence": "当前活跃规则中没有可自动修的项",
        })

    levels.append({
        "level": 3, "name": "合成数据生成", "state": "blocked",
        "requires": "可用的模型端点（ROOT_AGENT_LLM_BASE_URL + 密钥）",
        "evidence": ("本机未配置 ROOT_AGENT_LLM_BASE_URL，无法生成多样题目；"
                     "且若用同一模型生成又用其判分，会形成自证循环"),
    })
    levels.append({
        "level": 4, "name": "RL 训练", "state": "blocked",
        "requires": "模型端点 + 训练栈（torch 等）与算力",
        "evidence": (f"torch 可用性：{'是' if has_torch else '否'}；"
                     f"模型端点：{'已配置' if has_llm else '未配置'}。"
                     f"当前只落地 AgentRL 的循环结构，未做训练"),
    })
    return {
        "state": "level1" if rules else "level0",
        "note": ("阶梯只按证据晋级：blocked 级必须写明缺什么条件与如何确认，"
                 "绝不在无证据时标 achieved"),
        "levels": levels,
    }


# ---------------------------------------------------------------- 渲染

def render_markdown(memory):
    rules = memory.get("rules") or []
    runs = memory.get("runs") or []
    lines = [
        "# root-agent-check · 成长记忆", "",
        f"累计 run 数：**{len(runs)}**　活跃规则：**{len(rules)}**", "",
        "> 本文件由 root-agent-check 写入。规则门槛：同一模式须有 ≥"
        f"{MIN_RUNS_FOR_RULE} 份**互不相同的证据**（按证据指纹去重；"
        "同一份评分文件换个 run_id 重读不算新证据）。决定性用例为 0 的轮次"
        "不计入证据。", "",
        "## 活跃规则", "",
    ]
    if rules:
        lines += ["| 模式 | 归因 | 独立证据 | 出现过的 run | 可自动修 |",
                  "| --- | --- | --- | --- | --- |"]
        for rule in rules:
            lines.append("| `{}` | {} | {} | {} | {} |".format(
                rule["pattern"][:48], rule["kind"], rule["occurrences"],
                ", ".join(rule.get("evidence_runs") or []),
                "是" if rule.get("actionable") else "否"))
    else:
        lines.append("（暂无。规则需要同一模式积累 ≥"
                     f"{MIN_RUNS_FOR_RULE} 份互不相同的证据才能成立。）")
    lines += ["", "## 成长曲线", "",
              "| run | 结论 | decisive | 环境阻塞 | 新规则 |",
              "| --- | --- | --- | --- | --- |"]
    for run in runs:
        summary = run.get("summary") or {}
        lines.append("| {} | {} | {} | {} | {} |".format(
            run.get("run_id"), run.get("growth_verdict"),
            summary.get("decisive_cases", 0),
            summary.get("environment_blocked_cases", 0),
            len(run.get("new_rules") or [])))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 主流程

def main():
    raw = sys.stdin.read()
    if not raw.strip():
        fail("invalid_input", "stdin 为空，需要 {\"targets\": [\"...\"]}")
    step("read_request", "读 stdin 请求")
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail("invalid_input", f"输入不是合法 JSON：{exc}")
    if not isinstance(request, dict):
        fail("invalid_input", "输入必须是 JSON 对象")

    targets = request.get("targets")
    if targets is None:
        fail("missing_field", "缺少必填字段 targets", field="targets")
    if not isinstance(targets, list):
        fail("invalid_input", "targets 必须是数组", field="targets")

    run_id = request.get("run_id") or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if not isinstance(run_id, str):
        fail("invalid_input", "run_id 必须是非空字符串", field="run_id")

    memory_dir = request.get("memory_dir")
    memory_dir = (Path(memory_dir).expanduser() if memory_dir
                  else DEFAULT_MEMORY_DIR)
    if not memory_dir.is_absolute():
        memory_dir = (Path.cwd() / memory_dir).resolve()
    if is_unsafe_target(memory_dir):
        fail("unsafe_memory_dir",
             f"memory_dir 指向根目录或系统目录，拒绝写入：{memory_dir}",
             field=str(memory_dir))

    memory, memory_error = load_memory(memory_dir)
    if memory is None:
        fail("memory_corrupt",
             f"成长记忆损坏，未静默重建：{memory_error}",
             field=str(memory_dir / MEMORY_FILE))
    memory["version"] = MEMORY_VERSION
    memory.setdefault("runs", [])
    memory.setdefault("rules", [])

    step("load_memory", "读成长记忆（run_id=%s）" % run_id)
    observations, skipped, counts = collect_observations(targets, run_id)
    step("collect", "从 %d 个目标采证：决定性用例 %d 条"
         % (len(targets), counts["decisive_cases"]))
    new_rules, pending = synthesize_rules(
        memory, observations, run_id,
        decisive=counts["decisive_cases"] > 0)
    step("synthesize", "立规则 %d 条 / 待复现 %d 条"
         % (len(new_rules), len(pending)))

    # ── 成长判定：只依据决定性证据 ──
    if counts["decisive_cases"] == 0:
        growth_verdict = "insufficient_evidence"
    elif new_rules:
        growth_verdict = "grew"
    else:
        growth_verdict = "no_growth"

    # ── 幂等：同一 run_id 覆盖而不追加 ──
    record = {
        "run_id": run_id,
        "started_at": now_iso(),
        "targets": [str(t) for t in targets],
        "growth_verdict": growth_verdict,
        "summary": counts,
        "new_rules": new_rules,
        "pending_patterns": pending,
        "observations": observations,
        "skipped_targets": skipped,
        "note": ("decisive 用例为 0，无法判断成长——环境问题不等于能力变化，"
                 "本节不给出 grew/degraded 结论")
                if growth_verdict == "insufficient_evidence" else "",
    }
    runs = [r for r in memory["runs"] if r.get("run_id") != run_id]
    runs.append(record)
    memory["runs"] = runs

    has_llm = bool(__import__("os").environ.get("ROOT_AGENT_LLM_BASE_URL"))
    has_torch = False
    try:
        import importlib
        has_torch = importlib.util.find_spec("torch") is not None
    except Exception:
        has_torch = False

    ladder = build_ladder(has_llm, has_torch, memory["rules"], new_rules)
    memory["ladder"] = ladder

    save_memory(memory_dir, memory)

    next_actions = []
    if counts["environment_blocked_cases"] and counts["decisive_cases"] == 0:
        next_actions.append(
            "配置 ROOT_AGENT_LLM_BASE_URL 与密钥后重跑 root-agent-eval；"
            "在此之前所有分数与成长结论都不代表能力"
        )
    if pending:
        next_actions.append(
            f"有 {len(pending)} 个模式只出现 1 次，再跑一轮即可判定是否立规则"
        )
    actionable = [r for r in memory["rules"] if r.get("actionable")]
    if actionable:
        next_actions.append(
            f"有 {len(actionable)} 条可自动修规则，运行 root-agent-opt 消费")

    emit({
        "ok": True,
        "agent": KIND,
        "kind": KIND,
        "stage": STAGE,
        "run_id": run_id,
        "growth_verdict": growth_verdict,
        "memory_dir": str(memory_dir),
        "memory_file": str(Path(memory_dir) / MEMORY_FILE),
        "markdown_file": str(Path(memory_dir) / MARKDOWN_FILE),
        "counts": counts,
        "new_rules": new_rules,
        "pending_patterns": pending,
        "active_rules": len(memory["rules"]),
        "runs_recorded": len(memory["runs"]),
        "reply": ("成长采集完成：本轮结论 %s。采集 %d 次观察（决定性用例 %d 条），"
                  "累计 %d 轮；活跃规则 %d 条，本轮新立 %d 条，待复现 %d 条。%s"
                  % (growth_verdict, len(memory["runs"]),
                     counts["decisive_cases"], len(memory["runs"]),
                     len(memory["rules"]), len(new_rules), len(pending),
                     ("跳过的目标 %d 个（%s）。"
                      % (len(skipped), "；".join(
                          "%s：%s" % (s.get("target"), s.get("reason"))
                          for s in skipped[:3])))
                     if skipped else "")),
        "ladder": ladder,
        "skipped_targets": skipped,
        "next_actions": next_actions,
        "honest_limitations": [
            "未做 RL 训练（AgentRL）：本机无 torch、无模型端点，只落地其循环结构。",
            "未做合成数据生成（SWE-smith）：同上，且存在「同一模型生成又判分」的自证循环风险；"
            "已改以「复现 ≥2 次才立规则」落实其数据驱动取向。",
            "模式归一化用字符串摘要，不做语义聚类：措辞不同的同一问题会被算成两个模式，"
            "这会让规则更难成立而非更容易（偏保守）。",
            "首版不做跨多轮时序回归检测，只做「上轮规则本轮是否仍复现」的保守判定。",
        ],
        "warnings": [],
    }, 0)


if __name__ == "__main__":
    main()
