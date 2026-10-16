#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把补充优化应用到**主线的 fix/ 与 mounts/**（用户 2026-10-04「你改」授权）。

底本 = 主线**现役** fix（含它 21:31 的 description 内容）；本工具只做格式层增量：
  ① description 换成 `out/merged-desc.json`（触发句前置 + 补触发词行；★负例块与判归块逐字保留）
  ② 新增 `references/gotchas.md`（「错误 + 修正」强模式 + 「本 skill 不处理 X，即使措辞看起来相似」）
  ③ `kb-check` / `kb-p0-check` / `kb-recall` 补「停用条件」节（清单⑩）
  ④ 正文末尾补 gotchas 指针（正文余量不足则**如实报错不硬塞**）
  ⑤ 重建挂载位 + 重生成 `freeze-manifest.json`（diff 必须为空）

落盘一律走 `base64 -d`（非 python 进程）—— 本机实测 python 写出的文件会带 4096 字节信封。
**不做**：不碰 L0 线（它的 A 卷已跑完，动它会作废）；不碰 `zz-mount-probe` 等主线自建探针目录。
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUPP = os.path.dirname(HERE)
WS = os.path.dirname(SUPP)
PROJ = os.path.join(WS, "_eval-L1L7-gap-20261004")
FIX = os.path.join(PROJ, "fix")
MOUNTS = os.path.join(PROJ, "mounts")

LIMITS = {"minimal": 2000, "standard": 4000, "complex": 8000}
POINTER = "\n**Gotchas（错误 → 修正）→ `references/gotchas.md`**\n"

TAGS = {
    "kb-ingest-extractor": "ingestfix",
    "kb-media-extractor": "mediafix",
    "kb-clause-extractor": "clausefix",
    "kb-canonical-lookup": "canonfix",
    "kb-p0-check": "p0fix",
    "kb-recall": "recallfix-l1l7",
    "kb-check": "checkfix",
}


def write_clean(path, text):
    payload = base64.b64encode(text.encode("utf-8"))
    subprocess.run(["/bin/sh", "-c", 'base64 -d > "$1"', "sh", path], input=payload, check=True)
    if open(path, "rb").read() != text.encode("utf-8"):
        raise SystemExit(f"!! 落盘校验失败：{path}")
    if os.path.getsize(path) != len(text.encode("utf-8")):
        raise SystemExit(f"!! 仍带信封：{path}")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def split_front(txt):
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    return m.group(1), txt[m.end():]


def replace_desc(fm, new_desc):
    lines, out, i, done = fm.split("\n"), [], 0, False
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^description:", ln) and not done:
            out.append("description: |")
            out += ["  " + d for d in new_desc.split("\n")]
            done = True
            i += 1
            while i < len(lines) and not re.match(r"^[A-Za-z_][\w-]*:", lines[i]):
                i += 1
            continue
        out.append(ln)
        i += 1
    return "\n".join(out)


def bump(fm):
    m = re.search(r'^version:\s*"?([\d.]+)"?\s*$', fm, re.M)
    fm = re.sub(r"^last_updated:\s*.*$", "last_updated: 2026-10-04", fm, flags=re.M)
    if not m:
        return fm, None, None
    old = m.group(1)
    p = old.split(".")
    p[-2] = str(int(p[-2]) + 1)
    p[-1] = "0"
    new = ".".join(p)
    fm = re.sub(r'(^version:\s*)"?[\d.]+"?', lambda mm: mm.group(1) + f'"{new}"',
                fm, count=1, flags=re.M)
    return fm, old, new


