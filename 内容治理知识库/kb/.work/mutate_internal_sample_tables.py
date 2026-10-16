#!/usr/bin/env python3
"""变异自证（`INTERNAL_SAMPLE_TABLES` 单一真源）：把缺陷**真造一遍**，判据必须**精确变红**。

对应判据：`kb/l8/internal_sample_tables.py --selftest`（8 例，其中 ⑥/⑦ 专防再分叉）。
库规（`~/.dsh/AGENTS.md`）：「**新增任何判据，必须同时给反向对照** —— 否则它就是注释。」

## 为什么原地改 + 必还原

被测件是**按固定路径**被读/被执行的（真源本体 ＋ 两个消费端），副本没法顶替。
⇒ 三条安全措施缺一不可：① 先存 `sha256`；② `finally` **必定**还原（哪怕抛异常）；
③ 还原后**回读复算 sha**，不符即非零退出。

## 「精确变红」判的是**集合相等**

每个变异声明它该打中哪几例，判据是 `实际失败集 == 声明集`：
少了报「**漏**」、多了报「**脆**」，分开报。
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
MOD = os.path.join(KB, "l8", "internal_sample_tables.py")
L3 = os.path.join(KB, "l8", "l3_scope.py")
L6 = os.path.join(KB, ".work", "l6_scope_lib.py")

# (名称, 目标文件, 原文, 改成, 预期失败的判据编号集)
MUT = [
    ("M1 L3 又把名单写回字面量（分叉复发）", L3,
     'INTERNAL_SAMPLE_TABLES = _load_internal_sample_tables()',
     'INTERNAL_SAMPLE_TABLES = ("专家修订汇总表", "负面样本", "正面和负面样本")',
     {"⑥[L3]"}),

    ("M2 L6 又把名单写回字面量（分叉复发）", L6,
     'INTERNAL_SAMPLE_TABLES = _m_ist.INTERNAL_SAMPLE_TABLES',
     'INTERNAL_SAMPLE_TABLES = {"专家修订汇总表", "负面样本", "正面和负面样本"}',
     {"⑥[L6]"}),

    ("M3 真源里悄悄少一张表（静默缩小范围）", MOD,
     'INTERNAL_SAMPLE_TABLES = ("专家修订汇总表", "负面样本", "正面和负面样本")',
     'INTERNAL_SAMPLE_TABLES = ("专家修订汇总表", "负面样本")',
     {"①"}),

    ("M4 把 tuple 改成 set（会改 L3 拒绝理由的渲染）", MOD,
     'INTERNAL_SAMPLE_TABLES = ("专家修订汇总表", "负面样本", "正面和负面样本")',
     'INTERNAL_SAMPLE_TABLES = {"专家修订汇总表", "负面样本", "正面和负面样本"}',
     {"②", "③"}),

    ("M5 把容器表名「材料收集」塞进名单", MOD,
     'INTERNAL_SAMPLE_TABLES = ("专家修订汇总表", "负面样本", "正面和负面样本")',
     'INTERNAL_SAMPLE_TABLES = ("专家修订汇总表", "负面样本", "正面和负面样本", "材料收集")',
     {"①", "⑤"}),
]


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _run():
    """→ (退出码, {失败的判据编号})"""
    r = subprocess.run([sys.executable, MOD, "--selftest"], capture_output=True, text=True, cwd=ROOT)
    ids = set()
    for line in r.stdout.splitlines():
        s = line.strip()
        if s.startswith("✗ "):
            ids.add(s[2:].strip().split()[0])
    return r.returncode, ids


def main():
    rc, failed = _run()
    tail = [x for x in subprocess.run([sys.executable, MOD, "--selftest"], capture_output=True,
                                      text=True, cwd=ROOT).stdout.splitlines() if "selftest" in x]
    print("基线：exit=%s ｜ %s" % (rc, tail[-1] if tail else "?"))
    if rc != 0 or failed:
        print("❌ 基线没过（判据自己就是红的）⇒ 停止")
        return 2

    ok = bad = 0
    for name, target, old, new, expect in MUT:
        src = open(target, encoding="utf-8").read()
        if src.count(old) != 1:
            print("❌ %-46s 锚点不唯一(%d)" % (name, src.count(old)))
            bad += 1
            continue
        before = _sha(target)
        bak = target + ".mutbak"
        shutil.copy2(target, bak)
        try:
            open(target, "w", encoding="utf-8").write(src.replace(old, new, 1))
            rc2, failed2 = _run()
        finally:
            shutil.copy2(bak, target)
            os.unlink(bak)
        if _sha(target) != before:
            print("❌ %-46s 还原失败（sha 变了）⇒ 立即停止" % name)
            return 4

        missing, extra = expect - failed2, failed2 - expect
        if rc2 != 0 and not missing and not extra:
            ok += 1
            print("✅ %-46s ⇒ 精确变红：%s" % (name, "、".join(sorted(expect))))
        elif missing:
            bad += 1
            print("❌ %-46s ⇒ **漏**：该红的没红 %s（实际 %s）" % (name, sorted(missing), sorted(failed2) or "无"))
        else:
            bad += 1
            print("❌ %-46s ⇒ **脆**：多红了 %s" % (name, sorted(extra)))

    rc3, failed3 = _run()
    print("\n收尾复跑：exit=%s ｜ 失败=%s" % (rc3, sorted(failed3) or "无"))
    if rc3 != 0 or failed3:
        print("❌ 还原后判据仍红 ⇒ 盘上留了残迹")
        return 4

    print("\n变异自证：%d 通过 / %d 失败" % (ok, bad))
    return 0 if bad == 0 else 3


raise SystemExit(main())
