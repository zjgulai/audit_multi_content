#!/usr/bin/env python3
"""变异自证：把缺陷**真造一遍**，自证必须**精确变红**（否则那些判据就是注释）。

库规（AGENTS.md）逐字：
    新增任何判据，必须同时给反向对照 —— 否则它就是注释。
    自证方式：把缺陷**真造一遍**，尺子必须**精确变红**、退出码 3。

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
SRC = os.path.join(KB, "l3", "kb_rule_dimensions.py")

#: (变异名, 期望变红的判据, 替换 (old, new))
MUTATIONS = [
    (
        "M1 把 p_level 批量兜底加回来（P1→High）",
        "①f[P1 不兜底]",
        ('    return level or RISK_LEVEL_UNKNOWN, why or "源无 风险等级 / 灯色状态 / 修订类型 ⇒ **不编**（留 %s）" % RISK_LEVEL_UNKNOWN',
         '    if level is None and str(row.get("p_level") or "") == "P1":\n'
         '        return "High", "源无 风险等级；按 p_level=P1 映射（PRD §6.2）"\n'
         '    return level or RISK_LEVEL_UNKNOWN, why or "源无 风险等级 / 灯色状态 / 修订类型 ⇒ **不编**（留 %s）" % RISK_LEVEL_UNKNOWN'),
    ),
    (
        "M2 把「去绝对化」判成 Critical（撑大红线档）",
        "①i4 去绝对化不是红线",
        ('"去绝对化": ("High", "PRD §6.2 P1 消费者安全（表述缺少适用边界；**非** §7.3-3 广告绝对化用语）", False),',
         '"去绝对化": ("Critical", "PRD §7.3-3 一票否决：绝对化用语", True),'),
    ),
    (
        "M3 复合值直接拆 `/`（整值不优先）",
        "①i3 复合键不拆散",
        ('    toks = [s] if s in REVISION_TYPE_TO_RISK else [t.strip() for t in s.split("/") if t.strip()]',
         '    toks = [t.strip() for t in s.split("/") if t.strip()]'),
    ),
    (
        "M4 复合值取**最低**档（而非最高）",
        "①i 复合取最高",
        ('        if lvl and (best is None or RISK_ORDER[lvl] > RISK_ORDER[best]):',
         '        if lvl and (best is None or RISK_ORDER[lvl] < RISK_ORDER[best]):'),
    ),
    (
        "M5 去掉 P0 地板（红线规则失去下限）",
        "①e2 P0地板只提不降且留痕",
        ('    if str(row.get("p_level") or "").strip() == P0_FLOOR["p_level"]:',
         '    if False and str(row.get("p_level") or "").strip() == P0_FLOOR["p_level"]:'),
    ),
]


def main() -> int:
    base = subprocess.run([sys.executable, SRC, "--selftest"],
                          capture_output=True, text=True)
    print("基线：%s" % base.stdout.strip().splitlines()[0])
    if base.returncode != 0:
        print("❌ 基线就没过，先修基线"); return 2
    m = re.search(r"(\d+)/(\d+)", base.stdout)
    base_ok, base_tot = int(m.group(1)), int(m.group(2))

    print()
    passed = failed = 0
    tmpd = tempfile.mkdtemp(prefix="kb-mut-")
    src_text = open(SRC, encoding="utf-8").read()
    # 副本要能 import 同目录的兄弟模块（本模块只依赖标准库，直接放临时目录即可）
    for name, expect, (old, new) in MUTATIONS:
        assert src_text.count(old) == 1, "变异锚点不唯一：%s" % name
        p = os.path.join(tmpd, "mut.py")
        open(p, "w", encoding="utf-8").write(src_text.replace(old, new))
        r = subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True)
        first = (r.stdout.strip().splitlines() or [""])[0]
        mm = re.search(r"(\d+)/(\d+)", first)
        ok = int(mm.group(1)) if mm else -1
        red = r.returncode != 0
        expect_hit = ("✗ " + expect) in r.stdout
        if red and expect_hit:
            passed += 1
            print("✅ %-38s ⇒ 变红（%s）且**精确命中** %s" % (name, first, expect))
        else:
            failed += 1
            print("❌ %-38s ⇒ 没红或没命中预期判据" % name)
            print("      exit=%s  %s" % (r.returncode, first))
            print("      期望变红判据：%s" % expect)
            for line in r.stdout.splitlines():
                if line.strip().startswith("✗"):
                    print("      实际红项：%s" % line.strip())
    shutil.rmtree(tmpd, ignore_errors=True)

    print()
    print("变异自证：%d 通过 / %d 失败（基线 %d/%d）" % (passed, failed, base_ok, base_tot))
    print("※ 源文件未被改动；变异只在临时副本上做。")
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
