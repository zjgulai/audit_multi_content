#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l0_l3_skill_evidence.py —— 核 **L0–L3** 的「逐层调了 skill」是否成立（只读）。

## 为什么需要它（2026-10-05 用户裁定「补一把核 L0–L3 的尺子」）

库里的 `kb/l7/scripts/skill_invocation_audit.py` 只覆盖 **L4–L7**（那是 ②d 四条审计的定义）。
于是「日更走 skill」这条链上，**L0/L1/L2/L3 的 skill 证据从来没有被任何尺子量过** ——
落章里写了 `skill` 字段，但没人核它**是不是本层该调的那个**、也**没人核它是不是非预演**。
⇒ 那是「静默退化」的完美入口：某层漏调 skill，其余闸门全绿。

## 我不是新造第 7 把尺子（重要）

判据**完全沿用库里已有的两样东西**，一个字都没有新发明：
  · **该调谁** = `kb/l7/registry/layers.yaml` 各层的 `skill:` 字段（唯一真源，现读，不抄）；
  · **有没有调** = 层侧落章 `kb/<lx>/runs/<RUN>*.json` 的 `skill` 字段（与审计同一处证据）；
  · **是不是真跑** = 落章的 `applied` 必须为真（预演件不算 —— 与审计 E5 同一口径）。
即：**同一把尺子，量到原审计没覆盖的那四层。**

## 用法

    python3 kb/l8/l0_l3_skill_evidence.py --base daily-20261005-0957
    python3 kb/l8/l0_l3_skill_evidence.py --base <BASE> --json

退出码：0 = 四层都核到了且一致 ｜ 3 = 有红或 no-data ｜ 2 = 用不了（参数/注册表问题）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAYERS_YAML = os.path.join(ROOT, "kb", "l7", "registry", "layers.yaml")
CHECK_LAYERS = ["L0", "L1", "L2", "L3"]          # 只补审计没覆盖的那四层


def declared():
    """从 layers.yaml 现读「层 → 该调的 skill 列表」。读不到就拒绝跑（不猜）。"""
    try:
        import yaml
    except Exception as exc:                                    # noqa: BLE001
        raise SystemExit("!! 需要 pyyaml：%r" % (exc,))
    with open(LAYERS_YAML, encoding="utf-8") as fh:
        d = yaml.safe_load(fh)
    out = {}
    for L in d.get("layers") or []:
        lid = L.get("id") or L.get("layer")
        if lid is None:
            continue
        sk = L.get("skill")
        if isinstance(sk, str):
            sk = [sk]
        out[str(lid).upper()] = [s for s in (sk or []) if s]
    return out


def norm(v):
    """落章里的 skill 可能是 str / 'a,b' / list —— 归一成集合。"""
    if v is None:
        return set()
    if isinstance(v, str):
        return {x.strip() for x in v.split(",") if x.strip()}
    if isinstance(v, (list, tuple)):
        out = set()
        for x in v:
            out |= norm(x)
        return out
    return set()


def stamps(lid, base):
    """取该层本 RUN 的**非预演**落章（预演件按 E5 口径不算执行证据）。"""
    pat = os.path.join(ROOT, "kb", lid.lower(), "runs", base + "*.json")
    got = []
    for p in sorted(glob.glob(pat)):
        n = os.path.basename(p).lower()
        if "dryrun" in n or "dry-run" in n:
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:                                       # noqa: BLE001
            continue
        got.append((p, d))
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="日更 RUN 前缀，如 daily-20261005-0957")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    want = declared()
    rows, red = [], 0
    for lid in CHECK_LAYERS:
        d_sk = set(want.get(lid) or [])
        if not d_sk:
            rows.append({"layer": lid, "state": "⚪ no-data",
                         "why": "layers.yaml 没给该层登记 skill"})
            red += 1
            continue
        ss = stamps(lid, a.base)
        if not ss:
            rows.append({"layer": lid, "state": "⚪ no-data",
                         "why": "本 RUN 在该层没有非预演落章（未跑 / 只跑了预演）",
                         "declared": sorted(d_sk)})
            red += 1
            continue
        obs, applied, files, ignored = set(), [], [], []
        for p, d in ss:
            # ★ 只看**声称调了 skill** 的落章（带 skill 字段的那些）。
            #   层里还有引擎自己的台账件（如 L1.json），它们**根本没声称调 skill**，
            #   2016-10-05 实测：把它们一并要求 applied=true 会**误判红** —— 判据一开始被我定严了。
            if "skill" not in d:
                ignored.append(os.path.basename(p))
                continue
            obs |= norm(d.get("skill"))
            applied.append(bool(d.get("applied")))
            files.append(os.path.relpath(p, ROOT))
        if not files:
            rows.append({"layer": lid, "state": "⚪ no-data",
                         "why": "本 RUN 在该层没有「声称调了 skill」的落章（未跑 / 只跑了预演）",
                         "declared": sorted(d_sk), "ignored": ignored})
            red += 1
            continue
        ok_skill = (obs == d_sk)
        # 至少**一枚**是非预演 = 这一层真的执行过（有台账件不算执行证据）
        ok_applied = any(applied)
        st = "✅ 过" if (ok_skill and ok_applied) else "🔴 红"
        if not (ok_skill and ok_applied):
            red += 1
        rows.append({"layer": lid, "state": st,
                     "declared": sorted(d_sk), "observed": sorted(obs),
                     "applied": applied, "stamps": files, "ignored": ignored,
                     "why": ("落章 skill 与声明一致、且至少一枚非预演" if (ok_skill and ok_applied)
                             else ("落章 skill %s ≠ 声明 %s" % (sorted(obs), sorted(d_sk)) if not ok_skill
                                   else "声称调 skill 的落章**全是预演**（applied 无一为真）⇒ 不算执行证据"))})

    res = {"base": a.base, "layers_yaml": os.path.relpath(LAYERS_YAML, ROOT),
           "red_total": red, "rows": rows}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("=" * 74)
        print("L0–L3 「逐层调了 skill」核验（只读）｜ BASE = %s" % a.base)
        print("判据：该调谁 = layers.yaml 的 skill 字段 ｜ 有没有调 = 层侧落章 skill ｜ 真跑 = applied")
        print("=" * 74)
        for r in rows:
            print("  %-14s %s" % (r["state"], r["layer"]))
            if "declared" in r:
                print("      声明 %s ｜ 落章 %s ｜ applied %s"
                      % (r.get("declared"), r.get("observed"), r.get("applied")))
            print("      %s" % r["why"])
        print("-" * 74)
        print("结论：%s ｜ 红 %d/%d" % ("✅ 全过" if red == 0 else "🔴 有红或 no-data",
                                      red, len(CHECK_LAYERS)))
        print("退出码：%d" % (0 if red == 0 else 3))
    return 0 if red == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
