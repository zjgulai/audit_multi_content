#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 description 草稿：折叠后长度 + 逐规则单元可见性。

用法：python3 check_draft.py <draft.txt> [...]
草稿文件 = 仅 description 正文（不含 `description:` 键、不含 frontmatter）。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog_visible import MAXLEN, cutoff, norm, render  # noqa: E402

SPLIT = re.compile(r"[、；。]|(?<=\s)/(?=\s)")
BOLD = re.compile(r"\*\*|`|\*")

SEC = re.compile(r"rm\s*-rf|清空|越权|破坏|--apply|curl\s*\|\s*sh|读他人|泄露|拒绝|不加载|不写|只读|危险")
ASK = re.compile(r"追问|先问|欠定|只打本名|指代不明|只有名词|别加载|不要加载")
ROUTE = re.compile(r"→")


def check(path):
    name = os.path.basename(path).replace(".description.txt", "")
    body = open(path, encoding="utf-8").read()
    n = norm(body)
    cut = cutoff(body)
    over = len(n) - MAXLEN
    units, inv = 0, []
    for raw in SPLIT.split(n):
        u = BOLD.sub("", raw).strip(" ：:（）()")
        if len(u) < 2:
            continue
        units += 1
        i = n.find(raw.strip()) if raw.strip() else -1
        if i < 0:
            i = n.find(u)
        if not (0 <= i < cut):
            tags = []
            if ROUTE.search(u):
                tags.append("判归")
            if SEC.search(u):
                tags.append("安全")
            if ASK.search(u):
                tags.append("欠定")
            inv.append((i, "/".join(tags), u))

    status = "✅ 进窗" if over <= 0 else f"❌ 超 {over}"
    print(f"{name:<24} 折叠后={len(n):>4}  可见区={cut}  {status}  规则单元={units}  不可见={len(inv)}")
    for i, tags, u in inv:
        print(f"      ✂ pos={i:>4} [{tags or '—'}] {u[:64]}")
    print(f"      末尾：…{render(body)[-40:]}")
    return over <= 0 and not inv


if __name__ == "__main__":
    allok = True
    for p in sys.argv[1:]:
        allok &= check(p)
        print()
    raise SystemExit(0 if allok else 1)
