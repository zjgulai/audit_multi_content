#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""root-agent-doctor · 体检型 agent（验证阶段的前置闸门）

契约（见 ../refs/agent-contract.yaml）：
    interface: cli
    run:       python3 agent.py
    input:     stdin-json      —— {"agent_dir": "...", "skip_instantiate": bool}
    output:    stdout-json     —— 体检报告

doctor 只回答一个问题：**这个 agent 包能不能被实例化、能不能被安全地跑起来。**
它不评能力（走 root-agent-eval），不修包（走 root-agent-opt）。

三个检查维度取自三个参照仓库：
  - SWE-bench/SWE-bench       → dataset check / images check：包完整性与字段校验
  - THUDM/AgentBench          → task worker 健康检查：能否实例化
  - anthropics/claude-agent-sdk → 子 agent 包的目录结构与提示词校验方法论

硬约束：doctor 是只读的。除自身外不修改任何文件，被检包在体检前后必须逐字节不变。
"""

import ast
import hashlib
import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT_AGENTS = HERE.parents[0]                     # root-agents/
REFS_DIR = ROOT_AGENTS / "refs"

KIND = "root-agent-doctor"
STAGE = "verify"
INSTANTIATE_TIMEOUT = 120

# 契约字段（兜底；优先从 refs/agent-contract.yaml 读）
FALLBACK_CONTRACT_FIELDS = [
    "name",
    "version",
    "interface",
    "run",
    "input",
    "profile",
    "task_types",
    "deliverables",
    "tools",
    "env",
]

# deliverables 子字段与允许的交付形态（与 root-agent-creater 保持一致）
DELIVERABLE_REQUIRED = ["id", "name", "format", "acceptance"]
VALID_DELIVERABLE_FORMATS = {"docx", "xlsx", "md", "json", "state", "text"}

# 需要扫描的文本类文件后缀
TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".json", ".txt", ".sh", ".cfg", ".toml"}

SECRET_PATTERNS = [
    ("openai_style_key", re.compile(r"sk-[A-Za-z0-9]{16,}")),
    ("api_key_literal", re.compile(r"(?i)api[_-]?key\s*[=:]\s*['\"][^'\"${\s]{8,}")),
    ("token_literal", re.compile(r"(?i)\btoken\s*[=:]\s*['\"][^'\"${\s]{8,}")),
    ("secret_literal", re.compile(r"(?i)\bsecret\s*[=:]\s*['\"][^'\"${\s]{8,}")),
]

DANGER_PATTERNS = [
    ("rm_rf_root", re.compile(r"rm\s+-[rf]{1,2}\s+/(?:\s|$|\*|['\"`])")),
    ("rm_rf_home", re.compile(r"rm\s+-[rf]{1,2}\s+~")),
    ("curl_pipe_shell", re.compile(r"(?i)\b(?:curl|wget)\b[^\n|]*\|\s*(?:ba|z|k)?sh\b")),
    ("chmod_777", re.compile(r"chmod\s+(?:-R\s+)?777")),
    # 词边界 + 明确实参：早期版本用裸 "request" 当词，把 EVAL = ... 这类
    # 变量赋值误判成危险调用（doctor 自检 ref 时实测踩到）。
    ("eval_input", re.compile(r"\beval\s*\(\s*(?:input\s*\(|sys\.stdin|"
                              r"os\.environ|request\s*\[|request\.get)")),
]


# ---------------------------------------------------------------- 输出

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
    emit(
        {"ok": False, "agent": KIND, "kind": KIND, "stage": STAGE,
         "error": error, "reply": message, "checks": [], "warnings": []},
        1,
    )


# ---------------------------------------------------------------- 最小 YAML 读取

def _strip_comment(line):
    out, quote = [], None
    for ch in line:
        if quote:
            if ch == quote:
                quote = None
            out.append(ch)
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _scalar(value):
    """标量解析。

    必须认识内联空集合 `[]` / `{}`：实测踩到——agent.yaml 里写 `targets: []`，
    早期版本解析成字符串 "[]"，导致体检时被测 agent 收到 {"targets": "[]"} 并报
    「必须是数组」→ doctor 误判 unhealthy。数字与布尔也一并解析，
    否则下游拿到字符串无法比较。
    """
    if value in ("", "null", "~"):
        return None
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if (len(value) >= 2 and value[0] == value[-1]
            and value[0] in "\"'"):
        return value[1:-1]
    # 列表项的内联映射（- {label: x}）不做完整解析，原样返回供调用方降级处理
    if value.startswith("{") and value.endswith("}"):
        return value
    if value in ("true", "false"):
        return value == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _blocks(text):
    items = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = _strip_comment(raw)
        if not line.strip():
            continue
        items.append((len(line) - len(line.lstrip()), line.strip()))
    return items


def _parse_map(items, index, indent):
    result = {}
    while index < len(items):
        level, content = items[index]
        if level < indent:
            break
        if level > indent or content.startswith("- ") or ":" not in content:
            index += 1
            continue
        key, _, value = content.partition(":")
        key, value = key.strip(), value.strip()
        index += 1
        if value:
            result[key] = _scalar(value)
            continue
        if index < len(items) and items[index][0] > level:
            child_indent = items[index][0]
            if items[index][1].startswith("- "):
                result[key], index = _parse_list(items, index, child_indent)
            else:
                result[key], index = _parse_map(items, index, child_indent)
        else:
            result[key] = {}
    return result, index


def _parse_list(items, index, indent):
    result = []
    while index < len(items):
        level, content = items[index]
        if level != indent or not content.startswith("- "):
            break
        inline = content[2:].strip()
        index += 1
        if ":" in inline and inline[0] not in "\"'":
            key, _, value = inline.partition(":")
            entry = {}
            if value.strip():
                entry[key.strip()] = _scalar(value.strip())
            if index < len(items) and items[index][0] > level:
                child, index = _parse_map(items, index, items[index][0])
                entry.update(child)
            result.append(entry)
        else:
            result.append(_scalar(inline))
    return result, index


def parse_yaml_text(text):
    items = _blocks(text)
    if not items:
        return {}
    parsed, _ = _parse_map(items, 0, items[0][0])
    return parsed


def contract_fields():
    """优先从 refs/agent-contract.yaml 读契约字段；读不到用兜底。"""
    path = REFS_DIR / "agent-contract.yaml"
    try:
        parsed = parse_yaml_text(path.read_text(encoding="utf-8"))
        if all(field in parsed for field in FALLBACK_CONTRACT_FIELDS):
            return [f for f in FALLBACK_CONTRACT_FIELDS if f in parsed]
    except Exception:
        pass
    return list(FALLBACK_CONTRACT_FIELDS)


# ---------------------------------------------------------------- check 构造

def make_check(check_id, level, status, detail=""):
    return {"id": check_id, "level": level, "status": status, "detail": detail}


def iter_text_files(pkg, skip_dirs=("evals",)):
    """遍历包内文本文件。

    skip_dirs：评测器自己的产物目录（evals/）。里面的 cases/results 是**生成物**，
    装着安全用例的假密钥夹具；扫它们等于拿自测数据判被测方。实测踩到：
    root-agent-creater 因 evals/cases.json 命中密钥模式被误判 unhealthy。
    """
    pkg = Path(pkg)
    for path in sorted(pkg.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        rel_parts = path.relative_to(pkg).parts
        if any(part in skip_dirs for part in rel_parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def scan_patterns(pkg, patterns):
    """返回 [(相对路径, 行号, 模式名), ...]。"""
    hits = []
    for path in iter_text_files(pkg):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            for name, pattern in patterns:
                if pattern.search(line):
                    hits.append((str(path.relative_to(pkg)), lineno, name))
    return hits


# ---------------------------------------------------------------- 三组检查

def check_deliverables(manifest):
    """交付物结构检查（doctor 只查结构，不评交付物内容好不好）。

    级别划分：
      deliverables.present   fail —— 缺失 / 不是数组 / 空数组，阻断
      deliverables.id_unique fail —— id 重复，阻断
      deliverables.fields    warn —— 某项缺必填子字段
      deliverables.format    warn —— format 不在允许集合内
    """
    checks = []
    dels = manifest.get("deliverables")

    if not isinstance(dels, list) or not dels:
        checks.append(make_check(
            "deliverables.present", "fail", "fail",
            "deliverables 缺失、不是数组或为空——每个 agent 至少交 1 样东西",
        ))
        return checks

    names = "、".join(
        str(d.get("name") or d.get("id"))
        for d in dels if isinstance(d, dict)
    )
    checks.append(make_check(
        "deliverables.present", "fail", "pass",
        f"deliverables 共 {len(dels)} 项：{names}",
    ))

    ids = [d.get("id") for d in dels if isinstance(d, dict) and d.get("id")]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    checks.append(make_check(
        "deliverables.id_unique", "fail", "fail" if dup else "pass",
        f"id 重复：{dup}" if dup else "id 唯一",
    ))

    bad = []
    for idx, d in enumerate(dels):
        if not isinstance(d, dict):
            bad.append(f"[{idx}]不是对象")
            continue
        for sub in DELIVERABLE_REQUIRED:
            if not d.get(sub):
                bad.append(f"[{idx}].{sub}")
    checks.append(make_check(
        "deliverables.fields", "warn", "fail" if bad else "pass",
        (f"缺少必填子字段：{bad}" if bad
         else "每项子字段齐全（id/name/format/acceptance）"),
    ))

    badfmt = [
        f"[{i}]{d.get('format')}" for i, d in enumerate(dels)
        if isinstance(d, dict) and d.get("format")
        and d["format"] not in VALID_DELIVERABLE_FORMATS
    ]
    checks.append(make_check(
        "deliverables.format", "warn", "fail" if badfmt else "pass",
        (f"format 非法：{badfmt}，允许 {sorted(VALID_DELIVERABLE_FORMATS)}"
         if badfmt else "format 全部合法"),
    ))

    return checks


def check_structure(pkg):
    """A 组：结构与契约（SWE-bench 的 dataset/images check 语义）。"""
    checks = []

    exists = Path(pkg).is_dir()
    checks.append(make_check(
        "dir.exists", "fail", "pass" if exists else "fail",
        f"目录：{pkg}" if exists else f"目录不存在：{pkg}",
    ))
    if not exists:
        return checks, None

    manifest_path = Path(pkg) / "agent.yaml"
    if not manifest_path.is_file():
        checks.append(make_check("manifest.exists", "fail", "fail", "缺少 agent.yaml"))
        checks.append(make_check("manifest.parse", "fail", "skipped", "无 agent.yaml 可解析"))
        checks.append(make_check("manifest.fields", "fail", "skipped", "无 agent.yaml 可校验"))
        checks.append(make_check("manifest.run_present", "fail", "skipped", "无 agent.yaml"))
        return checks, None

    checks.append(make_check("manifest.exists", "fail", "pass", "agent.yaml 存在"))

    try:
        manifest = parse_yaml_text(manifest_path.read_text(encoding="utf-8"))
        if not manifest:
            raise ValueError("解析结果为空")
        checks.append(make_check("manifest.parse", "fail", "pass", "agent.yaml 可解析"))
    except Exception as exc:
        checks.append(make_check("manifest.parse", "fail", "fail", f"解析失败：{exc}"))
        checks.append(make_check("manifest.fields", "fail", "skipped", "无法解析"))
        checks.append(make_check("manifest.run_present", "fail", "skipped", "无法解析"))
        return checks, None

    required = contract_fields()
    missing = [f for f in required if f not in manifest]
    checks.append(make_check(
        "manifest.fields", "fail", "fail" if missing else "pass",
        (f"缺少字段：{missing}" if missing
         else f"契约字段齐全（{len(required)} 项）：{'/'.join(required)}"),
    ))

    checks.extend(check_deliverables(manifest))

    run_ok = bool(manifest.get("run"))
    checks.append(make_check(
        "manifest.run_present", "fail", "pass" if run_ok else "fail",
        f"run={manifest.get('run')!r}",
    ))

    # env 值必须经 ${managed} 注入（fail 级）
    env = manifest.get("env") or {}
    literal = [k for k, v in env.items()
               if isinstance(v, str) and "${" not in v]
    checks.append(make_check(
        "env.managed", "fail", "fail" if literal else "pass",
        (f"env 含字面量值：{literal}，应为 ${{managed}}" if literal
         else "env 全部经 ${managed} 注入"),
    ))

    # 工具声明与实现一致性
    entry = Path(pkg) / "agent.py"
    if entry.is_file():
        checks.append(make_check("entry.exists", "fail", "pass", "agent.py 存在"))
    else:
        checks.append(make_check("entry.exists", "fail", "fail", "缺少 agent.py"))

    declared = [t.get("name") for t in (manifest.get("tools") or [])
                if isinstance(t, dict) and t.get("name")]
    tools_dir = Path(pkg) / "tools"
    present, stubs = set(), set()
    if tools_dir.is_dir():
        for tool_file in sorted(tools_dir.glob("*.py")):
            if tool_file.stem == "__init__":
                continue
            present.add(tool_file.stem)
            # 「有文件」不等于「实现了」：抛 NotImplementedError 的桩照样跑不了。
            # 历史缺陷：只数文件存在，于是工具桩被判成「声明与实现一致」→ healthy。
            try:
                text = tool_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "raise NotImplementedError" in text:
                stubs.add(tool_file.stem)

    if declared:
        absent = sorted(set(declared) - present)
        stub_declared = sorted(set(declared) & stubs)
        problems = []
        if absent:
            problems.append(f"缺文件：{absent}")
        if stub_declared:
            problems.append(f"工具桩未实现：{stub_declared}")
        checks.append(make_check(
            "tools.declared_implemented", "fail", "fail" if problems else "pass",
            ("；".join(problems) if problems
             else f"声明与实现一致：{sorted(set(declared))}"),
        ))
    else:
        checks.append(make_check(
            "tools.declared_implemented", "fail", "pass", "未声明工具，跳过一致性检查",
        ))

    implemented = present
    orphan = sorted(implemented - set(declared))
    checks.append(make_check(
        "tools.orphan", "warn", "pass" if not orphan else "fail",
        "无未声明工具" if not orphan else f"未声明但存在：{orphan}",
    ))

    return checks, manifest


def check_syntax(pkg):
    """C 组之一：Python 语法（claude-code 的 skill 校验语义）。"""
    problems = []
    compiled = 0
    for path in sorted(Path(pkg).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
                py_compile.compile(str(path), cfile=tmp.name, doraise=True)
            compiled += 1
        except py_compile.PyCompileError as exc:
            problems.append(f"{path.relative_to(pkg)}: {exc.msg.strip().splitlines()[-1]}")
        except Exception as exc:
            problems.append(f"{path.relative_to(pkg)}: {type(exc).__name__}: {exc}")

    return make_check(
        "py.syntax", "fail", "fail" if problems else "pass",
        ("；".join(problems) if problems else f"{compiled} 个 .py 文件语法通过"),
    )


def check_security(pkg):
    """C 组之二：密钥与危险命令扫描。"""
    secret_hits = scan_patterns(pkg, SECRET_PATTERNS)
    danger_hits = scan_patterns(pkg, DANGER_PATTERNS)
    fmt = lambda hits: "；".join(f"{f}:{n} ({name})" for f, n, name in hits[:5])
    return [
        make_check(
            "secret.scan", "fail", "fail" if secret_hits else "pass",
            fmt(secret_hits) if secret_hits else "未发现字面量密钥",
        ),
        make_check(
            "danger.scan", "fail", "fail" if danger_hits else "pass",
            fmt(danger_hits) if danger_hits else "未发现危险命令模式",
        ),
    ]


def check_extras(pkg):
    """C 组之三：提示词与用例（warn 级）。"""
    checks = []

    prompt = Path(pkg) / "prompts" / "system.md"
    prompt_ok = prompt.is_file() and prompt.read_text(encoding="utf-8").strip() != ""
    checks.append(make_check(
        "prompts.exists", "warn", "pass" if prompt_ok else "fail",
        "prompts/system.md 非空" if prompt_ok else "prpts/system.md 缺失或为空".replace("prpts", "prompts"),
    ))

    smoke = Path(pkg) / "tests" / "smoke.json"
    smoke_ok = False
    smoke_detail = "tests/smoke.json 缺失"
    if smoke.is_file():
        try:
            json.loads(smoke.read_text(encoding="utf-8"))
            smoke_ok = True
            smoke_detail = "tests/smoke.json 是合法 JSON"
        except json.JSONDecodeError as exc:
            smoke_detail = f"tests/smoke.json 非法 JSON：{exc}"
    checks.append(make_check(
        "tests.exists", "warn", "pass" if smoke_ok else "fail", smoke_detail,
    ))

    return checks


# ════════════════════════════════════════════════ 六项扩展检查（D 组）
#
# 覆盖 refs/agent-contract.yaml 的六个**选填**字段节：scope / routing /
# limits / deps / state / handoff。分级口径写死在这里，改之前先想清楚：
#
#   fail    —— 缺陷：引用的文件不存在、占位符没替换、硬编码个人路径、
#              无界循环、能力已在却不满足自己声明的约定
#   warn    —— 声明缺项：职责边界、路由条件、终止预算、清理与并发约定、
#              依赖清单。缺它不影响包能不能跑，硬判 unhealthy 会把健康包挡在门外
#   skipped —— 能力不适用：无状态 / 单 agent。**不扣分，也不假装查过**
#
# 第 10、11 项「按实际能力启用」：先在包里找状态与协作的**证据**
# （契约声明 / 模块级常量 / 真实路径引用），找到才检查对应配置。
# 一个无状态、不派子 agent 的包，不会因为「没写记忆配置」被判缺陷；
# 反过来，真在写状态、真在调别的 agent 的包，才必须把自己的约定写清楚。

ARTIFACT_DIRS = {
    "evals", "memory", "outputs", "output", "out", "dist", "build",
    "logs", "cache", "tmp", "state",
}

INSTRUCTION_SUFFIXES = {".md", ".markdown", ".txt"}
CONFIG_SCRIPT_SUFFIXES = {".yaml", ".yml", ".sh", ".bash", ".json",
                          ".toml", ".cfg", ".ini"}
CODE_SUFFIXES = {".py"}

# 可核对的引用：带目录的相对路径 + 有后缀的文件名。
# 纯文件名（agent.py、README.md）不算引用——那多半是泛指的约定名，不是具体文件。
PATH_REF_RE = re.compile(
    r"(?<![\w/.\-])((?:\.{1,2}/)?(?:[A-Za-z0-9_\-.]+/)+[A-Za-z0-9_\-.]+"
    r"\.(?:md|markdown|py|sh|bash|yaml|yml|json|txt|csv|tsv|toml|cfg|ini"
    r"|html|sql|docx|xlsx|j2|jinja|tmpl|template))"
)

# 未替换的占位符：模板变量形态。fenced code block 里的不算——提示词里贴
# 「生成 Jinja 模板」的示例是合法内容，不能当缺陷。
PLACEHOLDER_RE = re.compile(r"\{\{[^}\n]{1,40}\}\}|\{%[^%\n]{1,40}%\}|<PLACEHOLDER>")
LEFTOVER_RE = re.compile(r"\bTODO\b|\bFIXME\b|\bTBD\b|待补|待填|\bXXX\b")

# 指令里点名要用、但契约没声明也没实现的工具名（背引号包着的标识符）
TOOL_REF_RE = re.compile(
    r"`([a-z][a-z0-9_]{2,})`\s*(?:工具|tool)"
    r"|(?:工具|tool|调用|使用|use|call)\s*[:：]?\s*`([a-z][a-z0-9_]{2,})`")

# 环境变量读取走 AST 解析（见 env_reads）：正则会把生成器源码里的模板字符串
# 一起算进来，实测在 root-agent-creater 上误报过。

# 环境自带的键：不声明也不算缺（这些由宿主进程给，不是包自己的配置）
AMBIENT_ENV = {
    "PATH", "HOME", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "TZ", "PWD",
    "USER", "LOGNAME", "SHELL", "TERM", "TMPDIR", "PYTHONPATH",
    "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED", "PYTHONHASHSEED",
}

# 个人主目录硬编码。字面量拆开写：否则 doctor 扫自己时会命中这段正则源码
# （与 DANGER_PATTERNS 同一类自伤，实测踩到过）。
HOME_PATH_RE = re.compile(
    r"/Use" r"rs/[A-Za-z0-9_.\-]+"
    r"|/home/[a-z][A-Za-z0-9_.\-]*"
    r"|[A-Za-z]:\\\\?Use" r"rs\\\\?[A-Za-z0-9_.\-]+"
)

# 状态能力的证据：模块级常量名（MEMORY_FILE / STATE_PATH …）+ 真实的持久化调用。
# 分两档是为了少误报：STATE / MEMORY / CHECKPOINT 裸名就够明确，
# 而 CONTEXT / SESSION / HISTORY / CACHE 是内存里也常见的名字，必须带后缀才算，
# 或者值本身是一条持久化路径（下面用字符串后缀判）。
STATE_CONST_STRICT_RE = re.compile(
    r"^(STATE|MEMORY|CHECKPOINT)(_FILE|_PATH|_DIR|_STORE|_KEY|_ROOT|_JSON)?$")
STATE_CONST_LOOSE_RE = re.compile(
    r"^(SESSION|HISTORY|CACHE|CONTEXT)(_FILE|_PATH|_DIR|_STORE|_KEY|_ROOT|_JSON)$")
STATE_PATH_SUFFIXES = (".json", ".db", ".sqlite", ".sqlite3", ".pkl", ".pickle",
                       ".txt", ".log", ".jsonl")
STATE_STORE_RE = re.compile(
    r"\bsqlite3\.connect\s*\(|\bshelve\.open\s*\(|\bpickle\.dump\s*\(")

# 协作能力的证据：指向别的 agent 包的具体路径
COLLAB_PATH_RE = re.compile(
    r"((?:[\w.\-]+/)*(?:sub-?agents?|[\w\-]+-agent|root-agent-[\w\-]+)"
    r"/[\w.\-/*]*agent\.py"
    r"|(?:[\w.\-]+/)*sub-?agents?/[\w.\-/]+\.(?:py|md|json|yaml))")
# 指令面里的协作措辞：动词 + 子 agent。只认动宾结构——
# 「参照仓库里有子 agent 编造指标」这类叙述不是协作能力。
COLLAB_PROSE_RE = re.compile(
    r"(调用|派生|派给|交给|转交|委派|交接|handoff|hand\s*off|delegate|spawn)"
    r"[^。\n]{0,16}(子\s?agent|sub-?agent|另一个\s?agent|其它\s?agent|其他\s?agent)",
    re.IGNORECASE)

DEPENDENCY_FILES = ("requirements.txt", "requirements-dev.txt", "pyproject.toml",
                    "setup.py", "Pipfile", "poetry.lock", "package.json")


def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def iter_files(pkg, suffixes):
    """遍历包内文件，跳过评测/记忆一类**产物目录**。

    产物目录里的路径是运行时生成的（evals/、memory/…），拿它们判「引用悬空」
    等于拿上一轮的输出判这一轮的源码。doctor 只读不写，所以这些目录它自己
    不会产生，但被测包跑过之后会在。
    """
    pkg = Path(pkg)
    for path in sorted(pkg.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(pkg)
        if any(part in ARTIFACT_DIRS for part in rel.parts[:-1]):
            continue
        if path.suffix.lower() in suffixes:
            yield path


def instruction_files(pkg):
    """指令/声明面：prompts/、docs/、根目录 README。"""
    out = []
    for path in iter_files(pkg, INSTRUCTION_SUFFIXES):
        rel = path.relative_to(pkg)
        head = rel.parts[0]
        if head in ("prompts", "docs"):
            out.append(path)
        elif len(rel.parts) == 1 and rel.name.lower().startswith(("readme", "agents")):
            out.append(path)
    return out


def config_script_files(pkg):
    """配置与脚本面：agent.yaml、*.sh、*.json 等。

    tests/ 下的 json 是用例数据，里面的路径是**题面素材**不是包的依赖，
    拿它判悬空引用会误伤（用例本就该包含「这个文件不存在」这类场景）。
    """
    out = []
    for path in iter_files(pkg, CONFIG_SCRIPT_SUFFIXES):
        rel = path.relative_to(pkg)
        if rel.parts[0] in ("prompts", "docs", "tests"):
            continue
        out.append(path)
    return out


def code_files(pkg):
    return list(iter_files(pkg, CODE_SUFFIXES))


def _ref_is_checkable(ref):
    if len(ref) > 120 or any(ch in ref for ch in "*?<>{}[]$"):
        return False
    segments = ref.split("/")
    if any(part in ARTIFACT_DIRS for part in segments[:-1]):
        return False                      # 产物目录里的路径，不判悬空
    return True


def _ref_resolves(pkg, ref_file, ref):
    """引用是否落地。解析基准依次是：引用所在目录 → 包根 → 家族根 → 上级。

    多个基准是必要的：包内文档写 `prompts/system.md`（包根基准），
    成员包写 `../refs/agent-contract.yaml`（家族根基准），业务包里
    写 `../shared/x.md`（上级基准）。任一处存在即算落地。
    """
    pkg = Path(pkg)
    for root in (ref_file.parent, pkg, pkg.parent, pkg.parent.parent):
        try:
            if (root / ref).exists():
                return True
        except OSError:
            continue
    return False


COMMENT_LINE_SUFFIXES = {".yaml", ".yml", ".sh", ".bash", ".cfg", ".ini", ".toml"}


def effective_lines(path):
    """按行返回 (行号, 正文)，配置文件与脚本里的注释行按空行处理。

    注释里写的出处不算「引用」：creater 生成的 agent.yaml 首行写着
    「本文件遵循 refs/agent-contract.yaml」，那是对家族契约的出处说明，
    生成的包落到家族之外时这条路径本来就不存在（实测把健康包判成了 unhealthy）。
    """
    pkg_suffix = path.suffix.lower()
    for lineno, raw in enumerate(read_text(path).splitlines(), start=1):
        if pkg_suffix in COMMENT_LINE_SUFFIXES:
            stripped = raw.lstrip()
            if stripped.startswith("#") or stripped.startswith("//"):
                yield lineno, ""
                continue
            yield lineno, _strip_comment(raw) if pkg_suffix in (".yaml", ".yml") else raw
        else:
            yield lineno, raw


def scan_dangling_refs(paths, pkg):
    """返回 [(相对路径, 行号, 引用)]，同一引用只报第一次出现。"""
    pkg = Path(pkg)
    seen, hits = set(), []
    for path in paths:
        for lineno, line in effective_lines(path):
            for match in PATH_REF_RE.finditer(line):
                ref = match.group(1)
                if not _ref_is_checkable(ref) or ref in seen:
                    continue
                if not _ref_resolves(pkg, path, ref):
                    seen.add(ref)
                    hits.append((str(path.relative_to(pkg)), lineno, ref))
    return hits


def _fmt_refs(hits, limit=5):
    return "；".join(f"{rel}:{lineno} 指向 {ref}" for rel, lineno, ref in hits[:limit])


def fenced_lines(text):
    """代码块（``` / ~~~）覆盖的行号集合。"""
    fenced, inside = set(), False
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            inside = not inside
            fenced.add(idx)
            continue
        if inside:
            fenced.add(idx)
    return fenced


def as_list_of_str(value):
    if not isinstance(value, list):
        return None
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        out.append(item.strip())
    return out


# ---------------------------------------------------------------- 第 3 项：职责与适用范围

def check_scope(manifest):
    """职责与适用范围：目标 / 处理范围 / 不处理的事项 / 路由条件。"""
    checks = []
    scope = manifest.get("scope")

    if scope is None:
        checks.append(make_check(
            "scope.declared", "warn", "fail",
            "未声明职责与适用范围。契约选填节 scope: {does: [...], not_for: [...]} "
            "——does 写这个 agent 管什么，not_for 写它明确不做的事。"
            "缺这句，调用方只能从提示词里猜它的边界",
        ))
    elif not isinstance(scope, dict):
        checks.append(make_check(
            "scope.declared", "warn", "fail",
            f"scope 应是映射（does / not_for），实际：{type(scope).__name__}",
        ))
    else:
        does = as_list_of_str(scope.get("does"))
        not_for = as_list_of_str(scope.get("not_for"))
        missing = []
        if not does:
            missing.append("does（处理范围）")
        if not not_for:
            missing.append("not_for（不处理的事项）")
        checks.append(make_check(
            "scope.declared", "warn", "fail" if missing else "pass",
            (f"scope 缺：{'、'.join(missing)}" if missing
             else f"职责与边界已声明：管 {len(does)} 项 / 不管 {len(not_for)} 项"),
        ))

    checks.append(scope_consistency_check(manifest, scope))
    checks.append(routing_check(manifest))
    return checks


def scope_consistency_check(manifest, scope):
    """声明内部是否自相矛盾（类型非法、既管又不管、边界与交付物撞车）。"""
    if scope is None:
        return make_check("scope.consistent", "fail", "skipped",
                          "未声明 scope，无可校验的一致性")
    if not isinstance(scope, dict):
        return make_check("scope.consistent", "fail", "fail",
                          f"scope 类型非法：{type(scope).__name__}，应为映射")

    problems = []
    raw_does, raw_not_for = scope.get("does"), scope.get("not_for")
    does = as_list_of_str(raw_does)
    not_for = as_list_of_str(raw_not_for)
    for key, raw, parsed in (("does", raw_does, does), ("not_for", raw_not_for, not_for)):
        if raw is not None and parsed is None:
            problems.append(f"{key} 应为「非空字符串」的数组")

    if does and not_for:
        both = sorted(set(does) & set(not_for))
        if both:
            problems.append(f"同一件事既在 does 又在 not_for：{both}")

    deliveries = set()
    for item in (manifest.get("deliverables") or []):
        if isinstance(item, dict):
            for key in ("name", "id"):
                if item.get(key):
                    deliveries.add(str(item[key]))
    if not_for and deliveries:
        clash = sorted(set(not_for) & deliveries)
        if clash:
            problems.append(f"not_for 声明不做的事，却出现在 deliverables 里：{clash}")

    return make_check(
        "scope.consistent", "fail", "fail" if problems else "pass",
        ("；".join(problems) if problems else "职责声明内部一致"),
    )


def routing_check(manifest):
    """路由条件：参与路由的包必须写清「什么情况下选它」。"""
    routing = manifest.get("routing")
    if routing is None:
        return make_check("routing.conditions", "warn", "skipped",
                          "未声明 routing —— 不参与路由，不适用（不扣分）")
    if not isinstance(routing, dict):
        return make_check("routing.conditions", "warn", "fail",
                          f"routing 类型非法：{type(routing).__name__}，应为映射")
    when = as_list_of_str(routing.get("when"))
    if not when:
        return make_check(
            "routing.conditions", "warn", "fail",
            "声明参与路由，但 routing.when 为空 —— 选择条件不清楚，"
            "路由方无从判断何时该选它",
        )
    return make_check("routing.conditions", "warn", "pass",
                      f"路由选择条件已声明 {len(when)} 条")


# ---------------------------------------------------------------- 第 5 项：指令质量与一致性

def check_instructions(pkg, manifest):
    """指令面：悬空引用 / 未替换占位符 / 残留标记 / 点名了没声明的工具。

    能确定性判定的都判；跨文件语义矛盾与优先级冲突静态判不了，
    不在这里假装判过（真实语义一致性由 eval 的行为用例覆盖）。
    """
    files = instruction_files(pkg)
    if not files:
        return [
            make_check("instructions.dangling_refs", "fail", "skipped",
                       "包内没有指令面文件（prompts/、README），无可检索的引用"),
            make_check("instructions.placeholders", "fail", "skipped",
                       "包内没有指令面文件，无占位符可查"),
            make_check("instructions.leftovers", "warn", "skipped",
                       "包内没有指令面文件，无残留标记可查"),
            make_check("instructions.tool_refs", "warn", "skipped",
                       "包内没有指令面文件，无工具引用可查"),
        ]

    pkg = Path(pkg)
    dangling = scan_dangling_refs(files, pkg)

    placeholders, leftovers = [], []
    for path in files:
        text = read_text(path)
        fenced = fenced_lines(text)
        rel = str(path.relative_to(pkg))
        for lineno, line in enumerate(text.splitlines(), start=1):
            if lineno in fenced:
                continue
            if PLACEHOLDER_RE.search(line):
                placeholders.append(f"{rel}:{lineno}")
            if LEFTOVER_RE.search(line):
                leftovers.append(f"{rel}:{lineno}")

    declared_tools = {str(t.get("name")) for t in (manifest.get("tools") or [])
                      if isinstance(t, dict) and t.get("name")}
    implemented = set()
    tools_dir = pkg / "tools"
    if tools_dir.is_dir():
        implemented = {p.stem for p in tools_dir.glob("*.py")
                       if p.stem != "__init__"}
    known = declared_tools | implemented | {
        str(s) for s in (manifest.get("skills") or []) if isinstance(s, str)
    } | {"python", "python3", "json", "yaml", "bash", "shell", "markdown",
         "stdin", "stdout", "agent", "tool", "skill"}

    tool_refs = []
    for path in files:
        text = read_text(path)
        fenced = fenced_lines(text)
        rel = str(path.relative_to(pkg))
        for lineno, line in enumerate(text.splitlines(), start=1):
            if lineno in fenced:
                continue
            for match in TOOL_REF_RE.finditer(line):
                name = match.group(1) or match.group(2)
                if name and name not in known:
                    tool_refs.append(f"{rel}:{lineno} 点名 `{name}`")

    return [
        make_check(
            "instructions.dangling_refs", "fail", "fail" if dangling else "pass",
            (_fmt_refs(dangling) if dangling
             else f"指令面 {len(files)} 个文件里提到的包内路径都存在"),
        ),
        make_check(
            "instructions.placeholders", "fail", "fail" if placeholders else "pass",
            ("未替换的占位符：" + "、".join(placeholders[:5]) if placeholders
             else "未发现未替换的占位符（代码块内的模板示例不计）"),
        ),
        make_check(
            "instructions.leftovers", "warn", "fail" if leftovers else "pass",
            ("残留标记（TODO/TBD/待补 一类）：" + "、".join(leftovers[:5])
             if leftovers else "未发现残留标记"),
        ),
        make_check(
            "instructions.tool_refs", "warn", "fail" if tool_refs else "pass",
            ("指令点名了未声明也未实现的工具：" + "；".join(tool_refs[:5])
             if tool_refs
             else "指令点名的工具都在契约里声明或已实现"),
        ),
    ]


# ---------------------------------------------------------------- 第 7 项：文件与环境依赖

def _stdlib_names():
    """本机标准库顶层模块名：从标准库目录现场枚举，不硬编码清单。

    硬编码清单会随 Python 版本漂移（3.9 有 distutils、3.12 没有），
    现场枚举的结果与运行这个 doctor 的解释器一致。
    """
    names = set(sys.builtin_module_names)
    stdlib = os.path.dirname(os.__file__)
    try:
        entries = os.listdir(stdlib)
    except OSError:
        return names
    for entry in entries:
        full = os.path.join(stdlib, entry)
        if entry.endswith(".py"):
            names.add(entry[:-3])
        elif os.path.isdir(full) and os.path.isfile(os.path.join(full, "__init__.py")):
            names.add(entry)
    dynload = os.path.join(stdlib, "lib-dynload")
    if os.path.isdir(dynload):
        for entry in os.listdir(dynload):
            names.add(entry.split(".")[0])
    return names


def _optional_import_lines(tree):
    """try 块里的 import 行号：可选依赖，不当成缺声明的第三方依赖。"""
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    lines.add(sub.lineno)
    return lines


def third_party_imports(pkg):
    """返回 {模块名: 相对路径}，只算无 try 兜底、非本机标准库、非包内模块的导入。"""
    pkg = Path(pkg)
    stdlib = _stdlib_names()
    local = {p.stem for p in pkg.rglob("*.py") if "__pycache__" not in p.parts}
    local |= {p.name for p in pkg.iterdir() if p.is_dir()}
    found = {}
    for path in code_files(pkg):
        source = read_text(path)
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            continue                      # 语法错由 py.syntax 报，这里不重复
        optional = _optional_import_lines(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if node.lineno in optional:
                continue
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            else:
                modules = [(node.module or "").split(".")[0]]
            for module in modules:
                if not module or module in stdlib or module in local:
                    continue
                found.setdefault(module, str(path.relative_to(pkg)))
    return found


def env_reads(pkg):
    """代码里真实读取的环境变量，返回 [(相对路径, 行号, 变量名)]。

    走 AST 而不是正则：creater 会把一段「生成出来的 agent 代码」当**模板字符串**
    写在源码里，正则扫源码会把模板里的 os.environ.get("AGENT_LLM_BASE_URL")
    算成 creater 自己在读那个变量（实测踩到）。字符串常量不进 AST 的 Call 节点，
    正好把「模板」与「真实调用」分开。
    """
    pkg = Path(pkg)
    reads = []
    for path in code_files(pkg):
        try:
            tree = ast.parse(read_text(path))
        except (SyntaxError, ValueError):
            continue
        rel = str(path.relative_to(pkg))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "get":
                    base = func.value
                    if (isinstance(base, ast.Attribute) and base.attr == "environ") or \
                       (isinstance(base, ast.Name) and base.id == "environ"):
                        name = _first_str_arg(node)
                elif isinstance(func, ast.Attribute) and func.attr == "getenv":
                    name = _first_str_arg(node)
            elif isinstance(node, ast.Subscript):
                base = node.value
                if isinstance(base, ast.Attribute) and base.attr == "environ":
                    name = node.slice.value if isinstance(node.slice, ast.Constant) \
                        else None
            if isinstance(name, str) and name:
                reads.append((rel, getattr(node, "lineno", 0), name))
    return reads


def _first_str_arg(node):
    """调用里的第一个字符串实参（环境变量名就在这个位置）。"""
    if node.args and isinstance(node.args[0], ast.Constant) \
            and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def check_dependencies(pkg, manifest):
    """文件与环境依赖：引用是否落地、个人路径、环境变量与第三方依赖是否声明。"""
    pkg = Path(pkg)
    refs = scan_dangling_refs(config_script_files(pkg), pkg)

    hardcoded = []
    for path in iter_files(pkg, CODE_SUFFIXES | CONFIG_SCRIPT_SUFFIXES
                           | INSTRUCTION_SUFFIXES):
        rel = str(path.relative_to(pkg))
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            match = HOME_PATH_RE.search(line)
            if match:
                hardcoded.append(f"{rel}:{lineno} ({match.group(0)})")
                break

    declared_env = set()
    env_block = manifest.get("env")
    if isinstance(env_block, dict):
        declared_env |= {str(k) for k in env_block}
    used_env = sorted({
        f"{rel}:{lineno} 读了 {name}"
        for rel, lineno, name in env_reads(pkg)
        if name not in AMBIENT_ENV and name not in declared_env
    })

    third_party = third_party_imports(pkg)
    dep_files = [name for name in DEPENDENCY_FILES if (pkg / name).is_file()]
    declared_deps = bool(dep_files) or isinstance(manifest.get("deps"), (dict, list))

    if not third_party:
        third_party_check = make_check(
            "deps.third_party", "warn", "pass",
            "未发现第三方导入（标准库与本包内模块之外的导入）",
        )
    elif declared_deps:
        third_party_check = make_check(
            "deps.third_party", "warn", "pass",
            f"第三方导入 {sorted(third_party)}，依赖清单已声明：{dep_files or ['agent.yaml deps']}",
        )
    else:
        third_party_check = make_check(
            "deps.third_party", "warn", "fail",
            "有第三方导入但没声明依赖：" + "、".join(
                f"{m}（{f}）" for m, f in sorted(third_party.items()))
            + "。补 requirements.txt / pyproject.toml，或在 agent.yaml 写 deps:",
        )

    return [
        make_check(
            "deps.refs_exist", "fail", "fail" if refs else "pass",
            (_fmt_refs(refs) if refs
             else "配置与脚本面提到的包内文件都存在"),
        ),
        make_check(
            "deps.hardcoded_path", "fail", "fail" if hardcoded else "pass",
            ("硬编码个人主目录路径：" + "；".join(hardcoded[:5]) if hardcoded
             else "未发现硬编码的个人主目录路径"),
        ),
        make_check(
            "deps.env_declared", "warn", "fail" if used_env else "pass",
            ("读了未在 agent.yaml env 里声明的环境变量：" + "；".join(used_env[:5])
             if used_env else "代码读取的环境变量都已在契约里声明（或属环境自带）"),
        ),
        third_party_check,
    ]


# ---------------------------------------------------------------- 第 8 项：执行流程与终止条件

def _loop_is_bounded(node):
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Break, ast.Return, ast.Raise)):
            return True
    return False


def check_flow(pkg, manifest):
    """执行流程：无界循环、无上限递归、终止预算声明。"""
    pkg = Path(pkg)
    unbounded, recursive = [], []

    for path in code_files(pkg):
        rel = str(path.relative_to(pkg))
        source = read_text(path)
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                test = node.test
                always_true = (isinstance(test, ast.Constant) and bool(test.value)) or \
                              (isinstance(test, ast.NameConstant) and test.value is True)
                if always_true and not _loop_is_bounded(node):
                    unbounded.append(f"{rel}:{node.lineno}")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                guard = {arg.arg for arg in node.args.args} & {
                    "depth", "level", "n", "remaining", "max_depth", "budget"}
                if guard:
                    continue
                # 只认**裸名字调用**（foo() 调到 foo）：path.read_text() 这类属性调用
                # 与自递归无关，早期把 attr == 函数名 也算进去，误报了 read_text。
                calls_self = any(
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id == node.name
                    for sub in ast.walk(node)
                )
                # 有 if 的函数多半在收敛（对有限数据结构递归），不算「无上限」。
                # 只报「既自递归、又没有任何分支判断」的写法——那才是退不出来的形状。
                has_branch = any(isinstance(sub, ast.If) for sub in ast.walk(node))
                if calls_self and not has_branch:
                    recursive.append(f"{rel}:{node.lineno} {node.name}()")

    limits = manifest.get("limits") or manifest.get("termination")
    if limits is None:
        limits_check = make_check(
            "flow.limits_declared", "warn", "fail",
            "未声明终止预算。契约选填节 limits: {timeout_s: 120, max_iterations: 3} "
            "——没有预算的 agent，调用方只能自己拍超时",
        )
    elif not isinstance(limits, dict) or not limits:
        limits_check = make_check(
            "flow.limits_declared", "warn", "fail",
            f"limits 应为非空映射（timeout_s / max_iterations / max_depth），"
            f"实际：{limits!r}",
        )
    else:
        bad = [k for k, v in limits.items()
               if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0]
        limits_check = make_check(
            "flow.limits_declared", "warn", "fail" if bad else "pass",
            (f"limits 里这些项不是正数：{bad}" if bad
             else f"终止预算已声明：{limits}"),
        )

    return [
        make_check(
            "flow.loop_bound", "fail", "fail" if unbounded else "pass",
            ("无界循环（while 恒真且循环体内没有 break/return/raise）："
             + "、".join(unbounded[:5]) if unbounded
             else "未发现无界循环"),
        ),
        make_check(
            "flow.recursion_bound", "warn", "fail" if recursive else "pass",
            ("自递归但未见深度上限参数（depth/level/max_depth 一类）："
             + "、".join(recursive[:5]) if recursive
             else "未发现无上限的自递归"),
        ),
        limits_check,
    ]


# ---------------------------------------------------------------- 第 10 项：状态与记忆（能力门控）

def detect_state_capability(pkg, manifest):
    """这个包到底有没有状态？返回 (有无, 证据)。

    只认三种证据，宁漏不误：
      1. 契约里声明了 state；
      2. 模块级常量是状态：STATE / MEMORY / CHECKPOINT（裸名即算），
         或 SESSION / HISTORY / CACHE / CONTEXT 加后缀，或值是一条持久化路径；
      3. 用了 sqlite3 / shelve / pickle 这类持久化调用。
    「写过文件」不算——写交付物、写评测产物都是正常产出，不是状态。
    """
    state = manifest.get("state")
    if state:
        return True, "契约声明了 state"

    for path in code_files(pkg):
        rel = str(path.relative_to(pkg))
        source = read_text(path)
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            tree = None
        if tree is not None:
            for node in tree.body:            # 只看模块级赋值
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if STATE_CONST_STRICT_RE.match(target.id):
                        return True, f"{rel} 的模块级常量 {target.id}"
                    if STATE_CONST_LOOSE_RE.match(target.id):
                        return True, f"{rel} 的模块级常量 {target.id}"
                    if _assigns_state_path(node, target.id):
                        return True, f"{rel} 的模块级常量 {target.id} 指向状态文件"
        match = STATE_STORE_RE.search(source)
        if match:
            return True, f"{rel} 调用了 {match.group(0).strip('(')}"
    return False, ""


def _assigns_state_path(node, target_id):
    """模块级常量被赋成一条持久化路径（`STATE = "/tmp/x.json"` 这种）。

    只看名字会漏掉「名字不像状态、值是状态文件」的写法；只看值会误伤
    「值恰好是 .json 的配置路径」。两者都要求，才当证据。
    """
    if not re.search(r"state|memory|session|history|cache|checkpoint|context",
                     target_id, re.IGNORECASE):
        return False
    value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value.endswith(STATE_PATH_SUFFIXES)
    return False


def check_state(pkg, manifest):
    """状态与记忆：位置 / 隔离 / 生命周期 / 并发。无状态能力 → 全项 skipped。"""
    capable, evidence = detect_state_capability(pkg, manifest)
    na = ("未检测到状态能力（无 state 声明、无状态常量、无持久化调用）"
          "—— 第 10 项不适用，不计入扣分")

    if not capable:
        return [
            make_check("state.declared", "fail", "skipped", na),
            make_check("state.isolation", "fail", "skipped", na),
            make_check("state.lifecycle", "warn", "skipped", na),
            make_check("state.concurrency", "warn", "skipped", na),
        ]

    state = manifest.get("state")
    if not isinstance(state, dict):
        return [
            make_check("state.declared", "fail", "fail",
                       f"检测到状态能力（{evidence}），但契约里没有 state 声明。"
                       f"补 state: {{path: ..., scope: ..., key: ..., cleanup: ...}}"),
            make_check("state.isolation", "fail", "fail", "无 state 声明，隔离约定无从谈起"),
            make_check("state.lifecycle", "warn", "fail", "无 state 声明，生命周期约定无从谈起"),
            make_check("state.concurrency", "warn", "fail", "无 state 声明，并发约定无从谈起"),
        ]

    path_value = state.get("path") or state.get("dir") or state.get("store")
    isolation = state.get("key") or state.get("isolation") or state.get("scope")
    lifecycle = state.get("cleanup") or state.get("ttl_s") or state.get("retention")
    lock = state.get("lock") or state.get("atomic") or state.get("concurrency")

    source_blob = "\n".join(read_text(p) for p in code_files(pkg))
    lock_evidence = bool(re.search(
        r"fcntl\.|filelock|portalocker|threading\.Lock|os\.replace\(", source_blob))
    cleanup_evidence = bool(re.search(
        r"\.unlink\(|os\.remove\(|shutil\.rmtree\(|rotate", source_blob))

    return [
        make_check(
            "state.declared", "fail", "pass" if path_value else "fail",
            (f"状态位置已声明：{path_value}（证据：{evidence}）" if path_value
             else f"检测到状态能力（{evidence}），但 state 里没写 path/dir/store"),
        ),
        make_check(
            "state.isolation", "fail", "pass" if isolation else "fail",
            (f"隔离约定已声明：{isolation}" if isolation
             else "没写 state.key/isolation/scope —— 不同用户或任务共用一个状态文件，"
                  "先写后读会互相污染"),
        ),
        make_check(
            "state.lifecycle", "warn", "pass" if (lifecycle or cleanup_evidence) else "fail",
            ("生命周期约定已声明：" + str(lifecycle) if lifecycle
             else ("代码里有删除/轮转动作，视为有清理" if cleanup_evidence
                   else "没写 state.cleanup/ttl_s/retention —— 状态什么时候清、旧状态何时失效没说")),
        ),
        make_check(
            "state.concurrency", "warn", "pass" if (lock or lock_evidence) else "fail",
            ("并发约定已声明：" + str(lock) if lock
             else ("代码里用了锁或原子替换" if lock_evidence
                   else "没写 state.lock/concurrency，代码里也没有锁或原子替换 —— "
                        "并发写入的约定缺失")),
        ),
    ]


# ---------------------------------------------------------------- 第 11 项：多 agent 协作（能力门控）

def detect_collab_capability(pkg, manifest):
    """这个包到底有没有跟别的 agent 协作？返回 (有无, 证据)。

    只认三种证据：
      1. 契约里声明了 handoff / subagents / collaborators；
      2. **代码与配置**里出现指向别的 agent 包的具体路径（路径形态见 COLLAB_PATH_RE）
         —— 那是真的在调它；
      3. 指令面出现动宾结构的协作措辞（「交给子 agent 汇总」）。

    不算证据的两类：
      · 叙述性提及（「参照仓库的子 agent 曾编造指标」）——没有动词就不是委托；
      · **文档里只写路径、没有委托动作**（README 里贴一行「用法：python3 <路径>/agent.py」）
        ——那是出处说明，不是协作能力。实测有包因为 README 写了这么一行被判缺 handoff：
        路径引用与交接动作是两件事，文档面的引用改由 instructions.dangling_refs 管存在性。
      · tests/ 下的引用也不算：测试指着兄弟包取夹具，不是这个包的协作能力。
    """
    for field in ("handoff", "subagents", "collaborators"):
        if manifest.get(field):
            return True, f"契约声明了 {field}"

    code_surfaces = list(iter_files(pkg, CODE_SUFFIXES | CONFIG_SCRIPT_SUFFIXES))
    for path in code_surfaces:
        rel = path.relative_to(pkg)
        if "tests" in rel.parts:
            continue
        match = COLLAB_PATH_RE.search(read_text(path))
        if match:
            return True, f"{rel} 引用了 {match.group(1)}"

    for path in instruction_files(pkg):
        rel = str(path.relative_to(pkg))
        match = COLLAB_PROSE_RE.search(read_text(path))
        if match:
            return True, f"{rel} 写着「{match.group(0)[:24]}」"
    return False, ""


def handoff_target_resolves(pkg, target):
    """handoff.to 写的对象能不能找到。

    只在它**看起来可定位**时才判：带 / 的路径、或以 -agent 结尾的包名。
    其余（外部服务名、宿主提供的调度器名）不判——共置与否不是这个包能决定的。
    """
    if not isinstance(target, str) or not target.strip():
        return None                        # 没什么可判的
    target = target.strip()
    looks_locatable = ("/" in target or target.endswith("-agent")
                       or target.startswith("root-agent-")
                       or target.startswith("subagent"))
    if not looks_locatable:
        return None
    pkg = Path(pkg)
    for root in (pkg, pkg.parent, pkg.parent.parent):
        try:
            if (root / target).exists() or (root / target / "agent.py").is_file():
                return True
        except OSError:
            continue
    return False


def check_collaboration(pkg, manifest):
    """多 agent 协作：交接对象 / 交接约定 / 无界调用。单 agent → 全项 skipped。"""
    capable, evidence = detect_collab_capability(pkg, manifest)
    na = ("未检测到协作能力（无 handoff 声明、无子 agent 引用、无协作措辞）"
          "—— 第 11 项不适用，不计入扣分")

    if not capable:
        return [
            make_check("collab.refs_exist", "fail", "skipped", na),
            make_check("collab.handoff_declared", "fail", "skipped", na),
            make_check("collab.bounds", "warn", "skipped", na),
        ]

    pkg = Path(pkg)
    handoff = manifest.get("handoff")
    if handoff is None and manifest.get("subagents"):
        handoff = {"to": manifest.get("subagents")}

    refs_check = make_check(
        "collab.refs_exist", "fail", "pass",
        f"协作引用已在包内落地（证据：{evidence}）",
    )
    dangling = scan_dangling_refs(
        [p for p in iter_files(pkg, CODE_SUFFIXES | CONFIG_SCRIPT_SUFFIXES
                               | INSTRUCTION_SUFFIXES)
         if "tests" not in p.relative_to(pkg).parts], pkg)
    collab_refs = [h for h in dangling if COLLAB_PATH_RE.search(h[2])]
    if collab_refs:
        refs_check = make_check("collab.refs_exist", "fail", "fail",
                                "引用的子 agent 不存在：" + _fmt_refs(collab_refs))
    else:
        target_ok = handoff_target_resolves(pkg, (handoff or {}).get("to")
                                            if isinstance(handoff, dict) else None)
        if target_ok is False:
            refs_check = make_check(
                "collab.refs_exist", "fail", "fail",
                f"handoff.to 写的「{handoff.get('to')}」在包内与同级目录都找不到 —— "
                f"交接对象不存在，交接无从发生",
            )
        elif target_ok is True:
            refs_check = make_check(
                "collab.refs_exist", "fail", "pass",
                f"交接对象已定位：{handoff.get('to')}",
            )

    if not isinstance(handoff, dict):
        declared = make_check(
            "collab.handoff_declared", "fail", "fail",
            f"检测到协作能力（{evidence}），但没有 handoff 声明。"
            f"补 handoff: {{to: ..., input: [...], output: [...]}}",
        )
    else:
        missing = [k for k in ("to", "input", "output") if not handoff.get(k)]
        declared = make_check(
            "collab.handoff_declared", "fail", "fail" if missing else "pass",
            (f"handoff 缺：{missing} —— 交接的输入输出没写清，对方无从对接"
             if missing else f"交接约定已声明：to={handoff.get('to')}"),
        )

    bounds = None
    if isinstance(handoff, dict):
        bounds = handoff.get("bounds") or handoff.get("max_depth")
    code_blob = "\n".join(read_text(p) for p in code_files(pkg))
    guard = bool(bounds) or bool(re.search(
        r"max_depth|max_calls|MAX_DEPTH|MAX_CALLS|timeout\s*=|TIMEOUT", code_blob))
    bounds_check = make_check(
        "collab.bounds", "warn", "pass" if guard else "fail",
        ("调用上限已声明/有超时约束" if guard
         else "没写 handoff.bounds（max_depth / max_calls）也没见超时约束 —— "
              "相互调用或等待可能没有上限"),
    )

    return [refs_check, declared, bounds_check]


# 探针：工具型 agent 收结构化命令，业务型 agent 收 {"question": ...}。
# 契约的 profile 字段区分不了运行命令，故允许 agent.yaml 显式声明 health.input。
PROTOCOL_MISMATCH_CODES = {
    "missing_field", "invalid_input", "invalid_name", "unknown_tool",
    "unknown_dimension", "invalid_interface",
}


def _run_probe(pkg, payload, env):
    """跑一次探针。返回 (proc, error_checks_or_None)。"""
    try:
        proc = subprocess.run(
            [sys.executable, "agent.py"],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            cwd=str(pkg),
            env=env,
            timeout=INSTANTIATE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, f"实例化超时（>{INSTANTIATE_TIMEOUT}s）"
    except OSError as exc:
        return None, f"无法执行：{exc}"
    return proc, None


def _is_protocol_mismatch(proc):
    """被测 agent 是否只是"不认识这个输入"，而非真的坏了。

    判据：退出非零 + stdout 是合法 JSON + ok:false + error.code 属输入类错误。
    这是「协议不符」与「不健康」的分界，不能混为一谈。
    """
    if proc.returncode == 0:
        return False
    try:
        parsed = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(parsed, dict) or parsed.get("ok") is not False:
        return False
    code = (parsed.get("error") or {}).get("code")
    return code in PROTOCOL_MISMATCH_CODES


def check_instantiate(pkg, manifest):
    """B 组：实例化健康（AgentBench 的 task worker 健康检查语义）。

    必须真跑一次：字段填对 ≠ 进程能起来。
    以 cwd=agent_dir 执行，因为契约的 run: python3 agent.py 是相对路径语义。
    """
    ids = ("instantiate.run", "instantiate.protocol", "instantiate.ok_field")
    # ok 字段表达"这次任务成不成"，不是"这个包能不能跑"，故为 warn 级。
    # 退出码与 JSON 协议才是实例化能否成立的判据。
    LEVELS = {"instantiate.run": "fail", "instantiate.protocol": "fail",
              "instantiate.ok_field": "warn"}

    entry = Path(pkg) / "agent.py"
    if not entry.is_file():
        return [make_check(i, LEVELS[i], "skipped", "无 agent.py，无法实例化") for i in ids]

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "PYTHONDONTWRITEBYTECODE": "1",   # 只读约束：不留下 __pycache__
    }
    # 探针顺序：声明的 health.input > question 探针 > {} 退化探针
    declared = manifest.get("health")
    declared_input = declared.get("input") if isinstance(declared, dict) else None

    # 探针来源只有两个：声明的 health.input，或契约默认的 question 探针。
    # 不猜测其它负载——猜不出来，只会把协议不符误报成不健康。
    if isinstance(declared_input, dict):
        probes = [("声明探针 health.input", declared_input)]
    else:
        probes = [("question 探针", {"question": "ping"})]

    proc, error, used = None, None, None
    for label, payload in probes:
        proc, error = _run_probe(pkg, payload, env)
        used = label
        break

    if error:
        return [
            make_check(ids[0], LEVELS[ids[0]], "fail", error),
            make_check(ids[1], LEVELS[ids[1]], "skipped", "未产出输出"),
            make_check(ids[2], LEVELS[ids[2]], "skipped", "未产出输出"),
        ]

    checks = []
    run_ok = proc.returncode == 0
    mismatch = _is_protocol_mismatch(proc)
    if run_ok:
        run_detail = f"退出码 0（{used}）"
    elif mismatch:
        run_detail = (
            f"退出码 {proc.returncode}：{used} 被协议拒绝"
            f"（被测 agent 拒绝该输入形状）。若这是工具型 agent，"
            f"请在 agent.yaml 声明 health.input 提供合法探针负载，"
            f"例如 health:\n  input: {{name: probe, ...}}；"
            f"否则它会被误判为不健康。"
        )
    else:
        run_detail = (f"退出码 {proc.returncode}（{used}）；"
                      f"stderr 前 300 字：{proc.stderr[:300]}")
    checks.append(make_check(ids[0], LEVELS[ids[0]], "pass" if run_ok else "fail",
                             run_detail))

    parsed = None
    try:
        parsed = json.loads(proc.stdout)
        checks.append(make_check(ids[1], LEVELS[ids[1]], "pass", "stdout 是合法 JSON"))
    except json.JSONDecodeError as exc:
        checks.append(make_check(
            ids[1], LEVELS[ids[1]], "fail",
            f"stdout 不是合法 JSON：{exc}；前 200 字：{proc.stdout[:200]}",
        ))

    if parsed is None:
        checks.append(make_check(ids[2], LEVELS[ids[2]], "skipped", "无 JSON 可校验"))
    elif isinstance(parsed, dict) and isinstance(parsed.get("ok"), bool):
        checks.append(make_check(
            ids[2], LEVELS[ids[2]], "pass",
            f"ok={parsed['ok']}（业务返回值，不参与实例化判定）",
        ))
    else:
        checks.append(make_check(
            ids[2], LEVELS[ids[2]], "fail", "stdout JSON 缺少布尔字段 ok",
        ))

    return checks


# ---------------------------------------------------------------- 主流程

REQUIRED_CHECK_IDS = [
    ("dir.exists", "fail"),
    ("manifest.exists", "fail"),
    ("manifest.parse", "fail"),
    ("manifest.fields", "fail"),
    ("manifest.run_present", "fail"),
    ("deliverables.present", "fail"),
    ("deliverables.id_unique", "fail"),
    ("deliverables.fields", "warn"),
    ("deliverables.format", "warn"),
    ("entry.exists", "fail"),
    ("tools.declared_implemented", "fail"),
    ("tools.orphan", "warn"),
    ("env.managed", "fail"),
    ("instantiate.run", "fail"),
    ("instantiate.protocol", "fail"),
    ("instantiate.ok_field", "warn"),
    ("py.syntax", "fail"),
    ("secret.scan", "fail"),
    ("danger.scan", "fail"),
    ("prompts.exists", "warn"),
    ("tests.exists", "warn"),
    # ── D 组：第 3 项职责与适用范围 ──
    ("scope.declared", "warn"),
    ("scope.consistent", "fail"),
    ("routing.conditions", "warn"),
    # ── D 组：第 5 项指令质量与一致性 ──
    ("instructions.dangling_refs", "fail"),
    ("instructions.placeholders", "fail"),
    ("instructions.leftovers", "warn"),
    ("instructions.tool_refs", "warn"),
    # ── D 组：第 7 项文件与环境依赖 ──
    ("deps.refs_exist", "fail"),
    ("deps.hardcoded_path", "fail"),
    ("deps.env_declared", "warn"),
    ("deps.third_party", "warn"),
    # ── D 组：第 8 项执行流程与终止条件 ──
    ("flow.loop_bound", "fail"),
    ("flow.recursion_bound", "warn"),
    ("flow.limits_declared", "warn"),
    # ── D 组：第 10 项状态与记忆（能力门控，无状态 → skipped 不扣分）──
    ("state.declared", "fail"),
    ("state.isolation", "fail"),
    ("state.lifecycle", "warn"),
    ("state.concurrency", "warn"),
    # ── D 组：第 11 项多 agent 协作（能力门控，单 agent → skipped 不扣分）──
    ("collab.refs_exist", "fail"),
    ("collab.handoff_declared", "fail"),
    ("collab.bounds", "warn"),
]

# C 组 + D 组：结构检查没过就整组跳过，避免级联误报
CONTENT_CHECK_IDS = [
    ("secret.scan", "fail"), ("danger.scan", "fail"),
    ("prompts.exists", "warn"), ("tests.exists", "warn"),
    ("scope.declared", "warn"), ("scope.consistent", "fail"),
    ("routing.conditions", "warn"),
    ("instructions.dangling_refs", "fail"), ("instructions.placeholders", "fail"),
    ("instructions.leftovers", "warn"), ("instructions.tool_refs", "warn"),
    ("deps.refs_exist", "fail"), ("deps.hardcoded_path", "fail"),
    ("deps.env_declared", "warn"), ("deps.third_party", "warn"),
    ("flow.loop_bound", "fail"), ("flow.recursion_bound", "warn"),
    ("flow.limits_declared", "warn"),
    ("state.declared", "fail"), ("state.isolation", "fail"),
    ("state.lifecycle", "warn"), ("state.concurrency", "warn"),
    ("collab.refs_exist", "fail"), ("collab.handoff_declared", "fail"),
    ("collab.bounds", "warn"),
]


def diagnose(pkg, skip_instantiate=False):
    checks = []
    warnings = []

    structure_checks, manifest = check_structure(pkg)
    checks.extend(structure_checks)
    step("check_structure", "目录 / 契约字段 / 交付物 / 入口 %d 项"
         % len(structure_checks))

    # A 组失败则不进入实例化，避免级联误报（规格 Implementation Decisions）
    structure_ok = not any(
        c["status"] == "fail" and c["level"] == "fail" for c in structure_checks
    )

    syntax = check_syntax(pkg) if Path(pkg).is_dir() else None
    if syntax is not None:
        checks.append(syntax)
    step("check_syntax", "包内 Python 源码可编译性")

    if structure_ok:
        checks.extend(check_security(pkg))
        checks.extend(check_extras(pkg))
        checks.extend(check_scope(manifest))
        checks.extend(check_instructions(pkg, manifest))
        checks.extend(check_dependencies(pkg, manifest))
        checks.extend(check_flow(pkg, manifest))
        checks.extend(check_state(pkg, manifest))
        checks.extend(check_collaboration(pkg, manifest))
        step("check_content", "安全扫描 / 规范 / 指令 / 依赖 / 流程 / 状态 / 协作")
    else:
        for cid, level in CONTENT_CHECK_IDS:
            checks.append(make_check(cid, level, "skipped", "结构检查未通过，跳过"))

    # 实例化：前置条件全部满足才跑
    instantiate_ids = ("instantiate.run", "instantiate.protocol", "instantiate.ok_field")
    if skip_instantiate:
        checks.extend(
            make_check(i, "fail", "skipped", "调用方要求跳过实例化")
            for i in instantiate_ids
        )
    elif not structure_ok or manifest is None:
        checks.extend(
            make_check(i, "fail", "skipped", "结构或契约检查未通过，无法实例化")
            for i in instantiate_ids
        )
    elif syntax is not None and syntax["status"] == "fail":
        checks.extend(
            make_check(i, "fail", "skipped", "存在语法错误，无法实例化")
            for i in instantiate_ids
        )
    else:
        checks.extend(check_instantiate(pkg, manifest))
        step("instantiate", "真起子进程跑健康探针，验协议与 ok 字段")

    # 补齐缺失的 check id（保证接口稳定，下游可无条件读取）
    present = {c["id"] for c in checks}
    for cid, level in REQUIRED_CHECK_IDS:
        if cid not in present:
            checks.append(make_check(cid, level, "skipped", "未执行"))

    order = {cid: idx for idx, (cid, _) in enumerate(REQUIRED_CHECK_IDS)}
    checks.sort(key=lambda c: order.get(c["id"], len(order)))

    blockings = [c for c in checks if c["level"] == "fail" and c["status"] == "fail"]
    warnings.extend(
        f"{c['id']}: {c['detail']}"
        for c in checks
        if c["level"] == "warn" and c["status"] == "fail"
    )
    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    skipped = sum(1 for c in checks if c["status"] == "skipped")

    return {
        "checks": checks,
        "blockings": blockings,
        "warnings": warnings,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
    }


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

    agent_dir = request.get("agent_dir")
    if not agent_dir or not isinstance(agent_dir, str):
        fail("missing_field", "缺少必填字段 agent_dir", field="agent_dir")

    pkg = Path(agent_dir).expanduser()
    if not pkg.is_absolute():
        pkg = (Path.cwd() / pkg).resolve()

    result = diagnose(pkg, skip_instantiate=bool(request.get("skip_instantiate")))
    verdict = "unhealthy" if result["blockings"] else "healthy"

    emit(
        {
            "ok": True,
            "agent": KIND,                       # 运行中的 agent 身份
            "kind": KIND,
            "stage": STAGE,
            "target": pkg.name,                  # 被检 agent 包名
            "inspected": str(pkg),
            "verdict": verdict,
            "reply": ("体检完成：%s 的结论是 %s。%d 项检查里 %d 项通过、%d 项未通过。%s"
                      % (pkg.name, verdict, len(result["checks"]),
                         sum(1 for c in result["checks"]
                             if c["status"] == "pass"),
                         sum(1 for c in result["checks"]
                             if c["status"] == "fail"),
                         ("阻断项：" + "；".join(c["detail"] for c in
                                              result["blockings"][:3]) + "。")
                         if result["blockings"] else "没有阻断项。")),
            "summary": result["summary"],
            "checks": result["checks"],
            "blockings": [
                {"id": c["id"], "detail": c["detail"]} for c in result["blockings"]
            ],
            "warnings": result["warnings"],
        },
        0 if verdict == "healthy" else 1,
    )


if __name__ == "__main__":
    main()
