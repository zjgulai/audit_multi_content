#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「description 首句触发改写 + gotchas 强模式」应用到一个**独立副本树**。

★ 硬约束（本工具存在的理由）：
  1. **绝不写 fix/ 与 mounts/** —— 那两处是 main 线的冻结评测靶点，改它们等于把在跑的
     盲测证据作废（freeze-manifest 要求 diff=[]）。本工具只写 `optimized/<skill>/`。
  2. **正文不得越过 complexity 上限**（minimal 2000 / standard 4000 / complex 8000）。
     实测三件余量极小：kb-l0-feishu 7977/8000、kb-media-extractor 3945/4000、
     kb-canonical-lookup 1949/2000 ⇒ gotchas **一律下沉 references/**，正文只放指针；
     指针放不下就**如实报错并列出还需要腾多少字符**，不硬塞（硬塞会触发 error 封顶 ≤79）。
  3. 副本逐文件**保真**：内容、权限位照抄源，不自作主张加 +x。

用法：
  python3 build_optimized.py --cases out/apply-plan.json [--dry]
"""
import argparse
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUPP = os.path.dirname(HERE)
WS = os.path.dirname(SUPP)

LIMITS = {"minimal": 2000, "standard": 4000, "complex": 8000}


def write_clean(path, text):
    """**用非 python 进程落盘** —— 本机实测的硬约束。

    python3 进程写出的文件，在**磁盘上**会比内容多 **4096 字节的信封头**
    （raw 头形如 `887d1cd8…`，且信封段是变换过的、不是简单前缀 ⇒ 不能靠 skip 4096 还原）。
    后果：宿主 `read` 工具把它判成 `binary file` —— 一个宿主读不了的 SKILL.md 等于废件
    （AGENTS.md 早有此条：「写 .md 只许走 node / /bin/cp 通道」）。

    实测对照（本机）：
      python open().write / stdout 重定向 / shutil.copyfile  → 全部 +4096 ✗
      printf 重定向 / /bin/cp / node fs.writeFileSync / `base64 -d >`  → 干净 ✓

    ⇒ 本函数把内容经 stdin 交给 `base64 -d`（**非 python 进程**）写盘，
      并**回读校验**内容与磁盘大小，任一项不符即 fail-loud。
    """
    import subprocess
    import base64 as _b64
    payload = _b64.b64encode(text.encode("utf-8"))
    subprocess.run(["/bin/sh", "-c", 'base64 -d > "$1"', "sh", path],
                   input=payload, check=True)
    if open(path, "rb").read() != text.encode("utf-8"):
        raise SystemExit(f"!! 落盘内容校验失败：{path}")
    if os.path.getsize(path) != len(text.encode("utf-8")):
        raise SystemExit(f"!! 落盘仍带信封（大小不符）：{path}")



# 指针尽量短：三件余量极小（L0 23 / media 55 / canonical 51），长指针会直接把正文顶过上限，
# 而正文超限 = 家族校验器 ERROR = 轨道 C 封顶 ≤79、market_ready=false。
POINTER = "\n**Gotchas（错误 → 修正）→ `references/gotchas.md`**\n"


def split_front(txt):
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not m:
        raise SystemExit("!! 没有 frontmatter")
    return m.group(1), txt[m.end():]


def replace_desc(fm, new_desc):
    """替换 description 块（含 YAML `|` 块标量），其余 frontmatter 原样保留。"""
    lines = fm.split("\n")
    out, i, done = [], 0, False
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^description:", ln) and not done:
            out.append("description: |")
            for d in new_desc.split("\n"):
                out.append("  " + d)
            done = True
            i += 1
            while i < len(lines) and not re.match(r"^[A-Za-z_][\w-]*:", lines[i]):
                i += 1
            continue
        out.append(ln)
        i += 1
    return "\n".join(out)


def bump(fm, dry):
    m = re.search(r'^version:\s*"?([\d.]+)"?\s*$', fm, re.M)
    old = m.group(1) if m else None
    fm = re.sub(r'^last_updated:\s*.*$', 'last_updated: 2026-10-04', fm, flags=re.M)
    if not old:
        return fm, old, old
    parts = old.split(".")
    parts[-2] = str(int(parts[-2]) + 1)
    parts[-1] = "0"
    new = ".".join(parts)
    fm = re.sub(r'(^version:\s*)"?[\d.]+"?', lambda mm: mm.group(1) + f'"{new}"', fm, count=1, flags=re.M)
    return fm, old, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=os.path.join(SUPP, "out", "apply-plan.json"))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    plan = json.load(open(a.cases, encoding="utf-8"))
    descs = json.load(open(os.path.join(SUPP, "out", "desc-candidates.json"), encoding="utf-8"))
    gots = json.load(open(os.path.join(SUPP, "out", "gotchas.json"), encoding="utf-8"))

    report = []
    for skill, src in plan.items():
        src = os.path.join(WS, src) if not os.path.isabs(src) else src
        skillmd = os.path.join(src, "SKILL.md")
        if not os.path.isfile(skillmd):
            report.append((skill, "!! 源不存在", "", "", "", ""))
            continue
        txt = open(skillmd, encoding="utf-8").read()
        fm, body = split_front(txt)
        cx = re.search(r'^complexity:\s*"?(\w+)"?', fm, re.M)
        cx = cx.group(1) if cx else "standard"
        limit = LIMITS.get(cx, 4000)
        fm2 = replace_desc(fm, descs[skill])
        fm2, vold, vnew = bump(fm2, a.dry)

        # gotchas 落 references/
        gl = gots[skill]
        gmd = [f"# Gotchas —— {skill}（错误 → 修正）\n",
               "> 由 `_supp-creator-audit-20261004` 补充优化加入（root-skills-creator 清单②③：",
               "> gotchas 用「错误 + 修正」强模式，并写明「本 skill 不处理 X，即使措辞看起来相似」）。\n"]
        for wrong, fix in gl:
            gmd.append(f"- **错误**：{wrong}\n  **修正**：{fix}\n")
        gmd = "\n".join(gmd)

        # 正文指针：若正文**已经**点名了 references/gotchas.md，则读取条件已满足（creator 清单⑦），
        # 不再重复插入 —— kb-l0-feishu 就是这一档（§4 收口表与 §8 都已写「更多坑见 references/gotchas.md」），
        # 且它正文余量只有 23 字符，硬插指针必然超限 ⇒ 不插才是对的。
        already_named = "references/gotchas.md" in body
        # 清单⑩（维护与退役机制）：kb-p0-check / kb-recall / kb-check 三件**正文与 references
        # 都没有任何「停用 / 退役」表述**（实测命中 0），属真实缺口 ⇒ 补一节，走 tail.json。
        tail = ""
        tpath = os.path.join(SUPP, "out", "tail.json")
        if os.path.exists(tpath):
            tl = json.load(open(tpath, encoding="utf-8"))
            if skill in tl:
                # 正文末尾已有点名 gotchas 的行时，把新节插在它**前面**，保持末尾整洁
                tail = "\n" + tl[skill]
        base_body = body.rstrip("\n") + "\n"
        body_new = (base_body + tail.lstrip("\n") if tail else body.rstrip("\n") + "\n") + POINTER.lstrip("\n")
        used = len(body_new)
        if already_named:
            fits = True
            body_new = body
            used = len(body)
            note = f"正文 {len(body)} / 上限 {limit}；**正文已点名 references/gotchas.md，无需指针**"
        elif used <= limit:
            fits = True
            note = f"正文 {len(body)} → {used} / 上限 {limit}（插指针）"
        else:
            fits = False
            note = (f"正文 {len(body)} → {used} / 上限 {limit} ⇒ **放不下，还差 {used - limit} 字符**"
                    f"（未插入指针，gotchas 仍落 references/）")
            body_new = body
            used = len(body)

        if not a.dry:
            dst = os.path.join(SUPP, "optimized", skill)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst, symlinks=True, copy_function=shutil.copy2)
            # 逐文件对齐权限（含目录），不擅自加 +x
            for root, dirs, files in os.walk(src):
                rel = os.path.relpath(root, src)
                for n in files:
                    s, d = os.path.join(root, n), os.path.join(dst, rel, n)
                    if os.path.exists(d):
                        os.chmod(d, os.stat(s).st_mode & 0o7777)
            write_clean(os.path.join(dst, "SKILL.md"),
                        "---\n" + fm2 + "\n---\n" + body_new)
            os.makedirs(os.path.join(dst, "references"), exist_ok=True)
            # ★ kb-l0-feishu **本来就有人工维护的 references/gotchas.md**（79 行台账）。
            #   绝不能覆盖它 —— 已存在的**逐字保留**，本次内容作为新增章节**追加**在后。
            #   （本工具第一版正是直接 "w" 覆盖，虽只波及自己的副本树，仍属必须修掉的缺陷。）
            gpath = os.path.join(dst, "references", "gotchas.md")
            if os.path.exists(gpath):
                prev = open(gpath, encoding="utf-8").read()
                if not prev.endswith("\n"):
                    prev += "\n"
                gmd = prev + "\n---\n\n" + gmd
                appended = "追加"
            else:
                appended = "新建"
            gpath2 = os.path.join(dst, "references", "gotchas.md")
            # 追加档：gmd 已含原文；整体重写也必须走干净通道
            write_clean(gpath2, gmd)

            # ── 保真自证：副本与源**只允许**在两处不同（SKILL.md / references/gotchas.md），
            #    其余逐文件 sha256 必须全等。防的正是"顺手改坏了别的东西"这类静默事故。
            import hashlib
            def sha(p):
                return hashlib.sha256(open(p, "rb").read()).hexdigest()
            diffs, checked = [], 0
            for root, dirs, files in os.walk(src):
                rel = os.path.relpath(root, src)
                for n in files:
                    r = os.path.normpath(os.path.join(rel, n))
                    if r in ("SKILL.md", os.path.join("references", "gotchas.md")):
                        continue
                    a_, b_ = os.path.join(root, n), os.path.join(dst, r)
                    checked += 1
                    if not os.path.exists(b_) or sha(a_) != sha(b_):
                        diffs.append(r)
            if diffs:
                raise SystemExit(f"!! 保真自证失败：{skill} 有非预期差异 {diffs}")

        report.append((skill, f"{vold} → {vnew}", f"{len(descs[skill]):>3} 字候选", note,
                       "是" if fits else "★否", cx))

    print(f"{'skill':<22}{'版本':<14}{'desc':<10}{'正文/上限':<26}{'指针入正文':<10}{'complexity'}")
    for r in report:
        print(f"{r[0]:<22}{r[1]:<14}{r[2]:<10}{r[3]:<26}{r[4]:<10}{r[5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
