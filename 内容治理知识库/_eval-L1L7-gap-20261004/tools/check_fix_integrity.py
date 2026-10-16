#!/usr/bin/env python3
"""替换前后的完整性校验器（要复用 7 次，不许每件手搓）。

三件事，各自独立报，**不通过就非零退出**：

① 三处同源 sha（用户 2026-10-04 裁定：**「存在则必须一致」**）
   真源   <库根>/kb/l7/skills/<skill>
   装载位  ~/.dsh/skills/<skill>
   第三处  <库根>/.dsh/skills/<skill>  ← **不存在不算「缺一」**；存在则 sha 必须与真源一致
   ⚠️ 第三处**不许新建副本**（与「所有 skill 只留两份」的裁定冲突）。
   判据：真源为基准；装载位 / 第三处**凡存在就必须等于真源**。

② 正文点名路径必须真实存在（**本批特有风险**）
   7 件 fix 都动过正文结构与章节号（例：kb-ingest-extractor 把 §2/§2.1 共 1270 字符
   下沉到**新建的** references/engine-commands.md）。
   层引擎是**由 agent 照 skill 正文去调的** ⇒ 正文点了名、文件却不在 = **链路断**。
   ★ 只报「点名了但不存在」；**不报**「文件存在但正文没点名」（那是候选优化项，不是缺陷）。

③ 正文提到的别件 skill 名（只报，不判红）。

两种用法（**判据不同，别混**）：

  替换**前**（量 fix 副本，此时 fix 还没装，**真源≠fix 是正常的、不判红**）：
      python3 tools/check_fix_integrity.py <skill> --dir fix
      python3 tools/check_fix_integrity.py --all           # 默认 --dir fix

  替换**后**（要求真源 / 装载位 / 第三处 / fix 四处全等）：
      python3 tools/check_fix_integrity.py <skill> --after --dir fix
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KB_ROOT = os.path.dirname(ROOT)                       # <库根>
TRUE_SRC = os.path.join(KB_ROOT, "kb", "l7", "skills")
INSTALL = os.path.expanduser("~/.dsh/skills")
THIRD = os.path.join(KB_ROOT, ".dsh", "skills")

SKILLS = [
    "kb-media-extractor", "kb-clause-extractor", "kb-ingest-extractor",
    "kb-check", "kb-p0-check", "kb-recall", "kb-canonical-lookup",
]

RES_DIRS = ("references", "scripts", "assets", "templates")
PATH_RE = re.compile(
    r"(?<![\w/-])(" + "|".join(RES_DIRS) + r")/([A-Za-z0-9_][A-Za-z0-9._/-]*[A-Za-z0-9_])"
)


def sha(path):
    if not os.path.isfile(path):
        return None
    out = subprocess.run(["shasum", "-a", "256", path],
                         capture_output=True, text=True)
    return out.stdout.split()[0][:12] if out.returncode == 0 else None


def ssha(d):
    return sha(os.path.join(d, "SKILL.md")) if d else None


def version(d):
    p = os.path.join(d, "SKILL.md")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.startswith("version:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def fmt(label, d):
    s = ssha(d)
    if s:
        return f"   {label:<30} {s}  v{version(d)}"
    return f"   {label:<30} （不存在）"


def check_three_sources(skill, fix_dir=None, after=False):
    """① 三处同源。真源为基准；装载位/第三处凡存在必须等于真源。

    after=True 时额外要求 fix_dir 也等于真源（= 替换真的生效了）。
    """
    print("\n① 三处同源 sha（裁定：存在则必须一致；不存在不算缺一）")
    t = os.path.join(TRUE_SRC, skill)
    i = os.path.join(INSTALL, skill)
    h = os.path.join(THIRD, skill)
    print(fmt("真源   kb/l7/skills", t))
    print(fmt("装载位 ~/.dsh/skills", i))
    print(fmt("第三处 <库根>/.dsh/skills", h))
    if fix_dir:
        print(fmt("fix 副本（" + ("要求相等" if after else "替换前，不判红") + "）",
                  os.path.join(fix_dir, skill)))

    bad = []
    base = ssha(t)
    if base is None:
        bad.append("真源 SKILL.md 不存在")
    for label, d in (("装载位 ~/.dsh/skills", i),
                     ("第三处 <库根>/.dsh/skills", h)):
        s = ssha(d)
        if s is None:
            if "第三处" in label:
                print("   · 第三处不存在 ⇒ 按裁定**不算缺一**，不判红")
            else:
                bad.append(f"{label} 缺失（装载位必须在）")
        elif base and s != base:
            bad.append(f"{label} sha {s} ≠ 真源 {base}")

    if after and fix_dir:
        f = ssha(os.path.join(fix_dir, skill))
        if f != base:
            bad.append(f"**替换未生效**：fix 副本 sha {f} ≠ 真源 {base}")

    if bad:
        print("   ❌ " + "；".join(bad))
    else:
        print("   ✅ 通过" + ("（替换已生效，四处同源）" if after else "（现役三处自洽）"))
    return not bad


def check_referenced_paths(skill, base_dir):
    print(f"\n② 正文点名路径是否真实存在（目录：{base_dir}）")
    p = os.path.join(base_dir, "SKILL.md")
    if not os.path.isfile(p):
        print("   **SKILL.md 不存在，无法检查 ⇒ 判红**")
        return False
    body = open(p, encoding="utf-8").read()
    refs = sorted({f"{a}/{b}" for a, b in PATH_RE.findall(body)})
    if not refs:
        print("   （正文未点名任何 references/scripts/assets 路径）")
        return True
    missing = []
    for r in refs:
        ok = os.path.exists(os.path.join(base_dir, r))
        print(f"   {'✓' if ok else '❌'} {r}")
        if not ok:
            missing.append(r)
    if missing:
        print(f"   ❌ 点名但不存在 {len(missing)} 处：{missing}  ⇒ **链路断，不许替换**")
        return False
    print(f"   ✅ {len(refs)} 处点名全部存在")
    return True


def check_cross_skill(skill, base_dir):
    p = os.path.join(base_dir, "SKILL.md")
    if not os.path.isfile(p):
        return
    body = open(p, encoding="utf-8").read()
    hits = [s for s in SKILLS if s != skill and s in body]
    print(f"\n③ 正文提到的别件 skill（只报不判红）：{hits or '无'}")
    unknown = sorted({t for t in re.findall(r"\bkb-[a-z0-9-]+\b", body)
                      if t not in SKILLS})
    if unknown:
        print(f"   另提到本批之外的 kb-* 名字（正常，供人看）：{unknown}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("skill", nargs="?")
    ap.add_argument("--dir", default=None,
                    help="fix 副本的父目录（如 fix）；默认 <工作台>/fix")
    ap.add_argument("--after", action="store_true",
                    help="替换后模式：额外要求 fix 副本 sha == 真源")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    targets = SKILLS if a.all else ([a.skill] if a.skill else [])
    if not targets:
        ap.error("给一个 skill 名，或 --all")
    fixdir = a.dir or os.path.join(ROOT, "fix")

    ok = True
    for s in targets:
        sdir = os.path.join(fixdir, s)
        if not os.path.isdir(sdir):
            print(f"\n!! {s}：fix 目录不存在 {sdir}")
            ok = False
            continue
        print("=" * 78)
        print(f"校验 {s}   模式={'替换后(要求四处同源)' if a.after else '替换前'}")
        print("=" * 78)
        ok &= check_three_sources(s, fix_dir=fixdir, after=a.after)
        ok &= check_referenced_paths(s, sdir)
        check_cross_skill(s, sdir)

    print("\n" + "=" * 78)
    print("✅ 全部通过" if ok else "❌ 有不通过项，**不许替换/视为未生效**")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
