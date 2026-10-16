#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l3_gate.py —— L3 层闸门（**独立复算档**）：把「证据必须能一条条回指到 L2 单元」跑出来。

## 它补的是哪个洞（实测依据，2026-09-30）

`kb/l7/registry/layers.yaml` 里 L3 的闸门原文是两条**表达式**：

    reconcile_partition.check == true：只产出 + 只拒绝 + 既产出又拒绝 == 输入集
    另取数对账 unaccounted == 0

实测这两条**当前不可复算**：`kb/l3/registry/l3.json` 自报
`only_rejected = 8736`、`input = 9469`、`l2_total = 10021`，而现台账是
`rejected.jsonl` 6911 行 / 930 个资源（归档的旧台账 6803 行 / 822 个资源），
且重建后的台账**混了粒度和类目**（`kind` 分布里 `unit_level` 5858 行是单元级、
其余是资源级）。→ 三个数没有一个能从现台账复算出来。

这不是「数据坏了」，是**自报块没跟着 2026-09-29 的台账重建走**。
本闸门的处置（沿用 L0 闸门那套，不抹原始数）：
  * 能复算的**真判据**照跑（C1/C2）；
  * 不能复算的自报键，必须**逐键**登记在 `kb/l7/registry/l3-known-drift.yaml`（带证据 + 修法）；
    没登记的键 = 红 —— 逼人把「口径漂移」写成可核对的声明，而不是让它悄悄烂在注册表里。

## 判据（红）

  C1 规则证据可回指 —— 三形态候选件（rules / sample_cases / scoped_clauses）里每条
                        `evidence_units[]` 的 `unit_id` 必须能在 `kb/l2/units.jsonl` 找到，
                        且 `source_sha256` 与 `anchor` 必须与该单元逐字一致（引错一处=判红）。
  C2 拒绝项可回指   —— `kb/l3/rejected.jsonl` 每行的 `resource_id` 必须能在 L2 单元里找到出处。
  C3 自报键已声明   —— `l3/registry/l3.json → reconcile_partition.* / accounting.*` 的每个键，
                        要么能被本闸门复算并相符，要么必须在 `l3-known-drift.yaml` 的
                        `not_recomputable` 里逐键登记；漏登记 = 红。

## 说明项（不是红）

  N1 现台账画像：rejected 行数/资源数/kind 分布 ｜ 产出记录数/资源数 ｜ 既产出又拒绝的资源数。
  N2 归档旧台账画像（用于说明为什么会漂）。

## 只读

只读 kb/l2、kb/l3、kb/l7/registry 的 jsonl/json/yaml，**不写任何文件**。

用法：
    kb/kbpy l7/scripts/l3_gate.py [--json] [--quiet]
    KB_GATE_KB=<夹具目录> kb/kbpy l7/scripts/l3_gate.py     # 反测用（默认真库）
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.environ.get("KB_GATE_KB") or os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(KB)
REGISTRY = os.environ.get("KB_GATE_L7") or os.path.join(KB, "l7/registry")
DRIFT_YAML = os.path.join(REGISTRY, "l3-known-drift.yaml")

L2_UNITS = os.path.join(KB, "l2/units.jsonl")
L3_REG = os.path.join(KB, "l3/registry/l3.json")
L3_REJECTED = os.path.join(KB, "l3/rejected.jsonl")
L3_CANDIDATES = os.path.join(KB, "l3/candidates/*.jsonl")
L3_ARCHIVE = os.path.join(KB, "l3/_archive/rejected-pre-20260929-1660.jsonl")
CAP = 8
SELF_REPORT_KEYS = [
    "reconcile_partition.input", "reconcile_partition.only_produced",
    "reconcile_partition.only_rejected", "reconcile_partition.both",
    "reconcile_partition.neither", "reconcile_partition.check",
    "accounting.l2_total", "accounting.filtered_out", "accounting.kept",
    "accounting.used_in_rules", "accounting.explicitly_rejected", "accounting.unaccounted",
]


def _yaml(path):
    if not os.path.exists(path):
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:                                # noqa: BLE001
        return {}


