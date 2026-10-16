#!/usr/bin/env python3
"""蒸完之后的**结构 + 格式**自检。不评分。

用法:
    python3 check-skill.py <skill目录>
    python3 check-skill.py <skill目录> --json

退出码: 0=通过(可能有警告)  1=有阻断错误  2=用法错误

边界（刻意不做的事）:
  - 不评分          → root-skills-eval
  - 不修结构        → root-skills-doctor
  - 不改低分项      → root-skills-opt
本脚本只查"该有的东西有没有、格式对不对"。
"""
import json
import re
import sys
from pathlib import Path

MAX_BODY_CHARS = 8000          # complex 上限
KEEP_RATE_LO, KEEP_RATE_HI = 0.25, 0.50   # 淘汰率正常区间 50%~75%

WEAK_PHRASES = ["注意质量", "小心触发", "多检查", "视情况而定", "尽量", "注意一下"]

# 弱写法三特征 + 空话
def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return None, text
    fm_raw, body = m.group(1), m.group(2)
    fm = {}
    key = None
    for line in fm_raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if re.match(r"^\s+\S", line) and key:          # 续行 (块标量)
            fm[key] = (fm.get(key) or "") + "\n" + line.strip()
            continue
        m2 = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m2:
            key = m2.group(1)
            # 剥掉成对引号：`name: "tdd"` 的裸值若不去引号，会与目录名 `tdd`
            # 比对失败，把 7 个写法正常的 skill 误报成阻断错误。
            fm[key] = m2.group(2).strip().strip('"').strip("'")
    return fm, body


