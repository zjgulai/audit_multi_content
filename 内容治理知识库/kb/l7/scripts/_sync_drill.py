#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_sync_drill.py —— P2 写档编排（kb_pipeline.py --sync）的**演练台**：在夹具库上真跑写档。

## 为什么必须在夹具里跑

`--sync --apply` 会调各层引擎**真落盘**。当前口径是「两周只读观察期」，所以：
  * 真库只读：演练开始/结束各取一次真库 L2/L3 台账的 sha256，**必须一模一样**；
  * 写档动作在**夹具库**里做 —— 夹具是 kb/ 的镜像（真目录 + 文件软链），
    凡引擎会 append 的文件（units.jsonl / index/l2.jsonl / manifest_l2.jsonl / rejected.jsonl）
    都先换成**真副本**，避免写穿软链改到真库。

## 夹具必须做对的两件事（第一版踩过，记在这）

1. **夹具根下要有一层 `kb/`**：引擎与闸门里全是 `kb/...` 相对路径，按 cwd 解析。
   少了这层，读取会穿透回真库（反测台那边也踩过同一个坑）。
2. **`kb_pipeline.py` 必须是夹具里的真副本**：它用 `__file__` 反推 `KB`，
   若还是软链（指向真库），编排器会以为自己在真库上跑 —— **这是能写坏真库的错**。
   同理 `layers.yaml` 里的 `cwd` 也要改写成夹具根。

## 演练用例

  A 预演        `--sync --only L2`            → 不落盘、产物 0 变化
  B 写档幂等    `--sync --only L2 --apply` ×2 → 第二遍必须报「幂等」且三份数据文件逐字节相同
  C 红线②锁     造一个「持有者还活着」的锁 → 写档被拒（exit 2）
  D 红线③红闸门 把夹具里的 L2 闸门改成必红 → 写档**在写之前**停下，夹具 L2 数据不动
  E 红线①归档   `--sync --only L3 --check-archive` → 归档成功且 sha 一致；归档目录不可写 → 拒绝

用法：
    kb/kbpy l7/scripts/_sync_drill.py [--keep]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(KB)

# 引擎会 append 的文件 → 夹具里必须是真副本（否则写穿软链 = 写坏真库）
REALIZE = [
    "l7/scripts/kb_pipeline.py",
    "l7/registry/layers.yaml",
    "l2/units.jsonl", "l2/index/l2.jsonl", "l2/manifest_l2.jsonl", "l2/registry/l2.json",
    "l3/rejected.jsonl",
    "l7/scripts/l2_gate.py",
    "l7/scripts/daily_health.py",       # 夹具里也要真副本：它用 __file__ 反推 KB
    # ⚠️ kbpy 也必须换成真副本：它按**自己的真实路径**反推库根。
    # 夹具里若只是软链，kbpy 会解析回真库 → 夹具里跑的其实是真的 pipeline（第一版 D2 就是这么假的）。
    "kbpy",
    "l7/reports/2026-09-30-daily-health.md",   # 日报是写入目标：软链会被写穿到真库
    "l7/reports/daily-health-latest.json",
]
MIRROR = ["l0", "l1", "l2", "l3", "l8", ".work", "l7", "versions"]
GUARD = ["l2/units.jsonl", "l2/index/l2.jsonl", "l2/manifest_l2.jsonl", "l3/rejected.jsonl"]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def guard_real():
    return {p: sha(os.path.join(KB, p)) for p in GUARD if os.path.exists(os.path.join(KB, p))}


def mirror(dst):
    for sub in MIRROR:
        src_root = os.path.join(KB, sub)
        for dirpath, dirnames, filenames in os.walk(src_root):
            rel = os.path.join("kb", os.path.relpath(dirpath, KB))
            os.makedirs(os.path.join(dst, rel), exist_ok=True)
            for fn in filenames:
                link = os.path.join(dst, rel, fn)
                if not os.path.lexists(link):
                    os.symlink(os.path.join(dirpath, fn), link)
    for fn in (".kb-python",):
        src = os.path.join(KB, fn)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(dst, "kb", fn))


