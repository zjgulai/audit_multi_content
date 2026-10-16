#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l2_gate.py —— L2 层闸门（**独立复算档**）：不读 l2.json 的自报计数，直接从原始件重算。

## 它补的是哪个洞（实测依据，2026-09-30 逐条跑出来的）

① `kb/l2/registry/l2.json → accounting_rule` 原文：

      每类库：L1 中有内容的资源数 == 被切分资源数 + 明确跳过资源数（差额必须为 0）

   实测：按「当前快照」重算这条等式**永远不平衡**（合计差 23；逐库 −20 / +64 / −4 / −13 / −4）。
   原因不是数据坏了，是这条式子**拿两个不同时点的数在相减**：
   「L1 中有内容的资源数」是**今天的快照**（L0 失效/撤回会把资源移出输入集），
   「被切分资源数」是**历次 run 累积**的产出。
   → snapshot 上做减法，是一条**不可计算**的判据。本闸门不照抄它（照抄 = 每天报一个假红）。

② 台账里 `unit_count` 的口径**没有定义清楚**，实测三种口径都不全域成立：

   | 口径 | 相符 / 有单元的资源数 |
   |---|---|
   | 只取该资源「最后一条 split 行」的 unit_count | 1520 / 1626 |
   | 该资源「所有 split 行」之和 | 1624 / 1626 |
   | 该资源「所有行（含 invalidated）」之和 | 1320 / 1626 |

   两种真实形态并存：
   * **追加形态**：`split=1`(09-24) → `invalidated=1` → `split=5`(09-29)，实际 6 条 → 两批都留；
   * **替换形态**：`split=12` → `invalidated=12` → `split=12`，实际 12 条 → 后批替换前批。
   两者行序完全一样，**用行本身分不出来**。
   → 所以本闸门**不去猜公式**，改用**能证的上下界**（C3），并把这份口径歧义如实报成 N3。

## 判据（红外按顺序）

  C1 台账行可解析 —— 每行都必须是合法 JSON（坏行 = 台账被写坏，无歧义 → 红）。
                     「非资源行」（有 resource_id 才叫资源行）**不判红**：它可能是层引擎
                     有意追加的变更记录（见 N4），属**口径待裁**，一律打印 + 给出修法。
  C2 run 内序列合法 —— 同一 (resource_id, observed_at) 只允许：单行；或 `invalidated → split` /
                     `invalidated → skipped`（重切约定）。其余组合（split→invalidated、两条 split…）
                     一律判红 ——「谁说了算」必须有唯一答案。
  C3 账实上下界   —— 有单元的每个资源：`max(各行 unit_count) ≤ 实际单元数 ≤ Σ(split 行 unit_count)`。
                     下界破 = 最新一批的单元**少了**（疑似丢数）；上界破 = 有单元**没有台账出处**。
  C4 产物归属     —— units.jsonl 里的 resource_id 必须**至少有过一条 split 行**（否则单元无出处）。
  C5 上游可溯     —— 每条 split 行的 resource_id 必须能在 kb/l1/manifest_l1.jsonl 里找到。

## 说明项（不是红，但必须打印，不许静默）

  N1 被作废后仍留产物 —— 有 split 行、其后又被 invalidated 的资源数（上游变更，L2 现状不撤产物）。
  N2 滞后            —— 当前输入集（L0 有效 + L1 ok/extracted）里还没有 split/skipped 结论的资源数。
  N3 口径歧义        —— 上述 ② 的三口径不符数（要 L2 层主把 unit_count 口径写进 l2.json，属整改项）。

## 只读

只读 kb/l0、kb/l1、kb/l2 的 jsonl，**不写任何文件**（连报告都不写）。

用法：
    kb/kbpy l7/scripts/l2_gate.py            # 给人看
    kb/kbpy l7/scripts/l2_gate.py --json     # 机器可读
    kb/kbpy l7/scripts/l2_gate.py --quiet    # 只出汇总
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.environ.get("KB_GATE_KB") or os.path.dirname(os.path.dirname(HERE))   # …/kb
ROOT = os.path.dirname(KB)                            # kb/ 的上一级（cwd 约定）
# KB_GATE_KB：**只给反测用** —— 指向一份夹具目录（同样的 l0/l1/l2 布局），
# 好在「不碰真库」的前提下把判据弄坏、确认闸门真的会红。默认永远是真库。

L0_MANIFEST = os.path.join(KB, "l0/manifest.jsonl")
L1_MANIFEST = os.path.join(KB, "l1/manifest_l1.jsonl")
L2_MANIFEST = os.path.join(KB, "l2/manifest_l2.jsonl")
L2_UNITS = os.path.join(KB, "l2/units.jsonl")

