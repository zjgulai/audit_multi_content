#!/usr/bin/env python3
"""
Universal Skill Validator

验证 Skill 是否符合 Universal Skill Schema 规范。
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional

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


class ValidationError:
    """Validation error with location and message"""
    def __init__(self, location: str, message: str, severity: str = "error"):
        self.location = location
        self.message = message
        self.severity = severity  # error, warning, info
    
    def __str__(self):
        prefix = {
            "error": "❌ ERROR",
            "warning": "⚠️  WARNING",
            "info": "ℹ️  INFO"
        }.get(self.severity, "UNKNOWN")
        return f"{prefix} [{self.location}]: {self.message}"


class SkillValidator:
    """Validator for Universal Skills"""
    
    # 保留名称（不能用于 Skill 名称）
    RESERVED_NAMES = {
        'claude', 'anthropic', 'kimi', 'moonshot', 
        'gpt', 'openai', 'minimax', 'dsh', 'codex'
    }
    
    # 建议的目录结构（registry 为家族管理器类 skill 的注册表/清单数据目录）
    ALLOWED_DIRS = {'scripts', 'references', 'assets', 'examples', 'tests', 'templates', 'eval-reports', 'registry'}
    ORDERED_ALLOWED_DIRS = tuple(sorted(ALLOWED_DIRS))

    # 必需目录（根据 Universal Skill Schema - 仅 SKILL.md 是必需的）
    REQUIRED_DIRS = set()  # 所有目录现在都是可选的

    # 推荐目录（complex 级别推荐有 references/）
    RECOMMENDED_DIRS = {'references'}  # complex 级别推荐
    ORDERED_RECOMMENDED_DIRS = tuple(sorted(RECOMMENDED_DIRS))

    # 必需文件
    REQUIRED_FILES = {'SKILL.md'}

    # 推荐文件
    RECOMMENDED_FILES = {'README.md'}

    # 元数据目录
    META_DIR = '.skill-meta'
    LOCAL_FILE_EXTENSIONS = r"(?:md|py|sh|js|json|yaml|yml|txt|csv|png|jpg|jpeg|gif|svg)"
    REFERENCE_RE = re.compile(
        rf'`(?P<backtick>[^`]+\.{LOCAL_FILE_EXTENSIONS})`|'
        rf'\[(?P<bracket>[^\]]+\.{LOCAL_FILE_EXTENSIONS})\]|'
        rf'(?<![\w./-])(?P<local>(?:references|scripts|examples|assets)/[\w\-./]+\.{LOCAL_FILE_EXTENSIONS})',
        re.IGNORECASE,
    )
    
    def __init__(self, skill_path: Path):
        self.skill_path = Path(skill_path)
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
        self.infos: List[ValidationError] = []
        self.score: int = 0
        # 结构层未通过时，后续 4 组检查会被整段跳过（见 validate()）。
        # 必须记下这件事：否则错误数只反映「已跑的那 1 组」，
        # 严重性被低估——实测一个只有 agent.yaml 的包（无 SKILL.md）
        # 拿 90 分「Excellent」，方向是反的。
        self.aborted_early: bool = False

        self.frontmatter: Dict = {}
        self.body: str = ""
        self.referenced_files: set = set()
    
    def add_error(self, location: str, message: str):
        self.errors.append(ValidationError(location, message, "error"))
    
    def add_warning(self, location: str, message: str):
        self.warnings.append(ValidationError(location, message, "warning"))
    
    def add_info(self, location: str, message: str):
        self.infos.append(ValidationError(location, message, "info"))
    
    def validate(self, json_mode: bool = False) -> bool:
        """Run all validations. Returns True if valid."""
        if not json_mode:
            print(f"🔍 Validating Skill: {self.skill_path}\n")

        # 基本结构验证
        self._validate_structure()

        # 结构没过 → 下面 4 组检查全跳过。标记只在此处置位，
        # 因此它精确表示「因结构失败而提前终止」，供评分封顶用。
        self.aborted_early = bool(self.errors)

        if not self.errors:  # 只在结构有效时继续
            # 解析 SKILL.md
            self._parse_skill_md()

            # Frontmatter 验证
            self._validate_frontmatter()

            # 依赖 frontmatter 的结构规则必须在解析后执行。
            self._validate_recommended_dirs()

            # Body 验证
            self._validate_body()

            # 资源文件验证
            self._validate_resources()

        # 输出结果
        self._print_results(suppress=json_mode)

        return len(self.errors) == 0
    
    def _validate_structure(self):
        """Validate directory structure"""
        # 检查 SKILL.md 是否存在
        skill_md = self.skill_path / "SKILL.md"
        if not skill_md.exists():
            self.add_error("structure", "SKILL.md not found (case-sensitive)")
            return
        
        # 检查 README.md（按 Schema 单一权威源：recommended，缺失为 warning，存在为 info）
        readme_md = self.skill_path / "README.md"
        if readme_md.exists():
            self.add_info("structure", "README.md found (recommended)")
        else:
            self.add_warning("structure", "README.md is recommended (per Universal Skill Schema)")
        
        # 检查 .skill-meta/ 目录（推荐）
        meta_dir = self.skill_path / ".skill-meta"
        if meta_dir.exists():
            manifest = meta_dir / "manifest.yaml"
            if manifest.exists():
                self.add_info("structure", f"Metadata manifest found (recommended for MCP)")
        else:
            self.add_warning("structure", ".skill-meta/ is recommended for future MCP integration")
        
        # 检查是否有不允许的文件/目录
        for item in self.skill_path.iterdir():
            if item.name in ['SKILL.md', 'README.md']:
                continue
            if item.name.startswith('.') or item.name == '.skill-meta':
                continue
            if item.is_dir() and item.name not in self.ALLOWED_DIRS:
                self.add_warning("structure",
                    f"Unknown directory: {item.name}. "
                    f"Allowed: {', '.join(self.ALLOWED_DIRS)}")

    def _validate_recommended_dirs(self):
        """Validate directory recommendations that depend on parsed frontmatter."""
        complexity = self.frontmatter.get('complexity', 'standard')
        for recommended_dir in self.ORDERED_RECOMMENDED_DIRS:
            dir_path = self.skill_path / recommended_dir
            if not dir_path.exists():
                if complexity == 'complex':
                    self.add_warning("structure",
                        f"Missing recommended directory for complex skill: {recommended_dir}/")
            elif not any(dir_path.iterdir()):
                self.add_warning("structure",
                    f"Empty directory: {recommended_dir}/. Consider adding .gitkeep if intentional.")
    
    def _parse_skill_md(self):
        """Parse SKILL.md into frontmatter and body"""
        skill_md = self.skill_path / "SKILL.md"
        content = skill_md.read_text(encoding='utf-8')
        
        # 解析 frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                import yaml
                try:
                    self.frontmatter = yaml.safe_load(parts[1]) or {}
                    self.body = parts[2].strip()
                except yaml.YAMLError as e:
                    self.add_error("frontmatter", f"Invalid YAML: {e}")
            else:
                self.add_error("frontmatter", "Invalid frontmatter format")
        else:
            self.add_error("frontmatter", "Missing frontmatter (should start with ---)")
    
    def _validate_frontmatter(self):
        """Validate YAML frontmatter"""
        if not self.frontmatter:
            return
        
        # 检查必需字段
        if 'name' not in self.frontmatter:
            self.add_error("frontmatter", "Missing required field: 'name'")
        else:
            self._validate_name(self.frontmatter['name'])
        
        if 'description' not in self.frontmatter:
            self.add_error("frontmatter", "Missing required field: 'description'")
        else:
            self._validate_description(self.frontmatter['description'])
        
        # 检查可选字段
        if 'version' in self.frontmatter:
            self._validate_version(self.frontmatter['version'])
        
        if 'complexity' in self.frontmatter:
            self._validate_complexity(self.frontmatter['complexity'])
        else:
            self.add_warning("frontmatter", 
                "Consider adding 'complexity' field (minimal/standard/complex)")
        
        if 'compatibility' in self.frontmatter:
            self._validate_compatibility(self.frontmatter['compatibility'])
    
    def _validate_name(self, name: str):
        """Validate skill name"""
        kind = classify_skill_name(name)
        if kind == "invalid":
            if _has_unicode_letter(name):
                self.add_error(
                    "name",
                    f"Name '{name}' 含非法字符；中文/Unicode name 仅允许字母（含中文）、数字、连字符",
                )
            else:
                self.add_error(
                    "name",
                    f"Name '{name}' must be kebab-case (lowercase letters, numbers, hyphens)",
                )
        # unicode：与目录一致即可，kebab-case 记 na，不报 error
        
        # 检查保留名称
        name_lower = name.lower()
        for reserved in self.RESERVED_NAMES:
            if reserved in name_lower:
                self.add_warning("name", 
                    f"Name contains reserved word '{reserved}'")
        
        # 检查长度
        if len(name) > 64:
            self.add_warning("name", f"Name is long ({len(name)} chars), consider shortening")
        
        # 检查是否与目录名匹配（考虑 kebab-case 与 snake_case 的映射）
        dir_name = self.skill_path.name
        expected_from_dir = dir_name.replace('_', '-')
        if name != dir_name and name != expected_from_dir:
            self.add_warning("name",
                f"Name '{name}' doesn't match directory name '{dir_name}' (expected '{expected_from_dir}')")
    
    def _validate_description(self, description: str):
        """Validate description field"""
        # 检查长度
        if len(description) > 1024:
            self.add_error("description", 
                f"Description too long ({len(description)} chars, max 1024)")
        
        # 检查是否包含触发词
        if len(description) < 50:
            self.add_warning("description", 
                "Description is very short, may not trigger effectively")
        
        # 检查 XML 标签
        if '<' in description and '>' in description:
            self.add_error("description", 
                "Description contains XML tags (< >), which are not allowed")
        
        # 检查是否包含触发提示
        trigger_indicators = ['当', 'when', '提及', 'mention', '请求', 'ask', '使用', 'use']
        if not any(indicator in description.lower() for indicator in trigger_indicators):
            self.add_warning("description", 
                "Description may lack trigger conditions. "
                "Consider adding 'when', 'mention', 'ask' etc.")
    
    def _validate_version(self, version: str):
        """Validate version field"""
        # 简单语义化版本检查
        if not re.match(r'^\d+\.\d+\.\d+', version):
            self.add_warning("version", 
                f"Version '{version}' doesn't follow semantic versioning (X.Y.Z)")
    
    def _validate_complexity(self, complexity: str):
        """Validate complexity field"""
        valid_levels = {'minimal', 'standard', 'complex'}
        if complexity not in valid_levels:
            self.add_error("complexity", 
                f"Invalid complexity '{complexity}'. Valid: {', '.join(valid_levels)}")
        else:
            self.add_info("complexity", f"Complexity level: {complexity}")
    
    def _validate_compatibility(self, compatibility: Dict):
        """Validate compatibility field"""
        valid_models = {'claude', 'kimi', 'cursor', 'gpt', 'minimax', 'dsh', 'codex'}
        valid_statuses = {'native', 'bridge', 'unsupported'}
        
        for model, config in compatibility.items():
            if model not in valid_models:
                self.add_warning("compatibility", 
                    f"Unknown model: {model}. Valid: {', '.join(valid_models)}")
                continue
            
            # 支持两种格式：字符串或字典
            if isinstance(config, str):
                status = config
            elif isinstance(config, dict):
                status = config.get('status', '')
            else:
                self.add_warning("compatibility", 
                    f"Invalid config type for {model}")
                continue
            
            if status not in valid_statuses:
                self.add_warning("compatibility", 
                    f"Unknown status '{status}' for {model}. "
                    f"Valid: {', '.join(valid_statuses)}")
    
    def _validate_body(self):
        """Validate SKILL.md body"""
        if not self.body:
            self.add_error("body", "SKILL.md body is empty")
            return
        
        # 检查长度（根据 complexity 分级）
        word_count = len(self.body.split())
        char_count = len(self.body)
        
        # 根据 complexity 确定限制
        complexity = self.frontmatter.get('complexity', 'standard')
        limits = {
            'minimal': 2000,
            'standard': 4000,
            'complex': 8000
        }
        max_chars = limits.get(complexity, 4000)
        
        if char_count > max_chars:
            if complexity == 'complex':
                self.add_warning("body", 
                    f"Body exceeds complex limit ({char_count} > {max_chars}). "
                    f"Consider splitting further.")
            else:
                self.add_error("body", 
                    f"Body too long ({char_count} chars, max {max_chars} for {complexity}). "
                    f"Consider moving content to references/ or increasing complexity.")
        elif char_count > max_chars * 0.8:
            self.add_warning("body", 
                f"Body is approaching limit ({char_count}/{max_chars} for {complexity}).")
        
        self.add_info("body", f"Body length: {word_count} words, {char_count} chars")
        
        # 检查第二人称
        second_person_patterns = [
            r'\b你应该\b', r'\b你需要\b', r'\b你可以\b',
            r'\byou should\b', r'\byou need\b', r'\byou can\b',
            r'\byour\b',
        ]
        for pattern in second_person_patterns:
            if re.search(pattern, self.body, re.IGNORECASE):
                self.add_warning("body", 
                    f"Possible second person usage detected: '{pattern}'"
                    "Use imperative form instead.")
        
        # 提取引用的文件
        self._extract_references()
    
    def _extract_references(self):
        """Extract referenced files from body"""
        for match in self.REFERENCE_RE.finditer(self.body):
            ref = next(value for value in match.groupdict().values() if value)
            self.referenced_files.add(ref.rstrip('.,;)'))
    
    def _validate_resources(self):
        """Validate resource files"""
        # 检查引用的文件是否存在
        for ref in sorted(self.referenced_files):
            # 解析路径
            parts = Path(ref).parts
            if len(parts) > 1:
                if parts[0] in self.ALLOWED_DIRS:
                    file_path = self.skill_path / ref
                    if not file_path.exists():
                        self.add_warning("resources", 
                            f"Referenced file not found: {ref}")
        
        # 检查各资源目录
        for dir_name in self.ORDERED_ALLOWED_DIRS:
            dir_path = self.skill_path / dir_name
            if dir_path.exists():
                files = sorted(dir_path.iterdir())
                if files:
                    self.add_info("resources", 
                        f"{dir_name}/: {len(files)} file(s)")
                    
                    # 检查 scripts 是否可执行
                    if dir_name == 'scripts':
                        for script in files:
                            if script.is_file():
                                if script.name == '.gitkeep':
                                    continue
                                self._validate_script(script)
    
    def _validate_script(self, script: Path):
        """Validate a script file"""
        content = script.read_text(encoding='utf-8', errors='ignore')
        
        # 检查 shebang
        if not content.startswith('#!'):
            self.add_warning("scripts", 
                f"{script.name}: Missing shebang (e.g., #!/bin/bash)")

        if re.search(r"from\s+skills\._shared|import\s+skills\._shared", content):
            self.add_warning(
                "scripts",
                f"{script.name}: 依赖 skills._shared（单包目录下通常不存在）。记 warning，不阻断；不要为修它改 name。",
            )
        
        # 检查执行权限 (Unix only)
        if os.name != 'nt':  # not Windows
            if not os.access(script, os.X_OK):
                self.add_warning("scripts", 
                    f"{script.name}: Not executable (run: chmod +x {script.name})")
    
    def _compute_score(self) -> int:
        """质量分：满分 100，每个 error 扣 10、每个 warning 扣 2，扣完为止。

        结构层未通过时**封顶 30**。理由：结构一挂，后面 4 组检查
        （frontmatter / 推荐目录 / body / 资源）整段不执行，
        不封顶就等于把「没检查」当成「没问题」——连 SKILL.md 都不存在的
        目录会拿到 90 分「Excellent」。封顶后落到「❌ Major issues」，
        与「这压根不是一个合格 skill」的事实对齐。
        """
        score = max(0, 100 - len(self.errors) * 10 - len(self.warnings) * 2)
        if self.aborted_early:
            score = min(score, 30)
        return score

    def _print_results(self, suppress: bool = False):
        """Print validation results"""
        if suppress:
            # Still compute score for JSON consumers
            self.score = self._compute_score()
            return

        # 输出所有消息
        for error in self.errors:
            print(error)
        for warning in self.warnings:
            print(warning)
        for info in self.infos:
            print(info)

        print()

        # 总结
        total_issues = len(self.errors) + len(self.warnings)

        if len(self.errors) == 0:
            print(f"✅ Validation passed! ({len(self.warnings)} warnings)")
        else:
            print(f"❌ Validation failed: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")

        # 评分
        self.score = self._compute_score()
        print(f"📊 Quality Score: {self.score}/100")
        if self.aborted_early:
            print("   ⛔ 结构未通过：5 组检查只跑了结构 1 组，其余已跳过，分数封顶 30")

        if self.score >= 90:
            print("   🌟 Excellent!")
        elif self.score >= 70:
            print("   👍 Good")
        elif self.score >= 50:
            print("   ⚠️  Needs improvement")
        else:
            print("   ❌ Major issues")


def main():
    parser = argparse.ArgumentParser(
        description='Validate Universal Skill structure and content'
    )
    parser.add_argument('skill_path', type=Path, help='Path to skill directory')
    parser.add_argument('--strict', action='store_true', 
        help='Treat warnings as errors')
    parser.add_argument('--json', action='store_true',
        help='Output results as JSON')
    
    args = parser.parse_args()
    
    # 验证路径
    if not args.skill_path.exists():
        print(f"Error: Path not found: {args.skill_path}")
        sys.exit(1)
    
    if not args.skill_path.is_dir():
        print(f"Error: Path is not a directory: {args.skill_path}")
        sys.exit(1)
    
    # 运行验证
    validator = SkillValidator(args.skill_path)
    is_valid = validator.validate(json_mode=args.json)

    # JSON 输出
    if args.json:
        result = {
            'valid': is_valid,
            'score': validator.score,
            'status': 'excellent' if validator.score >= 90 else 'good' if validator.score >= 70 else 'needs_improvement' if validator.score >= 50 else 'major_issues',
            'errors': [{'location': e.location, 'message': e.message}
                      for e in validator.errors],
            'warnings': [{'location': w.location, 'message': w.message}
                        for w in validator.warnings],
            'infos': [{'location': i.location, 'message': i.message}
                     for i in validator.infos]
        }
        print(json.dumps(result, indent=2))
    
    # 退出码
    if args.strict:
        sys.exit(0 if is_valid and len(validator.warnings) == 0 else 1)
    else:
        sys.exit(0 if is_valid else 1)


if __name__ == '__main__':
    main()
