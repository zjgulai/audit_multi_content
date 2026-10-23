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
RETIRED_YAML = os.path.join(REGISTRY, "l3-retired-resources.yaml")

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


def _same_anchor(u, anc):
    """定稿/候选里的 anchor 与 L2 单元**现在的**锚点是不是同一坐标。

    ★ 2026-10-20 补（与 l4_gate 同一条，两把尺子必须同口径）：L2 的图片级单元把字段级锚点
      从 `#素材/<rec>/图片素材/#img.1`（历史误用）改成 `#素材/<rec>/图片素材`，旧锚点留进
      `legacy_anchors`（写方自述「不丢引用」）。只比 `anchor` ⇒ 一次**坐标修正**把本闸门红 512。
      ⇒ 判据 = `anchor` 相同 **或** 命中 `legacy_anchors`；sha 与「单元必须存在」一个字没放宽。
      反向对照：`--selftest` 的 T3 把 legacy 摘掉必须**精确变红**。
    """
    return anc == (u.get("anchor") or "") or (anc is not None and
                                              anc in (u.get("legacy_anchors") or []))


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
                elif not _same_anchor(u, eu.get("anchor")):
                    c1.append([os.path.basename(p), d.get("rule_id"), uid, "anchor 对不上"])

    # C2 拒绝项回指
    # ★★ 2026-10-20：**资源已下线的台账行不算红**，但必须是**逐条登记**过的
    #   （`kb/l7/registry/l3-retired-resources.yaml`，每条带下线原因 + 退役 run + 证据）。
    #   为什么非加不可：飞书「负面样本」表 2026-10-14 整表重建 ⇒ 记录 id 全换代；
    #   那批旧资源的单元于 2026-10-20T16:17:26 被 `prune_gone_units.py` 退役
    #   （run=prune-20261020-161725），而 12:55 那轮重建的拒绝台账仍指着旧资源 ⇒ C2 红 240。
    #   **没有放宽**：没登记的照样红；登记的进说明项被逐条点名（不静默）。
    retired = set()
    for x in (_yaml(RETIRED_YAML).get("retired") or []):
        if isinstance(x, dict) and x.get("resource_id"):
            retired.add(str(x["resource_id"]))
        elif isinstance(x, str):
            retired.add(x)
    c2, c2_retired, rej_res, rej_rows = [], [], set(), 0
    rej_kind = collections.Counter()
    for ln, d in _iter(L3_REJECTED):
        rej_rows += 1
        rid = d.get("resource_id")
        rej_kind[str(d.get("kind"))] += 1
        if rid:
            rej_res.add(rid)
            if rid not in res_ids:
                if rid in retired:
                    c2_retired.append([ln, rid])
                else:
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
        "C2_bad_rejected": c2[:CAP], "C2_n": len(c2), "C2_retired_n": len(c2_retired),
        "C3_undeclared_keys": undeclared, "C3_n": len(undeclared),
        "C3_declared_keys": sorted(declared), "C3_present_keys": present,
        "N1_reject_kinds": dict(rej_kind), "N2_archive": arch,
        "drift_yaml": os.path.relpath(DRIFT_YAML, ROOT),
    }
    rep["red_total"] = rep["C1_n"] + rep["C2_n"] + rep["C3_n"]
    return rep, None


def _selftest_fixture(root, unit_anchor, legacy, unit_sha, ev_anchor, ev_sha,
                      unit_exists=True, reject_res="res-1", retired=None):
    """最小夹具：1 个 L2 单元 + 1 条候选证据 + 1 行拒绝台账。只写临时目录。"""
    for d in ("l2", "l3/candidates", "l3/registry", "l7/registry"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    unit = {"unit_id": "u1", "resource_id": "res-1", "anchor": unit_anchor,
            "source_sha256": unit_sha}
    if legacy:
        unit["legacy_anchors"] = legacy
    with open(os.path.join(root, "l2/units.jsonl"), "w", encoding="utf-8") as fh:
        if unit_exists:
            fh.write(json.dumps(unit, ensure_ascii=False) + "\n")
    with open(os.path.join(root, "l3/candidates/cand.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"rule_id": "r1", "evidence_units": [
            {"unit_id": "u1", "anchor": ev_anchor, "source_sha256": ev_sha}]},
            ensure_ascii=False) + "\n")
    with open(os.path.join(root, "l3/rejected.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "unit_level", "resource_id": reject_res},
                            ensure_ascii=False) + "\n")
    with open(os.path.join(root, "l3/registry/l3.json"), "w", encoding="utf-8") as fh:
        json.dump({}, fh)
    with open(os.path.join(root, "l7/registry/l3-retired-resources.yaml"), "w", encoding="utf-8") as fh:
        fh.write("retired:\n")
        for r in (retired or []):
            fh.write("  - resource_id: %s\n    why: 夹具：源已下线\n" % r)


