#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l3_rejected_status.py —— `kb/l3/rejected.jsonl`（L3 逐单元拒绝台账）的**只读查询档**。

## 补的是哪个洞（2026-10-08）

`kb/l3/rejected.jsonl` 是**追加式台账**，且已被日更**叠了 6 版**（实测 51017 行）。
而现有查询面 `l3_status.py` 打的是**原始行数** ——
它现在会显示「拒收（内部）**51017 行**」，**虚高约 6 倍**，没人能据此办事。

根因不是"谁忘了"，而是**这本账从来没被登记进读侧契约**：
`kb/l7/registry/ledger-read-contract.yaml` 的抬头在 2026-10-02 就写明了这个病 ——
> 「写入侧各自无条件追加、读侧各自默认取最后一行，**没有任何一处声明它们是同一套契约**，
>  于是「**台账每跑一遍就翻一倍**」既没人拦、也说不清算不算违背契约。」

而它当时登记的三本主台账是 `l1_manifest` / `l3_manifest` / `l0_manifest` ——
**`rejected.jsonl` 不在其中**。⇒ 治法是**按同一套契约把它登记进去**，本脚本是该契约的读侧入口。

## 它照实报四个数，不替人抹平

    总行数          —— 盘上有多少行（含全部历史版本）
    原始行          —— 事故后的资源粒度行（无 `rebuild_note`），**不属于任何版本**
    重建行          —— 带 `rebuild_note` 的行（可有多版）
    版本数 / 最新版  —— 按**行序**判（append-only ⇒ 行序即时间序）

**取"最新版"按行序，不按 `rejected_at` 字符串排序。**
本库的 RUN 有两种形态（`20261008-1500-scope-fix` 与 `daily-20261007-1605-L3`），
字典序里 `'d' > '2'` ⇒ 字符串 `max()` **恒选中旧的 daily 版**。
（这个坑 2026-10-08 真踩过：幂等判断因此把已写好的正确版当成"上一版"，又追加了一遍。）

## 只读

只读 `kb/l3/rejected.jsonl`。**不写任何文件、不落报告、不跑审计、不改台账。**

## 退出码

    0 = 读成功（不代表"没问题"）
    2 = 用法错 / 库根不对 / 台账读不到
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

LEDGER = "kb/l3/rejected.jsonl"


def find_root(start="."):
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, LEDGER)):
            return d
        q = os.path.dirname(d)
        if q == d:
            return None
        d = q


def load(path):
    """返回 (原始行 list, 重建行 list, 解析失败数)。"""
    raw, rebuilt, bad = [], [], 0
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                bad += 1
                continue
            d["_lineno"] = lineno
            (rebuilt if d.get("rebuild_note") else raw).append(d)
    return raw, rebuilt, bad


def versions_of(rebuilt):
    """按**行序**归一版本：返回 [(版本名, {unit_id: row}, 最后出现行号)]，按最后出现行号升序。"""
    vs = {}
    for r in rebuilt:
        at = str(r.get("rejected_at"))
        vs.setdefault(at, {"rows": {}, "last": -1})
        if r.get("unit_id"):
            vs[at]["rows"][r["unit_id"]] = r
        vs[at]["last"] = max(vs[at]["last"], r["_lineno"])
    return sorted(((at, v["rows"], v["last"]) for at, v in vs.items()), key=lambda x: x[2])


