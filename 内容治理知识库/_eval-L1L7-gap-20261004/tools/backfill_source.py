#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回灌真源（步骤 8）——**本批唯一会写真源的操作，因此门控最严**。

前置门控（**任一不过即拒跑**，fail-loud）：
  1) fix 副本存在且有 SKILL.md；
  2) **该 fix 的评测已达标**：`score.json` 存在且 `market_ready == true`
     （未达标一律不回灌 —— 这是用户口径「第 8 步一定要评测通过后才能回灌真源」的机器化）；
  3) 该 fix 的挂载位 `freeze-manifest.json` 的 `diff` 为空（证明评的就是这份字节）；
  4) fix 的 `version` **严格大于** 真源当前 version（防回灌旧版/同版）；
  5) **真源当前内容已归档**（本工具自己做，且归档后校验 sha 一致才继续）。

动作（顺序固定，每步都留痕）：
  1) 归档真源 → `<archive>/<skill>-pre-backfill-<date>-<src_sha>-<src_ver>/`，并校验归档 sha == 真源 sha；
  2) 真源解只读 → 用 fix 内容替换 → **立刻核对** 真源 sha == fix sha；
  3) 同步装载位 `~/.dsh/skills/<skill>`（若该处是 symlink 则不动，天然同源）；
  4) 打印唯一性表（复用 verify_workbench）。
任何一步核对失败：**停止并打印回滚命令**，不硬扛。

用法：
  python3 tools/backfill_source.py --skill kb-media-extractor --fix fix/kb-media-extractor \
      --score runs/mediafix-a/score.json [--apply]
  不加 --apply 只做门控与预演。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
ROOT = os.path.dirname(PROJ)
SRC_ROOT = os.path.join(ROOT, "kb", "l7", "skills")
USER_SKILLS = os.path.expanduser("~/.dsh/skills")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ★ 评测工作区**不是 skill 内容**：L0 的 fix 目录里含整个 evals/（评测产物、跑批、报告），
#   回灌时必须排除，否则会把评测产物灌进真源。比对与复制两侧都要排。
EXCLUDE = ("evals/", ".git/", ".pytest_cache/")


def tree(root, exclude=EXCLUDE):
    out = {}
    for dp, _dn, fn in os.walk(root):
        for f in sorted(fn):
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, root)
            if any(rel.startswith(x) for x in exclude):
                continue
            out[rel] = sha(full)
    return out


def tsha(root, exclude=EXCLUDE):   # ★ 必须与 tree() 同一默认，否则比对与复制的基准不同（实测踩过）
    return hashlib.sha256(json.dumps(tree(root, exclude), sort_keys=True).encode()).hexdigest()


def version_of(p):
    t = open(p, encoding="utf-8").read()
    m = re.search(r'^version:\s*"?([0-9.]+)"?', t, re.M)
    return m.group(1) if m else None


def vcmp(a, b):
    return [int(x) for x in a.split(".")] > [int(x) for x in b.split(".")]