def realize(fix, rel):
    """把夹具里的某个路径换成**真副本**。

    两种情况都要覆盖（第二版才补上，第一版漏了它导致 D2 假绿）：
      * 夹具里已有这个路径（镜像造的软链）→ 拆掉软链，复制真库那份过来；
      * 夹具里**根本没有**这个路径（MIRROR 只镜像目录树，kb 根下的文件如 kbpy 不在其中）
        → 建好父目录，直接复制。少了这一支，夹具里就没有 kbpy，
          而 daily_health.py 正是用 `<KB>/kbpy` 去驱动 pipeline 的 → 命令行直接失败，
          日报照写不误但内容是空的（**假绿**）。
    """
    p = os.path.join(fix, "kb", rel)
    src = os.path.realpath(p) if os.path.islink(p) else os.path.join(KB, rel)
    if os.path.islink(p):
        os.unlink(p)
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copyfile(src, p)
        if rel == "kbpy":
            os.chmod(p, 0o755)
    return p


def build(fix):
    os.makedirs(fix, exist_ok=True)
    mirror(fix)
    for rel in REALIZE:
        realize(fix, rel)
    # layers.yaml：cwd 全部改写成夹具根（否则闸门/引擎的 cwd 指向真库）
    ly = os.path.join(fix, "kb/l7/registry/layers.yaml")
    txt = open(ly, encoding="utf-8").read()
    txt = re.sub(r"(?m)^(\s*cwd:\s*).*$", lambda m: m.group(1) + fix.replace("\\", "/"), txt)
    open(ly, "w", encoding="utf-8").write(txt)
    return fix


