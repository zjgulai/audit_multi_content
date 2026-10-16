#!/usr/bin/env python3
"""变异自证（audit_sample）：把缺陷真造一遍，尺子必须**精确变红**。只在副本上变异。"""

from __future__ import annotations
import os, re, shutil, subprocess, sys, tempfile

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(KB, "l8", "audit_sample.py")

MUTATIONS = [
    ("M1 预填「人判」栏（= 把人工抽检这道工序删掉）", "⑥ 人判栏全空（反向对照）",
     ('                    "", "", ""])          # ★ 人判三列**留空**',
      '                    _state_of(r), "自动填的", "机器"])   # ← 变异：预填')),
    ("M2 不去重（同一素材的复跑全留下）", "① 复跑只留最早",
     ('        if dedup:\n            deduped.append(g[0])',
      '        if False:\n            deduped.append(g[0])')),
    ("M3 一条没填也报「通过」（返回 0 而不是 3）", "⑦ 未填 ⇒ 退出码 3（未测，不是 0 分）",
     ('        print("⛔ **还没有人判** —— 抽查记录为空。这不是「通过」，是**未测**（不许按 0 或 100 报）。")\n        return 3',
      '        print("✅ 全部通过（0 条分母）")\n        return 0')),
    ("M4 不按比例分层（全抽第一层）", "④d[PASS] 按比例",
     ('        exact = n * L / total\n        quota[k] = min(L, max(1, int(exact)))',
      '        exact = n * L / total\n        quota[k] = L if k == "BLOCK" else 0')),
]


def main() -> int:
    base = subprocess.run([sys.executable, SRC, "--selftest"], capture_output=True, text=True)
    first = (base.stdout.strip().splitlines() or [""])[-1]
    print("基线：%s" % first)
    if base.returncode != 0:
        print("❌ 基线没过"); return 2
    src = open(SRC, encoding="utf-8").read()
    # ★ 副本必须放**同目录**：`audit_sample.py` 靠 `__file__` 定位 `kb/.work/_safe_write.py`，
    #   放 /tmp 会 ModuleNotFoundError（首版就栽在这）。
    tmp = os.path.join(KB, "l8")
    ok = bad = 0
    for name, expect, (a, b) in MUTATIONS:
        if src.count(a) != 1:
            print("❌ %-42s 变异锚点不唯一（%d 处）" % (name, src.count(a)))
            bad += 1
            continue
        p = os.path.join(tmp, "_mut_audit_sample.py")
        open(p, "w", encoding="utf-8").write(src.replace(a, b))
        r = subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True)
        hit = ("✗ " + expect) in r.stdout
        if r.returncode != 0 and hit:
            ok += 1
            print("✅ %-42s ⇒ 变红且精确命中 %s" % (name, expect))
        else:
            bad += 1
            print("❌ %-42s ⇒ 没红/没命中预期" % name)
            print("      exit=%s" % r.returncode)
            for line in (r.stdout + r.stderr).splitlines()[-6:]:
                print("      | %s" % line)
    try:
        os.unlink(os.path.join(tmp, "_mut_audit_sample.py"))
    except OSError:
        pass
    print()
    print("变异自证：%d 通过 / %d 失败" % (ok, bad))
    return 0 if bad == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
