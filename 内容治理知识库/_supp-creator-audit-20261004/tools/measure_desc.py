#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按宿主真实口径量候选 description：折叠空白 → 500 字窗口 → 逐规则单元可见性。

口径与 tools/desc_lint.py 同源（都已用宿主源码 :18/:338/:339 核过），
并**交叉验过** root-skills-eval 工程里 L1–L7 七件的既有实测值（475/478/491/492/492/496 全中）。

用法：python3 measure_desc.py <candidates.json>
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from desc_lint import norm  # noqa: E402

MAXLEN = 500


def report(name, desc):
    flat = norm(desc)
    over = len(flat) > MAXLEN
    cut = MAXLEN - 3 if over else len(flat)
    inv, pos, seen = [], 0, set()
    for u in re.split(r"[、；。]", flat):
        if not u.strip():
            continue
        i = flat.find(u, pos)
        if i < 0:
            i = flat.find(u)
        pos = max(pos, i + len(u))
        if u in seen:
            continue
        seen.add(u)
        if i >= cut:
            inv.append(u.strip()[:36])
    first = re.split(r"[。；]", flat)[0]
    return {
        "skill": name, "folded": len(flat), "over": over, "visible": cut,
        "first_is_trigger": bool(re.match(r"^\s*当用户", first)),
        "has_trigger_kw": "触发词：" in flat,
        "has_boundary": bool(re.search(r"不适用|判归|→\s*kb-", flat)),
        "has_undefined": bool(re.search(r"追问|不加载", flat)),
        "has_safety": bool(re.search(r"rm -rf|破坏|越权|--apply|清空", flat)),
        "invisible": inv,
    }


def main():
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    print(f"{'skill':<24}{'折叠':>5}{'超窗':>5}{'可见':>5} {'首句触发':<9}{'触发词块':<9}{'边界':<6}{'欠定':<6}{'安全':<6}{'不可见单元':>10}")
    bad = 0
    for k, v in d.items():
        r = report(k, v)
        flag = "★" if r["over"] or not r["first_is_trigger"] or not r["has_trigger_kw"] else " "
        print(f"{r['skill']:<24}{r['folded']:>5}{('是' if r['over'] else '否'):>5}{r['visible']:>5} "
              f"{('是' if r['first_is_trigger'] else '否'):<9}{('是' if r['has_trigger_kw'] else '否'):<9}"
              f"{('是' if r['has_boundary'] else '否'):<6}{('是' if r['has_undefined'] else '否'):<6}"
              f"{('是' if r['has_safety'] else '否'):<6}{len(r['invisible']):>10}{flag}")
        if r["over"] or not r["first_is_trigger"] or not r["has_trigger_kw"] or r["invisible"]:
            bad += 1
            for u in r["invisible"]:
                print(f"      ↳ 不可见: {u}")
    print(f"\n不合格 {bad} / {len(d)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
