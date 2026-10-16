#!/usr/bin/env python3
"""
manage.py - root-skills 家族管理器 CLI

维护 registry/skills.json：状态查看、一致性校验、成员注册、状态切换、路由建议。

用法:
    python scripts/manage.py status            # 查看家族全景
    python scripts/manage.py check             # 校验注册表一致性（路径/版本/依赖）
    python scripts/manage.py register <name> --path <path> --role <role> [--description "..."]
    python scripts/manage.py set-status <name> <planned|active|deprecated>
    python scripts/manage.py route "<用户请求>"  # 路由建议

约定:
    注册表位于 registry/skills.json（相对本脚本的上级目录）。
    成员 path 相对注册表文件所在目录。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent.parent / "registry" / "skills.json"
ROLES = {"create", "manage", "diagnose", "evaluate", "optimize", "check", "orchestrate"}
STATUSES = {"planned", "active", "deprecated"}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

# 路由关键词表（命中数最多者胜，平局取靠前者；diagnose 置于 optimize 之前，
# 使「修复 skill 目录结构」类请求优先路由到 doctor，而非被 opt 的「修复」吞掉）
ROUTE_TABLE = [
    ("diagnose", ["诊断", "什么问", "为什么触发", "问题在哪", "diagnos", "troubleshoot",
                  "目录结构", "目录整理", "结构检测", "结构问题", "skill 结构",
                  "skill-doctor", "结构医生", "体检", "规范检查", "批量修复", "整理"]),
    ("optimize", ["优化", "修复", "改好", "根据报告修", "improve", "fix", "optimize"]),
    ("evaluate", ["评估", "评分", "质量", "打分", "评价", "eval", "score", "quality",
                  "触发评测", "用例测试", "3轮", "复杂度出题", "评测skill", "测试skill",
                  "skill评测", "评测 skill", "测试 skill", "schema"]),
    ("create", ["创建", "新建", "写一个", "做一个", "变成 skill", "create", "build", "write a skill"]),
    ("orchestrate", ["批量评测", "批跑", "批量回归", "断点续跑", "无进展超时",
                  "subagent 卡死", "心跳检测", "批量评估编排", "batch-driver"]),
    ("check", ["核对报告", "报告核对", "报告完整性", "漏数据", "评测报告校验", "报告质检",
               "数据资产入库", "知识蒸馏", "自动成长"]),
    ("manage", ["家族", "全景", "成员", "管理", "路由", "注册表", "manage", "registry"]),
]
ROLE_TO_MEMBER = {
    "create": "root-skills-creator",
    "manage": "root-skills-manage",
    "diagnose": "root-skills-doctor",
    "evaluate": "root-skills-eval",
    "optimize": "root-skills-opt",
    "check": "root-skills-check",
    "orchestrate": "root-skills-batch-driver",
}


def _load_registry() -> dict:
    if not REGISTRY.exists():
        print(f"[error] 注册表不存在: {REGISTRY}", file=sys.stderr)
        sys.exit(1)
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _save_registry(data: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _find_member(data: dict, name: str):
    for m in data["members"]:
        if m["name"] == name:
            return m
    return None


def _member_frontmatter(path: Path) -> dict[str, str]:
    """使用标准库读取成员 SKILL.md 的顶层标量 frontmatter。"""
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        return {}
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    result = {}
    for line in parts[1].splitlines():
        match = re.match(r"^(name|version):\s*[\"']?([^\"'#\s]+)", line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def _member_skill_version(path: Path):
    """读取成员 SKILL.md frontmatter 的 version。"""
    return _member_frontmatter(path).get("version")


def _family_root(data: dict) -> Path | None:
    root_dir = data.get("root_dir")
    if not isinstance(root_dir, str) or not root_dir.strip():
        return None
    return (REGISTRY.parent / root_dir).resolve()


def _is_within(path: Path, root: Path) -> bool:
    """拒绝通过绝对路径、.. 或符号链接逃出家族根目录。"""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def cmd_status() -> int:
    data = _load_registry()
    print(f"== root-skills 家族全景 (v{data.get('version', '?')}) ==")
    print(f"   更新于: {data.get('updated_at', '?')}")
    print()
    for m in data["members"]:
        status = m["status"]
        mark = {"active": "●", "planned": "○", "deprecated": "✕"}.get(status, "?")
        ver = m.get("version") or "-"
        deps = ", ".join(m.get("depends_on", [])) or "-"
        print(f"  {mark} {m['name']:<22} [{status:<10}] v{ver}")
        print(f"      role: {m['role']:<9} path: {m['path']}")
        print(f"      desc: {m['description']}")
        print(f"      deps: {deps}")
    return 0


def cmd_check() -> int:
    data = _load_registry()
    errors = 0
    base = REGISTRY.parent
    print("== 注册表一致性校验 ==")

    if data.get("family") != "root-skills":
        print(f"  [error] family 必须为 root-skills，当前为 {data.get('family')!r}")
        errors += 1
    if not SEMVER_RE.fullmatch(str(data.get("version", ""))):
        print(f"  [error] 注册表 version 不是 semver: {data.get('version')!r}")
        errors += 1
    members = data.get("members")
    if not isinstance(members, list):
        print("  [error] members 必须是数组")
        print(f"== 结果: 有 {errors + 1} 个错误 ==")
        return 1

    family_root = _family_root(data)
    if family_root is None or not family_root.is_dir():
        print(f"  [error] root_dir 无效或不存在: {data.get('root_dir')!r}")
        errors += 1
        family_root = (base / ".." / "..").resolve()

    names = [m.get("name") for m in members if isinstance(m, dict)]
    known_names = {n for n in names if isinstance(n, str)}
    duplicate_names = sorted({n for n in known_names if names.count(n) > 1})
    for name in duplicate_names:
        print(f"  [error] 成员名重复: {name}")
        errors += 1

    active_roles: dict[str, str] = {}
    for index, m in enumerate(members, 1):
        member_errors_before = errors
        if not isinstance(m, dict):
            print(f"  [error] members[{index}] 必须是对象")
            errors += 1
            continue
        name = str(m.get("name", ""))
        role = m.get("role")
        status = m.get("status")
        rel_path = m.get("path")

        if not NAME_RE.fullmatch(name):
            print(f"  [error] 非法成员名（必须 kebab-case）: {name!r}")
            errors += 1
        if role not in ROLES:
            print(f"  [error] {name or index}: 非法 role={role!r}")
            errors += 1
        if status not in STATUSES:
            print(f"  [error] {name or index}: 非法 status={status!r}")
            errors += 1
        if status == "active" and role in ROLES:
            previous = active_roles.get(role)
            if previous and previous != name:
                print(f"  [error] role={role} 存在多个 active 成员: {previous}, {name}")
                errors += 1
            else:
                active_roles[role] = name
        if not isinstance(rel_path, str) or not rel_path.strip():
            print(f"  [error] {name or index}: path 必须是非空字符串")
            errors += 1
            continue

        path = (base / rel_path).resolve()
        if not _is_within(path, family_root):
            print(f"  [error] {name}: 路径逃出家族根目录 {path}")
            errors += 1
            continue
        if not path.exists():
            if status == "planned":
                print(f"  [ok] {name}: planned（路径尚未创建，符合预期）")
                continue
            print(f"  [error] {name}: 路径不存在 {path}")
            errors += 1
            continue
        if not (path / "SKILL.md").exists():
            print(f"  [error] {name}: 缺少 SKILL.md")
            errors += 1
            continue

        metadata = _member_frontmatter(path)
        skill_name = metadata.get("name")
        ver = metadata.get("version")
        reg_ver = m.get("version")
        if skill_name != name:
            print(f"  [error] {name}: 目录成员与 frontmatter name 不一致 ({skill_name!r})")
            errors += 1
        if status == "active":
            if ver is None:
                print(f"  [error] {name}: active 成员 SKILL.md 无 version 字段")
                errors += 1
            elif reg_ver != ver:
                print(f"  [error] {name}: 版本不一致 frontmatter={ver} registry={reg_ver}")
                errors += 1
        for dep in m.get("depends_on", []):
            if dep not in known_names:
                print(f"  [error] {name}: 依赖未登记 {dep}")
                errors += 1
        if errors == member_errors_before:
            print(f"  [ok] {name}: {path.name} (v{ver or '-'})")

    # Universal Skill Schema 单一事实来源：三副本 SHA-256 必须一致，防止规范漂移
    schema_dirs = ["root-skills-creator", "root-skills-eval", "root-skills-opt"]
    schema_hashes = {}
    missing = []
    for d in schema_dirs:
        schema_path = family_root / d / "references" / "universal-skill-schema.md"
        if schema_path.exists():
            schema_hashes[d] = hashlib.sha256(schema_path.read_bytes()).hexdigest()
        else:
            missing.append(d)
    if missing:
        print(f"  [error] universal-skill-schema.md 缺失于: {', '.join(missing)}")
        errors += 1
    elif len(set(schema_hashes.values())) > 1:
        print(f"  [error] universal-skill-schema.md 三副本漂移: {schema_hashes}")
        errors += 1
    else:
        digest = next(iter(schema_hashes.values()))
        print(f"  [ok] universal-skill-schema.md 三副本一致 (sha256 {digest[:12]}…)")

    print(f"== 结果: {'有 ' + str(errors) + ' 个错误' if errors else '通过'} ==")
    return 1 if errors else 0


def cmd_register(name: str, path: str, role: str, description: str) -> int:
    data = _load_registry()
    if not NAME_RE.fullmatch(name):
        print("[error] name 必须是 kebab-case", file=sys.stderr)
        return 1
    if role not in ROLES:
        print(f"[error] role 必须是 {sorted(ROLES)}", file=sys.stderr)
        return 1
    if _find_member(data, name):
        print(f"[error] 成员已存在: {name}", file=sys.stderr)
        return 1
    family_root = _family_root(data)
    resolved = (REGISTRY.parent / path).resolve()
    if family_root is None or not _is_within(resolved, family_root):
        print("[error] path 必须位于 root_dir 内", file=sys.stderr)
        return 1
    data["members"].append({
        "name": name,
        "path": path,
        "status": "planned",
        "version": None,
        "role": role,
        "description": description or f"{name}（{role}）",
        "depends_on": [],
    })
    data["updated_at"] = _now()
    _save_registry(data)
    print(f"[ok] 已登记 {name} (role={role}, status=planned)")
    return 0


def cmd_set_status(name: str, status: str) -> int:
    data = _load_registry()
    if status not in STATUSES:
        print(f"[error] status 必须是 {sorted(STATUSES)}", file=sys.stderr)
        return 1
    m = _find_member(data, name)
    if not m:
        print(f"[error] 成员不存在: {name}", file=sys.stderr)
        return 1
    if status == "active":
        duplicate = next((x for x in data["members"]
                          if x is not m and x.get("role") == m.get("role")
                          and x.get("status") == "active"), None)
        if duplicate:
            print(f"[error] role={m.get('role')} 已有 active 成员 {duplicate.get('name')}",
                  file=sys.stderr)
            return 1
        member_path = (REGISTRY.parent / m["path"]).resolve()
        version = _member_skill_version(member_path)
        if version is None:
            print(f"[error] 无法激活：{member_path}/SKILL.md 缺少 version", file=sys.stderr)
            return 1
        m["version"] = version
    m["status"] = status
    data["updated_at"] = _now()
    _save_registry(data)
    print(f"[ok] {name} → {status}")
    return 0


def cmd_route(request: str) -> int:
    data = _load_registry()
    best_role = None
    best_hits = 0
    for role, keywords in ROUTE_TABLE:
        hits = sum(1 for k in keywords if k in request)
        if hits > best_hits:
            best_hits = hits
            best_role = role
    if best_role is None or best_hits == 0:
        print(f"[suggest] 无法明确路由「{request}」，请澄清意图。")
        return 0
    member = ROLE_TO_MEMBER[best_role]
    reg = _find_member(data, member)
    if reg is None:
        print(f"[suggest] {request} → {member}（未登记）")
        return 0
    if reg["status"] == "active":
        print(f"[suggest] {request} → {member} (active)")
    elif reg["status"] == "planned":
        print(f"[suggest] {request} → {member}（planned，尚未创建）")
    else:
        print(f"[suggest] {request} → {member}（deprecated，已停用）")
    return 0


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(description="root-skills 家族管理器 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="查看家族全景")
    sub.add_parser("check", help="校验注册表一致性")

    p_reg = sub.add_parser("register", help="登记新成员")
    p_reg.add_argument("name")
    p_reg.add_argument("--path", required=True)
    p_reg.add_argument("--role", required=True)
    p_reg.add_argument("--description", default="")

    p_ss = sub.add_parser("set-status", help="切换成员状态")
    p_ss.add_argument("name")
    p_ss.add_argument("status", choices=sorted(STATUSES))

    p_rt = sub.add_parser("route", help="路由建议")
    p_rt.add_argument("request")

    args = parser.parse_args()

    if args.command == "status":
        sys.exit(cmd_status())
    elif args.command == "check":
        sys.exit(cmd_check())
    elif args.command == "register":
        sys.exit(cmd_register(args.name, args.path, args.role, args.description))
    elif args.command == "set-status":
        sys.exit(cmd_set_status(args.name, args.status))
    elif args.command == "route":
        sys.exit(cmd_route(args.request))


if __name__ == "__main__":
    main()
