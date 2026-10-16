#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
proposed-criterion-probe.py —— **只读**：把 `option_A_impl_sketch` 的 (A) 判据在**活数据**上模拟一遍。

它**不改** kb/l8/workflow_check.py、**不写**任何库内文件、**不写**任何 run 记录。
它的唯一用途：回答「**批了 (A) 之后，闸门会不会绿**」——2026-10-04 第 11 轮 kb-repair 的实测结论是：

    ② 会转绿（L3 现 sha 被 58 条 run 记录申报，最新一次 == 活库）
    ③ 仍红 3/45（最新申报停在 kb/l7/runs/20260923-1500.json 的那三个路径）
    ⇒ (A) 单独不够；唯一能转绿的组合 = (A) ＋ (C)（为那 3 项补落章）

用法（在库根跑）：
    python3 kb/l7/_backups/kb-repair-workflow-R11-20261004-1407/proposed-criterion-probe.py

(A) 的判据口径（与 `option_A_impl_sketch` 一致）：
  · ②：l0/l1/l2 仍比 L5 基线（不动）；l3 改成「活库 sha 若能被**更新**的 run 记录申报 ⇒ 记已溯源的演进，不定红」。
  · ③：基线从「09-23 那四份固定 run 记录」换成「**最新**一次申报该产物 sha 的 run 记录」；
        **查不到任何 run 记录出处**的改动**仍判红**（绊线不许一起拆掉）。
"""
import glob
import hashlib
import json
import os
import sys

SRC = [  # 现行判据 ③ 迭代的那四份 09-23 记录（kb/l8/workflow_check.py:129-130）
    "kb/l4/runs/20260923-1445.json",
    "kb/l5/runs/20260923-1430.json",
    "kb/l6/runs/20260923-1440.json",
    "kb/l7/runs/20260923-1500.json",
]
L3 = "kb/l3/candidates/rules.jsonl"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def index_run_records():
    """path -> [(sortkey, run_basename, sha256)]；只读原始 run 记录，不采信任何脚本自述。"""
    idx = {}
    n = 0
    for f in glob.glob("kb/l*/runs/*.json"):
        d = load(f)
        if not isinstance(d, dict):
            continue
        arts = d.get("artifacts")
        if not isinstance(arts, list):
            continue
        n += 1
        ts = str(d.get("at") or d.get("checked_at") or d.get("generated_at") or "")
        for a in arts:
            if isinstance(a, dict) and isinstance(a.get("sha256"), str):
                idx.setdefault(a.get("path"), []).append((ts, os.path.basename(f), a["sha256"]))
    for k in idx:
        idx[k].sort()
    return idx, n


def main():
    idx, nrec = index_run_records()
    print(f"run records with artifact lists: {nrec}")

    # ── ② 新判据 ─────────────────────────────────────────────────────────
    live = sha(L3)
    ents = idx.get(L3, [])
    newest = ents[-1] if ents else None
    leg2_ok = bool(newest) and newest[2] == live
    print(f"\n[②] {L3}")
    print(f"     live sha          = {live[:16]}…")
    print(f"     declared by       = {len(ents)} run records")
    print(f"     newest declaration= {newest[1] if newest else '-'} @ {newest[0][:19] if newest else '-'}"
          f"  sha={newest[2][:16] + '…' if newest else '-'}")
    print(f"     新判据 ⇒ {'GREEN（已溯源的演进）' if leg2_ok else 'RED（查不到出处/最新申报不一致）'}")

    # ── ③ 新判据 ─────────────────────────────────────────────────────────
    paths = []
    for rp in SRC:
        d = load(rp) or {}
        for a in d.get("artifacts", []):
            paths.append(a["path"])
    red = []
    for p in paths:
        if not os.path.exists(p):
            red.append((p, "文件不存在"))
            continue
        e = idx.get(p, [])
        if not e:
            red.append((p, "0 条 run 记录申报过该路径"))
        elif e[-1][2] != sha(p):
            red.append((p, f"最新申报 {e[-1][1]} @{e[-1][0][:19]} sha={e[-1][2][:16]}… != 活库 {sha(p)[:16]}…"))
    print(f"\n[③] 新判据下 red = {len(red)} / {len(paths)}")
    for p, why in red:
        print(f"     RED  {p}\n          {why}")

    verdict = leg2_ok and not red
    print(f"\n==> 若只批 (A)（不给那几项补落章）：workflow_check 裁决 = {'PASS' if verdict else 'FAIL'}")
    print("    ⇒ (A) 单独转绿的条件是『③ 的 red 清单为空』；否则必须 (A)＋(C) 同时做。")


if __name__ == "__main__":
    main()
