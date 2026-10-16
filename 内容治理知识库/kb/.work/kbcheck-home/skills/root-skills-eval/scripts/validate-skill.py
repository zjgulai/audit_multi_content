#!/usr/bin/env python3
"""
Shim: validate-skill.py

本文件不独立实现验证逻辑，唯一权威源为家族内的
`../root-skills-creator/scripts/validate-skill.py`。

此 shim 动态加载权威实现并转发命令行参数，避免脚本副本之间规则分歧。
"""

import sys
import runpy
from pathlib import Path


def main() -> None:
    here = Path(__file__).resolve()
    # scripts/ 的 parents[2] = root-skills 家族根目录
    # （root-skills-eval/scripts → parents[0]=scripts, parents[1]=root-skills-eval, parents[2]=root-skills）
    family_validator = here.parents[2] / "root-skills-creator" / "scripts" / "validate-skill.py"
    if not family_validator.exists():
        sys.stderr.write(
            "❌ 未找到权威验证器: {family_validator}\n"
            "请确认家族根目录下存在 root-skills-creator/scripts/validate-skill.py\n"
        )
        sys.exit(2)
    runpy.run_path(str(family_validator), run_name="__main__")


if __name__ == "__main__":
    main()
