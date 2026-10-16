#!/usr/bin/env python3
"""
Skill Doctor - 检测并修复 Skill 目录结构问题

用法:
    python skill-doctor.py /path/to/skill           # 单 Skill 检测+修复
    python skill-doctor.py /path/to/skill --check   # 仅检测
    python skill-doctor.py /path/to/skill --dry-run # 预览修复
    python skill-doctor.py /path/to/skills --batch  # 批量处理全部 Skill
    python skill-doctor.py /path/to/skill --rollback # 回滚到最近一次备份
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ASCII_KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
UNICODE_NAME = re.compile(r"^[^\W_]+(?:-[^\W_]+)*$", re.UNICODE)


def _has_unicode_letter(name: str) -> bool:
    return any(ord(c) > 127 and c.isalpha() for c in name)


def classify_skill_name(name: str) -> str:
    """Return 'ascii' | 'unicode' | 'invalid'. Unicode letters (incl. CJK) are valid."""
    if not name or name.startswith("-") or name.endswith("-") or "--" in name:
        return "invalid"
    if _has_unicode_letter(name):
        return "unicode" if UNICODE_NAME.fullmatch(name) else "invalid"
    return "ascii" if ASCII_KEBAB.fullmatch(name) else "invalid"


@dataclass
class Issue:
    """检测发现的问题"""
    code: str
    severity: str  # error, warning, info
    message: str
    auto_fixable: bool
    fix_action: Optional[str] = None
    path: Optional[str] = None


@dataclass
class FixResult:
    """修复结果"""
    success: bool
    action: str
    detail: str
    backup_path: Optional[str] = None


class SkillDoctor:
    """Skill 结构医生"""

    # 允许的根目录项
    ALLOWED_ROOT_ITEMS = {
        "SKILL.md", "README.md", ".skill-meta",
        "references", "examples", "scripts", "tests", "assets", "templates",
        "eval-reports", "registry", "evals", "validation",
    }

    # 特定文件名后缀优先于通用扩展名映射。
    SUFFIX_TO_DIR = {
        "-evaluation-report.yaml": "eval-reports",
        "-evaluation-report.yml": "eval-reports",
    }

    # 文件扩展名到目标目录的映射
    EXT_TO_DIR = {
        ".py": "scripts",
        ".sh": "scripts",
        ".js": "scripts",
        ".md": "references",
        ".yaml": "references",
        ".yml": "references",
        ".json": "references",
        ".txt": "references",
        ".csv": "references",
        ".png": "assets",
        ".jpg": "assets",
        ".jpeg": "assets",
        ".gif": "assets",
        ".svg": "assets",
    }

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.issues: List[Issue] = []
        self.fix_results: List[FixResult] = []
        self.backup_dir: Optional[Path] = None

    # ------------------------------------------------------------------
    # 扫描诊断
    # ------------------------------------------------------------------

    def scan(self, skill_path: Path) -> List[Issue]:
        """扫描单个 Skill，返回问题列表"""
        self.issues = []
        skill_path = Path(skill_path).resolve()

        if not skill_path.exists():
            self.issues.append(Issue("E001", "error", f"路径不存在: {skill_path}", False))
            return self.issues

        if not self._is_skill_directory(skill_path):
            self.issues.append(Issue("E002", "error", f"非 Skill 目录（缺少 SKILL.md）: {skill_path}", False))
            return self.issues

        # 1. 调用 validate-skill.py 获取基础问题
        self._run_validator(skill_path)

        # 2. Doctor 特有检测：根目录杂乱文件
        self._detect_clutter(skill_path)

        # 3. Doctor 特有检测：空目录缺少 .gitkeep
        self._detect_missing_gitkeep(skill_path)

        # 4. Doctor 特有检测：路径引用失效
        self._detect_broken_references(skill_path)

        # 5. D100 系列：frontmatter 规范检查（name/description/XML）
        self._detect_frontmatter_compliance(skill_path)

        # 6. D100 系列：正文长度检查
        self._detect_body_length(skill_path)

        # 7. D100 系列：脚本可执行权限
        self._detect_script_permissions(skill_path)

        # 8. D100 系列：危险命令与硬编码密钥
        self._detect_security(skill_path)

        # 9. D100 系列：references 长度 / assets 占位符 / evals / Constraints / last_updated
        self._detect_resource_compliance(skill_path)

        return self.issues

    def scan_batch(self, skills_dir: Path) -> Dict[str, List[Issue]]:
        """批量扫描目录下的全部 Skill"""
        skills_dir = Path(skills_dir).resolve()
        results = {}

        for item in sorted(skills_dir.iterdir()):
            if item.is_dir() and not item.name.startswith(".") and not item.name.endswith(".md"):
                if self._is_skill_directory(item):
                    results[item.name] = self.scan(item)

        return results

    def _is_skill_directory(self, path: Path) -> bool:
        return (path / "SKILL.md").exists()

    def _run_validator(self, skill_path: Path):
        """调用 validate-skill.py 获取问题"""
        # 家族内路径（root-skills-creator）
        validator_candidates = [
            Path(__file__).resolve().parents[2] / "root-skills-creator" / "scripts" / "validate-skill.py",
        ]
        validator_path = next((p for p in validator_candidates if p.exists()), None)
        if validator_path is None:
            self.issues.append(Issue(
                "V_UNAVAILABLE",
                "warning",
                f"validate-skill.py 不存在（已尝试: {[str(p) for p in validator_candidates]}）",
                False,
            ))
            return

        try:
            result = subprocess.run(
                [sys.executable, str(validator_path), str(skill_path), "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0 and not result.stdout:
                detail = result.stderr.strip() or f"exit code {result.returncode}"
                self.issues.append(Issue(
                    "V_RUN",
                    "warning",
                    f"validate-skill.py 执行失败: {detail}",
                    False,
                ))
                return

            data = json.loads(result.stdout)

            # 解析 errors
            for e in data.get("errors", []):
                self.issues.append(Issue(
                    code="V_ERR",
                    severity="error",
                    message=f"[{e['location']}] {e['message']}",
                    auto_fixable=False,
                ))

            # 解析 warnings → 映射到 doctor 问题码
            for w in data.get("warnings", []):
                msg = w["message"]
                loc = w["location"]

                if "README.md" in msg:
                    self.issues.append(Issue("D001", "warning", "缺少 README.md", True, "generate_readme"))
                elif ".skill-meta" in msg:
                    self.issues.append(Issue("D003", "warning", "缺少 .skill-meta/manifest.yaml", True, "generate_manifest"))
                elif "Missing recommended directory for complex skill: references" in msg:
                    self.issues.append(Issue("D004", "warning", "complex Skill 缺少 references/", True, "create_references"))
                elif "Empty directory" in msg:
                    # 消息格式: 'Empty directory: references/. Consider adding .gitkeep if intentional.'
                    dir_name = msg.split(":", 1)[1].split(".")[0].strip().rstrip("/")
                    if not dir_name:
                        dir_name = msg.split(":", 1)[1].strip().split()[0].rstrip("/.")
                    # 去重：_detect_missing_gitkeep 已对标准目录做检测，validator 消息只在目录非标准时记录
                    if dir_name in ("references", "examples", "scripts", "tests", "assets", "eval-reports"):
                        pass
                    else:
                        self.issues.append(Issue("D007", "info", f"空目录缺少 .gitkeep: {dir_name}", True, "add_gitkeep", path=dir_name))
                elif "Unknown directory" in msg:
                    pass  # 将在 _detect_clutter 中处理
                elif msg.startswith(".gitkeep:"):
                    pass  # .gitkeep 是占位文件，不需要 shebang 或可执行权限
                else:
                    self.issues.append(Issue("V_WARN", "warning", f"[{loc}] {msg}", False))

        except subprocess.TimeoutExpired:
            self.issues.append(Issue(
                "V_TIMEOUT",
                "warning",
                "validate-skill.py 执行超时",
                False,
            ))
        except json.JSONDecodeError as exc:
            self.issues.append(Issue(
                "V_JSON",
                "warning",
                f"validate-skill.py 输出不是合法 JSON: {exc}",
                False,
            ))
        except OSError as exc:
            self.issues.append(Issue(
                "V_RUN",
                "warning",
                f"validate-skill.py 无法执行: {exc}",
                False,
            ))

    def _detect_clutter(self, skill_path: Path):
        """检测根目录中的杂乱文件"""
        clutter = []
        for item in skill_path.iterdir():
            if item.name in self.ALLOWED_ROOT_ITEMS:
                continue
            if item.name.startswith("."):
                continue
            clutter.append(item)

        if clutter:
            names = ", ".join(c.name for c in clutter)
            self.issues.append(Issue(
                "D005", "warning",
                f"根目录存在杂乱文件: {names}",
                True, "migrate_clutter",
            ))

    def _detect_missing_gitkeep(self, skill_path: Path):
        """检测空目录是否缺少 .gitkeep"""
        for dir_name in [
            "references", "examples", "scripts", "tests", "assets", "eval-reports",
        ]:
            dir_path = skill_path / dir_name
            if dir_path.exists() and not any(dir_path.iterdir()):
                gitkeep = dir_path / ".gitkeep"
                if not gitkeep.exists():
                    self.issues.append(Issue(
                        "D007", "info",
                        f"空目录缺少 .gitkeep: {dir_name}/",
                        True, "add_gitkeep", path=dir_name,
                    ))

    def _detect_broken_references(self, skill_path: Path):
        """检测 SKILL.md 中的失效路径引用"""
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            return

        content = skill_md.read_text(encoding="utf-8")
        content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)

        # 匹配引用路径
        patterns = [
            r'`([^`]+/(?:references|scripts|examples|assets|eval-reports)/[^`]+)`',
            r'\(([^)]+/(?:references|scripts|examples|assets|eval-reports)/[^)]+)\)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content):
                ref_path = match.group(1)
                if not self._reference_exists(skill_path, ref_path):
                    self.issues.append(Issue(
                        "D006", "warning",
                        f"路径引用失效: {ref_path}",
                        True, "fix_reference", path=ref_path,
                    ))

    def _reference_exists(self, skill_path: Path, ref_path: str) -> bool:
        """支持 skill 内相对路径和仓库根路径两类引用。"""
        ref = Path(ref_path)
        if ref_path.startswith(("skills/", "layout/", "docs/", "archive/")):
            repo_root = Path(__file__).resolve().parents[3]
            return (repo_root / ref).exists()
        return (skill_path / ref).exists()

    # ------------------------------------------------------------------
    # D100 系列：frontmatter 规范 / 正文长度 / 脚本权限 / 安全 / 资源合规
    # 基于企业 AI Agent Skill 创建评测研究报告（5.2/4.3/5.6/6.1）
    # ------------------------------------------------------------------

    # 危险命令模式（D108）
    DANGEROUS_COMMANDS = [
        r"\brm\s+-rf\b", r"\brm\s+-fr\b", r"\brm\s+-r\s+/\b",
        r"\bdel\s+/[fsq]\b", r"\bformat\s+[a-zA-Z]:", r"\bshutdown\b",
        r"\bchmod\s+-R\s+777\b", r"\bdd\s+if=.*of=/dev/", r"\bmkfs\b",
    ]

    # 危险命令匹配时向前看的否定语境（说明性文案，如「无 rm -rf」「禁止 rm -rf」，
    # 出现在字符串/注释/文档中的安全说明不应判为危险命令）
    DANGEROUS_NEGATION = r"(无|不|禁止|避免|请勿|不要|不得|never|not|no|don'?t)\s*(?:执行|使用|运行|调用)?\s*$"

    def _find_dangerous_command(self, content: str, pattern: str):
        """在 content 中查找危险命令 pattern，但跳过否定语境的说明性引用。

        例如「脚本无 rm -rf」「禁止执行 rm -rf」「not rm -rf」这类说明
        不应触发 D108；真正的命令执行（subprocess/os.system/shell 调用等）
        前一般不含否定词，仍会被命中。
        """
        for m in re.finditer(pattern, content):
            # 检查匹配点之前的否定语境（最多看 12 个字符）
            before = content[max(0, m.start() - 12):m.start()]
            if re.search(self.DANGEROUS_NEGATION, before):
                continue
            return True
        return False

    # 密钥/凭据模式（D109）
    SECRET_PATTERNS = [
        r"api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}",
        r"secret\s*[:=]\s*['\"][A-Za-z0-9_\-]{12,}",
        r"password\s*[:=]\s*['\"][^'\"]{8,}",
        r"token\s*[:=]\s*['\"][A-Za-z0-9_\-\.]{20,}",
        r"sk-[A-Za-z0-9]{20,}",
        r"AKIA[A-Z0-9]{16}",
    ]

    def _parse_frontmatter(self, skill_path: Path):
        """解析 SKILL.md frontmatter，返回 (frontmatter_text, frontmatter_dict, body_text)。

        frontmatter_dict 优先用 PyYAML 解析（支持 | 块状 description），失败则回退简单解析。
        """
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            return None, {}, ""
        content = skill_md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None, {}, content
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None, {}, content
        fm_text = parts[1].strip()
        body = parts[2].strip()

        fm_dict = {}
        # 优先 PyYAML
        try:
            import yaml
            parsed = yaml.safe_load(fm_text)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    fm_dict[str(k)] = v if v is not None else ""
        except Exception:
            # 回退：简单 key: value 解析
            for line in fm_text.split("\n"):
                if ":" in line and not line.startswith(" "):
                    key, _, val = line.partition(":")
                    fm_dict[key.strip()] = val.strip().strip('"\'')

        # description 统一为字符串
        if "description" in fm_dict and not isinstance(fm_dict["description"], str):
            fm_dict["description"] = str(fm_dict["description"])
        return fm_text, fm_dict, body

    def _detect_frontmatter_compliance(self, skill_path: Path):
        """D101-D105: name 一致性/格式、description 长度与触发条件、XML 尖括号。"""
        fm_text, fm_dict, _ = self._parse_frontmatter(skill_path)
        if fm_text is None:
            return

        name = fm_dict.get("name", "")
        dir_name = skill_path.name

        # D101: name 与目录名不一致
        if name and name != dir_name:
            self.issues.append(Issue(
                "D101", "error",
                f"name '{name}' 与目录名 '{dir_name}' 不一致",
                False,
            ))

        # D102: ASCII 须 kebab-case；中文/Unicode 字母合法（kebab-case 记 na，禁止改回英文）
        if name:
            problems = []
            if len(name) > 64:
                problems.append(f"超64字符({len(name)})")
            kind = classify_skill_name(name)
            if kind == "invalid":
                if _has_unicode_letter(name):
                    problems.append("中文/Unicode name 含非法字符")
                else:
                    if not ASCII_KEBAB.fullmatch(name):
                        problems.append("含大写/下划线/空格或连字符使用不当")
                    if name.startswith("-") or name.endswith("-"):
                        problems.append("首尾连字符")
                    if "--" in name:
                        problems.append("连续连字符")
            if problems:
                self.issues.append(Issue(
                    "D102", "error",
                    f"name '{name}' 不符合格式: {'; '.join(problems)}",
                    False,
                ))

        # D103: description 超长
        desc = fm_dict.get("description", "")
        if len(desc) > 1024:
            self.issues.append(Issue(
                "D103", "warning",
                f"description 超长（{len(desc)}/1024 字符）",
                False,
            ))

        # D104: description 缺少触发条件（做什么 + 何时用）
        if desc:
            has_trigger = any(k in desc for k in ["当", "when", "use", "使用", "触发", "适用", "if", "whenever"])
            has_action = any(k in desc for k in ["创建", "生成", "处理", "检测", "修复", "转换", "提取", "优化", "评估", "管理", "create", "build", "handle", "process", "fix", "detect", "optimize"])
            if not has_trigger:
                self.issues.append(Issue(
                    "D104", "warning",
                    "description 缺少触发条件（何时使用）",
                    False,
                ))
            elif not has_action:
                self.issues.append(Issue(
                    "D104", "warning",
                    "description 缺少功能动词（做什么）",
                    False,
                ))

        # D105: frontmatter 含 XML 尖括号
        if "<" in fm_text or ">" in fm_text:
            self.issues.append(Issue(
                "D105", "error",
                "frontmatter 含 XML 尖括号 < >（违反 Agent Skills 规范）",
                False,
            ))

    def _detect_body_length(self, skill_path: Path):
        """D106: SKILL.md 正文超长（>500 行 或 >5000 tokens 估算）。"""
        _, _, body = self._parse_frontmatter(skill_path)
        if not body:
            return
        line_count = body.count("\n") + 1
        token_est = len(body) // 4  # 中英文混合粗略估算
        if line_count > 500 or token_est > 5000:
            self.issues.append(Issue(
                "D106", "warning",
                f"SKILL.md 正文超长（{line_count} 行 / 约 {token_est} tokens；建议 <500 行 <5000 tokens）",
                False,
            ))

    def _detect_script_permissions(self, skill_path: Path):
        """D107: scripts/ 存在无执行权限的脚本。"""
        scripts_dir = skill_path / "scripts"
        if not scripts_dir.exists():
            return
        for f in scripts_dir.iterdir():
            if f.is_file() and f.suffix in (".py", ".sh", ".js") and not f.name.startswith("."):
                if not (f.stat().st_mode & 0o111):
                    self.issues.append(Issue(
                        "D107", "warning",
                        f"脚本无执行权限: {f.name}",
                        True, "chmod_script", path=f.name,
                    ))

    def _detect_security(self, skill_path: Path):
        """D108-D109 / D115: 危险命令、硬编码密钥、单包 skills._shared。"""
        # 扫描 scripts/ 全部文件
        scripts_dir = skill_path / "scripts"
        if scripts_dir.exists():
            for f in scripts_dir.rglob("*"):
                if f.is_file() and f.suffix in (".py", ".sh", ".js", ".bash"):
                    try:
                        content = f.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    for pattern in self.DANGEROUS_COMMANDS:
                        if self._find_dangerous_command(content, pattern):
                            self.issues.append(Issue(
                                "D108", "error",
                                f"脚本含危险命令 {pattern}: {f.name}",
                                False,
                            ))
                            break
                    for pattern in self.SECRET_PATTERNS:
                        if re.search(pattern, content):
                            self.issues.append(Issue(
                                "D109", "error",
                                f"脚本疑似硬编码密钥 {pattern[:20]}: {f.name}",
                                False,
                            ))
                            break
                    if re.search(r"from\s+skills\._shared|import\s+skills\._shared", content):
                        self.issues.append(Issue(
                            "D115", "warning",
                            f"脚本依赖 skills._shared（单包目录下通常不存在）: {f.name}。不阻断；不要为修它改 name。",
                            False,
                        ))

        # 扫描 SKILL.md
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            content = skill_md.read_text(encoding="utf-8", errors="ignore")
            for pattern in self.SECRET_PATTERNS:
                if re.search(pattern, content):
                    self.issues.append(Issue(
                        "D109", "error",
                        f"SKILL.md 疑似硬编码密钥 {pattern[:20]}",
                        False,
                    ))
                    break

    def _detect_resource_compliance(self, skill_path: Path):
        """D110-D114: references 长度 / assets 占位符 / evals / Constraints / last_updated。"""
        # D110: references/ 单文件超长（>3000 tokens 估算）
        refs_dir = skill_path / "references"
        if refs_dir.exists():
            for f in refs_dir.iterdir():
                if f.is_file() and f.suffix == ".md":
                    token_est = f.stat().st_size // 4
                    if token_est > 3000:
                        self.issues.append(Issue(
                            "D110", "warning",
                            f"references/{f.name} 过长（约 {token_est} tokens；建议 <3000）",
                            False,
                        ))

        # D111: assets/ 模板缺 {{placeholder}} 占位符
        assets_dir = skill_path / "assets"
        if assets_dir.exists():
            for f in assets_dir.rglob("*"):
                if f.is_file() and f.suffix in (".md", ".txt", ".html", ".yaml", ".json", ".csv"):
                    try:
                        content = f.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    if content.strip() and "{{" not in content and "{%" not in content and "${" not in content:
                        self.issues.append(Issue(
                            "D111", "info",
                            f"assets/{f.relative_to(assets_dir)} 模板无占位符标记（建议用 {{{{var}}}}）",
                            False,
                        ))

        # D112: 缺少 evals/ 目录或 evals.json
        evals_dir = skill_path / "evals"
        has_evals = evals_dir.exists() and any(evals_dir.rglob("evals.json"))
        if not has_evals:
            self.issues.append(Issue(
                "D112", "info",
                "缺少 evals/ 目录或 evals.json（建议用 root-skills-creator 补评测）",
                False,
            ))

        # D113: 缺少 Constraints（NEVER/ALWAYS/IF…THEN）
        _, _, body = self._parse_frontmatter(skill_path)
        if body and not any(k in body for k in ["NEVER", "ALWAYS", "IF…THEN", "IF...THEN", "ONLY", "MAX", "MIN", "禁止", "不要", "不得"]):
            self.issues.append(Issue(
                "D113", "info",
                "正文缺少 Constraints（建议含 NEVER/ALWAYS/IF…THEN 等确定性约束）",
                False,
            ))

        # D114: 缺 last_updated / 版本字段
        _, fm_dict, _ = self._parse_frontmatter(skill_path)
        if fm_dict and "last_updated" not in fm_dict and "version" not in fm_dict:
            self.issues.append(Issue(
                "D114", "info",
                "frontmatter 缺 last_updated / version 字段",
                True, "generate_last_updated",
            ))

    # ------------------------------------------------------------------
    # 修复执行
    # ------------------------------------------------------------------

    def fix(self, skill_path: Path) -> List[FixResult]:
        """执行自动修复"""
        self.fix_results = []
        skill_path = Path(skill_path).resolve()

        if not self._is_skill_directory(skill_path):
            self.fix_results.append(FixResult(False, "skip", "非 Skill 目录"))
            return self.fix_results

        # 创建备份
        if not self.dry_run:
            self._create_backup(skill_path)

        for issue in self.issues:
            if not issue.auto_fixable:
                continue

            result = self._apply_fix(skill_path, issue)
            self.fix_results.append(result)

        return self.fix_results

    def _apply_fix(self, skill_path: Path, issue: Issue) -> FixResult:
        """应用单个修复"""
        action = issue.fix_action

        if action == "generate_readme":
            return self._fix_generate_readme(skill_path)
        elif action == "generate_manifest":
            return self._fix_generate_manifest(skill_path)
        elif action == "create_references":
            return self._fix_create_dir(skill_path, "references")
        elif action == "migrate_clutter":
            return self._fix_migrate_clutter(skill_path)
        elif action == "fix_reference":
            return self._fix_reference(skill_path, issue.path or "")
        elif action == "add_gitkeep":
            return self._fix_add_gitkeep(skill_path, issue.path or "")
        elif action == "chmod_script":
            return self._fix_chmod_script(skill_path, issue.path or "")
        elif action == "generate_last_updated":
            return self._fix_generate_last_updated(skill_path)

        return FixResult(False, "unknown", f"未知修复动作: {action}")

    def _fix_chmod_script(self, skill_path: Path, file_name: str) -> FixResult:
        """D107: 为无执行权限的脚本添加执行权限。"""
        script_path = skill_path / "scripts" / file_name
        if not script_path.exists():
            return FixResult(False, "chmod_script", f"脚本不存在: {file_name}")
        if self.dry_run:
            return FixResult(True, "chmod_script", f"[DRY-RUN] 将要 chmod +x scripts/{file_name}", None)
        script_path.chmod(script_path.stat().st_mode | 0o111)
        return FixResult(True, "chmod_script", f"chmod +x scripts/{file_name}", str(self.backup_dir))

    def _fix_generate_last_updated(self, skill_path: Path) -> FixResult:
        """D114: 为 frontmatter 补充 last_updated 字段。"""
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            return FixResult(False, "generate_last_updated", "SKILL.md 不存在")
        content = skill_md.read_text(encoding="utf-8")
        today = datetime.now().strftime("%Y-%m-%d")
        if self.dry_run:
            return FixResult(True, "generate_last_updated", f"[DRY-RUN] 将要写入 last_updated: {today}", None)
        # 在 frontmatter 末尾（第一个 --- 结束前）插入 last_updated
        if content.startswith("---"):
            second = content.find("---", 3)
            if second > 0:
                fm_end = content.rfind("\n", 3, second)
                insert_at = fm_end + 1 if fm_end > 0 else second
                content = content[:insert_at] + f'last_updated: "{today}"\n' + content[insert_at:]
                skill_md.write_text(content, encoding="utf-8")
                return FixResult(True, "generate_last_updated", f"写入 last_updated: {today}", str(self.backup_dir))
        return FixResult(False, "generate_last_updated", "无法定位 frontmatter")

    def _fix_generate_readme(self, skill_path: Path) -> FixResult:
        """生成 README.md 模板"""
        readme_path = skill_path / "README.md"

        # 从 SKILL.md 提取基本信息
        skill_md = skill_path / "SKILL.md"
        name = skill_path.name
        description = ""
        if skill_md.exists():
            content = skill_md.read_text(encoding="utf-8")
            # 简单提取第一行非空文本作为描述
            for line in content.split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    description = line[:100]
                    break

        template = f"""# {name}