RESULTS = ("split", "skipped", "invalidated")
L1_HAS_CONTENT = ("ok", "extracted")
ALLOWED_SEQ = {("invalidated", "split"), ("invalidated", "skipped")}
CAP = 8


def _iter_jsonl(path):
    """逐行产出 (行号, 对象, 错误)。坏 JSON 不抛异常。"""
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line), None
            except Exception as exc:                 # noqa: BLE001
                yield i, None, "%s" % exc


def compute():
    for p in (L0_MANIFEST, L1_MANIFEST, L2_MANIFEST, L2_UNITS):
        if not os.path.exists(p):
            return None, "输入缺失：%s" % os.path.relpath(p, ROOT)

    bad_json, m_rows, m_bad = [], [], []
    for ln, d, err in _iter_jsonl(L2_MANIFEST):
        if d is None:
            bad_json.append([ln, err])
            continue
        if (isinstance(d, dict) and d.get("resource_id") and d.get("kb_type")
                and d.get("observed_at") and d.get("result") in RESULTS):
            m_rows.append(d)
        else:
            m_bad.append([ln, {k: d.get(k) for k in ("change", "layer", "run_id", "result")}
                          if isinstance(d, dict) else str(d)[:80]])

    # C2：run 内序列合法
    per_run = collections.defaultdict(list)
    for d in m_rows:
        per_run[(d["resource_id"], d["observed_at"])].append(d["result"])
    c2 = [[k[0], k[1], "→".join(v)] for k, v in sorted(per_run.items())
          if len(v) > 1 and tuple(v) not in ALLOWED_SEQ]
    conflicts_ok = sum(1 for v in per_run.values() if len(v) > 1)

    units = collections.Counter()
    for ln, d, err in _iter_jsonl(L2_UNITS):
        if d is None:
            bad_json.append([ln, "units.jsonl: " + err])
            continue
        units[d.get("resource_id")] += 1

    uc = lambda d: int(d.get("unit_count") or 0)
    mx, sm, ever_split, has_split, inval_after = {}, {}, set(), set(), set()
    for d in m_rows:
        rid = d["resource_id"]
        if d["result"] == "split":
            has_split.add(rid)
            ever_split.add(rid)
            mx[rid] = max(mx.get(rid, 0), uc(d))
            sm[rid] = sm.get(rid, 0) + uc(d)
        elif d["result"] == "invalidated" and rid in ever_split:
            inval_after.add(rid)

    c3 = []
    for rid, n in units.items():
        if rid not in has_split:
            continue
        lo, hi = mx.get(rid, 0), sm.get(rid, 0)
        if n < lo or n > hi:
            c3.append([rid, lo, n, hi])
    c3.sort()
    c4 = sorted(rid for rid in units if rid not in ever_split)

    l1_ids = set()
    for ln, d, err in _iter_jsonl(L1_MANIFEST):
        if d is None:
            bad_json.append([ln, "manifest_l1.jsonl: " + err])
            continue
        if d.get("resource_id"):
            l1_ids.add(d["resource_id"])
    c5 = sorted({d["resource_id"] for d in m_rows if d["result"] == "split"} - l1_ids)

    # N2 滞后
    l0_valid = {d.get("resource_key") for _, d, e in _iter_jsonl(L0_MANIFEST)
                if d and d.get("status") not in ("gone", "retracted")}
    l1_rows = [d for _, d, e in _iter_jsonl(L1_MANIFEST) if d]
    l1_by_key = {d["resource_key"]: d for d in l1_rows if d.get("resource_key")}
    inp = [k for k in l0_valid if k in l1_by_key and l1_by_key[k].get("status") in L1_HAS_CONTENT]
    latest = {}
    for d in m_rows:
        latest[d["resource_id"]] = d
    lag, by_type = 0, collections.Counter()
    for k in inp:
        r = latest.get(l1_by_key[k].get("resource_id"))
        if not r or r.get("result") not in ("split", "skipped"):
            lag += 1
            by_type[l1_by_key[k].get("kb_type")] += 1

    # N3 口径歧义：三种口径各自不符的资源数
    n3_h1 = n3_h2 = n3_h3 = 0
    all_rows = collections.defaultdict(list)
    for d in m_rows:
        all_rows[d["resource_id"]].append(d)
    for rid, n in units.items():
        rs = all_rows.get(rid) or []
        if not rs:
            continue
        sp = [d for d in rs if d["result"] == "split"]
        if sp and n != uc(sp[-1]):
            n3_h1 += 1
        if sp and n != sum(uc(d) for d in sp):
            n3_h2 += 1
        if n != sum(uc(d) for d in rs):
            n3_h3 += 1

    rep = {
        "counts": {"l2_rows": len(m_rows), "units": sum(units.values()),
                   "resources_in_units": len(units), "input_set": len(inp)},
        "C1_bad_json": bad_json[:CAP], "C1_bad_json_n": len(bad_json),
        "C1_non_resource_rows": m_bad[:CAP], "C1_non_resource_n": len(m_bad),
        "C2_bad_sequence": c2[:CAP], "C2_n": len(c2),
        "C2_ok_resplit_pairs": conflicts_ok,
        "C3_bound_violation": [[r, lo, n, hi] for r, lo, n, hi in c3[:CAP]], "C3_n": len(c3),
        "C4_units_without_split": c4[:CAP], "C4_n": len(c4),
        "C5_split_without_l1": c5[:CAP], "C5_n": len(c5),
        "N1_invalidated_after_split_n": len(inval_after),
        "N2_lag_n": lag, "N2_lag_by_type": dict(by_type),
        "N3_ambiguity": {"latest_split_only": n3_h1, "sum_split_rows": n3_h2, "sum_all_rows": n3_h3},
    }
    rep["red_total"] = (rep["C1_bad_json_n"] + rep["C2_n"]
                        + rep["C3_n"] + rep["C4_n"] + rep["C5_n"])
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
        print(json.dumps({"gate": "l2_gate", "ok": ok, **rep}, ensure_ascii=False, indent=1))
        return 0 if ok else 1

    c = rep["counts"]
    print("=" * 74)
    print("L2 闸门（独立复算：manifest_l2.jsonl × units.jsonl × manifest_l1.jsonl）")
    print("  台账资源行 %d ｜ 单元 %d 条 / %d 个资源 ｜ 当前输入集 %d 个资源"
          % (c["l2_rows"], c["units"], c["resources_in_units"], c["input_set"]))
    print("  口径：unit_count 的具体语义**台账没定义**（N3），故只判可证上下界，不猜公式")
    print("-" * 74)
    if not a.quiet:
        if rep["C1_bad_json_n"]:
            print("C1 坏 JSON %d 行：%s" % (rep["C1_bad_json_n"], rep["C1_bad_json"][:3]))
        print("C2 run 内序列：非法 %d 处 ｜ 合规的重切对（invalidated→split/skipped）%d 处"
              % (rep["C2_n"], rep["C2_ok_resplit_pairs"]))
        for rid, run, seq in rep["C2_bad_sequence"][:3]:
            print("   非法：run %s ｜ %s ｜ %s" % (run, seq, rid[:48]))
        if rep["C3_n"]:
            print("C3 账实越界 %d 个资源（资源, 下界, 实际, 上界）：" % rep["C3_n"])
            for x in rep["C3_bound_violation"][:3]:
                print("   %s ｜ %s ≤ %s ≤ %s" % (str(x[0])[:48], x[1], x[2], x[3]))
        if rep["C4_n"]:
            print("C4 有单元但从未 split 的资源 %d 个：%s"
                  % (rep["C4_n"], [str(x)[:38] for x in rep["C4_units_without_split"][:3]]))
        if rep["C5_n"]:
            print("C5 split 行在 L1 找不到出处 %d 条：%s"
                  % (rep["C5_n"], [str(x)[:38] for x in rep["C5_split_without_l1"][:3]]))
    print("-" * 74)
    print("说明项（不是红）：被作废后仍留产物 %d 个资源 ｜ 滞后 %d 个资源未切分 %s"
          % (rep["N1_invalidated_after_split_n"], rep["N2_lag_n"],
             dict(rep["N2_lag_by_type"]) if rep["N2_lag_by_type"] else ""))
    n3 = rep["N3_ambiguity"]
    print("  N3 口径歧义：最新 split 行 %d 不符 ｜ split 行求和 %d 不符 ｜ 全行求和 %d 不符"
          " → 要 L2 层主在 l2.json 写明 unit_count 口径" % (n3["latest_split_only"],
                                                          n3["sum_split_rows"], n3["sum_all_rows"]))
    if rep["C1_non_resource_n"]:
        print("  N4 非资源行 %d 行（**口径待裁**，不是红）：" % rep["C1_non_resource_n"])
        for ln, d in rep["C1_non_resource_rows"][:3]:
            print("     行 %d：%s" % (ln, json.dumps(d, ensure_ascii=False)))
        print("     → 要人做什么：确认它是不是层引擎有意的变更记录；"
              "若是，把约定写进 l2.json；若不是，删掉该行（本轮只读，不动台账）")
    print("=" * 74)
    print("结论：%s" % ("✅ 过（五项判据 0 违规）" if ok else "❌ 未过（红 %d）" % rep["red_total"]))
    print("退出码：%d" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
