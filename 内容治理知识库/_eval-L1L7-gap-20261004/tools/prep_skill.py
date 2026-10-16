#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为一件 skill 准备隔离评测工作台：**冻结挂载位 + freeze-manifest + 专用 profile**。

三处落点（沿用既有约定，不新造）：
  ① 挂载位   <本工程>/mounts/<tag>/<skill>/     ← basename **必须** = skill 名，否则同名胜出不成立
  ② 冻结清单 <本工程>/mounts/<tag>/freeze-manifest.json   逐文件 sha256 + diff 必须为空
  ③ 隔离 profile  ~/.dsh/profiles/eval-<tag>/cordis.patch.yml
       给 skill-filesystem 加 customSkillDirs（rank 300 < user-dsh 400）⇒ 同名者由本根胜出，
       盲测会话**只看到挂载位版本**，绝不会看到 ~/.dsh/skills/<skill>。

用法：
  python3 prep_skill.py --skill kb-p0-check --src <真源目录> --tag p0symlink
"""
import argparse
import hashlib
import json
import os
import shutil

PROFILES = os.path.expanduser("~/.dsh/profiles")
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)

CORDIS_YML = """# dsh profile root — an empty entry list. The tree is composed as patches:
# each bundle in package.json's dsh.profile.bundles, then cordis.patch.yml, then any
# --patch overlays. Edit cordis.patch.yml, not this file.
[]
"""

PATCH_TMPL = """# 隔离评测 profile（{skill} 专用）—— 不改共享 profile。
# 目的：盲测会话必须只看到挂载位里的那一份，绝不能看到 ~/.dsh/skills/{skill}。
# 手法：给 skill-filesystem 加一个 custom 根（rank 300 < user-dsh 400），同名者由本根胜出。
#
# ★★★ 2026-10-04 重大更正（此前本模板写错过，导致隔离从未生效）：
#   `customSkillDirs` 的每一项必须是**装着 skill 子目录的父目录**，
#   **不是** skill 目录本身。加载器按 root 扫子目录再拼 SKILL.md：
#     node_modules/@deepseek-ai/dsh-skill-filesystem/lib/index.js:583-587
#       const entries = await listSkillRootEntries(root, ctx);
#       for (const entry of entries...) path: join(entry.path, "SKILL.md")
#   指到 skill 目录本身 ⇒ 只会扫到 references/ 与 scripts/，拼出
#   `references/SKILL.md`（不存在）⇒ **该根贡献 0 条** ⇒ 同名者照旧来自
#   ~/.dsh/skills（源版）⇒ **测出来的其实是源版**。
#   实测确认：media 的挂载位 description 折叠 483 字，而会话渲染出的是源版的 660 字。
#   落点 = 父目录 {mountroot}（其下 {skill}/ 的 basename 必须 = skill 名）。
- id: skill-filesystem
  config:
    customSkillDirs:
      - '{mountroot}'
"""


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tree_sha(root, exclude_prefixes=()):
    out = {}
    for dp, _dn, fn in os.walk(root):
        for f in sorted(fn):
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, root)
            if any(rel.startswith(x) for x in exclude_prefixes):
                continue
            out[rel] = sha256(full)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--src", required=True, help="被测 skill 的真源目录（只读）")
    ap.add_argument("--tag", required=True, help="评 batch 标识，profile 将成为 eval-<tag>")
    ap.add_argument("--force", action="store_true", help="挂载位已存在时覆盖重建")
    a = ap.parse_args()

    skill = a.skill
    tag = a.tag
    src = os.path.abspath(a.src)
    if not os.path.isfile(os.path.join(src, "SKILL.md")):
        raise SystemExit(f"!! {src} 下没有 SKILL.md")
    if os.path.basename(src) != skill:
        raise SystemExit(f"!! 真源目录名 {os.path.basename(src)} != skill 名 {skill}")

    mount_root = os.path.join(PROJ, "mounts", tag)
    mount = os.path.join(mount_root, skill)
    if os.path.exists(mount):
        if not a.force:
            raise SystemExit(f"!! 挂载位已存在：{mount}（要覆盖加 --force）")
        shutil.rmtree(mount)
    os.makedirs(mount_root, exist_ok=True)
    # 源可能只读（dr-xr-xr-x）⇒ copytree 只读即可
    shutil.copytree(src, mount, symlinks=True)

    man = {"tag": tag, "skill": skill, "source": src,
           "mount": tree_sha(mount), "diff": []}
    json.dump(man, open(os.path.join(mount_root, "freeze-manifest.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)

    prof = os.path.join(PROFILES, f"eval-{tag}")
    # ★ 护栏（2026-10-04 实测踩过）：**已有 profile 不许静默覆盖**。
    #   本批曾用 tag=recallfix 撞上 L0 工程早已存在的 eval-recallfix，把它的
    #   customSkillDirs 改指到别处 ⇒ 破坏了那条线。已有 profile 必须先人工确认或换 tag。
    if os.path.exists(os.path.join(prof, "cordis.patch.yml")) and not a.force:
        raise SystemExit(
            f"!! profile eval-{tag} 已存在且已有 cordis.patch.yml：{prof}\n"
            f"   拒绝静默覆盖（可能属于别的评测线）。请换一个 --tag，或确认后加 --force。")
    os.makedirs(prof, exist_ok=True)
    os.makedirs(os.path.join(prof, "node_modules"), exist_ok=True)
    os.makedirs(os.path.join(prof, ".dsh-module-fallback", "node_modules"), exist_ok=True)
    open(os.path.join(prof, "cordis.yml"), "w", encoding="utf-8").write(CORDIS_YML)
    open(os.path.join(prof, "cordis.patch.yml"), "w", encoding="utf-8").write(
        PATCH_TMPL.format(skill=skill, mount=mount, mountroot=mount_root))
    json.dump({"name": f"dsh-profile-eval-{tag}", "private": True,
               "dsh": {"profile": {"bundles": ["@deepseek-ai/dsh-base",
                                               "@deepseek-ai/dsh-headless"],
                                   "patchReload": "startup"}}},
              open(os.path.join(prof, "package.json"), "w", encoding="utf-8"), indent=2)
    open(os.path.join(prof, "pnpm-workspace.yaml"), "w", encoding="utf-8").write(
        "packages:\n  - .\n\nnodeLinker: hoisted\nautoInstallPeers: false\n")

    files = len(man["mount"])
    print(f"✅ {skill} @ tag={tag}")
    print(f"   挂载位   {mount}  （{files} 个文件）")
    print(f"   冻结清单 {os.path.join(mount_root, 'freeze-manifest.json')}  diff={man['diff']}")
    print(f"   profile  eval-{tag}  →  {prof}")
    print(f"   自证：python3 {os.path.join(HERE, 'extract_catalog.py')} --skill {skill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
