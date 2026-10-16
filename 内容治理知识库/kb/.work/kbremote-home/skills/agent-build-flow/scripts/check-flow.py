#!/usr/bin/env python3
"""agent-build-flow 阶段产出物 + agent.yaml 契约自检。

用法:
    python3 check-flow.py --probe                  # 探测本机装了哪些配套命令
    python3 check-flow.py <项目目录>                # 校验阶段产出物 + 契约
    python3 check-flow.py <项目目录> --contract-only  # 只校验 agent.yaml 契约
    python3 check-flow.py <项目目录> --json         # 机器可读输出

退出码: 0=通过(可能有警告)  1=有阻断错误  2=用法错误

设计原则:
  - 不重复评测: 本脚本只查"产出物齐不齐""契约合不合规", 不评分。
  - 警告不阻断; 只有硬门禁违反才阻断。
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------- 常量

CROSS_TEN_FIELDS = [
    "name", "version", "interface", "run", "input",
    "profile", "task_types", "deliverables", "tools", "env",
]

# 这些字段存在即可; 其余必须非空
ALLOW_EMPTY_OK = {"env"}

INTERFACES = {"cli", "http", "sdk"}
PROFILES = {"general", "code", "web-ops"}
TASK_TYPES = {"fact_qa", "reasoning", "multi_turn", "instruction", "rag", "safety"}

# 算成活的东西不能进 deliverables
NOT_A_DELIVERABLE = ["工具", "skill", "技能", "约束", "禁止", "不编造", "脱敏", "变体", "检索", "计算"]

# acceptance 里出现这些词 = 写了实现细节
IMPL_DETAIL_WORDS = [
    "返回 ", "返回20", "返回 20", "HTTP", "http ", "状态码", "assert",
    "调用 ", "调用`", "函数", "接口返回", "字段返回", "打印", "console.log",
]

# 配套命令 (user-invoked = 只能人手动敲, model-invoked = 模型可自行加载)
COMPANION_COMMANDS = {
    "grill-with-docs": "user",
    "grilling": "model",
    "domain-modeling": "model",
    "to-spec": "user",
    "prototype": "model",
    "to-tickets": "user",
    "implement": "user",
    "tdd": "user",
    "code-review": "model",
    "handoff": "user",
    "setup-matt-pocock-skills": "user",
}

SKILL_ROOTS = [
    Path.home() / ".dsh" / "skills",
    Path.home() / ".agents" / "skills",
]

# ---------------------------------------------------------------- 极简 YAML

def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def _scalar(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_unquote(x) for x in inner.split(",") if x.strip()]
    if v.startswith("{") and v.endswith("}"):
        return {}  # 只认作占位, 不解析内容
    return _unquote(v)


def parse_simple_yaml(text):
    """解析 agent.yaml 用到的子集: 顶层标量 / 顶层列表 / 嵌套列表-of-映射 / 嵌套映射。
    不支持的语法会优雅降级为字符串, 不抛异常。
    """
    data = {}
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, raw.strip()))

    i = 0
    while i < len(lines):
        indent, line = lines[i]
        if indent != 0 or ":" not in line:
            i += 1
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest:
            data[key] = _scalar(rest)
            i += 1
            continue
        # 块: 看下一行
        block = []
        j = i + 1
        while j < len(lines) and lines[j][0] > 0:
            block.append(lines[j])
            j += 1
        if not block:
            data[key] = None
            i = j
            continue
        if block[0][1].startswith("- "):
            data[key] = _parse_list_block(block)
        else:
            data[key] = _parse_map_block(block)
        i = j
    return data


def _parse_map_block(block):
    out = {}
    base = block[0][0]
    for indent, line in block:
        if indent != base or ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = _scalar(v) if v.strip() else None
    return out


def _parse_list_block(block):
    """列表块。元素可能是标量(- x) 或映射(- k: v 后续缩进行)。"""
    out = []
    base = block[0][0]
    idx = 0
    while idx < len(block):
        indent, line = block[idx]
        if indent != base or not line.startswith("- "):
            idx += 1
            continue
        head = line[2:].strip()
        if ":" in head:
            item = {}
            k, _, v = head.partition(":")
            item[k.strip()] = _scalar(v) if v.strip() else None
            idx += 1
            # 吸收该元素的后续缩进行
            while idx < len(block) and block[idx][0] > base:
                sub_indent, sub = block[idx]
                if sub.startswith("- "):
                    break
                if ":" in sub:
                    sk, _, sv = sub.partition(":")
                    sv = sv.strip()
                    if sv:
                        item[sk.strip()] = _scalar(sv)
                        idx += 1
                        continue
                    # 嵌套列表 (如 fields:)
                    sk = sk.strip()
                    idx += 1
                    sub_items = []
                    while idx < len(block) and block[idx][0] > sub_indent and block[idx][1].startswith("- "):
                        sub_items.append(_unquote(block[idx][1][2:].strip()))
                        idx += 1
                    item[sk] = sub_items
                    continue
                idx += 1
            out.append(item)
        else:
            out.append(_scalar(head))
            idx += 1
    return out


# ---------------------------------------------------------------- probe

def probe():
    print("agent-build-flow · 配套命令探测\n")
    missing = []
    rows = []
    for name in sorted(COMPANION_COMMANDS):
        kind = COMPANION_COMMANDS[name]
        found_at = None
        for root in SKILL_ROOTS:
            candidate = root / name
            if candidate.is_dir():
                found_at = str(candidate)
                break
        rows.append((name, kind, found_at))
        if not found_at:
            missing.append(name)

    print(f"{'命令':<30}{'类型':<8}{'状态'}")
    print("-" * 72)
    for name, kind, found_at in rows:
        mark = "已装" if found_at else "未装"
        label = "user-invoked(只能人敲)" if kind == "user" else "model-invoked"
        print(f"/{name:<29}{label:<24}{mark}")

    print("\n结论:")
    if missing:
        print(f"  未装 {len(missing)} 个: {', '.join(missing)}")
        print("  → 未装环节的判据请直接用本技能 references/ 里内置的那份, 不要引导用户跑不存在的命令。")
    else:
        print("  全部已装。")
    print("\n提醒: user-invoked 的命令 **任何 skill 都调不动**, 只能写文字请用户自己敲 /命令。")
    print("      不要写「本技能会调用 /to-tickets」——那是错的。")
    return 0


# ---------------------------------------------------------------- 阶段产出物

STAGE_ARTIFACTS = [
    ("阶段 0", "立项一页纸", ["one-pager.md", "立项一页纸.md", "docs/one-pager.md"]),
    ("阶段 1", "解决方案文档", ["solution.md", "解决方案.md", "docs/solution.md"]),
    ("阶段 2", "规格", ["spec.md", "规格.md", "docs/spec.md"]),
    ("阶段 2", "原型", ["prototype/", "prototypes/"]),
    ("阶段 3", "工单", [".scratch/", "issues/"]),
    ("阶段 4", "交接文档", ["handoff.md"]),
    ("阶段 5", "评测报告(HTML)", ["evals/report.html"]),
]


def check_artifacts(root: Path, errors, warnings, passes):
    print("── 阶段产出物 ──")
    found_count = 0
    for stage, name, candidates in STAGE_ARTIFACTS:
        hit = None
        for c in candidates:
            p = root / c
            if p.exists():
                hit = c
                break
        if hit:
            found_count += 1
            passes.append(f"{stage} {name}: 找到 {hit}")
            print(f"  [OK]   {stage} {name} → {hit}")
        else:
            warnings.append(f"{stage} {name}: 未找到（候选: {', '.join(candidates)}）")
            print(f"  [WARN] {stage} {name} → 未找到")
    if found_count == 0:
        errors.append("项目目录下没有任何阶段产出物——确认路径对不对？")
    print()


# ---------------------------------------------------------------- 契约校验

def check_contract(path: Path, errors, warnings, passes):
    print(f"── agent.yaml 契约 ({path}) ──")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"读取 agent.yaml 失败: {exc}")
        return

    data = parse_simple_yaml(text)

    # 1. 十字段齐全
    missing = [f for f in CROSS_TEN_FIELDS if f not in data]
    if missing:
        errors.append(f"十字段缺失: {', '.join(missing)}（硬门禁，不通过）")
        print(f"  [ERR]  十字段缺失: {', '.join(missing)}")
    else:
        passes.append("十字段齐全")
        print("  [OK]   十字段齐全")

    # 2. 空值检查
    for field in CROSS_TEN_FIELDS:
        if field in ALLOW_EMPTY_OK or field not in data:
            continue
        val = data.get(field)
        if val in (None, "", [], {}):
            errors.append(f"字段 `{field}` 为空（硬门禁）")
            print(f"  [ERR]  `{field}` 为空")

    # 3. 枚举合法性
    iface = data.get("interface")
    if iface and iface not in INTERFACES:
        errors.append(f"`interface` 非法: {iface}（应为 {'/'.join(sorted(INTERFACES))}）")
        print(f"  [ERR]  interface 非法: {iface}")

    profile = data.get("profile")
    if profile and profile not in PROFILES:
        warnings.append(f"`profile` 不在已知档位: {profile}")
        print(f"  [WARN] profile 未知: {profile}")

    tt = data.get("task_types")
    if isinstance(tt, list) and tt:
        unknown = [t for t in tt if t not in TASK_TYPES]
        if unknown:
            warnings.append(f"`task_types` 含未知维度: {', '.join(map(str, unknown))}")
            print(f"  [WARN] task_types 含未知维度: {', '.join(map(str, unknown))}")

    # 4. name 必须 kebab-case
    name = data.get("name")
    if isinstance(name, str) and name and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        errors.append(f"`name` 不是 kebab-case: {name}")
        print(f"  [ERR]  name 不是 kebab-case: {name}")

    # 5. run 命令要可解析
    run = data.get("run")
    if isinstance(run, str) and run.strip():
        first = run.strip().split()[0]
        if not (shutil.which(first) or Path(root_of(path), first).exists() or os.path.exists(first)):
            warnings.append(f"`run` 的首个可执行 `{first}` 在本机找不到（换机器可能仍可用）")
            print(f"  [WARN] run 首个可执行 `{first}` 本机找不到")
        else:
            passes.append("run 命令可解析")
            print("  [OK]   run 命令可解析")

    # 6. env 不得有字面量密钥（硬门禁）
    env = data.get("env")
    if isinstance(env, dict) and env:
        bad = []
        for k, v in env.items():
            if not isinstance(v, str):
                continue
            if v.strip() == "${managed}":
                continue
            if re.search(r"(sk-|ghp_|AKIA|xox[baprs]-)", v) or len(v) >= 24:
                bad.append(k)
            elif v and not v.startswith("${"):
                bad.append(k)
        if bad:
            errors.append(f"`env` 存在字面量密钥: {', '.join(bad)}（硬门禁，必须改 ${{managed}}）")
            print(f"  [ERR]  env 有字面量密钥: {', '.join(bad)}")
        else:
            passes.append("env 无字面量密钥")
            print("  [OK]   env 无字面量密钥")

    # 7. deliverables 深度校验
    dels = data.get("deliverables")
    if not isinstance(dels, list) or not dels:
        errors.append("`deliverables` 为空或格式不对（硬门禁）")
        print("  [ERR]  deliverables 为空或格式不对")
    else:
        print(f"  [OK]   len(deliverables) = {len(dels)} → 这个 agent 能干 {len(dels)} 件活")
        passes.append(f"deliverables = {len(dels)} 件活")
        for idx, d in enumerate(dels, 1):
            if not isinstance(d, dict):
                errors.append(f"deliverables[{idx}] 不是映射结构")
                continue
            for req in ("id", "name", "acceptance"):
                if not d.get(req):
                    errors.append(f"deliverables[{idx}] 缺 `{req}`（每件活必须有 id/name/acceptance）")
                    print(f"  [ERR]  deliverables[{idx}] 缺 `{req}`")
            acc = d.get("acceptance") or ""
            if isinstance(acc, str):
                hits = [w for w in IMPL_DETAIL_WORDS if w in acc]
                if hits:
                    warnings.append(
                        f"deliverables[{idx}].acceptance 疑似实现细节: {', '.join(hits)}"
                        "（应改成业务语言）"
                    )
                    print(f"  [WARN] deliverables[{idx}].acceptance 疑似实现细节: {', '.join(hits)}")
                for word in NOT_A_DELIVERABLE:
                    if word in acc and word in ("工具", "检索", "计算"):
                        warnings.append(
                            f"deliverables[{idx}].acceptance 提到「{word}」——工具是手段不是验收标准"
                        )
                        break
            dn = d.get("name") or ""
            if isinstance(dn, str):
                for word in ("检索", "计算", "工具"):
                    if dn.strip() == word or dn.strip().startswith(word):
                        warnings.append(
                            f"deliverables[{idx}].name =「{dn}」疑似把工具当成活（工具不算活，应进 tools）"
                        )
                        print(f"  [WARN] deliverables[{idx}] 疑似把工具当成交付物: {dn}")
                        break

    print()


def root_of(path: Path) -> str:
    return str(path.parent)


# ---------------------------------------------------------------- main

def run(target: str, as_json: bool, contract_only: bool = False):
    root = Path(target).expanduser().resolve()
    if not root.is_dir():
        print(f"错误: 不是目录: {root}", file=sys.stderr)
        return 2

    errors, warnings, passes = [], [], []

    if not as_json:
        print(f"agent-build-flow 自检: {root}"
              + ("  [--contract-only]" if contract_only else "") + "\n")
    if not contract_only:
        check_artifacts(root, errors, warnings, passes)

    yamls = sorted(root.rglob("agent.yaml"))
    yamls = [y for y in yamls if "node_modules" not in str(y)]
    if not yamls:
        warnings.append("项目目录下没找到 agent.yaml（阶段 5 前属正常）")
        if not as_json:
            print("── agent.yaml 契约 ──\n  [WARN] 没找到 agent.yaml（阶段 5 前属正常）\n")
    else:
        for y in yamls[:5]:
            check_contract(y, errors, warnings, passes)

    if as_json:
        print(json.dumps(
            {"target": str(root), "passes": passes, "warnings": warnings, "errors": errors},
            ensure_ascii=False, indent=2,
        ))
    else:
        print("=" * 72)
        print(f"通过 {len(passes)} 项 | 警告 {len(warnings)} 项 | 阻断 {len(errors)} 项")
        if warnings:
            print("\n警告（不阻断）:")
            for w in warnings:
                print(f"  - {w}")
        if errors:
            print("\n阻断错误（必须修）:")
            for e in errors:
                print(f"  - {e}")
        print()
        if errors:
            print("结论: 不通过。先修阻断项再看警告。")
        elif warnings:
            print("结论: 通过（有警告）。硬门禁全过。")
        else:
            print("结论: 通过。")

    return 1 if errors else 0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}

    if "--help" in flags or "-h" in flags:
        print(__doc__)
        return 0
    if "--probe" in flags:
        return probe()
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    return run(args[0], "--json" in flags, "--contract-only" in flags)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
