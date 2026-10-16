#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取回**路由器实渲染的技能目录行**（不是静态推算），用于两件事：

  ① symlink 试点：确认 `~/.dsh/skills/<skill>` 改成符号链接后，该 skill 仍出现在目录里；
  ② 链路自检（symlink 方案的必需护栏）：加载器对**断裂**符号链接只打一条 warning 后
     `return void 0`（`dsh-skill-filesystem/lib/index.js:766-770`）⇒ skill 会**静默消失**。
     故每次改装载位后必须跑本工具确认目录行仍在。

数据来源：会话归档 `~/.dsh/sessions/<dir>/<sid>/session.jsonl.zstd` 里的 `<available_skills>` 块。

用法：
  python3 extract_catalog.py                      # 取最近一个有 available_skills 的会话
  python3 extract_catalog.py <session.jsonl.zstd>
  python3 extract_catalog.py --skill kb-p0-check  # 只看这一条
"""
import glob
import json
import os
import re
import sys

import zstandard

SESS = os.path.expanduser("~/.dsh/sessions")


def read_session(path):
    return zstandard.ZstdDecompressor().stream_reader(
        open(path, "rb")).read().decode("utf-8", "replace")


def find_catalog(text):
    """从会话原文里抠出 <available_skills> 块——取最长的一段（系统提示里那份）。"""
    best = ""
    for m in re.finditer(r"<available_skills>(.*?)</available_skills>", text, re.S):
        if len(m.group(1)) > len(best):
            best = m.group(1)
    return best


def newest_session():
    cands = glob.glob(os.path.join(SESS, "*", "*", "session.jsonl.zstd"))
    if not cands:
        return None
    cands.sort(key=os.path.getmtime, reverse=True)
    for p in cands[:40]:
        try:
            if "<available_skills>" in read_session(p):
                return p
        except Exception:
            continue
    return cands[0]


def unescape(block):
    """会话原文里目录块是 **JSON 转义**过的（`\\n` 是反斜杠+n，不是真换行）⇒ 先还原。"""
    b = block.replace("\\n", "\n").replace('\\"', '"').replace("\\t", "\t")
    return b.replace("\\\\", "\\")


def entries(block):
    """目录行形如： - `name`: description...（分隔符为还原后的真换行）"""
    b = unescape(block)
    out = {}
    for m in re.finditer(r"^-\s*`([^`]+)`\s*:\s*(.*?)(?=\n-\s*`|\Z)", b, re.S | re.M):
        out[m.group(1)] = " ".join(m.group(2).split())
    return out


def main(argv):
    path, only = None, None
    i = 0
    while i < len(argv):
        if argv[i] == "--skill":
            only = argv[i + 1]
            i += 2
        else:
            path = argv[i]
            i += 1
    path = path or newest_session()
    if not path:
        print("!! 找不到会话归档")
        return 2

    text = read_session(path)
    block = find_catalog(text)
    if not block:
        print(f"!! 该会话无 available_skills：{path}")
        return 2
    ent = entries(block)

    print(f"会话：{path}")
    print(f"目录条数：{len(ent)}")
    if only:
        d = ent.get(only)
        if d is None:
            print(f"❌ **`{only}` 不在目录里** —— 装载位可能已断链（skill 会静默消失）")
            return 1
        print(f"✅ `{only}` 在目录里；渲染长度 {len(d)} 字")
        print(f"   渲染内容：{d}")
        return 0

    for name in sorted(ent):
        d = ent[name]
        flag = "⚠️超500" if len(d) >= 500 else ""
        print(f"{name:<28} {len(d):>5}字 {flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