def selftest():
    """C1/C2 的**反向对照**：判据改完还必须能精确变红。"""
    import shutil
    import tempfile

    global L2_UNITS, L3_REG, L3_REJECTED, L3_CANDIDATES, L3_ARCHIVE, DRIFT_YAML, RETIRED_YAML
    saved = (L2_UNITS, L3_REG, L3_REJECTED, L3_CANDIDATES, L3_ARCHIVE, DRIFT_YAML, RETIRED_YAML)
    NEW, OLD, sha = "#素材/R1/图片素材", "#素材/R1/图片素材/#img.1", "sha-A"
    cases = [
        ("T1 锚点逐字相同 ⇒ 过", dict(unit_anchor=NEW, legacy=None, unit_sha=sha,
                                    ev_anchor=NEW, ev_sha=sha), 0, 0, None),
        ("T2 旧写法 + 单元留了 legacy ⇒ 过（本次修复要治的那条）",
         dict(unit_anchor=NEW, legacy=[OLD], unit_sha=sha, ev_anchor=OLD, ev_sha=sha),
         0, 0, None),
        ("T3 反例：同样的旧锚点、把 legacy 摘掉 ⇒ C1 必须红",
         dict(unit_anchor=NEW, legacy=None, unit_sha=sha, ev_anchor=OLD, ev_sha=sha),
         1, 0, "anchor 对不上"),
        ("T4 反例：sha 不一致 ⇒ C1 必须红",
         dict(unit_anchor=NEW, legacy=[OLD], unit_sha=sha, ev_anchor=OLD, ev_sha="sha-B"),
         1, 0, "source_sha256 对不上"),
        ("T5 反例：L2 里没有这个单元 ⇒ C1 必须红（C2 不判：单元整份没有时台账那行也必然找不到）",
         dict(unit_anchor=NEW, legacy=[OLD], unit_sha=sha, ev_anchor=OLD, ev_sha=sha,
              unit_exists=False), 1, None, "没有这个 unit_id"),
        ("T6 反例：拒绝台账指向 L2 没有的资源 ⇒ C2 必须红（证明没把 C2 改坏）",
         dict(unit_anchor=NEW, legacy=[OLD], unit_sha=sha, ev_anchor=OLD, ev_sha=sha,
              reject_res="res-404"), 0, 1, None),
        ("T7 同一行资源**已登记下线** ⇒ C2 不红（进说明项，不静默）",
         dict(unit_anchor=NEW, legacy=[OLD], unit_sha=sha, ev_anchor=OLD, ev_sha=sha,
              reject_res="res-404", retired=["res-404"]), 0, 0, None),
        ("T8 反向对照：登记件里换成别的资源 ⇒ 原来那行必须精确变红",
         dict(unit_anchor=NEW, legacy=[OLD], unit_sha=sha, ev_anchor=OLD, ev_sha=sha,
              reject_res="res-404", retired=["res-other"]), 0, 1, None),
    ]
    rows, ok = [], True
    tmp = tempfile.mkdtemp(prefix="l3gate-selftest-")
    try:
        for name, kw, want_c1, want_c2, why in cases:
            root = os.path.join(tmp, name.split()[0])
            _selftest_fixture(root, **kw)
            L2_UNITS = os.path.join(root, "l2/units.jsonl")
            L3_REG = os.path.join(root, "l3/registry/l3.json")
            L3_REJECTED = os.path.join(root, "l3/rejected.jsonl")
            L3_CANDIDATES = os.path.join(root, "l3/candidates/*.jsonl")
            L3_ARCHIVE = os.path.join(root, "l3/_archive/none.jsonl")
            DRIFT_YAML = os.path.join(root, "l7/registry/l3-known-drift.yaml")
            RETIRED_YAML = os.path.join(root, "l7/registry/l3-retired-resources.yaml")
            rep, err = compute()
            if rep is None:
                rows.append((name, False, "夹具算不出来：%s" % err))
                ok = False
                continue
            got_why = " ".join(str(x[-1]) for x in rep["C1_bad_refs"])
            good = rep["C1_n"] == want_c1 and \
                (want_c2 is None or rep["C2_n"] == want_c2) and \
                (why is None or why in got_why)
            ok = ok and good
            rows.append((name, good, "C1_n=%d C2_n=%d%s"
                         % (rep["C1_n"], rep["C2_n"], ("：" + got_why) if got_why else "")))
    finally:
        L2_UNITS, L3_REG, L3_REJECTED, L3_CANDIDATES, L3_ARCHIVE, DRIFT_YAML, RETIRED_YAML = saved
        shutil.rmtree(tmp, ignore_errors=True)

    for name, good, detail in rows:
        print("  %s %s ｜ %s" % ("✅" if good else "❌", name, detail))
    print("l3_gate --selftest %s（%d/%d）" % ("PASS" if ok else "FAIL",
                                             sum(1 for _, g, _ in rows if g), len(rows)))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="C1/C2 判据的反向对照（造夹具，不碰真库）")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

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
        if rep.get("C2_retired_n"):
            print("  说明项（不是红）：拒绝台账里 %d 行指向**已登记下线**的旧资源"
                  "（`kb/l7/registry/l3-retired-resources.yaml`，源记录已随飞书表重建换代）"
                  % rep["C2_retired_n"])
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