def pipe(fix, args, env_extra=None):
    env = dict(os.environ, KB_INTERP_OK="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("KB_GATE_KB", None)
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([sys.executable, os.path.join(fix, "kb/l7/scripts/kb_pipeline.py")] + args,
                       cwd=fix, capture_output=True, text=True, env=env, timeout=1800)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def snap(fix, rels):
    out = {}
    for p in rels:
        q = os.path.join(fix, "kb", p)
        out[p] = sha(q) if os.path.isfile(q) else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--only", default=None, help="只跑某个用例（如 D2）")
    a = ap.parse_args()

    before_real = guard_real()
    tmp = tempfile.mkdtemp(prefix="kb-sync-drill-")
    results, bad = [], 0

    def rec(name, ok, detail):
        nonlocal bad
        if a.only and not name.startswith(a.only):
            return
        if not ok:
            bad += 1
        results.append((name, ok, detail))

    # ── 基线：夹具造好后，先复核夹具与真库数据一致 ──────────────────────────
    fix = build(os.path.join(tmp, "kb-sync"))
    L2F = ["l2/units.jsonl", "l2/index/l2.jsonl", "l2/manifest_l2.jsonl"]
    base = snap(fix, L2F)
    rec("0 夹具就绪", all(base.values()) and base == {p: sha(os.path.join(KB, p)) for p in L2F},
        "夹具 L2 三份数据与真库逐字节一致（真副本，不是软链）")

    # ── A 预演 ────────────────────────────────────────────────────────────
    if not a.only or a.only.startswith("A"):
        pass
    rc, out = pipe(fix, ["--sync", "--only", "L2"])
    same = snap(fix, L2F) == base
    rec("A 预演不落盘", rc == 0 and same,
        "exit=%d ｜ 数据变化 %s ｜ %s" % (rc, "无" if same else "有",
                                       [l for l in out.splitlines() if "dry-run" in l][:1]))

    # ── B 写档 ×2：幂等 ───────────────────────────────────────────────────
    rc1, out1 = pipe(fix, ["--sync", "--only", "L2", "--apply", "--run", "20260930-1101"])
    s1 = snap(fix, L2F)
    rc2, out2 = pipe(fix, ["--sync", "--only", "L2", "--apply", "--run", "20260930-1102"])
    s2 = snap(fix, L2F)
    idem_marker = "幂等" in out2 or "产物变化 0 个" in out2
    rec("B 写档幂等", rc1 == 0 and rc2 == 0 and s1 == s2 and idem_marker,
        "run1 exit=%d ｜ run2 exit=%d ｜ 两次后数据%s ｜ run2 %s"
        % (rc1, rc2, "逐字节相同" if s1 == s2 else "**不同**",
           [l.strip() for l in out2.splitlines() if "幂等" in l or "产物变化" in l][:1]))

    # ── C 红线②：锁 ───────────────────────────────────────────────────────
    lock = os.path.join(fix, "kb/.work/.kb.lock")
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    json.dump({"run_id": "drill", "pid": os.getpid(), "at": "now"}, open(lock, "w", encoding="utf-8"))
    rc3, out3 = pipe(fix, ["--sync", "--only", "L2", "--apply"])
    rec("C 红线②锁生效", rc3 == 2 and "已有锁" in out3,
        "exit=%d ｜ %s" % (rc3, [l.strip() for l in out3.splitlines() if "锁" in l][:1]))
    os.remove(lock)

    # ── D 红线③：闸门红 → 写之前就停 ──────────────────────────────────────
    gate_path = os.path.join(fix, "kb/l7/scripts/l2_gate.py")
    orig = open(gate_path, encoding="utf-8").read()
    open(gate_path, "w", encoding="utf-8").write(
        orig.replace('if __name__ == "__main__":', 'if __name__ == "__main__":\n    sys.exit(1)  # drill: 强制红'))
    s_pre = snap(fix, L2F)
    rc4, out4 = pipe(fix, ["--sync", "--only", "L2", "--apply", "--run", "20260930-1103"])
    rec("D 红线③红闸门即停", rc4 == 1 and snap(fix, L2F) == s_pre and "停下" in out4,
        "exit=%d ｜ 数据未动=%s ｜ %s" % (rc4, snap(fix, L2F) == s_pre,
                                       [l.strip() for l in out4.splitlines() if "闸门" in l or "停下" in l][:2]))
    open(gate_path, "w", encoding="utf-8").write(orig)

    # ── D2 失败清单（P3）：闸门红时，日报必须点名「哪层 / 谁 / 跑什么」──────
    # 闸门此刻仍是上面 D 用例改红的那个（D 用例跑完会还原，所以这里重新改红）
    open(gate_path, "w", encoding="utf-8").write(
        orig.replace('if __name__ == "__main__":', 'if __name__ == "__main__":\n    sys.exit(1)  # drill'))
    env = dict(os.environ, KB_INTERP_OK="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("KB_GATE_KB", None)
    r = subprocess.run([sys.executable, os.path.join(fix, "kb/l7/scripts/daily_health.py")],
                       cwd=fix, capture_output=True, text=True, env=env, timeout=1800)
    rep = os.path.join(fix, "kb/l7/reports/2026-09-30-daily-health.md")
    md = open(rep, encoding="utf-8").read() if os.path.isfile(rep) else ""
    ok_d2 = ("L2 闸门红" in md) and ("谁" in md and "l2_gate.py" in md)
    open(gate_path, "w", encoding="utf-8").write(orig)
    rec("D2 失败清单点名到人", ok_d2,
        "日报里 %s ｜ %s" % ("有「L2 闸门红」" if "L2 闸门红" in md else "**没点名**",
                            next((l.strip()[:100] for l in md.splitlines() if "谁" in l), "无处置行")))

    # ── E 红线①：归档 ─────────────────────────────────────────────────────
    rc5, out5 = pipe(fix, ["--sync", "--only", "L3", "--check-archive", "--run", "20260930-1104"])
    arch = os.path.join(fix, "kb/l3/_archive/rejected-pre-20260930-1104.jsonl")
    ok_arch = os.path.isfile(arch) and sha(arch) == sha(os.path.join(fix, "kb/l3/rejected.jsonl"))
    rec("E 红线①归档可执行", rc5 == 0 and ok_arch,
        "exit=%d ｜ 归档 sha 一致=%s ｜ %s" % (rc5, ok_arch,
                                            [l.strip()[:90] for l in out5.splitlines() if "已归档" in l][:1]))
    # 归档目录不可写 → 必须拒绝（不许「归档失败还接着写」）
    adir = os.path.join(fix, "kb/l3/_archive")
    os.chmod(adir, stat.S_IRUSR | stat.S_IXUSR)
    try:
        rc6, out6 = pipe(fix, ["--sync", "--only", "L3", "--check-archive", "--run", "20260930-1105"])
    finally:
        os.chmod(adir, stat.S_IRWXU)
    rec("E2 归档失败即拒绝", rc6 == 1 and "红线①" in out6,
        "exit=%d ｜ %s" % (rc6, [l.strip()[:90] for l in out6.splitlines() if "❌" in l][:1]))

    # ── 真库守门 ──────────────────────────────────────────────────────────
    after_real = guard_real()
    rec("F 真库一个字节未动", before_real == after_real,
        "L2/L3 台账 sha256 演练前后一致（%d 个文件）" % len(before_real))

    print("=" * 100)
    print("P2 写档编排演练（夹具库上真跑 --apply；真库只读并逐字节复核）")
    print("=" * 100)
    for name, ok, detail in results:
        print("%-22s %s  %s" % (name, "✅" if ok else "❌", detail))
    print("-" * 100)
    print("合计 %d 例，通过 %d，未通过 %d" % (len(results), len(results) - bad, bad))
    print("夹具：%s%s" % (os.path.join(tmp, "kb-sync"), "" if a.keep else "（用完即删）"))
    if not a.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