{description}

## 快速开始

```
/{name}
```

## 参考资源

- `references/` — 详细文档
- `examples/` — 使用示例
"""

        if self.dry_run:
            return FixResult(True, "generate_readme", f"[DRY-RUN] 将要生成 README.md", None)

        readme_path.write_text(template, encoding="utf-8")
        return FixResult(True, "generate_readme", f"生成 README.md", str(self.backup_dir))

    def _fix_generate_manifest(self, skill_path: Path) -> FixResult:
        """生成 manifest.yaml"""
        meta_dir = skill_path / ".skill-meta"
        manifest_path = meta_dir / "manifest.yaml"

        # 从 SKILL.md frontmatter 提取信息
        name = skill_path.name
        version = '"1.0.0"'
        complexity = "standard"

        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            content = skill_md.read_text(encoding="utf-8")
            if content.startswith("---"):
                fm_end = content.find("---", 3)
                if fm_end > 0:
                    fm = content[3:fm_end].strip()
                    for line in fm.split("\n"):
                        if line.startswith("name:"):
                            name = line.split(":", 1)[1].strip()
                        elif line.startswith("version:"):
                            version = line.split(":", 1)[1].strip()
                        elif line.startswith("complexity:"):
                            complexity = line.split(":", 1)[1].strip().strip('"')

        template = f"""name: {name}
