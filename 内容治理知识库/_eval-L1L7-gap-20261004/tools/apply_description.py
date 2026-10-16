#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 description 草稿应用到一份 skill 副本上（**源只读，绝不写回**）。

做三件事，且**只做这三件**：
  1) 用草稿替换 frontmatter 的 `description:` 块（按 YAML `|` 块标量写，每行缩进 2 格）
  2) 版本号升一位 minor、`last_updated` 置为今天（留痕）
  3) 若存在 `references/CHANGELOG.md`，**在最前面**插一条本次改动说明（不删旧条目）

不做的事：不动正文、不动 scripts、不动 references 其它文件。

用法：
  python3 apply_description.py --src <真源目录> --draft <draft.txt> --out <副本目录> \
      [--note "本轮改了什么"] [--dry]
"""
import argparse
import os
import re
import shutil
from datetime import date


def force_writable(root):
    """把整棵树解只读。**必须保留文件原有的执行位** ——
    否则 scripts/ 下的脚本会丢掉 +x，家族校验器会新增「Not executable」warning（实测踩过）。"""
    for dp, dn, fn in os.walk(root):
        # 目录：owner rwx（副本要能写），组/其他读+执行
        os.chmod(dp, (os.stat(dp).st_mode & 0o777) | 0o700)
        for f in fn:
            p = os.path.join(dp, f)
            if os.path.islink(p):
                continue
            try:
                # **保留原有执行位**（否则 scripts/ 会丢 +x，校验器新增 Not executable warning），
                # 只加 owner 读写 —— 源的 SKILL.md 常是 -r--------，照抄会让自己都改不了。
                os.chmod(p, (os.stat(p).st_mode & 0o777) | 0o600)
            except OSError:
                pass


def bump(v):
    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?$", str(v).strip())
    if not m:
        return None
    return f"{m.group(1)}.{int(m.group(2)) + 1}.0"


def get_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise SystemExit("!! 取不到 frontmatter")
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    src = os.path.abspath(a.src)
    md = os.path.join(src, "SKILL.md")
    text = open(md, encoding="utf-8").read()
    m = get_fm(text)
    fm = m.group(1)
    body = text[m.end():]

    draft = open(a.draft, encoding="utf-8").read().strip("\n")
    lines = fm.split("\n")
    out_lines, on, replaced = [], False, False
    for ln in lines:
        if re.match(r"^description:", ln):
            on = True
            out_lines.append("description: |")
            for dl in draft.split("\n"):
                out_lines.append("  " + dl.rstrip())
            replaced = True
            continue
        if on:
            if re.match(r"^[A-Za-z_]+:", ln):
                on = False
            else:
                continue          # 丢掉旧 description 的续行
        out_lines.append(ln)
    if not replaced:
        raise SystemExit("!! frontmatter 里没有 description: 行")

    new_version, old_version = None, None
    for i, ln in enumerate(out_lines):
        mm = re.match(r'^version:\s*"?([0-9.]+)"?\s*$', ln)
        if mm:
            old_version = mm.group(1)
            new_version = bump(old_version)
            if new_version:
                out_lines[i] = f'version: "{new_version}"'
        if re.match(r"^last_updated:", ln):
            out_lines[i] = f"last_updated: {date.today().isoformat()}"

    new_text = "---\n" + "\n".join(out_lines) + "\n---\n" + body
    collapsed = len(" ".join(draft.split()))
    print(f"src        {src}")
    print(f"out        {os.path.abspath(a.out)}")
    print(f"version    {old_version} → {new_version}")
    print(f"description 折叠后 {collapsed} 字符 {'✅ ≤500' if collapsed <= 500 else '❌ 超 %d' % (collapsed-500)}")
    if a.dry:
        print("（--dry：未写盘）")
        return 0
    if collapsed > 500:
        raise SystemExit("!! 草稿折叠后 >500，拒绝落盘（会掉出路由可见区）")

    out = os.path.abspath(a.out)
    if os.path.exists(out):
        force_writable(out)      # 上轮可能留下只读副本（源是 0555）⇒ 先解只读再删
        shutil.rmtree(out)
    shutil.copytree(src, out, symlinks=True)
    # ★ 源目录可能是 dr-xr-xr-x（kb-check / kb-recall 就是）⇒ copytree 会把只读位带过来，
    #   连 references/ 子目录一起只读，后面写 SKILL.md 与 CHANGELOG 就会 PermissionError。
    #   副本是**工作副本**，必须可写。
    force_writable(out)
    open(os.path.join(out, "SKILL.md"), "w", encoding="utf-8").write(new_text)
    os.chmod(os.path.join(out, "SKILL.md"), 0o644)

    cl = os.path.join(out, "references", "CHANGELOG.md")
    if os.path.isfile(cl):
        old = open(cl, encoding="utf-8").read()
        entry = (f"## {new_version} — {date.today().isoformat()}\n\n"
                 f"- description 重写：折叠后 {collapsed} 字符（≤500 生效面），"
                 f"判归句与安全边界句全部移入路由器可见区。\n"
                 f"- {a.note or '（未填 note）'}\n"
                 f"- 正文与 scripts/references 未改动。\n\n")
        open(cl, "w", encoding="utf-8").write(entry + old)
        print(f"CHANGELOG  references/CHANGELOG.md 已插入 {new_version} 条目")
    else:
        print("CHANGELOG  （无 references/CHANGELOG.md，跳过）")
    print("✅ 副本已生成（**真源未被改动**）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