def _out_of_scope(root, a):
    """**范围外**清单：被门剔掉、**从未进入蒸馏**的单元。

    ★ 为什么它**不在** `rejected.jsonl` 里（Owner 2026-10-08 裁定口径 C）：
      「拒绝」的原义是「**进了门**、蒸馏跑了、但这单元没成规则」；
      被门剔掉的是**范围没覆盖**，是另一个指标（口径分解见 `kb/l8/l3_scope.py` 抬头）。
      它是 `exclusion_of()` 的**纯函数产物** ⇒ **不存快照、每次现算**，故不会腐烂。

    ★ 这也是 2026-10-08 那个问题的答案：负面样本 170 条为什么不蒸馏？
      ⇒ 它们**在被门剔掉的那一批里**（`gate=out_of_scope_table`），压根没走到蒸馏。
    """
    import collections
    l2 = os.path.join(root, "kb/l2/units.jsonl")
    if not os.path.isfile(l2):
        print(f"用法错：读不到 {l2}（范围外是现算的，必须有 L2 单元）", file=sys.stderr)
        return 2
    sys.path.insert(0, os.path.join(root, "kb/l8"))
    try:
        from l3_scope import build_scope, out_of_scope_units        # noqa: PLC0415
    except Exception as e:                                          # noqa: BLE001
        print(f"用法错：读不到判据模块 kb/l8/l3_scope.py —— {e}", file=sys.stderr)
        return 2
    scope = build_scope(os.path.join(root, "kb/l0/registry/kb.json"))
    units = [json.loads(x) for x in open(l2, encoding="utf-8") if x.strip()]
    pairs = out_of_scope_units(units, scope)
    if a.gate:
        pairs = [(u, cw) for u, cw in pairs if cw[0] == a.gate]
    dist = collections.Counter(c for _, (c, _) in pairs)
    if a.json:
        print(json.dumps({"mode": "out_of_scope", "count": len(pairs),
                          "by_gate": dict(dist),
                          "note": "纯函数现算，不存快照；与 rejected.jsonl 的「拒绝」是两个指标",
                          "sample": [{"unit_id": u.get("unit_id"), "anchor": u.get("anchor"),
                                      "gate_code": c, "why": w} for u, (c, w) in pairs[:5]]},
                         ensure_ascii=False, indent=1))
        return 0
    print("L3 **范围外**清单（被门剔掉、从未进入蒸馏）｜现算，不存快照")
    print(f"  条数            {len(pairs)}" + (f"（已按 --gate {a.gate} 过滤）" if a.gate else ""))
    print("  按门分布:")
    for k, v in dist.most_common():
        print(f"     {v:>6}  {k}")
    print("  样例（前 5）:")
    for u, (c, w) in pairs[:5]:
        print(f"     {u.get('unit_id')}  {u.get('anchor')}")
        print(f"        [{c}] {w}")
    print()
    print("  ⚠️ 这批**不在** rejected.jsonl 里 —— 「拒绝」= 进了门却没成规则（口径 C）；")
    print("     被门剔掉的是**范围问题**，是另一个指标。两个都看，别只数一个。")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="kb/l3/rejected.jsonl 只读查询档")
    ap.add_argument("--root", default=".", help="库根（默认自动上溯找 kb/l3/rejected.jsonl）")
    ap.add_argument("--unit", default=None, help="查某个 unit_id 的**最新一版**拒绝原因")
    ap.add_argument("--gate", default=None, help="只看某个 gate_code（如 out_of_scope_table）")
    ap.add_argument("--out-of-scope", action="store_true",
                    help="**范围外**清单（被门剔掉的）—— 它**不在拒绝台账里**，本模式按 L2 + 判据**现算**")
    ap.add_argument("--json", action="store_true", help="机读输出")
    a = ap.parse_args(argv)

    root = find_root(a.root)
    if not root:
        print(f"用法错：上溯找不到 {LEDGER}", file=sys.stderr)
        return 2

    if a.out_of_scope:
        return _out_of_scope(root, a)

    path = os.path.join(root, LEDGER)
    raw, rebuilt, bad = load(path)
    vs = versions_of(rebuilt)
    if not vs:
        print("台账里没有重建行（只有原始行）—— 本查询档的主要口径无从取值", file=sys.stderr)
        return 2

    latest_at, latest_rows, _ = vs[-1]

    if a.unit:
        row = latest_rows.get(a.unit)
        out = {"unit_id": a.unit, "latest_batch": latest_at,
               "found_in_latest_reject_set": row is not None}
        if row:
            out.update({"reason": row.get("reason"), "gate_code": row.get("gate_code"),
                        "kb_type": row.get("kb_type"), "unit_type": row.get("unit_type"),
                        "anchor": row.get("anchor")})
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=1))
        else:
            print(f"unit_id = {a.unit}｜最新一版 = {latest_at}")
            if row:
                print(f"  拒绝原因 = {row.get('reason')}")
                print(f"  gate_code = {row.get('gate_code') or '（进了门，未产出规则）'}")
                print(f"  定位 = {row.get('anchor')}")
            else:
                print("  **不在最新版的拒绝集里** —— 它可能已被规则/样例引用（进得去门）。")
                print("  查「它进了哪条规则」请用 kb/l7/scripts/l3_status.py 或直接搜 candidates/。")
        return 0

    dist = collections.Counter((r.get("gate_code") or "进了门（未产出规则）") for r in latest_rows.values())
    if a.gate:
        hit = [r for r in latest_rows.values() if (r.get("gate_code") or "") == a.gate]
        if a.json:
            print(json.dumps({"gate_code": a.gate, "count": len(hit),
                              "sample": [{k: r.get(k) for k in
                                          ("unit_id", "reason", "anchor", "kb_type")} for r in hit[:5]]},
                             ensure_ascii=False, indent=1))
        else:
            print(f"gate_code = {a.gate} ｜ 最新一版里 **{len(hit)} 条**")
            for r in hit[:5]:
                print(f"   {r.get('unit_id')}  {r.get('anchor')}")
                print(f"      {r.get('reason')}")
        return 0

    if a.json:
        print(json.dumps({
            "ledger": path, "total_rows": len(raw) + len(rebuilt), "unparsable": bad,
            "original_rows": len(raw), "rebuilt_rows": len(rebuilt),
            "versions": [{"batch": at, "rows": len(rows), "last_lineno": last} for at, rows, last in vs],
            "latest_batch": latest_at, "latest_rows": len(latest_rows),
            "latest_gate_distribution": dict(dist),
            "read_rule": "同 unit_id 取【行序最靠后】的那一版；原始行不参与版本比较",
        }, ensure_ascii=False, indent=1))
        return 0

    print("L3 逐单元拒绝台账（只读查询档）｜", path)
    print(f"  总行数            {len(raw) + len(rebuilt)}" + (f"（其中解析失败 {bad}）" if bad else ""))
    print(f"  原始行（不属于任何版本）  {len(raw)}")
    print(f"  重建行（可有多版）        {len(rebuilt)}")
    print(f"  版本数            {len(vs)}")
    if len(vs) == 1 and len(latest_rows) == len(rebuilt):
        print("                    ← **这是快照**（一行一单元，无重复版本）✅ 分家后应有的形状")
    elif len(vs) > 1:
        print(f"                    ← ⚠️ **同一份快照被追加了 {len(vs)} 遍** —— "
              "分家前的老形状；取【最新一版】，别取总行数")
    print(f"  最新一版          {latest_at}（{len(latest_rows)} 条）  ← 取它，别取总行数")
    print("  各版（按行序）:")
    for at, rows, last in vs:
        mark = "  ← 最新" if at == latest_at else ""
        print(f"     {at:<32} {len(rows):>6} 条  末行 {last}{mark}")
    print(f"  最新一版的 gate_code 分布:")
    for k, v in dist.most_common():
        print(f"     {v:>6}  {k}")
    print()
    print("  读法（与 kb/l7/registry/ledger-read-contract.yaml 登记一致）：")
    print("    同 unit_id 取【行序最靠后】的那一版；原始行不参与版本比较。")
    print("    ⚠️ 直接数总行数会虚高约 %d 倍 —— l3_status.py 现在打的就是总行数。" % max(len(vs), 1))
    print("  查单条：--unit <unit_id> ｜ 按门看：--gate <code> ｜ 机读：--json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