description: |
  {{从 SKILL.md 提取 description}}
version: {version}
complexity: {complexity}
compatibility:
  claude: {{ status: native }}
  kimi: {{ status: native }}
  cursor: {{ status: native }}
  gpt: {{ status: bridge }}
  minimax: {{ status: bridge }}
  dsh: {{ status: native }}
  codex: {{ status: native }}
"""

        if self.dry_run:
            return FixResult(True, "generate_manifest", f"[DRY-RUN] 将要生成 .skill-meta/manifest.yaml", None)

        meta_dir.mkdir(exist_ok=True)
        manifest_path.write_text(template, encoding="utf-8")
        return FixResult(True, "generate_manifest", f"生成 .skill-meta/manifest.yaml", str(self.backup_dir))

    def _fix_create_dir(self, skill_path: Path, dir_name: str) -> FixResult:
        """创建目录"""
        dir_path = skill_path / dir_name
        if self.dry_run:
            return FixResult(True, "create_dir", f"[DRY-RUN] 将要创建 {dir_name}/", None)

        dir_path.mkdir(exist_ok=True)
        return FixResult(True, "create_dir", f"创建 {dir_name}/", str(self.backup_dir))

    def _fix_migrate_clutter(self, skill_path: Path) -> FixResult:
        """迁移根目录杂乱文件"""
        moves = []
        for item in skill_path.iterdir():
            if item.name in self.ALLOWED_ROOT_ITEMS:
                continue
            if item.name.startswith("."):
                continue

            target_dir_name = self._target_dir_for_file(item)
            target_dir = skill_path / target_dir_name

            if self.dry_run:
                moves.append(f"{item.name} -> {target_dir_name}/")
                continue

            target_dir.mkdir(exist_ok=True)
            shutil.move(str(item), str(target_dir / item.name))
            moves.append(f"{item.name} -> {target_dir_name}/")

        if self.dry_run:
            return FixResult(True, "migrate_clutter", f"[DRY-RUN] 将要迁移: {', '.join(moves)}", None)

        # 更新路径引用
        self._update_path_references(skill_path, moves)

        return FixResult(True, "migrate_clutter", f"迁移 {len(moves)} 个文件", str(self.backup_dir))

    def _target_dir_for_file(self, item: Path) -> str:
        """根据文件名语义优先分类，再回退到扩展名。"""
        name = item.name.lower()
        for suffix, dir_name in self.SUFFIX_TO_DIR.items():
            if name.endswith(suffix):
                return dir_name
        return self.EXT_TO_DIR.get(item.suffix.lower(), "references")

    def _fix_reference(self, skill_path: Path, ref_path: str) -> FixResult:
        """修复失效路径引用"""
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            return FixResult(False, "fix_reference", "SKILL.md 不存在")

        content = skill_md.read_text(encoding="utf-8")
        # 尝试找到正确的路径（在允许的目录中搜索同名文件）
        file_name = Path(ref_path).name
        for dir_name in ["references", "scripts", "examples", "assets", "eval-reports"]:
            candidate = skill_path / dir_name / file_name
            if candidate.exists():
                new_path = f"{dir_name}/{file_name}"
                if self.dry_run:
                    return FixResult(True, "fix_reference", f"[DRY-RUN] 将要更新引用: {ref_path} -> {new_path}", None)

                content = content.replace(ref_path, new_path)
                skill_md.write_text(content, encoding="utf-8")
                return FixResult(True, "fix_reference", f"更新引用: {ref_path} -> {new_path}", str(self.backup_dir))

        return FixResult(False, "fix_reference", f"找不到 {file_name} 的替代路径")

    def _fix_add_gitkeep(self, skill_path: Path, dir_name: str) -> FixResult:
        """添加 .gitkeep"""
        dir_path = skill_path / dir_name
        gitkeep = dir_path / ".gitkeep"

        if self.dry_run:
            return FixResult(True, "add_gitkeep", f"[DRY-RUN] 将要创建 {dir_name}/.gitkeep", None)

        gitkeep.write_text("", encoding="utf-8")
        return FixResult(True, "add_gitkeep", f"创建 {dir_name}/.gitkeep", str(self.backup_dir))

    def _update_path_references(self, skill_path: Path, moves: List[str]):
        """更新 SKILL.md 和 README.md 中的路径引用"""
        for md_file in ["SKILL.md", "README.md"]:
            md_path = skill_path / md_file
            if not md_path.exists():
                continue

            content = md_path.read_text(encoding="utf-8")
            original = content

            for move in moves:
                # 解析 "filename -> dir/"
                if " -> " in move:
                    file_name = move.split(" -> ")[0].strip()
                    dir_name = move.split(" -> ")[1].strip().rstrip("/")
                    # 替换根目录引用为子目录引用
                    content = content.replace(f"`{file_name}`", f"`{dir_name}/{file_name}`")
                    content = content.replace(f"]({file_name})", f"]({dir_name}/{file_name})")

            if content != original:
                md_path.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # 备份与回滚
    # ------------------------------------------------------------------

    def _create_backup(self, skill_path: Path) -> Path:
        """创建备份"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = skill_path / ".doctor-backup" / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = backup_dir

        # 备份所有将要修改的文件
        for item in skill_path.iterdir():
            if item.name.startswith(".") and item.name != ".skill-meta":
                continue
            if item.is_file():
                shutil.copy2(str(item), str(backup_dir / item.name))

        # 备份 .skill-meta/
        meta_dir = skill_path / ".skill-meta"
        if meta_dir.exists():
            backup_meta = backup_dir / ".skill-meta"
            backup_meta.mkdir(exist_ok=True)
            for f in meta_dir.iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(backup_meta / f.name))

        # 记录操作日志
        log_path = backup_dir / "operation.log"
        log_path.write_text(f"备份时间: {timestamp}\n", encoding="utf-8")

        return backup_dir

    def rollback(self, skill_path: Path) -> List[FixResult]:
        """回滚到最近一次备份"""
        skill_path = Path(skill_path).resolve()
        backup_root = skill_path / ".doctor-backup"

        if not backup_root.exists():
            return [FixResult(False, "rollback", "无备份可回滚")]

        # 找最新的备份
        backups = sorted(backup_root.iterdir(), key=lambda p: p.name, reverse=True)
        if not backups:
            return [FixResult(False, "rollback", "无备份可回滚")]

        latest = backups[0]
        results = []

        # 恢复文件
        for item in latest.iterdir():
            if item.name == "operation.log":
                continue
            target = skill_path / item.name
            if item.is_file():
                shutil.copy2(str(item), str(target))
                results.append(FixResult(True, "rollback", f"恢复 {item.name}"))
            elif item.is_dir():
                if target.exists():
                    shutil.rmtree(str(target))
                shutil.copytree(str(item), str(target))
                results.append(FixResult(True, "rollback", f"恢复 {item.name}/"))

        return results

    # ------------------------------------------------------------------
    # 报告生成
    # ------------------------------------------------------------------

    def generate_report(self, skill_path: Path) -> str:
        """生成检测报告"""
        lines = [f"# Skill Doctor 报告: {skill_path.name}", ""]

        errors = [i for i in self.issues if i.severity == "error"]
        warnings = [i for i in self.issues if i.severity == "warning"]
        infos = [i for i in self.issues if i.severity == "info"]

        lines.append(f"**检测时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**问题统计**: ❌ {len(errors)}  error | ⚠️  {len(warnings)} warning | ℹ️  {len(infos)} info")
        lines.append("")

        if errors:
            lines.append("## Errors")
            for e in errors:
                lines.append(f"- ❌ [{e.code}] {e.message}")
            lines.append("")

        if warnings:
            lines.append("## Warnings")
            for w in warnings:
                fix_tag = "(可自动修复)" if w.auto_fixable else "(需手动处理)"
                lines.append(f"- ⚠️  [{w.code}] {w.message} {fix_tag}")
            lines.append("")

        if infos:
            lines.append("## Info")
            for i in infos:
                fix_tag = "(可自动修复)" if i.auto_fixable else ""
                lines.append(f"- ℹ️  [{i.code}] {i.message} {fix_tag}")
            lines.append("")

        if self.fix_results:
            lines.append("## 修复结果")
            for r in self.fix_results:
                icon = "✅" if r.success else "❌"
                lines.append(f"- {icon} {r.action}: {r.detail}")
            lines.append("")

        auto_fixable = [i for i in self.issues if i.auto_fixable]
        if auto_fixable:
            lines.append(f"**可自动修复**: {len(auto_fixable)} 项")
            lines.append("")
            if not self.dry_run and not any(r.action != "skip" for r in self.fix_results):
                lines.append("运行 `skill-doctor.py --fix` 执行自动修复。")
        else:
            lines.append("**无自动修复项。**")

        return "\n".join(lines)

    def generate_batch_report(self, results: Dict[str, List[Issue]]) -> str:
        """生成批量检测报告"""
        today = datetime.now().strftime("%Y-%m-%d")
        lines = [
            "---",
            "title: Skill Doctor 批量检测报告",
            "doc_type: analysis",
            "module: root-skills-doctor",
            "topic: batch-structure-health",
            "status: stable",
            f"created: {today}",
            f"updated: {today}",
            "owner: self",
            "source: ai",
            "---",
            "",
            "# Skill Doctor 批量检测报告",
            "",
        ]

        total = len(results)
        total_errors = sum(len([i for i in issues if i.severity == "error"]) for issues in results.values())
        total_warnings = sum(len([i for i in issues if i.severity == "warning"]) for issues in results.values())
        total_infos = sum(len([i for i in issues if i.severity == "info"]) for issues in results.values())
        total_auto_fixable = sum(len([i for i in issues if i.auto_fixable]) for issues in results.values())
        auto_fixable_warnings = sum(
            len([i for i in issues if i.severity == "warning" and i.auto_fixable])
            for issues in results.values()
        )
        auto_fixable_infos = sum(
            len([i for i in issues if i.severity == "info" and i.auto_fixable])
            for issues in results.values()
        )

        lines.append(f"**扫描 Skill 总数**: {total}")
        lines.append(f"**问题汇总**: ❌ {total_errors} error | ⚠️  {total_warnings} warning | ℹ️  {total_infos} info")
        lines.append(f"**可自动修复**: {total_auto_fixable} 项（warning {auto_fixable_warnings} / info {auto_fixable_infos}）")
        lines.append("")

        issue_counter = Counter(
            (issue.code, issue.severity, issue.auto_fixable)
            for issues in results.values()
            for issue in issues
        )
        if issue_counter:
            lines.append("## 问题类型分布")
            lines.append("")
            lines.append("| Code | Severity | Count | Auto-fixable |")
            lines.append("|------|----------|------:|--------------|")
            for (code, severity, auto_fixable), count in sorted(issue_counter.items(), key=lambda item: (-item[1], item[0])):
                lines.append(f"| {code} | {severity} | {count} | {'yes' if auto_fixable else 'no'} |")
            lines.append("")

        # 按问题数量排序
        sorted_results = sorted(results.items(), key=lambda x: len(x[1]), reverse=True)

        lines.append("| Skill | Errors | Warnings | Info | 可自动修复 |")
        lines.append("|-------|--------|----------|------|-----------|")
        for name, issues in sorted_results:
            e = len([i for i in issues if i.severity == "error"])
            w = len([i for i in issues if i.severity == "warning"])
            info = len([i for i in issues if i.severity == "info"])
            a = len([i for i in issues if i.auto_fixable])
            lines.append(f"| {name} | {e} | {w} | {info} | {a} |")

        lines.append("")
        lines.append("**建议**: 优先修复 error 和可自动修复的 warning。")

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Skill Doctor - 检测并修复 Skill 目录结构")
    parser.add_argument("path", type=Path, help="Skill 目录或 skills 父目录")
    parser.add_argument("--batch", action="store_true", help="批量处理目录下的全部 Skill")
    parser.add_argument("--check", action="store_true", help="仅检测，不修复")
    parser.add_argument("--dry-run", action="store_true", help="预览修复操作，不实际修改")
    parser.add_argument("--rollback", action="store_true", help="回滚到最近一次备份")
    parser.add_argument("--fix", action="store_true", help="执行自动修复（默认行为）")

    args = parser.parse_args()
    target = Path(args.path).resolve()

    doctor = SkillDoctor(dry_run=args.dry_run)

    # 回滚模式
    if args.rollback:
        if args.batch:
            print("批量回滚暂不支持，请逐个 Skill 回滚。")
            sys.exit(1)
        results = doctor.rollback(target)
        for r in results:
            icon = "✅" if r.success else "❌"
            print(f"{icon} {r.action}: {r.detail}")
        sys.exit(0)

    # 批量模式
    if args.batch:
        if not target.is_dir():
            print(f"❌ 批量模式需要目录路径: {target}")
            sys.exit(1)

        results = doctor.scan_batch(target)
        report = doctor.generate_batch_report(results)
        print(report)

        # 保存报告
        report_path = target.parent / "docs" / "skill-doctor-batch-report-current.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        print(f"\n💾 报告已保存: {report_path}")
        sys.exit(0)

    # 单 Skill 模式
    if not target.exists():
        print(f"❌ 路径不存在: {target}")
        sys.exit(1)

    issues = doctor.scan(target)

    if args.check:
        report = doctor.generate_report(target)
        print(report)
        sys.exit(0)

    # 检测 + 修复
    if not args.dry_run:
        print(f"🔍 扫描 {target.name}...")
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        infos = [i for i in issues if i.severity == "info"]
        print(f"  发现: ❌ {len(errors)} error | ⚠️  {len(warnings)} warning | ℹ️  {len(infos)} info")

        auto_fixable = [i for i in issues if i.auto_fixable]
        if auto_fixable:
            print(f"\n🔧 执行 {len(auto_fixable)} 项自动修复...")

    doctor.fix(target)
    report = doctor.generate_report(target)
    print(report)

    # 保存报告
    report_path = target / f".doctor-backup/doctor-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
