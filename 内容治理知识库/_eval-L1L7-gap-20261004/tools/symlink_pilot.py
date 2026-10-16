#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""symlink 装载位试点（用户裁定：**先在 kb-p0-check 单点验证加载器行为**）。

背景与代码级依据（已核实，非推测）：
  `@deepseek-ai/dsh-skill-filesystem/lib/index.js:755-771` `nodeEntryKind()`：
      if (entry.isDirectory()) return "directory";
      if (!entry.isSymbolicLink()) return void 0;
      const info = await stat(fullPath);          // stat 跟随符号链接
      if (info.isDirectory()) return "directory";
  ⇒ **目录符号链接会被识别为 directory**；另 `:499 watchFollowSymlinks ?? true` 默认跟随。

★ 必须配的护栏：链接**断裂**时该函数只打一条 warning 后 `return void 0`（**静默跳过**）
  ⇒ skill 会**从目录里消失**。故改装后必须用 `tools/extract_catalog.py --skill <name>`
  取一次**实渲染目录行**确认它还在（这就是链路自检）。

用法：
  python3 symlink_pilot.py --skill kb-p0-check --src <真源>            # 预演（不改任何东西）
  python3 symlink_pilot.py --skill kb-p0-check --src <真源> --apply    # 执行
  python3 symlink_pilot.py --skill kb-p0-check --rollback              # 回滚
"""
import argparse
import hashlib
import json
import os
import shutil
import time

SKILLS = os.path.expanduser("~/.dsh/skills")
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tree_sha(root):
    out = {}
    for dp, _dn, fn in os.walk(root):
        for f in sorted(fn):
            full = os.path.join(dp, f)
            out[os.path.relpath(full, root)] = sha256(full)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--src", default=None, help="真源目录（默认 kb/l7/skills/<skill>）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args()

    skill = a.skill
    dst = os.path.join(SKILLS, skill)
    src = os.path.abspath(a.src or os.path.join(PROJ, "..", "kb", "l7", "skills", skill))
    arch = os.path.join(PROJ, "_archive-装载位试点-20261004")

    if a.rollback:
        bak = os.path.join(arch, f"dsh-skills-{skill}")
        if not os.path.isdir(bak):
            raise SystemExit(f"!! 找不到归档 {bak}")
        if os.path.islink(dst):
            os.unlink(dst)
        elif os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(bak, dst, symlinks=True)
        print(f"✅ 已回滚：{dst}（来自 {bak}）")
        print("   自证：python3 tools/extract_catalog.py --skill " + skill)
        return 0

    print(f"skill      {skill}")
    print(f"装载位     {dst}   当前类型：{'symlink -> ' + os.readlink(dst) if os.path.islink(dst) else 'dir' if os.path.isdir(dst) else '不存在'}")
    print(f"真源       {src}")
    if not os.path.isdir(src):
        raise SystemExit(f"!! 真源不存在：{src}")
    src_tree = tree_sha(src)
    print(f"真源       {len(src_tree)} 个文件，tree_sha={hashlib.sha256(json.dumps(src_tree, sort_keys=True).encode()).hexdigest()[:16]}")

    if not a.apply:
        print()
        print("【预演】将执行：")
        print(f"  1) mv {dst} → {arch}/dsh-skills-{skill}   （可恢复，不删）")
        print(f"  2) ln -s {src} {dst}")
        print(f"  3) 校验：readlink 可解析 + tree_sha 与真源一致")
        print(f"  4) ★链路自检：python3 {os.path.join(HERE, 'extract_catalog.py')} --skill {skill}")
        print("  加 --apply 才真正执行。")
        return 0

    os.makedirs(arch, exist_ok=True)
    bak = os.path.join(arch, f"dsh-skills-{skill}")
    if os.path.exists(dst) and not os.path.islink(dst):
        if os.path.exists(bak):
            raise SystemExit(f"!! 归档已存在，先人工确认：{bak}")
        shutil.move(dst, bak)
        print(f"  1) 已归档 → {bak}")
    elif os.path.islink(dst):
        os.unlink(dst)
        print("  1) 移除旧 symlink")
    os.symlink(src, dst)
    print(f"  2) 已建 symlink：{dst} → {src}")

    ok = os.path.islink(dst) and os.path.realpath(dst) == os.path.realpath(src)
    dst_tree = tree_sha(dst) if ok else {}
    same = dst_tree == src_tree
    print(f"  3) readlink 可解析={ok}  tree_sha 一致={same}")
    if not (ok and same):
        print("  ❌ 校验失败 —— 立即回滚：--rollback")
        return 1
    print()
    print("  ★ 下一步（链路自检，必须做）：起一个会话后运行")
    print(f"     python3 {os.path.join(HERE, 'extract_catalog.py')} --skill {skill}")
    print("     若报「不在目录里」⇒ 加载器没跟随符号链接 ⇒ 立刻 --rollback 并改用镜像方案")
    json.dump({"skill": skill, "src": src, "dst": dst, "backup": bak,
               "tree_sha_match": same, "at": time.strftime("%Y-%m-%d %H:%M:%S")},
              open(os.path.join(arch, f"{skill}-pilot.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
