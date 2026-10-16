#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1–L7 层 skill description「可见性」审计（只读，不改任何 skill）。

口径与 L0 那支 check_description_visibility.py 相同（先折叠空白，再按 500 截断），
但**规则清单不由人手写**（避免只挑对自己有利的规则）：

  把折叠后的 description 按 `、；。` 切成「规则单元」，逐单元算它在折叠串里的
  首次出现位置，凡**起始位置 ≥ 可见区**的单元即判「不可见」。
  另按关键词标注单元类型：判归(→) / 安全 / 欠定。

用法：
  python3 audit_description_visibility.py <SKILL.md> [<SKILL.md> ...]
  python3 audit_description_visibility.py --dir <skills 根>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog_visible import MAXLEN, cutoff, norm, render  # noqa: E402

SPLIT = re.compile(r"[、；。]|(?<=\s)/(?=\s)")
BOLD = re.compile(r"\*\*|`|\*")

SEC = re.compile(r"rm\s*-rf|清空|删|越权|危险|破坏|--apply|curl\s*\|\s*sh|读他人|泄露|拒绝|不加载|不写|只读")
ASK = re.compile(r"追问|先问|欠定|口令过短|只有名词|指代不明|别加载|不要加载")
ROUTE = re.compile(r"→|归\s*\*?\*?kb-|走\s*\*?\*?kb-|归[^，。；、]{0,6}neighbor")


def extract_desc(path):
    txt = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not m:
        return None
    lines = m.group(1).split("\n")
    out, on = [], False
    for ln in lines:
        if re.match(r"^description:", ln):
            on = True
            continue
        if on:
            if re.match(r"^[A-Za-z_]+:", ln):
                break
            out.append(ln)
    return "\n".join(out) if out else None


def classify(unit):
    tags = []
    if ROUTE.search(unit):
        tags.append("判归")
    if SEC.search(unit):
        tags.append("安全")
    if ASK.search(unit):
        tags.append("欠定")
    return tags


def audit(path):
    desc = extract_desc(path)
    name = os.path.basename(os.path.dirname(os.path.abspath(path)))
    if desc is None:
        print(f"!! {name}: 取不到 description")
        return None
    n = norm(desc)
    cut = cutoff(desc)
    truncated = len(n) > MAXLEN

    units = []
    for raw in SPLIT.split(n):
        u = BOLD.sub("", raw).strip(" ：:（）()")
        if len(u) < 2:
            continue
        i = n.find(raw.strip()) if raw.strip() else -1
        if i < 0:
            i = n.find(u)
        units.append({"text": u, "pos": i, "visible": 0 <= i < cut,
                      "tags": classify(u)})

    inv = [u for u in units if not u["visible"]]
    lost_tags = {}
    for u in inv:
        for t in u["tags"]:
            lost_tags[t] = lost_tags.get(t, 0) + 1

    return {"name": name, "path": path, "total": len(n), "cut": cut,
            "truncated": truncated, "units": len(units), "invisible": inv,
            "lost_tags": lost_tags, "render": render(desc)}


def main(argv):
    paths = []
    if len(argv) >= 2 and argv[0] == "--dir":
        root = argv[1]
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d, "SKILL.md")
            if os.path.isfile(p):
                paths.append(p)
    else:
        paths = argv

    results = []
    for p in paths:
        r = audit(p)
        if r:
            results.append(r)

    print("=" * 100)
    print("L1–L7 description 可见性审计（生效面 = 折叠空白后前 500 字）")
    print("=" * 100)
    print(f"{'skill':<24}{'折叠后':>7}{'可见区':>7}{'超窗':>6}{'规则单元':>9}{'不可见':>8}   不可见里含")
    print("-" * 100)
    for r in results:
        over = r["total"] - MAXLEN if r["truncated"] else 0
        tagtxt = " ".join(f"{k}×{v}" for k, v in sorted(r["lost_tags"].items())) or "—"
        print(f"{r['name']:<24}{r['total']:>7}{r['cut']:>7}{over:>6}"
              f"{r['units']:>9}{len(r['invisible']):>8}   {tagtxt}")

    print()
    for r in results:
        if not r["truncated"]:
            print(f"### {r['name']} — ✅ 未超窗（{r['total']} ≤ 500），全文可见")
            continue
        print(f"### {r['name']} — ⚠️ 超窗 {r['total'] - MAXLEN} 字，"
              f"{len(r['invisible'])}/{r['units']} 条规则单元对路由器不可见")
        for u in r["invisible"]:
            tags = ("[" + "/".join(u["tags"]) + "]") if u["tags"] else ""
            print(f"    ✂ pos={u['pos']:>4}  {tags:<12} {u['text'][:70]}")
        print()

    print("=" * 100)
    print("可见区末尾 60 字（路由器看到的就是到这里为止）：")
    for r in results:
        print(f"  {r['name']:<24} …{r['render'][-60:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
