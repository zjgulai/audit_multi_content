#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跑批**前置强制检查**：隔离 profile 到底有没有生效？

为什么非要有这个：2026-10-04 实测踩过一次**静默失效**——profile 里 `customSkillDirs`
指向了 skill 目录本身（而不是"装着 skill 的父目录"），加载器扫不到，于是会话照旧读
`~/.dsh/skills/<skill>`（**源版**）⇒ 我拿源版当"修复版"评了两轮，分数全废。
**这种失效不会报错**，只会安静地给你一份"看起来很合理"的错数。

判据（**必须逐字**，不许看"像不像"）：
  ① 起一个探针会话（复用跑批器 `harness/run_round.py`，与正式跑同一条路径）
  ② 取出加载器**实渲染**的目录行
  ③ 要求：渲染文本 == **挂载位那一份**的 description（折叠后；超 500 会被截断成 497+"..."）
     · 与挂载位一致  → ✅ 隔离生效
     · 与真源/装载位一致 → ❌ **隔离失效**（正在拿源版冒充修复版），非零退出
     · 两者都不一致 → ❓ 未知来源，非零退出

用法：
  python3 tools/verify_isolation.py --skill kb-media-extractor --tag mediafix
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
KBPY = os.path.join(PROJ, "harness", "run_round.py")
KB_ROOT = os.path.dirname(PROJ)
WORK = "/tmp/kb-l1l7-isoflcheck"


