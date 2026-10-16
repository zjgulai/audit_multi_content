#!/usr/bin/env python3
"""变异自证（risk_category）：只在副本上变异，源文件不改。★ 副本必须落**同目录**（靠 realpath 定位政策件）。"""
import os, subprocess, sys
KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts", "risk_category.py")
MUT = [
 ("M1 未映射的类别也蒙一个维度（把「不知道」当「合规」）", "④[原则性错误]留空且说待裁",
  ('    if un:\n        return None, "类别「%s」**未映射，待裁** —— %s" % (c, str(un)[:120])',
   '    if un:\n        return "合规", "类别「%s」**未映射，待裁** —— %s" % (c, str(un)[:120])')),
 ("M2 政策件读不到时退回内嵌兜底映射（= 造第二份口径）", "⑦ 政策件空 ⇒ 不编（无内嵌兜底）",
  ('    if not m:\n        return None, "政策件不可用（%s）⇒ **不编**" % (_POLICY_ERR or "未加载")',
   '    if not m:\n        return "合规", "内嵌兜底"')),
 ("M3 stamp 顺手改掉别的键（越权）", "⑧ stamp 只加两键",
  ('    finding["risk_category"] = lvl\n    finding["risk_category_basis"] = why\n    return finding',
   '    finding["risk_category"] = lvl\n    finding["risk_category_basis"] = why\n    finding.pop("reason", None)\n    return finding')),
]
def main():
    b = subprocess.run([sys.executable, SRC, "--selftest"], capture_output=True, text=True)
    print("基线：%s" % (b.stdout.strip().splitlines() or [""])[-1])
    if b.returncode: print("❌ 基线没过"); return 2
    src = open(SRC, encoding="utf-8").read(); ok = bad = 0
    d = os.path.dirname(SRC)
    for name, expect, (a, c) in MUT:
        if src.count(a) != 1:
            print("❌ %-44s 锚点不唯一(%d)" % (name, src.count(a))); bad += 1; continue
        p = os.path.join(d, "_mut_rc.py")
        open(p, "w", encoding="utf-8").write(src.replace(a, c))
        r = subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True)
        hit = ("✗ " + expect) in r.stdout
        if r.returncode and hit:
            ok += 1; print("✅ %-44s ⇒ 变红且精确命中 %s" % (name, expect))
        else:
            bad += 1; print("❌ %-44s ⇒ 没红/没命中预期 (exit=%s)" % (name, r.returncode))
        try: os.unlink(p)
        except OSError: pass
    print("\n变异自证：%d 通过 / %d 失败" % (ok, bad))
    return 0 if bad == 0 else 3
raise SystemExit(main())