def check(skill_dir: Path, as_json: bool):
    errors, warnings, passes, stats = [], [], [], {}

    if not skill_dir.is_dir():
        print(f"错误: 不是目录: {skill_dir}", file=sys.stderr)
        return 2

    # 用 `.` / `..` / 带尾斜杠调用时 Path.name 会是空串或 '..'，会让
    # 「frontmatter name 与目录名不一致」误报成阻断错误。此处先解析成绝对路径。
    skill_dir = skill_dir.resolve()
    name = skill_dir.name

    # --- 1. SKILL.md 存在 ---
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        errors.append("缺 SKILL.md（硬性）")
        fm, body = None, ""
    else:
        text = skill_md.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        if fm is None:
            errors.append("SKILL.md 缺 frontmatter（`---` 包裹的头部）")
            fm = {}

    # --- 2. name 一致 + 命名规范 ---
    # 规范允许两种：纯 ASCII kebab-case，或含 CJK 的同构写法（目录里已有
    # `蒸馏`、`web-执行测试用例` 两个先例）。空串/空格/下划线仍然拒。
    if fm:
        fm_name = fm.get("name", "")
        is_ascii_kebab = re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm_name) is not None
        is_cjk_kebab = re.fullmatch(
            r"[\u4e00-\u9fff0-9A-Za-z]+(-[\u4e00-\u9fff0-9A-Za-z]+)*", fm_name
        ) is not None
        if not fm_name:
            errors.append("frontmatter 缺 `name`")
        elif fm_name != name:
            errors.append(f"frontmatter name(`{fm_name}`) 与目录名(`{name}`) 不一致")
        elif not (is_ascii_kebab or is_cjk_kebab):
            errors.append(f"`name` 不符合命名规范（需 ASCII kebab-case 或含 CJK 同构）: {fm_name}")
        elif is_ascii_kebab:
            passes.append("name 与目录名一致且为 kebab-case")
        else:
            passes.append(f"name 与目录名一致且为 CJK 命名: {fm_name}")

    # --- 3. description: 存在 / 长度 / 触发词 / 负例 ---
    desc = fm.get("description", "") if fm else ""
    if not desc:
        errors.append("frontmatter 缺 `description`（它是路由触发器，不能空）")
    else:
        stats["description_chars"] = len(desc)
        if len(desc) < 40:
            warnings.append(f"description 偏短（{len(desc)} 字符），可能不足以路由")
        else:
            passes.append(f"description {len(desc)} 字符")

        # 触发词段：中文写「触发词」，英文原生的写 "Use when …" 也算。
        has_trigger = (
            ("触发词" in desc)
            or ("trigger" in desc.lower())
            or ("use when" in desc.lower())
            or ("use this" in desc.lower())
        )
        has_negative = ("不适用" in desc) or ("not for" in desc.lower()) or ("何时不用" in desc) or ("when not" in desc.lower())
        if not has_trigger:
            errors.append("description 里没有「触发词」——触发盲测会直接失败")
        else:
            passes.append("description 含触发词段")
        if not has_negative:
            warnings.append("description 里没写「不适用」场景——容易误触发")
        else:
            passes.append("description 含不适用场景")

        # 中英触发词都要有
        stats["desc_has_cjk"] = bool(re.search(r"[\u4e00-\u9fff]", desc))
        stats["desc_has_ascii_words"] = bool(re.search(r"[A-Za-z]{3,}", desc))
        if not stats["desc_has_cjk"]:
            warnings.append("description 没看到中文触发词")
        if not stats["desc_has_ascii_words"]:
            warnings.append("description 没看到英文触发词（评测要求中英触发词均须出正例）")

    # --- 4. 正文长度 ---
    complexity = (fm.get("complexity", "") or "").strip('"') if fm else ""
    stats["complexity"] = complexity
    limits = {"minimal": 2000, "standard": 4000, "complex": MAX_BODY_CHARS}
    limit = limits.get(complexity, MAX_BODY_CHARS)
    body_len = len(body)
    stats["body_chars"] = body_len
    if body_len > limit:
        errors.append(
            f"正文 {body_len} 字符 > {complexity or '默认 complex'} 上限 {limit}"
            "——把长资料搬到 references/"
        )
    else:
        passes.append(f"正文 {body_len} 字符（上限 {limit}）")

    if complexity and complexity not in limits:
        warnings.append(f"`complexity` 值未知: {complexity}（应为 minimal/standard/complex）")

    # --- 5. 弱写法 ---
    hits = [p for p in WEAK_PHRASES if p in body]
    if hits:
        warnings.append(f"正文出现弱写法/空话: {', '.join(hits)}——改成可判定的规则")
    else:
        passes.append("正文无弱写法三特征")

    # --- 6. 三件套齐全（structural_completeness 谓词）---
    # 关键词表必须中英双语：目录里有 ~9 个英文原生 skill（code-review /
    # prototype / handoff / domain-modeling …），只认中文会把它们全判阻断。
    trio = {
        "触发条件": ["什么时候用", "何时用", "入口判断", "触发",
                     "when to use", "use when", "when it applies", "usage", "entry"],
        "执行步骤": ["流程", "步骤", "主干", "阶段",
                     "workflow", "steps", "process", "procedure", "how it works"],
        "边界说明": ["不适用", "边界", "不做什么", "何时不用",
                     "when not", "not for", "out of scope", "boundaries", "limitations"],
    }
    missing_trio = []
    for label, keys in trio.items():
        if not any(k in body or k in body.lower() for k in keys):
            missing_trio.append(label)
    if missing_trio:
        errors.append(f"三件套缺失: {', '.join(missing_trio)}（structural_completeness 不通过）")
    else:
        passes.append("三件套齐全（触发条件/执行步骤/边界说明）")

    # --- 7. 目录与交付物 ---
    if complexity in ("standard", "complex"):
        for d in ("references", "examples"):
            if not (skill_dir / d).is_dir():
                warnings.append(f"缺 `{d}/` 目录（complexity={complexity} 建议有）")

    tres = skill_dir / "assets" / "templates" / "trigger-table.md"
    if not tres.is_file():
        warnings.append("缺 assets/templates/trigger-table.md——触发评测没有负例可用")
    else:
        t = tres.read_text(encoding="utf-8")
        n_neg = t.count("|") and len(re.findall(r"^\|\s*\d+\s*\|", t, re.M))
        if "负例" not in t:
            warnings.append("trigger-table.md 里没有「负例」段")
        else:
            passes.append("trigger-table.md 含负例段")

    eres = skill_dir / "assets" / "templates" / "eval-cases.md"
    if not eres.is_file():
        warnings.append("缺 assets/templates/eval-cases.md——盲测无题可出")

    dlog = skill_dir / "assets" / "templates" / "distill-log.md"
    if not dlog.is_file():
        warnings.append("缺 assets/templates/distill-log.md——出处无法核验")
    else:
        t = dlog.read_text(encoding="utf-8")
        if "淘汰率" in t:
            passes.append("distill-log.md 含淘汰率统计")
        if "裸模型对照" in t:
            passes.append("distill-log.md 含裸模型对照段")
        else:
            warnings.append("distill-log.md 里没有「裸模型对照」段——交付前必须做")

    # --- 8. 残留占位符 ---
    # 只把"像是没填的模板占位"当成问题。
    # 行内代码与代码块里的 <skill-name> / <skill目录> 是用法说明，不是没填完。
    if body:
        prose = re.sub(r"```.*?```", "", body, flags=re.S)   # 去代码块
        prose = re.sub(r"`[^`\n]*`", "", prose)              # 去行内代码
        hits = re.findall(r"<[^<>\n]{2,40}>", prose)
        hits = [h for h in hits
                if not re.fullmatch(r"<[\w./-]+\.(md|py|yaml|json|html|txt)>", h)
                and not re.fullmatch(r"<[a-z0-9]+(-[a-z0-9]+)*>", h)]
        if hits:
            warnings.append(f"正文残留 {len(hits)} 个占位符（如 {hits[0]}）——骨架没填完？")

    # --- 9. 越界检查：不该做评测/修复的事 ---
    if re.search(r"(给|本技能)(skill)?\s*(打分|评分)", body) and "root-skills-eval" not in body:
        warnings.append("正文提到自己评分，但没指向 root-skills-eval——会造出第二套标准")

    # --- 输出 ---
    if as_json:
        print(json.dumps({
            "skill": name, "path": str(skill_dir), "stats": stats,
            "passes": passes, "warnings": warnings, "errors": errors,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Skill 结构自检: {skill_dir}\n")
        print(f"  complexity={complexity or '(未声明)'}  正文 {body_len} 字符  description {stats.get('description_chars', 0)} 字符\n")
        for p in passes:
            print(f"  [OK]   {p}")
        for w in warnings:
            print(f"  [WARN] {w}")
        for e in errors:
            print(f"  [ERR]  {e}")
        print("\n" + "=" * 68)
        print(f"通过 {len(passes)} | 警告 {len(warnings)} | 阻断 {len(errors)}")
        if errors:
            print("结论: 不通过。先修阻断项。")
        elif warnings:
            print("结论: 通过（有警告）。")
        else:
            print("结论: 通过。")
        print("\n注意: 本脚本只查结构与格式，不评分。评分与触发盲测走 root-skills-eval。")

    return 1 if errors else 0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    if "-h" in flags or "--help" in flags or not args:
        print(__doc__)
        return 0 if args or ("-h" in flags or "--help" in flags) else 2
    return check(Path(args[0]).expanduser(), "--json" in flags)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