def desc_collapsed(p):
    # ★ 文件不存在要**返回 None**、不许抛：跑批期间装载位那份是**故意 park 掉的**，
    #   此刻 install 路径必然不存在（2026-10-04 实测：本检查器曾因此 FileNotFoundError 崩掉，
    #   把一次本该通过的核验变成"拒跑"）。
    if not p or not os.path.isfile(p):
        return None
    t = open(p, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
    if not m:
        return None
    return " ".join(str(yaml.safe_load(m.group(1)).get("description", "")).split())


def rendered(session_zst, skill):
    import zstandard
    raw = zstandard.ZstdDecompressor().stream_reader(open(session_zst, "rb")).read()
    text = raw.decode("utf-8", "replace")
    i = text.find("available_skills")
    if i < 0:
        return None, 0
    seg = text[i:]
    m = re.search(r"`" + re.escape(skill) + r"`\s*:\s*(.{0,4000}?)(?=\\n-\s*`|\\n\\n\")", seg, re.S)
    if not m:
        return None, -1
    blk = m.group(1).replace("\\n", " ").replace('\\"', '"')
    return " ".join(blk.split()), 0


def lcp(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--cases", default=None)
    a = ap.parse_args()

    mount = os.path.join(PROJ, "mounts", a.tag, a.skill)
    true_src = os.path.join(KB_ROOT, "kb", "l7", "skills", a.skill)
    install = os.path.expanduser(f"~/.dsh/skills/{a.skill}")
    cases = a.cases or os.path.join(PROJ, "cases", a.skill)

    print(f"skill={a.skill}  tag={a.tag}")
    prof = os.path.expanduser(f"~/.dsh/profiles/eval-{a.tag}/cordis.patch.yml")
    if not os.path.isfile(prof):
        print(f"❌ 无 profile：{prof}")
        return 1
    y = yaml.safe_load(open(prof, encoding="utf-8"))
    dirs = []
    for it in (y if isinstance(y, list) else []):
        dirs += ((it.get("config") or {}).get("customSkillDirs") or [])
    print(f"customSkillDirs = {dirs}")
    for d in dirs:
        if os.path.isfile(os.path.join(d, "SKILL.md")):
            print(f"❌ **指深了一层**：{d} 自身含 SKILL.md —— 加载器扫的是它的子目录，"
                  f"这个根贡献 0 条 ⇒ 必然读到源版（2026-10-04 踩过）")
            return 1

    # ── 影子副本扫描（2026-10-04 事故的直接成因）────────────────────────────
    # 加载器按 frontmatter 的 `name` 给条目命名，**不看目录名**。
    # 所以 `~/.dsh/skills/<skill>.PARKED/` 这种"改个目录名"根本不等于移走：
    # 它还在根里、还是被扫到、名字还是 <skill>。实测因此白跑过一整轮。
    shadow = []
    for root in [os.path.expanduser("~/.dsh/skills"), os.path.expanduser("~/.agents/skills")]:
        if not os.path.isdir(root):
            continue
        for e in sorted(os.listdir(root)):
            sd = os.path.join(root, e, "SKILL.md")
            if not os.path.isfile(sd):
                continue
            d0 = desc_collapsed(sd)
            try:
                nm = yaml.safe_load(re.match(r"^---\n(.*?)\n---\n",
                                             open(sd, encoding="utf-8").read(), re.S).group(1)).get("name")
            except Exception:
                nm = None
            if nm == a.skill:
                shadow.append(os.path.join(root, e))
    if shadow:
        print(f"⚠️ 在扫描根里发现**同名影子副本**（按 frontmatter name 判定）：")
        for s in shadow:
            print(f"     {s}")
        print("   ⇒ 它会被当成同一个 skill 参与同名竞争。park 必须挪到**扫描根之外**"
              "（如 ~/.dsh/_parked-skills/），改目录名无效。")

    # 起探针（复用跑批器，与正式跑同一条路径）
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    out = os.path.join(WORK, "out.jsonl")
    ids = "1"
    cm = json.load(open(os.path.join(cases, "cases-meta.json"), encoding="utf-8"))
    if cm.get("a_cases"):
        ids = str(cm["a_cases"][0]["n"])
    r = subprocess.run([sys.executable, KBPY, "--round", "98", "--skill", a.skill,
                        "--profile", f"eval-{a.tag}", "--cases", cases,
                        "--concurrency", "1", "--timeout", "300", "--ids", ids,
                        "--work-root", WORK, "--outfile", out],
                       capture_output=True, text=True)
    if not os.path.isfile(out):
        print(f"❌ 探针未产出记录：{r.stdout[-500:]}{r.stderr[-500:]}")
        return 1
    rec = json.loads(open(out, encoding="utf-8").readline())
    sd = rec.get("session_dir")
    f = glob.glob(os.path.join(sd or "", "*", "session.jsonl.zstd"))
    if not f:
        print(f"❌ 找不到会话文件：{sd}")
        return 1

    got, _ = rendered(f[0], a.skill)
    if not got:
        print(f"❌ 目录里没有 `{a.skill}`（渲染失败）—— 装载位可能断了")
        return 1

    md = desc_collapsed(os.path.join(mount, "SKILL.md"))
    td = desc_collapsed(os.path.join(true_src, "SKILL.md"))
    idd = desc_collapsed(os.path.join(install, "SKILL.md"))
    shown = got.rstrip(".")  # 截断处的 "..." 不算

    print(f"\n渲染长度 {len(got)} 字")
    print(f"  与挂载位 公共前缀 = {lcp(md or '', got)} / {len(md or '')}")
    print(f"  与真源   公共前缀   = {lcp(td or '', got)} / {len(td or '')}")
    print(f"  与装载位 公共前缀   = {lcp(idd or '', got)} / {len(idd or '')}")

    def match(d):
        if not d:
            return False
        return got.startswith(d[:len(got)].rstrip(".")) or d.startswith(got.rstrip("."))

    if match(md):
        print("\n✅ **隔离生效**：会话读到的是挂载位那一份")
        return 0
    if match(td) or match(idd):
        print("\n❌ **隔离失效**：会话读到的是**真源/装载位（源版）** —— "
              "此刻拿它评测等于在评源版，**分数无效，不许开跑**")
        return 1
    print("\n❓ 渲染内容与挂载位、真源、装载位**都不一致** —— 来源未知，**不许开跑**")
    print(f"   渲染前 120 字：{got[:120]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
