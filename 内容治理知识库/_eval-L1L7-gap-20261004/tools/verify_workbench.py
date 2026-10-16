#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作台自检 / 唯一性核对（对应任务书第八部分要交的那张表）。

对每件 skill 打印：真源路径 → 装载位路径 → 当前有几个同名副本 → sha 是否一致 → 各副本角色。
并核对：冻结清单 diff 为空、profile 指向正确挂载位、用例集齐全。

用法：python3 tools/verify_workbench.py            # 只看被测的 8 件
      python3 tools/verify_workbench.py --all      # 连工作台细节一起打
"""
import argparse
import hashlib
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
ROOT = os.path.dirname(PROJ)                      # 内容治理/
SKILLS_SRC = os.path.join(ROOT, "kb", "l7", "skills")
USER_SKILLS = os.path.expanduser("~/.dsh/skills")
PROFILES = os.path.expanduser("~/.dsh/profiles")

SKILLS = ["kb-l0-feishu", "kb-ingest-extractor", "kb-media-extractor", "kb-clause-extractor",
          "kb-canonical-lookup", "kb-p0-check", "kb-recall", "kb-check"]


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def find_all(name):
    """全盘找同名 skill 目录（限定已知根，避免全盘扫描拖死）。"""
    hits = []
    for base in (SKILLS_SRC, USER_SKILLS, os.path.join(ROOT, ".dsh", "skills"),
                 os.path.join(PROJ, "fix"), os.path.join(PROJ, "mounts")):
        if not os.path.isdir(base):
            continue
        for dp, dn, _fn in os.walk(base):
            if dp.count(os.sep) - base.count(os.sep) > 2:
                dn[:] = []
                continue
            for d in list(dn):
                if d == name:
                    hits.append(os.path.join(dp, d))
    return sorted(set(hits))


def role(path):
    if path.startswith(SKILLS_SRC):
        return "真源"
    if path.startswith(os.path.join(ROOT, ".dsh")):
        return "工作区装载位"
    if path == os.path.join(USER_SKILLS, os.path.basename(path)):
        return "装载位"
    if "/fix/" in path:
        return "fix 副本"
    if "/mounts/" in path:
        tag = path.split("/mounts/")[1].split("/")[0]
        return f"冻结靶点({tag})"
    return "其它"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    print("=" * 118)
    print("工作台自检 / 唯一性核对")
    print("=" * 118)
    for s in SKILLS:
        src = os.path.join(SKILLS_SRC, s)
        inst = os.path.join(USER_SKILLS, s)
        print(f"\n### {s}")
        src_md = os.path.join(src, "SKILL.md")
        inst_md = os.path.join(inst, "SKILL.md")
        s1 = sha(src_md) if os.path.isfile(src_md) else "—"
        s2 = sha(inst_md) if os.path.isfile(inst_md) else "—"
        kind = ("symlink → " + os.readlink(inst)) if os.path.islink(inst) else \
               ("dir" if os.path.isdir(inst) else "不存在")
        print(f"  真源      {src}   sha={s1}")
        print(f"  装载位    {inst}   [{kind}]   sha={s2}   "
              f"{'一致 ✓' if s1 == s2 else '★不一致（若为 symlink 则正常：同一份）'}")

        # 用例集
        cm = os.path.join(PROJ, "cases", s, "cases-meta.json")
        if os.path.isfile(cm):
            d = json.load(open(cm, encoding="utf-8"))
            print(f"  用例      a={len(d.get('a_cases',[]))} call={len(d.get('call_cases',[]))} "
                  f"b={len(d.get('b_cases',[]))}   "
                  f"{'✓' if d.get('a_cases') else '★缺 A 卷'}"
                  f"{'' if d.get('b_cases') else '　★缺 B 卷（交付门禁用）'}")
        else:
            print("  用例      ★无 cases-meta")

        # 挂载位 / profile
        mroot = os.path.join(PROJ, "mounts")
        tags = []
        if os.path.isdir(mroot):
            for t in sorted(os.listdir(mroot)):
                if os.path.isdir(os.path.join(mroot, t, s)):
                    fm = os.path.join(mroot, t, "freeze-manifest.json")
                    ok = "?"
                    if os.path.isfile(fm):
                        ok = "diff=[] ✓" if not json.load(open(fm, encoding="utf-8")).get("diff") else "★diff 非空"
                    patch = os.path.join(PROFILES, f"eval-{t}", "cordis.patch.yml")
                    pdir = "?"
                    if os.path.isfile(patch):
                        pdir = ("profile→本靶点 ✓"
                                if os.path.join(mroot, t, s) in open(patch, encoding="utf-8").read()
                                else "★profile 未指向本靶点")
                    tags.append(f"{t}({ok}, {pdir})")
        print(f"  靶点      {'; '.join(tags) if tags else '（无）'}")

        if a.all:
            hits = find_all(s)
            print(f"  同名副本  {len(hits)} 处：")
            for h in hits:
                md = os.path.join(h, "SKILL.md")
                print(f"      [{role(h):<16}] {h}   sha={sha(md) if os.path.isfile(md) else '—'}")
    print()
    print("说明：真源与装载位**同 sha** 表示二者为镜像；若装载位是 symlink，则物理上只有一份。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
