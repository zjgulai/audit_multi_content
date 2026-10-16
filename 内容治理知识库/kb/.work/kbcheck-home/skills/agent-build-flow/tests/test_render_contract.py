#!/usr/bin/env python3
"""render-contract.py 的回归测试。

重点防三个已修过的 bug:
  1. 占位符被 format 自身 -> 输出字面 "<TODO: %s>"
  2. profile 被"网页/页面"这类泛词带偏
  3. 中文标题被 slug 清空后剩下 "agent"
跑法: python3 tests/test_render_contract.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "render-contract.py"

SPEC = """\
# 规格：品牌问答 Agent

## 4. 实现决策

- 对外提供一个命令行工具，通过 stdin 读 JSON
- 需要接品牌知识库检索，需要计算器做折扣核算

### 交付物

| id | name | format | fields | acceptance |
|---|---|---|---|---|
| answer | 业务答复 | text | 结论、依据 | 先给结论再给依据；引用资料标来源 |
| weekly-report | 周度问题汇总 | markdown | 本期TOP5、处理率 | 数字和台账对得上 |

## 6. 范围外

不做法律意见，不做对外报价承诺。
"""

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  [OK]   {label}")
    else:
        print(f"  [FAIL] {label} {detail}")
        failures.append(label)


def main():
    print("render-contract.py 回归测试\n")

    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / "spec.md"
        spec.write_text(SPEC, encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPT), str(spec)],
                           capture_output=True, text=True)
        out = r.stdout

        check("退出码 0", r.returncode == 0, f"(got {r.returncode})")

        print("\n── bug 1: 占位符不能被 format 自身 ──")
        check("输出无字面 '<TODO: %s>'", "<TODO: %s>" not in out)
        check("占位符格式正确", "<TODO: " in out)

        print("\n── bug 2: profile 不被泛词带偏 ──")
        check("profile 是 general 不是 web-ops", "profile: general" in out,
              f"(got: {[l for l in out.splitlines() if l.startswith('profile')]})")

        print("\n── bug 3: 中文标题不能只剩 agent ──")
        check("name 留成 TODO 而不是 'agent'", "name: <TODO:" in out)

        print("\n── 交付物抽取 ──")
        check("抽到 answer", "id: answer" in out)
        check("抽到 weekly-report", "id: weekly-report" in out)
        check("id 已 kebab 化（不是 'weekly report'）", "weekly report" not in out)
        check("acceptance 原样保留", "先给结论再给依据" in out)
        check("env 用 ${managed}", "API_KEY: ${managed}" in out)
        check("末尾有「待人工确认」", "待人工确认" in out)

        print("\n── 绝不猜 ──")
        check("tools 留 TODO 不瞎填", "tool_name" in out)
        check("run 留 TODO", "run: <TODO:" in out)

    print("\n" + "=" * 60)
    if failures:
        print(f"失败 {len(failures)} 项: {', '.join(failures)}")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
