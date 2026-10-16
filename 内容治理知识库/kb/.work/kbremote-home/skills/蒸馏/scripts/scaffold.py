#!/usr/bin/env python3
"""生成一个符合 Universal Skill Schema 的 skill 目录骨架。

用法:
    python3 scaffold.py <skill-name> --out <父目录>        # 默认写到 ~/.dsh/skills/
    python3 scaffold.py <skill-name> --complexity standard
    python3 scaffold.py <skill-name> --dry-run

只建骨架, 不生成内容。骨架里的 <...> 占位必须人工填 —— 本脚本绝不替你编判断。
"""
import sys
from pathlib import Path

COMPLEXITY_DIRS = {
    "minimal": [],
    "standard": ["references", "examples"],
    "complex": ["references", "assets/templates", "scripts", "examples"],
}

DEFAULT_OUT = Path.home() / ".dsh" / "skills"


def render_skill_md(name, complexity):
    return f"""---
name: {name}
description: |
  <功能一句话>。<触发时机一句话>。
  当用户说"<真实用户会说的表达1>"、"<表达2>"、"<表达3>"时使用。
  触发词：<中文词1>、<中文词2>、<中文词3>、<英文词1>、<英文词2>。
  不适用：<相邻但会误触发的场景>（走 <对应 skill>）。
version: "1.0.0"
complexity: {complexity}
enabled: "true"
disable-model-invocation: false
user-invocable: true
---

# <标题>

<一句话说清这个 Skill 管什么、不管什么。>

## 一、<入口判断>

## 二、<主干流程>

## 三、<核心闸门 / 最值钱的判断>

## 四、边界与不做什么

<!--
待填清单（填完删掉本注释）：
[ ] 每条内容都过了三重验证，且非常识这一条是**实测**过的
[ ] 正文只有判断，没有事实和常识
[ ] 弱写法三特征（注意/小心/要保证）已改成可判定规则
[ ] description 写的是用户会怎么说，不是这个 skill 能干什么
[ ] 负例（不适用场景）已写
[ ] 正文 <= 8000 字符
-->
"""


def render_distill_log(name):
    return f"""# 蒸馏记录：{name}

## 素材总览
- 素材类型：
- 字数 / 时长：
- 走了哪几条路线：

## 候选与三重验证

| # | 候选 | 独立佐证 | 预测力 | 非常识 | 评分 | 结论 | 落点 |
|---|---|---|---|---|---|---|---|
| 1 | | | | | /6 | | |

## 统计
- 候选总数：
- keep 数：
- **淘汰率**：　（50%~75% 正常；<30% 复查是否放水）

## 待确认项（合法产出）

| # | 内容 | 出处 | 为什么不确定 |
|---|---|---|---|

## 裸模型对照
- 结论：☐ 明显优于　☐ 差不多（不保留）　☐ 更差

## 入库验收谓词
- [ ] structural_completeness
- [ ] source_traceability
- [ ] no_duplication
- [ ] boundary_declared
"""


def render_trigger_table():
    return """# 触发词表

## 正例（≥3 中文 + ≥3 英文）

| # | 表达 | 语种 |
|---|---|---|
| 1 | | 中 |
| 2 | | 中 |
| 3 | | 中 |
| 4 | | 英 |

## 负例：明确不触发（≥5 条）

| # | 表达 | 为什么不该触发 | 该走谁 |
|---|---|---|---|
| 1 | | | |
"""


def render_eval_cases():
    return """# 用例表

## 正例（≥3）

| # | 用户输入 | 期望行为 | 判定方式（must_contain / must_not_contain / answer_non_empty） |
|---|---|---|---|
| 1 | | | |

## 负例（≥3）

| # | 用户输入 | 期望行为 | 该走谁 |
|---|---|---|---|
| 1 | | | |

## 边界（≥1）

| # | 用户输入 | 期望行为 |
|---|---|---|
| 1 | | |
"""


def main(argv):
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    name = args[0]
    out_dir = DEFAULT_OUT
    complexity = "complex"
    dry_run = "--dry-run" in args

    i = 1
    while i < len(args):
        if args[i] == "--out" and i + 1 < len(args):
            out_dir = Path(args[i + 1]).expanduser(); i += 2; continue
        if args[i] == "--complexity" and i + 1 < len(args):
            complexity = args[i + 1]; i += 2; continue
        i += 1

    if complexity not in COMPLEXITY_DIRS:
        print(f"错误: complexity 只能是 {'/'.join(COMPLEXITY_DIRS)}", file=sys.stderr)
        return 2

    import re
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        print(f"错误: name 必须是 kebab-case: {name}", file=sys.stderr)
        return 2

    target = out_dir / name
    if target.exists():
        print(f"错误: 已存在，不覆盖: {target}", file=sys.stderr)
        return 2

    files = [(target / "SKILL.md", render_skill_md(name, complexity))]
    if complexity != "minimal":
        files.append((target / "assets" / "templates" / "distill-log.md", render_distill_log(name)))
        files.append((target / "assets" / "templates" / "trigger-table.md", render_trigger_table()))
        files.append((target / "assets" / "templates" / "eval-cases.md", render_eval_cases()))

    print(f"将创建 {target}  (complexity={complexity})")
    for d in COMPLEXITY_DIRS[complexity]:
        print(f"  + {d}/")
    for p, _ in files:
        print(f"  + {p.relative_to(target)}")

    if dry_run:
        print("\n--dry-run，未写盘。")
        return 0

    for d in COMPLEXITY_DIRS[complexity]:
        (target / d).mkdir(parents=True, exist_ok=True)
    for p, content in files:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    print(f"\n已创建 {target}")
    print("下一步:")
    print("  1. 填 SKILL.md 的 <...> 占位（内容必须过三重验证）")
    print("  2. 填 assets/templates/ 三张表")
    print("  3. python3 scripts/check-skill.py <路径>   ← 结构自检")
    print("  4. root-skills-doctor 体检 → root-skills-eval 评测")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
