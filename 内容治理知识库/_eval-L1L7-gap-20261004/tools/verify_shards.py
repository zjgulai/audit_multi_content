#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐分片复核隔离：每一片都要自证"渲染的是挂载位那一份"。

为什么必须逐片：2026-10-04 实测两次——media「a 片对 / b 片错」、clause「4 片对 / 2 片错」。
**同一个 run 里不同进程会各自解析到不同版本**，所以：
  · 跑前探一条（verify_isolation.py）是必要条件，**不充分**；
  · 事后只抽样一条也会漏（抽到 a 片就以为全对）。
⇒ 判据只能是**六片全验**，任何一片读到非挂载位 ⇒ **整轮作废**。

用法：python3 tools/verify_shards.py --skill kb-media-extractor --run-dir runs/mediafix-a
退出码：0 = 六片全绿（数据可信）；1 = 有片不绿（数据作废）
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)


def desc_collapsed(p):
    if not p or not os.path.isfile(p):
        return None
    t = open(p, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
    if not m:
        return None
    return " ".join(str(yaml.safe_load(m.group(1)).get("description", "")).split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tag", default=None, help="挂载位 tag；默认取 run-dir 的目录名去掉 -a")
    a = ap.parse_args()

    tag = a.tag or os.path.basename(a.run_dir.rstrip("/")).replace("-a", "")
    mount = os.path.join(PROJ, "mounts", tag, a.skill)
    md = desc_collapsed(os.path.join(mount, "SKILL.md"))
    if not md:
        print(f"!! 挂载位读不到：{mount}/SKILL.md")
        return 1
    print(f"skill={a.skill}  tag={tag}  挂载位 description 折叠 {len(md)} 字")

    files = sorted(glob.glob(os.path.join(a.run_dir, "*.jsonl")))
    if not files:
        print("!! 没有 jsonl")
        return 1

    bad, done = [], 0
    for f in files:
        recs = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        withsd = [r for r in recs if r.get("session_dir")]
        if not withsd:
            print(f"  {os.path.basename(f):<20} 无会话记录 ⇒ 判不成 ❌")
            bad.append(os.path.basename(f))
            continue
        sd = withsd[0]["session_dir"]
        fs = glob.glob(os.path.join(sd, "*", "session.jsonl.zstd"))
        if not fs:
            print(f"  {os.path.basename(f):<20} 会话文件缺失 ⇒ 判不成 ❌")
            bad.append(os.path.basename(f))
            continue
        out = subprocess.run([sys.executable, os.path.join(HERE, "extract_catalog.py"),
                              fs[0], "--skill", a.skill],
                             capture_output=True, text=True).stdout
        m = re.search(r"渲染长度 (\d+) 字", out)
        ln = int(m.group(1)) if m else -1
        ok = (ln == len(md))
        done += 1
        if not ok:
            bad.append(os.path.basename(f))
        print(f"  {os.path.basename(f):<20} 渲染 {ln:>4} 字 / 挂载位 {len(md)} 字  "
              f"{'✅ 挂载位' if ok else '❌ **非挂载位**'}")

    print()
    if bad:
        print(f"❌ {len(bad)}/{len(files)} 片读到非挂载位：{bad}")
        print("   ⇒ **整轮数据作废**，不许拿去出分（差多少片就必须补跑多少片）")
        return 1
    print(f"✅ {len(files)}/{len(files)} 片全部读到挂载位 ⇒ 本轮数据可信")
    return 0


if __name__ == "__main__":
    sys.exit(main())
