#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l2_units_manifest_reconcile.py —— 「L2 单元行 ↔ manifest_l2 台账」对账（只读）

## 为什么要有这个脚本（2026-09-30 立）

`l2_gate.py` 的 C3 判的是**可证的上下界**：
    max(split 行 unit_count) ≤ 实际单元数 ≤ Σ(split 行 unit_count)
上下界能抓住「丢数」（破下界）和「没出处」（破上界），但**抓不住声明虚高** ——
重复声明会把上界抬上去，于是越界判不出来，闸门照样绿。人要是拿 manifest 的行数
或声明求和去比 `units.jsonl` 的行数，永远对不上（14860 vs 12158），而且看不出
差在哪：台账是 append-only 的**流水账**，不是当前状态的索引。

本脚本把「对不上」拆成有名字的几笔账，并给出一条能验到 0 的恒等式。

## 口径（每个幂等键 = (resource_id, source_sha256, splitter_version)）

    manifest 声明 = 该键下所有行的 unit_count 求和
    实际          = units.jsonl 里该键的行数

对账恒等式（实测残差为 0）：

    Σ 全 manifest 声明
      − invalidated 声明     （资源被判失效后，旧单元仍留在 units.jsonl，台账不扣减）
      − 重复声明             （同一 (resource,sha) 被再次 split，unit_id 确定性 → 不产生新行）
      − skipped 声明         （设计上恒为 0）
      = units.jsonl 实际行数

典型值（2026-09-30）：14860 − 2681 − 21 − 0 = 12158 ✓

## 另两处已知错配（单独报，不算进恒等式）

  A. 版本错配：manifest 记的是「运行版本」，units 行记的是「产出者版本」。
     `l2.json.splitter_version_backfill` 把 9261 个单元补成实际产出者 l2-0.2，
     于是这些键在 manifest 侧是 l2-0.1、在 units 侧是 l2-0.2，按全键 join 会对不上。
     → join 时用 (resource_id, source_sha256) 两元组，不要带版本。
  B. 非资源行：manifest 里混着层变更记录（无 resource_id），不是单元行，对账前剔除。

用法：
  kbpy l8/l2_units_manifest_reconcile.py           # 人读
  kbpy l8/l2_units_manifest_reconcile.py --json    # 机器读（stdout 一个 JSON）

本脚本不写任何文件、不改台账。它只报账，不修账。
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L2 = os.path.join(ROOT, "kb", "l2")
AS_JSON = "--json" in sys.argv


