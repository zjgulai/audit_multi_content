#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_eval-backfill-skills-yaml.py —— 把盲测实测结果回填进 kb/l7/registry/skills.yaml（驱动侧助手）。

为什么要有它：三件 skill 的登记表 note 里写着「**触发盲测未跑**」。报告一出来就要把
这句话换成**实测 F1 + 日期 + 报告路径**，否则登记表继续撒谎（这正是本库最忌讳的
「声明与实现漂移」）。

设计（克制三条）：
  · **默认干跑**：不加 `--apply` 只打印将要写入的文本与逐行 diff，一个字节都不落盘；
  · **数据不全就拒绝**：三件里只要有一件没有 `f1`（报告没出/字段读不到），直接退出码 2，不半写；
  · **只追加一句**：只改 note 字段末尾追加一段，不动其它字段；写完提示必须复跑三个闸门。

用法：
    KB_INTERP_OK=1 /usr/bin/python3 _eval-backfill-skills-yaml.py            # 干跑（看 diff）
    KB_INTERP_OK=1 /usr/bin/python3 _eval-backfill-skills-yaml.py --apply    # 真写
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
SKILLS_YAML = os.path.join(ROOT, "kb", "l7", "registry", "skills.yaml")
THREE = ["kb-canonical-lookup", "kb-p0-check", "kb-recall"]


def collect():
    """复用汇总器的解析逻辑，拿三件的 f1 / report 路径。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("agg", os.path.join(ROOT, "_eval-agg-20260930.py"))
    agg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agg)
    out = {}
    for s in THREE:
        out[s] = agg.summarize(s)
    return out


def build_sentence(row):
    f1 = row.get("f1")
    if not isinstance(f1, (int, float)):
        return None
    today = _dt.date.today().isoformat()
    return (" ｜ **%s 触发盲测（root-skills-eval）**：**F1 = %.4f**%s，"
            "track_a = %s，封顶后 track_c = %s，报告 `%s`。"
            "（A 卷 %s 条 × 3 轮；B 卷 10 条封印，未进修复流程则不开封。）"
            % (today, f1,
               "（**过门槛 ≥0.90**）" if f1 >= 0.90 else "（**未过门槛 0.90**）",
               row.get("track_a"), row.get("track_c"), row.get("report") or "（读不到路径）",
               "25" if "p0" in row["skill"] or "canonical" in row["skill"] else "50"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写盘（默认干跑）")
    a = ap.parse_args()

    rows = collect()
    print("=" * 92)
    print("盲测结果回填 skills.yaml · %s" % ("**真写**" if a.apply else "干跑（不落盘）"))
    print("=" * 92)
    missing = []
    for s in THREE:
        r = rows[s]
        line = build_sentence(r) if r.get("state") == "ok" else None
        print("\n── %s" % s)
        print("   报告状态：%s" % r.get("state"))
        if r.get("report"):
            print("   报告：%s" % r["report"])
        if line is None:
            print("   ✗ 拿不到 f1 → **拒绝执行**（不半写）")
            missing.append(s)
        else:
            print("   将追加：%s" % line.strip()[:160])
    if missing:
        print("\n结论：%d/3 件缺 f1（%s）→ 报告还没出齐，**本次不写**。" % (len(missing), "、".join(missing)))
        print("     报告出齐后重跑本脚本；查看进度用 _eval-agg-20260930.py。")
        return 2

    text = open(SKILLS_YAML, encoding="utf-8").read()
    new = text
    for s in THREE:
        line = build_sentence(rows[s]).rstrip()
        # 定位该 skill 的 note 行，追加到该行末尾（引号内）
        marker = "  - id: %s\n" % s
        i = new.find(marker)
        if i < 0:
            print("✗ 在 skills.yaml 里找不到 %s 的行" % s)
            return 2
        j = new.find("\n    note: ", i)
        if j < 0:
            print("✗ %s 没有 note 字段" % s)
            return 2
        end = new.find('"\n', j)
        if end < 0:
            print("✗ %s 的 note 不是单行双引号串，本脚本不擅自改（交人处理）" % s)
            return 2
        new = new[:end] + line.replace('"', "'") + new[end:]

    print("\n" + "-" * 92)
    print("diff 摘要（只在三行 note 末尾各追加一段）：")
    for s in THREE:
        print("  · %s 的 note 追加 %d 字符" % (s, len(build_sentence(rows[s]).rstrip())))
    if not a.apply:
        print("\n干跑结束：**没有写任何文件**。要真写加 --apply。")
        return 0

    with open(SKILLS_YAML, "w", encoding="utf-8") as fh:      # .yaml 不受信封影响
        fh.write(new)
    print("\n已写入 %s" % os.path.relpath(SKILLS_YAML, ROOT))
    print("⚠️ 写完必须复跑三闸门证明登记表没被改坏：")
    print("   kb/kbpy l7/scripts/skills_check.py && kb/kbpy l7/scripts/layers_check.py && "
          "kb/kbpy l7/scripts/skill_conformance.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
