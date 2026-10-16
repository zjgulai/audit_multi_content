#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A 卷跑批驱动：一件 skill × 3 轮 × N 分片，全部走已冻结的挂载位 profile。

为什么要它：跑批是几十分钟到数小时的长任务，手敲 6 条命令容易错（本批已因接线手误
浪费过一整轮）。驱动把「分片 / 并发 / 限时 / 落盘位置 / 日志」一次性定死并**先自检**。

自检（**不通过就拒跑**，fail-loud）：
  1) 挂载位存在且 `freeze-manifest.json` 的 diff 为空；
  2) profile `eval-<tag>` 的 `customSkillDirs` **确实指向该挂载位**（防跑错靶点）；
  3) 用例目录里有 `round-prompts.json`，且条数与 `cases-meta.json` 的 a_cases+call_cases 一致；
  4) 输出目录为空（防把两批结果追加到一起 —— append 写入踩过一次）。

用法：
  python3 tools/run_a.py --skill kb-media-extractor --tag mediabase \
      --cases cases/kb-media-extractor --out runs/mediabase-a \
      [--concurrency 3] [--timeout 600] [--shards 2] [--dry]
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
RUN_ROUND = os.path.join(PROJ, "harness", "run_round.py")
PROFILES = os.path.expanduser("~/.dsh/profiles")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--shards", type=int, default=2)
    ap.add_argument("--work-root", default=None)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    mount_root = os.path.join(PROJ, "mounts", a.tag)
    mount = os.path.join(mount_root, a.skill)
    prof = os.path.join(PROFILES, f"eval-{a.tag}")
    patch = os.path.join(prof, "cordis.patch.yml")
    cases = os.path.abspath(a.cases)
    out = os.path.abspath(a.out)
    work = a.work_root or f"/tmp/kb-l1l7-blind-{a.tag}"

    # ── 自检 1：挂载位 + 冻结清单 ──────────────────────────────
    if not os.path.isdir(mount):
        raise SystemExit(f"!! 挂载位不存在：{mount}")
    man = os.path.join(mount_root, "freeze-manifest.json")
    if not os.path.isfile(man):
        raise SystemExit(f"!! 缺冻结清单：{man}")
    fm = json.load(open(man, encoding="utf-8"))
    if fm.get("diff"):
        raise SystemExit(f"!! 冻结清单 diff 非空：{fm['diff']}")

    # ── 自检 2：profile 必须指向本挂载位 ────────────────────────
    # ★★ 2026-10-04 重大更正：`customSkillDirs` 的每一项必须是**装着 skill 子目录的父目录**
    #    （即 mounts/<tag>），**不是** skill 目录本身（mounts/<tag>/<skill>）。
    #    原护栏要求等于 <mount>，与 prep_skill 的写法互为印证，把同一个错误假设**钉死**了：
    #    指到 skill 目录本身 ⇒ 加载器扫它的子目录再拼 SKILL.md ⇒ 拼出
    #    `references/SKILL.md`（不存在）⇒ **该根贡献 0 条** ⇒ 会话照旧读 ~/.dsh/skills（源版）
    #    ⇒ **评出来的其实是源版，而且不报错**。
    #    证据：dsh-skill-filesystem/lib/index.js:583-587（listSkillRootEntries + join(...,"SKILL.md")）。
    if not os.path.isfile(patch):
        raise SystemExit(f"!! profile 不存在或缺 cordis.patch.yml：{patch}")
    txt = open(patch, encoding="utf-8").read()
    mountroot = os.path.dirname(mount)
    if mountroot not in txt:
        raise SystemExit(
            f"!! profile eval-{a.tag} 的 customSkillDirs **没有**指向父目录 {mountroot}\n"
            f"   （必须指向父目录：加载器按 root 扫**子目录**再拼 SKILL.md；\n"
            f"     指到 {mount} 自身会让该根贡献 0 条 ⇒ 静默读到源版，分数全假）")
    if mount in txt:
        raise SystemExit(
            f"!! profile eval-{a.tag} 的 customSkillDirs 指向了 skill 目录本身 {mount}\n"
            f"   ⇒ 该根贡献 0 条，会话会静默读 ~/.dsh/skills（源版）。改为父目录 {mountroot}。")

    # ── 自检 3：用例条数一致 ───────────────────────────────────
    pj = os.path.join(cases, "round-prompts.json")
    cm = os.path.join(cases, "cases-meta.json")
    for p in (pj, cm):
        if not os.path.isfile(p):
            raise SystemExit(f"!! 缺用例文件：{p}")
    prompts = json.load(open(pj, encoding="utf-8"))
    meta = json.load(open(cm, encoding="utf-8"))
    want = len(meta["a_cases"]) + len(meta["call_cases"])
    if len(prompts) != want:
        raise SystemExit(f"!! 用例条数不一致：round-prompts={len(prompts)} vs "
                         f"cases-meta(a+call)={want}")

    # ── 自检 4：输出目录必须干净（append 写入，混批会静默出错）──
    os.makedirs(out, exist_ok=True)
    stale = [f for f in os.listdir(out) if f.endswith(".jsonl")]
    if stale:
        raise SystemExit(f"!! 输出目录已有 jsonl（append 会混批）：{stale}\n"
                         f"   请换 --out 或先清空。")

    ids = sorted(x["n"] for x in prompts)
    lo, hi = ids[0], ids[-1]
    step = (hi - lo + 1 + a.shards - 1) // a.shards
    shards = []
    for i in range(a.shards):
        s, e = lo + i * step, min(hi, lo + (i + 1) * step - 1)
        if s <= e:
            shards.append((s, e))

    print(f"skill      {a.skill}")
    print(f"tag        {a.tag}   profile=eval-{a.tag}")
    print(f"靶点       {mount}   freeze.diff={fm.get('diff')} ✓")
    print(f"用例       {len(prompts)} 条（n {lo}–{hi}），分 {len(shards)} 片：{shards}")
    print(f"限时       {a.timeout}s   并发 {a.concurrency}/片  ⇒ 全局 {a.concurrency*len(shards)*3} 并发")
    print(f"输出       {out}")
    print(f"work-root  {work}")
    if a.dry:
        print("（--dry：只自检，不跑）")
        return 0

    os.makedirs(os.path.join(out, "logs"), exist_ok=True)
    procs = []
    for r in (1, 2, 3):
        for i, (s, e) in enumerate(shards):
            suffix = "" if i == 0 else chr(ord("b") + i - 1)
            outfile = os.path.join(out, f"a-round-{r}{suffix}.jsonl")
            log = open(os.path.join(out, "logs", f"a{r}-{suffix or 'A'}.log"), "w")
            cmd = [sys.executable, RUN_ROUND, "--round", str(r), "--skill", a.skill,
                   "--profile", f"eval-{a.tag}", "--cases", cases,
                   "--concurrency", str(a.concurrency), "--timeout", str(a.timeout),
                   "--ids", f"{s}-{e}", "--work-root", work, "--outfile", outfile]
            print("  →", " ".join(cmd[-12:]), flush=True)
            procs.append((subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log, outfile))
    rc = 0
    for p, log, outfile in procs:
        p.wait()
        log.close()
        n = sum(1 for _ in open(outfile, encoding="utf-8")) if os.path.exists(outfile) else 0
        print(f"  ✓ {os.path.basename(outfile)}: {n} 条 (exit={p.returncode})")
        rc |= p.returncode
    print(f"\n完成。产物在 {out}；下一步：judge.py → score-trigger-eval.py → output_assertions.py → make_score.py")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