def build_refs(skill, gots, tails):
    """返回 (gotchas 正文, 停用条件节 or '')。"""
    entries = gots.get(skill, [])
    head = [f"# Gotchas —— {skill}（错误 → 修正）\n",
            "> 由补充优化包加入（root-skills-creator 清单②③：gotchas 用「错误 + 修正」强模式，",
            "> 并写明「本 skill 不处理 X，即使措辞看起来相似」）。\n"]
    for wrong, fix in entries:
        head.append(f"- **错误**：{wrong}\n  **修正**：{fix}\n")
    return "\n".join(head), (tails.get(skill, "") if tails else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    descs = json.load(open(os.path.join(SUPP, "out", "merged-desc.json"), encoding="utf-8"))
    gots = json.load(open(os.path.join(SUPP, "out", "gotchas.json"), encoding="utf-8"))
    tpath = os.path.join(SUPP, "out", "tail.json")
    tails = json.load(open(tpath, encoding="utf-8")) if os.path.exists(tpath) else {}

    rows = []
    for skill, tag in TAGS.items():
        f = os.path.join(FIX, skill, "SKILL.md")
        fm, body = split_front(open(f, encoding="utf-8").read())
        cx = re.search(r'^complexity:\s*"?(\w+)"?', fm, re.M)
        cx = cx.group(1) if cx else "standard"
        limit = LIMITS.get(cx, 4000)

        fm2, vold, vnew = bump(replace_desc(fm, descs[skill]))
        gmd, tail = build_refs(skill, gots, tails)

        # 正文：已有指针就不重复；再加停用条件节
        base = body.rstrip("\n") + "\n"
        if tail:
            base += "\n" + tail
        if "references/gotchas.md" not in body:
            base += POINTER
        newbody = base
        fits = len(newbody) <= limit
        rows.append((skill, tag, vold, vnew, len(body), len(newbody), limit, fits, cx))

        if not a.apply:
            continue
        if not fits:
            raise SystemExit(f"!! {skill} 正文 {len(newbody)} 超上限 {limit}，拒绝应用")

        write_clean(f, "---\n" + fm2 + "\n---\n" + newbody)
        refs = os.path.join(FIX, skill, "references")
        os.makedirs(refs, exist_ok=True)
        gpath = os.path.join(refs, "gotchas.md")
        if os.path.exists(gpath):
            prev = open(gpath, encoding="utf-8").read()
            if not prev.endswith("\n"):
                prev += "\n"
            gmd = prev + "\n---\n\n" + gmd
        write_clean(gpath, gmd)

        # ── 重建挂载位（只动 <skill> 子目录，保留主线自建探针目录）──
        mroot = os.path.join(MOUNTS, tag)
        mdst = os.path.join(mroot, skill)
        if os.path.exists(mdst):
            shutil.rmtree(mdst)
        shutil.copytree(os.path.join(FIX, skill), mdst, symlinks=True,
                        copy_function=shutil.copy2)
        # 逐文件对齐权限（保真，不擅自加 +x）
        for root, dirs, files in os.walk(os.path.join(FIX, skill)):
            rel = os.path.relpath(root, os.path.join(FIX, skill))
            for n in files:
                s_, d_ = os.path.join(root, n), os.path.join(mdst, rel, n)
                if os.path.exists(d_):
                    os.chmod(d_, os.stat(s_).st_mode & 0o7777)
        # 挂载位里的文本文件若带信封，重发一遍
        for root, dirs, files in os.walk(mdst):
            for n in files:
                p_ = os.path.join(root, n)
                if p_.endswith((".md", ".py", ".sh", ".yaml", ".yml")):
                    try:
                        t_ = open(p_, encoding="utf-8").read()
                    except Exception:
                        continue
                    write_clean(p_, t_)

        man = {"tag": tag, "skill": skill, "source": os.path.join(FIX, skill), "mount": {}}
        for root, dirs, files in os.walk(mdst):
            for n in files:
                p_ = os.path.join(root, n)
                man["mount"][os.path.relpath(p_, mdst)] = sha(p_)
        man["mount"] = dict(sorted(man["mount"].items()))
        man["diff"] = []
        write_clean(os.path.join(mroot, "freeze-manifest.json"),
                    json.dumps(man, ensure_ascii=False, indent=1))

    print(f"{'skill':<22}{'tag':<16}{'版本':<14}{'正文(旧→新/上限)':<26}{'可应用'}")
    for s, t, vo, vn, b0, b1, lim, fit, cx in rows:
        print(f"{s:<22}{t:<16}{str(vo)+'→'+str(vn):<14}{f'{b0}→{b1} / {lim}':<26}"
              f"{'是' if fit else '★否'}")
    if not a.apply:
        print("\n（--apply 未给：仅预演）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
