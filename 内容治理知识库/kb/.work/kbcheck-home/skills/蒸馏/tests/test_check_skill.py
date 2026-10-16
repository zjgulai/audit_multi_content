#!/usr/bin/env python3
"""check-skill.py 的回归测试。

跑法: python3 tests/test_check_skill.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "scripts" / "check-skill.py"
SCAFFOLD = ROOT / "scripts" / "scaffold.py"

GOOD = """\
---
name: demo-good
description: |
  演示用的 Skill。当用户说"做个演示"、"跑个 demo"、"演示一下"时使用。
  触发词：做个演示、跑个 demo、演示一下、run a demo、show me a demo。
  不适用：真实业务任务（走对应业务 skill）。
version: "1.0.0"
complexity: standard
---

# 演示

## 一、入口判断

什么时候该用这个 Skill。

## 二、主干流程

步骤一、步骤二。

## 三、边界与不做什么

不适用场景。
"""

BAD = """\
---
name: wrong-name
description: "太短。"
version: "1.0.0"
---

# 测试

注意质量，视情况而定。
"""

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  [OK]   {label}")
    else:
        print(f"  [FAIL] {label} {detail}")
        failures.append(label)


def run(path):
    return subprocess.run([sys.executable, str(CHECK), str(path)],
                          capture_output=True, text=True)


def main():
    print("check-skill.py 回归测试\n")

    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "demo-good"
        (d / "assets" / "templates").mkdir(parents=True)
        (d / "references").mkdir()
        (d / "examples").mkdir()
        (d / "SKILL.md").write_text(GOOD, encoding="utf-8")
        (d / "assets" / "templates" / "trigger-table.md").write_text(
            "# 触发词表\n\n## 负例：明确不触发\n\n| # | 表达 |\n|---|---|\n| 1 | x |\n",
            encoding="utf-8")
        (d / "assets" / "templates" / "eval-cases.md").write_text("# 用例表\n", encoding="utf-8")
        (d / "assets" / "templates" / "distill-log.md").write_text(
            "# 蒸馏记录\n\n## 统计\n\n淘汰率 62%\n\n## 裸模型对照\n\n明显优于\n", encoding="utf-8")

        r = run(d)
        print("── 合规 skill 应通过 ──")
        check("退出码 0", r.returncode == 0, f"(got {r.returncode})")
        check("三件套判定为齐全", "三件套齐全" in r.stdout)
        check("无阻断", "阻断 0" in r.stdout)

    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "bad-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(BAD, encoding="utf-8")

        r = run(d)
        print("\n── 违规 skill 应阻断 ──")
        check("退出码 1", r.returncode == 1, f"(got {r.returncode})")
        check("抓到 name 与目录名不一致", "不一致" in r.stdout)
        check("抓到 description 缺触发词", "触发词" in r.stdout)
        check("抓到三件套缺失", "三件套缺失" in r.stdout)
        check("警告弱写法", "弱写法" in r.stdout)

    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "no-skill-md"
        d.mkdir()
        r = run(d)
        print("\n── 缺 SKILL.md ──")
        check("退出码 1", r.returncode == 1, f"(got {r.returncode})")
        check("提示缺 SKILL.md", "缺 SKILL.md" in r.stdout)

    print("\n── scaffold 生成的骨架应可被检查器接受 ──")
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, str(SCAFFOLD), "scaf-demo", "--out", td],
                           capture_output=True, text=True)
        check("scaffold 退出码 0", r.returncode == 0, r.stderr[:200])
        check("骨架已建", (Path(td) / "scaf-demo" / "SKILL.md").is_file())
        check("含 references/", (Path(td) / "scaf-demo" / "references").is_dir())
        check("含三张表", (Path(td) / "scaf-demo" / "assets" / "templates" / "distill-log.md").is_file())

        r2 = run(Path(td) / "scaf-demo")
        check("骨架自检无阻断", "阻断 0" in r2.stdout, r2.stdout[-300:])

    print("\n── scaffold 拒绝非法入参 ──")
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, str(SCAFFOLD), "Bad_Name", "--out", td],
                           capture_output=True, text=True)
        check("非 kebab-case 被拒", r.returncode == 2, f"(got {r.returncode})")
        r = subprocess.run([sys.executable, str(SCAFFOLD), "ok-name", "--out", td,
                            "--complexity", "huge"], capture_output=True, text=True)
        check("非法 complexity 被拒", r.returncode == 2, f"(got {r.returncode})")
        subprocess.run([sys.executable, str(SCAFFOLD), "dup", "--out", td],
                       capture_output=True, text=True)
        r = subprocess.run([sys.executable, str(SCAFFOLD), "dup", "--out", td],
                           capture_output=True, text=True)
        check("已存在不覆盖", r.returncode == 2, f"(got {r.returncode})")

    print("\n" + "=" * 60)
    if failures:
        print(f"失败 {len(failures)} 项: {', '.join(failures)}")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