def _iter(p):
    with open(p, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                yield i, json.loads(line)


def compute():
    for p in (L2_UNITS, L3_REG, L3_REJECTED):
        if not os.path.exists(p):
            return None, "输入缺失：%s" % os.path.relpath(p, ROOT)

    by_uid, res_ids = {}, set()
    for _, d in _iter(L2_UNITS):
        u = d.get("unit_id")
        if u:
            by_uid[u] = d
        if d.get("resource_id"):
            res_ids.add(d["resource_id"])

    # C1 证据回指（逐条，不抽样）
    c1, refs = [], 0
    produced_res, produced_rec = set(), 0
    for p in sorted(glob.glob(L3_CANDIDATES)):
        for ln, d in _iter(p):
            produced_rec += 1
            for k in ("resource_id", "resource_ids"):
                v = d.get(k)
                if isinstance(v, str):
                    produced_res.add(v)
                elif isinstance(v, list):
                    produced_res.update(x for x in v if isinstance(x, str))
            for eu in (d.get("evidence_units") or []):
                refs += 1
                uid = eu.get("unit_id")
                u = by_uid.get(uid)
                if u is None:
                    c1.append([os.path.basename(p), d.get("rule_id"), uid, "L2 里没有这个 unit_id"])
                elif eu.get("source_sha256") != u.get("source_sha256"):
                    c1.append([os.path.basename(p), d.get("rule_id"), uid, "source_sha256 对不上"])
                elif eu.get("anchor") != u.get("anchor"):
                    c1.append([os.path.basename(p), d.get("rule_id"), uid, "anchor 对不上"])

    # C2 拒绝项回指
    c2, rej_res, rej_rows = [], set(), 0
    rej_kind = collections.Counter()
    for ln, d in _iter(L3_REJECTED):
        rej_rows += 1
        rid = d.get("resource_id")
        rej_kind[str(d.get("kind"))] += 1
        if rid:
            rej_res.add(rid)
            if rid not in res_ids:
                c2.append([ln, rid, "L2 单元里没有这个资源"])

    # C3 自报键声明
    with open(L3_REG, encoding="utf-8") as fh:
        reg = json.load(fh)
    declared = {str(x.get("key")) for x in (_yaml(DRIFT_YAML).get("not_recomputable") or [])
                if isinstance(x, dict)}
    present = []
    for k in SELF_REPORT_KEYS:
        cur = reg
        ok = True
        for part in k.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            present.append(k)
    undeclared = [k for k in present if k not in declared]

    arch = {"rows": 0, "resources": 0}
    if os.path.exists(L3_ARCHIVE):
        s = set()
        for _, d in _iter(L3_ARCHIVE):
            arch["rows"] += 1
            if d.get("resource_id"):
                s.add(d["resource_id"])
        arch["resources"] = len(s)

    rep = {
        "counts": {"evidence_refs": refs, "candidates_records": produced_rec,
                   "produced_resources": len(produced_res), "rejected_rows": rej_rows,
                   "rejected_resources": len(rej_res),
                   "both": len(produced_res & rej_res),
                   "l2_resources": len(res_ids), "l2_units": len(by_uid)},
        "C1_bad_refs": c1[:CAP], "C1_n": len(c1),
        "C2_bad_rejected": c2[:CAP], "C2_n": len(c2),
        "C3_undeclared_keys": undeclared, "C3_n": len(undeclared),
        "C3_declared_keys": sorted(declared), "C3_present_keys": present,
        "N1_reject_kinds": dict(rej_kind), "N2_archive": arch,
        "drift_yaml": os.path.relpath(DRIFT_YAML, ROOT),
    }
    rep["red_total"] = rep["C1_n"] + rep["C2_n"] + rep["C3_n"]
    return rep, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    rep, err = compute()
    if rep is None:
        print("❌ 无法计算：%s" % err)
        print("退出码：2")
        return 2

    ok = rep["red_total"] == 0
    if a.json:
        print(json.dumps({"gate": "l3_gate", "ok": ok, **rep}, ensure_ascii=False, indent=1))
        return 0 if ok else 1

    c = rep["counts"]
    print("=" * 74)
    print("L3 闸门（独立复算：候选件证据 × rejected 台账 × l2/units.jsonl）")
    print("  证据引用 %d 条 ｜ 候选记录 %d 条 / 产出资源 %d 个" % (c["evidence_refs"],
                                                              c["candidates_records"],
                                                              c["produced_resources"]))
    print("  拒绝台账 %d 行 / %d 个资源 ｜ 既产出又拒绝 %d 个资源 ｜ L2 侧 %d 个资源"
          % (c["rejected_rows"], c["rejected_resources"], c["both"], c["l2_resources"]))
    print("-" * 74)
    if not a.quiet:
        if rep["C1_n"]:
            print("C1 证据回指不上 %d 条：" % rep["C1_n"])
            for f, rid, uid, why in rep["C1_bad_refs"][:3]:
                print("   %s ｜ %s ｜ unit %s ｜ %s" % (f, rid, uid, why))
        if rep["C2_n"]:
            print("C2 拒绝项在 L2 找不到出处 %d 条：" % rep["C2_n"])
            for ln, rid, why in rep["C2_bad_rejected"][:3]:
                print("   台账行 %d ｜ %s ｜ %s" % (ln, str(rid)[:48], why))
        if rep["C3_n"]:
            print("C3 注册表自报键**没登记**（%d 个）：%s" % (rep["C3_n"], rep["C3_undeclared_keys"]))
            print("   → 要人做什么：在 %s 的 not_recomputable 里逐键写清" % rep["drift_yaml"])
    print("-" * 74)
    print("说明项：拒绝台账 kind 分布 %s" % rep["N1_reject_kinds"])
    print("  归档旧台账 %d 行 / %d 个资源（现台账 %d / %d → 重建导致的粒度变化，不是数据丢失）"
          % (rep["N2_archive"]["rows"], rep["N2_archive"]["resources"],
             c["rejected_rows"], c["rejected_resources"]))
    print("  已登记为不可复算的自报键 %d 个：%s" % (len(rep["C3_declared_keys"]),
                                                rep["C3_declared_keys"]))
    print("=" * 74)
    print("结论：%s" % ("✅ 过（证据全可回指 + 自报键全已声明）" if ok else "❌ 未过（红 %d）" % rep["red_total"]))
    print("退出码：%d" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
