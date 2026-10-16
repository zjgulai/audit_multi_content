#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""description 可见性审计器 —— L0 机制的**可复用**版本。

机制（宿主代码级，两处独立核实）：
  node_modules/@deepseek-ai/dsh-tool-skill/lib/index.js
    :18  DEFAULT_CATALOG_DESCRIPTION_MAX_LENGTH = 500
    :337 catalogDescription(): 先 `replaceAll(/\s+/g,' ').trim()`，再 `slice(0,497)+'...'`
  ⇒ **模型能看到的目录行 = 折叠空白后的前 500 字**。
    规范里的 1024（universal-skill-schema / evaluation-guide）只管**能不能过校验**，
    与**生效面**是两件事 —— 按 1024 自检会得出"合规"的假绿。

用法：
  python3 visibility_audit.py <skills根目录…>        # 逐个 skill 目录扫
  python3 visibility_audit.py --files a/SKILL.md …   # 指定文件

输出：逐件的折叠全长 / 可见长度 / 隐藏字数，以及**落在隐藏区的关键路由规则**（这是真正的病灶）。
"""
import json
import os
import re
import sys

EFFECTIVE_MAX = 500
VISIBLE_END = EFFECTIVE_MAX - 3          # slice(0,497) + '...'
KEY_PATTERNS = [
    ("不适用清单", r"不适用"),
    ("不加载指令", r"不(要|得|应)?加载|别加载"),
    ("判归句", r"归\s*kb-|→\s*kb-|走\s*kb-|交给\s*kb-"),
    ("写档边界", r"不写库|不改索引|不写回|只读|不发号|不晋升"),
    ("安全红线", r"rm -rf|curl\|sh|--apply|越权|凭据|token"),
    ("调用门槛", r"打本名|打成别的|没材料|斜杠"),
]


def parse(p):
    t = open(p, encoding="utf-8").read()
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", t, re.S)
    fm, body = m.group(1), t[m.end():]
    out, grab = [], False
    for ln in fm.split("\n"):
        if re.match(r"^description\s*:", ln):
            grab = True
            out.append(re.sub(r"^description\s*:\s*", "", ln))
            continue
        if grab:
            if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:", ln):
                grab = False
            else:
                out.append(ln)
    return " ".join(" ".join(out).split()), " ".join(body.split())


def audit(name, path):
    d, body = parse(path)
    hits = []
    if len(d) > EFFECTIVE_MAX:
        for rule, pat in KEY_PATTERNS:
            for m in re.finditer(pat, d):
                if m.start() >= VISIBLE_END:
                    hits.append({"rule": rule, "pos": m.start(),
                                 "frag": d[max(0, m.start() - 18):m.start() + 32]})
    return {"skill": name, "folded": len(d), "visible": min(len(d), EFFECTIVE_MAX),
            "hidden": max(0, len(d) - EFFECTIVE_MAX), "truncated": len(d) > EFFECTIVE_MAX,
            "hidden_hits": hits, "body_folded": len(body)}


def main():
    args = sys.argv[1:]
    targets = []
    if args and args[0] == "--files":
        for p in args[1:]:
            targets.append((os.path.basename(os.path.dirname(p)), p))
    else:
        for root in (args or [os.path.expanduser("~/.dsh/skills")]):
            for name in sorted(os.listdir(root)):
                p = os.path.join(root, name, "SKILL.md")
                if os.path.isfile(p):
                    targets.append((name, p))
    out, bad = {}, 0
    for name, p in targets:
        a = audit(name, p)
        out[name] = a
        if a["truncated"]:
            bad += 1
        print(f"{name:<24} 折叠={a['folded']:>5} 可见={a['visible']:>4} 隐藏={a['hidden']:>4} "
              f"{'❌被截' if a['truncated'] else '✅全可见'}  隐藏区关键规则 {len(a['hidden_hits'])} 条")
        for h in a["hidden_hits"]:
            print(f"      ! {h['rule']:<8} @{h['pos']:>4}  …{h['frag']}")
    print(f"\n合计 {len(targets)} 件，其中被截 {bad} 件")
    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visibility.json")
    json.dump(out, open(dst, "w"), ensure_ascii=False, indent=1)
    print(f"明细 → {dst}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
