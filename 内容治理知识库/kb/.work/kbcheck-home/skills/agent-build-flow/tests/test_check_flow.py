#!/usr/bin/env python3
"""check-flow.py 的回归测试。

跑法: python3 tests/test_check_flow.py
退出码: 0=全过 1=有失败
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check-flow.py"

GOOD = """\
name: good-agent
version: "0.1.0"
interface: cli
run: python3 agent.py
input: stdin-json
profile: general
task_types:
  - fact_qa
  - safety
deliverables:
  - id: answer
    name: 业务答复
    format: text
    fields:
      - 结论
      - 依据
    acceptance: 先给结论再给依据；引用资料时标出来源；没有依据就明说没有，不编造
tools:
  - name: search_kb
    description: 检索品牌知识库
    schema: {}
env:
  API_KEY: ${managed}
"""

BAD = """\
name: Bad_Name
version: "0.1.0"
interface: grpc
run: python3 agent.py
input: stdin-json
profile: general
deliverables:
  - id: search
    name: 检索知识库
    acceptance: 返回 200 表示成功
tools: []
env:
  API_KEY: sk-literal-secret-value-1234
"""

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  [OK]   {label}")
    else:
        print(f"  [FAIL] {label} {detail}")
        failures.append(label)


def run(path, *extra):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), *extra],
        capture_output=True, text=True,
    )


def main():
    print("check-flow.py 回归测试\n")

    with tempfile.TemporaryDirectory() as td:
        good_dir = Path(td) / "good-agent"
        good_dir.mkdir()
        (good_dir / "agent.yaml").write_text(GOOD, encoding="utf-8")

        r = run(good_dir, "--contract-only")
        print("── 正确契约应通过（--contract-only）──")
        check("退出码 0", r.returncode == 0, f"(got {r.returncode})")
        check("十字段齐全", "十字段齐全" in r.stdout)
        check("无阻断错误", "阻断 0 项" in r.stdout)

    with tempfile.TemporaryDirectory() as td:
        bad_dir = Path(td) / "bad-agent"
        bad_dir.mkdir()
        (bad_dir / "agent.yaml").write_text(BAD, encoding="utf-8")

        r = run(bad_dir)
        print("\n── 违规契约应阻断 ──")
        check("退出码 1", r.returncode == 1, f"(got {r.returncode})")
        check("抓到非 kebab-case name", "kebab-case" in r.stdout)
        check("抓到非法 interface", "interface 非法" in r.stdout)
        check("抓到字面量密钥", "字面量密钥" in r.stdout)
        check("抓到十字段缺失", "十字段缺失" in r.stdout)
        check("警告把工具当成活", "疑似把工具当成活" in r.stdout)
        check("警告 acceptance 是实现细节", "疑似实现细节" in r.stdout)
        print("\n── 负例不得静默通过 ──")
        check("有阻断结论", "结论: 不通过" in r.stdout)

    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "empty"
        empty.mkdir()
        r = run(empty)
        print("\n── 空目录 ──")
        check("退出码 1", r.returncode == 1, f"(got {r.returncode})")
        check("提示没有任何产出物", "没有任何阶段产出物" in r.stdout)

    print("\n── --probe 不老死 ──")
    r = subprocess.run([sys.executable, str(SCRIPT), "--probe"], capture_output=True, text=True)
    check("probe 退出码 0", r.returncode == 0)
    check("probe 输出 user-invoked 提醒", "user-invoked" in r.stdout)

    print("\n" + "=" * 60)
    if failures:
        print(f"失败 {len(failures)} 项: {', '.join(failures)}")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
