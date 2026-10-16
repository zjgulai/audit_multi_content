#!/usr/bin/env python3
"""变异自证（tiering 的严重度判据）：把缺陷真造一遍，尺子必须**精确变红**。

库规：新增任何判据，必须同时给反向对照 —— 否则它就是注释。
本脚本**只在副本上变异**，源文件一个字节都不改。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(KB, "l7", "review-engine", "core", "tiering.py")

MUTATIONS = [
    (
        "M1 只认旧中文（= 把本次修的缺陷原样造回来）",
        "⑤a 英文 Critical 认",
        ('CRITICAL_RISK_LEVELS = frozenset({"Critical", "高危", "高危·红"})',
         'CRITICAL_RISK_LEVELS = frozenset({"高危", "高危·红"})'),
    ),
    (
        "M2 改成按子串宽松判（「非高危·红…」也会命中）",
        "⑤d 不按子串宽松判",
        ('    return s.split("·")[0].strip() in CRITICAL_RISK_LEVELS',
         '    return "高危" in s or "Critical" in s'),
    ),
    (
        "M4 把 P2 也放进 BLOCK 白名单（= 回归集证伪的那个写法）",
        "⑥c P2+Critical⇒REVIEW",
        ('SEVERITY_BLOCK_TIERS = frozenset({"P0", "P1"})',
         'SEVERITY_BLOCK_TIERS = frozenset({"P0", "P1", "P2"})'),
    ),
    (
        "M3 空值也判 True（把「没判」当成「最高档」）",
        "⑤c[None] 不认",
        ('    if not s:\n        return False',
         '    if not s:\n        return True'),
    ),
]


def main() -> int:
    base = subprocess.run([sys.executable, SRC, "--selftest"], capture_output=True, text=True)
    print("基线：%s" % (base.stdout.strip().splitlines() or [""])[0])
    if base.returncode != 0:
        print("❌ 基线没过"); return 2

    tmpd = tempfile.mkdtemp(prefix="kb-mut-tier-")
    src = open(SRC, encoding="utf-8").read()
    ok = bad = 0
    for name, expect, (old, new) in MUTATIONS:
        assert src.count(old) == 1, "变异锚点不唯一：%s（%d 处）" % (name, src.count(old))
        p = os.path.join(tmpd, "mut.py")
        open(p, "w", encoding="utf-8").write(src.replace(old, new))
        r = subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True)
        first = (r.stdout.strip().splitlines() or [""])[0]
        red = r.returncode != 0
        hit = ("✗ " + expect) in r.stdout
        if red and hit:
            ok += 1
            print("✅ %-44s ⇒ 变红（%s）且精确命中 %s" % (name, first, expect))
        else:
            bad += 1
            print("❌ %-44s ⇒ 没红或没命中预期" % name)
            print("      exit=%s %s" % (r.returncode, first))
            for line in r.stdout.splitlines():
                if line.strip().startswith("✗"):
                    print("      实际红项：%s" % line.strip())
    shutil.rmtree(tmpd, ignore_errors=True)
    print()
    print("变异自证：%d 通过 / %d 失败" % (ok, bad))
    return 0 if bad == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