def iter_jsonl(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for ln, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield ln, json.loads(raw), None
            except Exception as exc:
                yield ln, None, "%s: %s" % (type(exc).__name__, exc)


def main():
    units, m_rows, m_non, bad = [], [], [], []
    for ln, d, err in iter_jsonl(os.path.join(L2, "units.jsonl")):
        if d is None:
            bad.append([ln, "units.jsonl: " + err])
            continue
        units.append(d)
    for ln, d, err in iter_jsonl(os.path.join(L2, "manifest_l2.jsonl")):
        if d is None:
            bad.append([ln, "manifest_l2.jsonl: " + err])
            continue
        if "resource_id" not in d:
            m_non.append([ln, d])
            continue
        m_rows.append(d)

    ucount = lambda d: int(d.get("unit_count") or 0)
    key2 = lambda d: (d.get("resource_id"), d.get("source_sha256"))
    key3 = lambda d: (d.get("resource_id"), d.get("source_sha256"), d.get("splitter_version"))

    # ---- 声明侧：按 key3 求和 ----
    decl3 = collections.Counter()
    for d in m_rows:
        decl3[key3(d)] += ucount(d)
    # ---- 实际侧 ----
    act3 = collections.Counter(key3(u) for u in units)

    # ---- 恒等式三笔 ----
    inval = sum(ucount(d) for d in m_rows if d.get("result") == "invalidated")
    skip = sum(ucount(d) for d in m_rows if d.get("result") == "skipped")
    split_rows = [d for d in m_rows if d.get("result") == "split"]

    decl2 = collections.Counter()
    for d in split_rows:
        decl2[key2(d)] += ucount(d)
    act2 = collections.Counter(key2(u) for u in units)
    dup = sorted(((k[0], decl2[k], act2.get(k, 0), decl2[k] - act2.get(k, 0))
                  for k in decl2 if decl2[k] > act2.get(k, 0)),
                 key=lambda x: -x[3])
    nosp = sorted(((k[0], decl2.get(k, 0), act2[k], act2[k] - decl2.get(k, 0))
                   for k in act2 if act2[k] > decl2.get(k, 0)),
                  key=lambda x: -x[3])
    dup_total = sum(x[3] for x in dup)
    nosp_total = sum(x[3] for x in nosp)

    decl_all = sum(decl3.values())
    residual = decl_all - inval - dup_total - skip - len(units)

    # ---- A. 版本错配 ----
    ver_m, ver_u = {}, {}
    for d in split_rows:
        if ucount(d) > 0:
            ver_m.setdefault(key2(d), set()).add(d.get("splitter_version"))
    for u in units:
        ver_u.setdefault(key2(u), set()).add(u.get("splitter_version"))
    ver_bad = [k for k in set(ver_m) & set(ver_u) if not (ver_m[k] & ver_u[k])]

    # ---- 仅键3 的孤立键 ----
    only_man = set(decl3) - set(act3)
    only_units = set(act3) - set(decl3)

    rep = {
        "units_rows": len(units),
        "units_resources": len({u.get("resource_id") for u in units}),
        "manifest_rows": len(m_rows),
        "manifest_non_resource_rows": len(m_non),
        "identity": {
            "declared_all": decl_all,
            "minus_invalidated": inval,
            "minus_duplicate_declaration": dup_total,
            "minus_skipped": skip,
            "equals_units_rows": len(units),
            "residual": residual,
        },
        "duplicate_declarations": [[x[0], x[1], x[2]] for x in dup],
        "declared_below_actual": [[x[0], x[1], x[2]] for x in nosp],
        "version_skew_keys": len(ver_bad),
        "version_skew_units_rows": sum(act3.get((k[0], k[1], v), 0) for k in ver_bad for v in ver_u[k]),
        "key3_only_in_manifest": len(only_man),
        "key3_only_in_units": len(only_units),
        "bad_json": bad,
    }

    if AS_JSON:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0 if residual == 0 else 1

    print("=" * 74)
    print("L2 单元行 ↔ manifest_l2 台账 对账（只读）")
    print("=" * 74)
    print("  units.jsonl 行数            %d（%d 个资源）" % (len(units), rep["units_resources"]))
    print("  manifest 资源行             %d（另有 %d 行非资源行）" % (len(m_rows), len(m_non)))
    print("  解析失败                    %d" % len(bad))
    print()
    print("--- 对账恒等式 ---")
    print("  全 manifest 声明合计        %8d" % decl_all)
    print("  − invalidated 声明          %8d   （失效资源旧单元仍在 units.jsonl，台账不扣减）" % inval)
    print("  − 重复声明                  %8d   （同一 resource+sha 再切，unit_id 确定性 → 不产生新行）" % dup_total)
    print("  − skipped 声明              %8d   （设计上恒为 0）" % skip)
    print("  =                           %8d" % (decl_all - inval - dup_total - skip))
    print("  units.jsonl 实际行数        %8d" % len(units))
    print("  残差                        %8d   %s" % (residual, "✓ 闭合" if residual == 0 else "✗ 有未解释差额"))
    print()
    if dup:
        print("--- 重复声明明细（同一 resource+sha 被再次 split，但没产生新行）---")
        for rid, a, b, d in dup[:20]:
            print("  声明=%-5d 实际=%-5d 多报=%-4d %s" % (a, b, d, rid[:56]))
        print("    成因：失效+重切同一次 run 里成对写出（invalidated 行 + split 行），")
        print("          而 unit_id 确定性 → 重复 append 被去重，实际行数不变。")
        print()
    if nosp:
        print("--- 声明少于实际（单元无台账出处）---")
        for rid, a, b, d in nosp[:20]:
            print("  声明=%-5d 实际=%-5d 少报=%-4d %s" % (a, b, d, rid[:56]))
        print()
    else:
        print("--- 声明少于实际：0 个键 ✓（没有无出处的单元）---")
        print()
    print("--- 已知错配（不计入恒等式）---")
    print("  版本错配键                  %d（影响 %d 行）" % (len(ver_bad), rep["version_skew_units_rows"]))
    print("    成因：manifest 记「运行版本」，units 行记「产出者版本」；")
    print("          l2.json.splitter_version_backfill 把 9261 个单元补成 l2-0.2。")
    print("    → 对账 join 用 (resource_id, source_sha256)，不要带 splitter_version。")
    print("  非资源行                    %d 行（层变更记录，对账前剔除）" % len(m_non))
    print("  仅 key3 在 manifest         %d" % len(only_man))
    print("  仅 key3 在 units            %d" % len(only_units))
    return 0 if residual == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
