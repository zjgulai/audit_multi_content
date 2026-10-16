#!/usr/bin/env python3
"""变异自证（「问题维度」全链）：把缺陷**真造一遍**，判据必须**精确变红**。

覆盖两端（Owner 2026-10-12 批准「推荐 ①」后，同一条口径落在两处，**两处都要能被钉住**）：

| 端 | 产物 | 判据 |
|---|---|---|
| 评审链 | 答复正文的 ≥3 分类汇总 | `kb/l7/review-engine/tests/test_review_dimension_wiring.py` |
| P0 快路 | 飞书回执 + 云文档报告的汇总 | `kb/l5/p0_fastpath.py --selftest`（⑥g 系列） |
| 共用 | 桶名唯一真源 | `kb/l7/skills/kb-content-review/scripts/risk_category.py --selftest`（⑪） |

库规（`~/.dsh/AGENTS.md`）：「**新增任何判据，必须同时给反向对照** —— 否则它就是注释。」

## 为什么这个脚本**原地**改，而不是像 `mutate_risk_category.py` 那样改副本

被测件是**按固定路径**被测试 import / 被执行（`review.py` / `report_memory.py` / `p0_fastpath.py`），
副本**没法被 import** ⇒ 只能原地。

⇒ 安全措施必须更硬，三条缺一不可：
  ① 先存 `sha256`；② `finally` **必定**还原（哪怕中途抛异常）；③ 还原后**回读复算 sha**，不符即非零退出。

## 「精确变红」判的是**集合相等**，不是「至少红一个」

每个变异**声明它该打中哪几例**（跨 runner 用 `runner:id` 命名），判据是 `实际失败集 == 声明集`：
  · 少了 ⇒ 报「**漏**」（尺子没钉住）；· 多了 ⇒ 报「**脆**」（尺子连坐）。两条分别报。
★ M1 故意声明三例全中 —— 它不是脆，是**真级联**（删掉两个键，「搬运/不编/按维度分组」同时断）。
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(KB, "l7", "review-engine", "tests", "test_review_dimension_wiring.py")
REVIEW = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts", "review.py")
RC = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts", "risk_category.py")
REPORT_MEM = os.path.join(KB, "l7", "review-engine", "core", "report_memory.py")
P0 = os.path.join(KB, "l5", "p0_fastpath.py")
ROOT = os.path.dirname(KB)


def _pytest():
    """→ (退出码, {用例名})"""
    r = subprocess.run([sys.executable, "-m", "pytest", TESTS, "-q", "--tb=no", "-rf"],
                       capture_output=True, text=True, cwd=ROOT)
    ids = set()
    for line in r.stdout.splitlines():
        m = re.match(r"FAILED\s+\S+::\w+::(\w+)", line.strip())
        if m:
            ids.add(m.group(1))
    return r.returncode, ids


def _selftest(path, mark):
    """→ (退出码, {判据编号})：判据编号 = 失败行 `❌/✗ <编号> …` 的第一个词。"""
    r = subprocess.run([sys.executable, path, "--selftest"], capture_output=True, text=True, cwd=ROOT)
    ids = set()
    for line in r.stdout.splitlines():
        s = line.strip()
        if s.startswith(mark + " "):
            ids.add(s[len(mark):].strip().split()[0])
    return r.returncode, ids


RUNNERS = {
    "pytest": _pytest,
    "p0": lambda: _selftest(P0, "❌"),
    "rc": lambda: _selftest(RC, "✗"),
}

# (名称, 目标文件, 原文, 改成, [runner…], 预期失败集 {"runner:id"})
MUT = [
    ("M1 ③ 那一棒不搬维度（= 2026-10-12 改前的真实缺陷）", REVIEW,
     '        "risk_category": f.get("risk_category"),\n'
     '        "risk_category_basis": f.get("risk_category_basis"),\n',
     '', ["pytest"],
     {"pytest:test_finding_to_risk_item_carries_dimension",
      "pytest:test_unmapped_category_keeps_none_and_carries_basis",
      "pytest:test_report_memory_groups_by_dimension_not_risk_type"}),

    ("M2 未映射的类别也蒙一个维度（把「不知道」当「合规」）", REVIEW,
     '        "risk_category": f.get("risk_category"),',
     '        "risk_category": f.get("risk_category") or "合规",',
     ["pytest"],
     {"pytest:test_unmapped_category_keeps_none_and_carries_basis"}),

    ("M3 报告不印「维度」那一行（PRD §8.3 每条包含：维度）", REVIEW,
     '        _dim = f.get("risk_category")\n        _dim_basis = f.get("risk_category_basis")\n'
     '        if _dim:',
     '        _dim = None\n        _dim_basis = f.get("risk_category_basis")\n        if _dim:',
     ["pytest"],
     {"pytest:test_report_renders_dimension_line"}),

    ("M4 报告记忆分组键换回 risk_type（PRD §5.3 分组失效）", REPORT_MEM,
     '        if item.get("risk_category"):\n',
     '        if item.get("risk_category") and False:\n',
     ["pytest"],
     {"pytest:test_report_memory_groups_by_dimension_not_risk_type"}),

    ("M5 评审链汇总换回库内类别（= 改前的真实缺陷）", REVIEW,
     '            k = (f.get("risk_category") or _bucket) if _bucket else (f.get("category") or "未分类")',
     '            k = f.get("category") or "未分类"',
     ["pytest"],
     {"pytest:test_render_summary_groups_by_dimension",
      "pytest:test_render_summary_unmapped_gets_own_bucket_last"}),

    ("M6 未映射的并进「合规」（桶被抹掉）", REVIEW,
     '            k = (f.get("risk_category") or _bucket) if _bucket else (f.get("category") or "未分类")',
     '            k = f.get("risk_category") or "合规"',
     ["pytest"],
     {"pytest:test_render_summary_unmapped_gets_own_bucket_last"}),

    ("M7 P0 快路汇总换回库内类别（另一端不同口径）", P0,
     '    return m.dimension_of(cat)[0] or m.UNMAPPED_BUCKET',
     '    return cat',
     ["p0"],
     {"p0:⑥g2", "p0:⑥g3b"}),

    ("M8 桶名改成真维度名（「不知道」当「合规」，跨两端）", RC,
     'UNMAPPED_BUCKET = "未标注维度"',
     'UNMAPPED_BUCKET = "合规"',
     ["rc", "pytest"],
     {"rc:⑪",
      "pytest:test_report_marks_unmapped_as_pending_not_fabricated",
      "pytest:test_render_summary_unmapped_gets_own_bucket_last"}),
]


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _baseline():
    out = {}
    for name, fn in RUNNERS.items():
        rc, ids = fn()
        out[name] = (rc, ids)
    return out


def main():
    base = _baseline()
    bad_base = {k: v for k, v in base.items() if v[0] != 0 or v[1]}
    print("基线：" + " ｜ ".join("%s exit=%s 失败=%s" % (k, v[0], sorted(v[1]) or "无")
                                for k, v in base.items()))
    if bad_base:
        print("❌ 基线没过（判据自己就是红的）⇒ 停止")
        return 2

    ok = bad = 0
    for name, target, old, new, runners, expect in MUT:
        src = open(target, encoding="utf-8").read()
        if src.count(old) != 1:
            print("❌ %-52s 锚点不唯一(%d) —— 改过代码就要同步改这里" % (name, src.count(old)))
            bad += 1
            continue
        before = _sha(target)
        bak = target + ".mutbak"
        shutil.copy2(target, bak)
        failed = set()
        rc_all = 0
        try:
            open(target, "w", encoding="utf-8").write(src.replace(old, new, 1))
            for rn in runners:
                rc, ids = RUNNERS[rn]()
                rc_all = rc_all or rc
                failed |= {"%s:%s" % (rn, i) for i in ids}
        finally:
            shutil.copy2(bak, target)
            os.unlink(bak)
        if _sha(target) != before:
            print("❌ %-52s 还原失败（sha 变了）⇒ 立即停止" % name)
            return 4

        missing, extra = expect - failed, failed - expect
        if rc_all != 0 and not missing and not extra:
            ok += 1
            print("✅ %-52s ⇒ 精确变红：%d 例" % (name, len(expect)))
        elif missing:
            bad += 1
            print("❌ %-52s ⇒ **漏**：该红的没红 %s（实际失败 %s）"
                  % (name, sorted(missing), sorted(failed) or "无"))
        else:
            bad += 1
            print("❌ %-52s ⇒ **脆**：多红了 %s" % (name, sorted(extra)))

    after = _baseline()
    print("\n收尾复跑：" + " ｜ ".join("%s exit=%s 失败=%s" % (k, v[0], sorted(v[1]) or "无")
                                      for k, v in after.items()))
    if any(v[0] != 0 or v[1] for v in after.values()):
        print("❌ 还原后判据仍是红的 ⇒ 盘上留了残迹")
        return 4

    print("\n变异自证：%d 通过 / %d 失败" % (ok, bad))
    return 0 if bad == 0 else 3


raise SystemExit(main())