def force_writable(root):
    for dp, _dn, fn in os.walk(root):
        os.chmod(dp, os.stat(dp).st_mode | 0o700)
        for f in fn:
            p = os.path.join(dp, f)
            if not os.path.islink(p):
                os.chmod(p, os.stat(p).st_mode | 0o600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--fix", required=True)
    ap.add_argument("--score", required=True, help="该 fix 的 score.json（须 market_ready=true）")
    ap.add_argument("--mount", default=None,
                    help="显式指定冻结靶点目录（默认在本工作台 mounts/ 下按 tree sha 自动找）")
    ap.add_argument("--archive-root", default=os.path.join(PROJ, "_archive-回灌-20261004"))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    fix = os.path.abspath(a.fix)
    src = os.path.join(SRC_ROOT, a.skill)
    inst = os.path.join(USER_SKILLS, a.skill)
    score = os.path.abspath(a.score)

    # ── 门控 ──────────────────────────────────────────────
    if not os.path.isfile(os.path.join(fix, "SKILL.md")):
        raise SystemExit(f"!! fix 副本无 SKILL.md：{fix}")
    if not os.path.isfile(score):
        raise SystemExit(f"!! 找不到评测结果：{score}\n   （未评测通过一律不回灌）")
    sc = json.load(open(score, encoding="utf-8"))
    if not sc.get("market_ready"):
        raise SystemExit(f"!! 该 fix **未达标**（market_ready={sc.get('market_ready')}）⇒ 拒绝回灌真源。\n"
                         f"   轨道 C={sc.get('track_c',{}).get('total')}  "
                         f"cap={sc.get('track_c',{}).get('cap')}")
    fx = None
    if a.mount:                       # 显式指定（如 L0 的靶点在 L0 工程里，不在本工作台）
        m = os.path.abspath(a.mount)
        if not os.path.isdir(m):
            raise SystemExit(f"!! --mount 不存在：{m}")
        mt, ft = tree(m), tree(fix)
        if mt != ft:
            only_m = sorted(set(mt) - set(ft)); only_f = sorted(set(ft) - set(mt))
            diffs = [k for k in set(mt) & set(ft) if mt[k] != ft[k]]
            raise SystemExit(f"!! --mount 与 fix **逐文件不一致**，靶点不自证：{m}\n"
                             f"   只在靶点 {only_m[:5]}；只在 fix {only_f[:5]}；内容不同 {diffs[:5]}")
        fx = m
    else:
        mroot = os.path.join(PROJ, "mounts")
        tags = [t for t in os.listdir(mroot) if os.path.isdir(os.path.join(mroot, t, a.skill))] \
            if os.path.isdir(mroot) else []
        for t in tags:
            fm = os.path.join(mroot, t, "freeze-manifest.json")
            if os.path.isfile(fm) and not json.load(open(fm, encoding="utf-8")).get("diff"):
                if tree(fix) == json.load(open(fm, encoding="utf-8")).get("mount", {}):
                    fx = os.path.join(mroot, t, a.skill)
                    break
    if fx is None:
        raise SystemExit(f"!! 找不到与 fix 逐文件一致的冻结靶点（freeze-manifest.diff 为空且 sha 相同）\n"
                         f"   现有挂载位 tag：{tags}")

    fix_v, src_v = version_of(os.path.join(fix, "SKILL.md")), version_of(os.path.join(src, "SKILL.md"))
    if not (fix_v and src_v and vcmp(fix_v, src_v)):
        raise SystemExit(f"!! 版本门不过：fix={fix_v} 必须**严格大于**真源={src_v}")

    print(f"skill      {a.skill}")
    print(f"真源       {src}   version={src_v}")
    print(f"fix        {fix}   version={fix_v}")
    print(f"冻结靶点   {fx}  （逐文件与 fix 一致、diff=[]）")
    print(f"评测       market_ready={sc['market_ready']}  轨道C={sc.get('track_c',{}).get('total')}  "
          f"{sc.get('track_c',{}).get('grade')}")
    print(f"装载位     {inst}  "
          f"{'[symlink → ' + os.readlink(inst) + ']（天然同源，无需同步）' if os.path.islink(inst) else '[dir] 需同步'}")
    if not a.apply:
        print("\n【预演】将执行：① 归档真源并校验 ② 真源替换为 fix 并核对 sha ③ 同步装载位 ④ 打印唯一性表")
        print("  加 --apply 才真正执行。")
        return 0

    # ── ① 归档真源 ────────────────────────────────────────
    src_h, fix_h = tsha(src), tsha(fix)
    arch = os.path.join(a.archive_root, f"{a.skill}-pre-backfill-{date.today().isoformat()}-"
                                        f"{src_v}-{src_h[:12]}")
    if os.path.exists(arch):
        # 归档已存在：**只有在它与当前真源逐字节相同**时才复用（重试场景）；
        # 否则说明归档是别的版本，必须人工确认 —— 绝不覆盖证据。
        if tsha(arch) == src_h:
            print(f"① 归档已存在且与真源逐字节一致，复用 → {arch}")
        else:
            raise SystemExit(f"!! 归档目录已存在且与当前真源**不一致**，先人工确认：{arch}")
    else:
        os.makedirs(os.path.dirname(arch), exist_ok=True)
        shutil.copytree(src, arch, symlinks=True)
        if tsha(arch) != src_h:
            raise SystemExit("!! 归档 sha 与真源不一致 —— 立即停止")
        print(f"① 已归档真源 → {arch}    sha 校验一致 ✓")

    # ── ② 替换真源 ────────────────────────────────────────
    force_writable(src)
    tmp = src + ".old-tmp"
    os.rename(src, tmp)
    try:
        shutil.copytree(fix, src, symlinks=True,
                        ignore=shutil.ignore_patterns(*[e.rstrip("/") for e in EXCLUDE]))
        force_writable(src)
    except Exception as e:                                     # noqa: BLE001
        os.rename(tmp, src)
        raise SystemExit(f"!! 替换失败，已回滚：{e}")
    new_h = tsha(src)
    if new_h != fix_h:
        shutil.rmtree(src, ignore_errors=True)
        os.rename(tmp, src)
        raise SystemExit(f"!! 替换后 sha 与 fix 不一致（{new_h[:12]} != {fix_h[:12]}）—— 已回滚")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"② 真源已替换为 fix，sha 校验一致 ✓   {src_h[:12]} → {new_h[:12]}")

    # ── ③ 同步装载位 ──────────────────────────────────────
    if os.path.islink(inst):
        print("③ 装载位是 symlink，天然同源，跳过")
    else:
        force_writable(inst)
        shutil.rmtree(inst)
        shutil.copytree(src, inst, symlinks=True)
        force_writable(inst)
        if tsha(inst) != new_h:
            raise SystemExit("!! 装载位同步后 sha 不一致 —— 请人工检查")
        print(f"③ 装载位已同步 ✓   sha={new_h[:12]}")

    # ── ④ 唯一性表 ────────────────────────────────────────
    print("④ 唯一性核对：")
    import subprocess
    p = subprocess.run([sys.executable, os.path.join(HERE, "verify_workbench.py"), "--all"],
                       capture_output=True, text=True)
    # 只打该 skill 那一段
    keep, on = [], False
    for line in p.stdout.split("\n"):
        if line.startswith("### "):
            on = line.strip() == f"### {a.skill}"
        if on:
            keep.append(line)
    print("\n".join(keep) if keep else p.stdout)
    print(f"\n✅ 回灌完成。回滚：rm -rf {src} && cp -R {arch} {src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
