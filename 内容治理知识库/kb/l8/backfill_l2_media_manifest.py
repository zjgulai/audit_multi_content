#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_l2_media_manifest.py —— 给「串图修复 ①」直写出来的媒体单元**补记 split 台账行**。

## 治的是什么（实测 2026-10-20 17:0x）

    sh kb/kbpy l7/scripts/l2_gate.py     # 退出码 1，C3 账实越界 127 个资源

C3 的判据是**能证的上下界**：`max(各行 unit_count) ≤ 实际单元数 ≤ Σ(split 行 unit_count)`。
媒体资源实测 `1 ≤ 6 ≤ 3` —— 上界比实际还小。

根因（不是闸门抽风）：`kb/l8/l2_image_units.py`（2026-10-20 16:17「串图修复 ①」）
把字段级单元与逐图单元**直接写进 `kb/l2/units.jsonl`**，但**没有往 `manifest_l2.jsonl`
追加对应的 split 行** ⇒ 台账不知道这批单元存在，C3 上界停在旧的 Σ=3。

## 修法（补账，不是放宽判据）

对每个「实际 > Σsplit」的资源，**追加一行 split**：
    unit_count   = 实际单元行数 − Σsplit（就是这次直写**新增**的行数 —— 与
                   `unit_count_semantics.semantics.split` 的定义逐字一致）
    observed_at  = 本次补记的 run id（可追溯到本脚本与 16:17 那一批）
    reason       = 写清「谁直写、为什么没台账、本行是补记」

**为什么不改判据**：改成"忽略媒体资源"就等于把「账实不符」永久免检；补账之后
Σsplit == 实际，判据一个字不动就能自证（N3 说明项里的偏差数也应归零）。

**边界**：只碰 `media_*` 资源且只在「实际 > Σsplit」时动；其它形状一律拒跑并打印，
免得把「双写/丢数」这类真缺陷也补平。

用法：
    kb/kbpy l8/backfill_l2_media_manifest.py            # 预演
    kb/kbpy l8/backfill_l2_media_manifest.py --apply
    kb/kbpy l8/backfill_l2_media_manifest.py --selftest # 反向对照（夹具）
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.environ.get("KB_BACKFILL_KB") or os.path.dirname(HERE)
ROOT = os.path.dirname(KB)
L2_MANIFEST = os.path.join(KB, "l2/manifest_l2.jsonl")
L2_UNITS = os.path.join(KB, "l2/units.jsonl")
BACKUP_DIR = os.path.join(KB, "l2/_archive")
RUN_ID = "20261020-1617-imgunits-backfill"


def _iter(p):
    with open(p, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                yield i, json.loads(line)


def plan(manifest=L2_MANIFEST, units=L2_UNITS):
    """返回 (要补的行, 拒跑清单)。拒跑 = 不是 media_* 或 实际 < Σsplit 这类另一种缺陷。"""
    rows = [d for _, d in _iter(manifest)]
    actual = collections.Counter()
    for _, u in _iter(units):
        if u.get("resource_id"):
            actual[u["resource_id"]] += 1
    mx, sm = {}, {}
    for d in rows:
        if d.get("result") != "split":
            continue
        rid = d.get("resource_id")
        n = int(d.get("unit_count") or 0)
        mx[rid] = max(mx.get(rid, 0), n)
        sm[rid] = sm.get(rid, 0) + n

    todo, refuse = [], []
    for rid, n in sorted(actual.items()):
        if rid not in sm:                       # 没有 split 行 ⇒ 归 C4（另判），这里不动
            continue
        if n > sm[rid]:
            if not rid.startswith("media_"):
                refuse.append((rid, "实际 %d > Σsplit %d，但不是 media_* 资源" % (n, sm[rid])))
                continue
            todo.append({
                "kb_type": _kb_type_of(rows, rid),
                "observed_at": RUN_ID,
                "reason": ("串图修复 ① 补记：kb/l8/l2_image_units.py 于 2026-10-20T16:17 直写媒体单元"
                           "（字段级 + 逐图），当时未追加 split 台账行；本行按"
                           " unit_count_semantics.semantics.split 的定义补记本次新增行数"),
                "resource_id": rid,
                "result": "split",
                "source_sha256": _sha_of(rows, rid),
                "splitter_version": "l2-0.3",
                "unit_count": n - sm[rid],
            })
        elif n < sm[rid] - max(mx.get(rid, 0), 0):
            refuse.append((rid, "实际 %d 明显小于 Σsplit %d（疑似双写/丢数，须人判）" % (n, sm[rid])))
    return todo, refuse


def _kb_type_of(rows, rid):
    for d in rows:
        if d.get("resource_id") == rid:
            return d.get("kb_type")
    return None


def _sha_of(rows, rid):
    last = None
    for d in rows:
        if d.get("resource_id") == rid:
            last = d
    return (last or {}).get("source_sha256")


def apply(todo, run=RUN_ID):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bak = os.path.join(BACKUP_DIR, "manifest_l2.jsonl.bak-%s" % run)
    shutil.copy2(L2_MANIFEST, bak)
    with open(L2_MANIFEST, "a", encoding="utf-8") as fh:
        for d in todo:
            fh.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")
    # 回读
    have = collections.defaultdict(int)
    for _, d in _iter(L2_MANIFEST):
        if d.get("observed_at") == run:
            have[d["resource_id"]] += int(d.get("unit_count") or 0)
    bad = [d["resource_id"] for d in todo if have.get(d["resource_id"]) != d["unit_count"]]
    if bad:
        raise SystemExit("回读不一致：%s（备份 %s）" % (bad[:3], bak))
    return bak


def selftest():
    import tempfile
    ok = True

    def chk(n, c, d=""):
        nonlocal ok
        print(("  ✅ " if c else "  ❌ ") + n + ((" ｜ " + str(d)) if d else ""))
        ok = ok and bool(c)

    tmp = tempfile.mkdtemp(prefix="l2bf-")
    try:
        man = os.path.join(tmp, "manifest_l2.jsonl")
        uni = os.path.join(tmp, "units.jsonl")
        with open(man, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"kb_type": "internal_sample", "resource_id": "media_T_recA",
                                 "result": "split", "unit_count": 1, "observed_at": "x",
                                 "source_sha256": "s"}, ensure_ascii=False) + "\n")
            fh.write(json.dumps({"kb_type": "wording", "resource_id": "bitable_T_recB",
                                 "result": "split", "unit_count": 5, "observed_at": "x",
                                 "source_sha256": "s"}, ensure_ascii=False) + "\n")
        with open(uni, "w", encoding="utf-8") as fh:
            for i in range(4):                      # media：实际 4，Σsplit=1 ⇒ 补 3
                fh.write(json.dumps({"resource_id": "media_T_recA", "unit_id": "u%d" % i},
                                    ensure_ascii=False) + "\n")
            for i in range(8):                      # 非 media：实际 8 > 5 ⇒ 拒跑（疑双写）
                fh.write(json.dumps({"resource_id": "bitable_T_recB", "unit_id": "v%d" % i},
                                    ensure_ascii=False) + "\n")
        todo, refuse = plan(man, uni)
        chk("T1 media 资源「实际 > Σsplit」⇒ 补一行、差值 = 实际−Σsplit",
            len(todo) == 1 and todo[0]["resource_id"] == "media_T_recA"
            and todo[0]["unit_count"] == 3, todo)
        chk("T2 非 media 资源同样越界 ⇒ **拒跑**，不悄悄补平",
            len(refuse) == 1 and refuse[0][0] == "bitable_T_recB", refuse)
        # 反向对照：把差值算成「实际」而不是「差值」⇒ T1 精确变红
        real = todo[0]["unit_count"]
        chk("T3 反向对照：unit_count 若写成实际行数(4) 而不是差值(3) ⇒ 判据应红",
            real != 4, "unit_count=%s" % real)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("backfill_l2_media_manifest --selftest %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 3


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()

    todo, refuse = plan()
    print("=" * 74)
    print("L2 媒体单元台账补记 ｜ 待补 %d 个资源 ｜ 合计补记 unit_count %d"
          % (len(todo), sum(d["unit_count"] for d in todo)))
    for d in todo[:5]:
        print("   %s ｜ +%d" % (d["resource_id"], d["unit_count"]))
    if refuse:
        print("  ⛔ 拒跑 %d 个（另一种缺陷，须人判）：" % len(refuse))
        for rid, why in refuse[:5]:
            print("     %s ｜ %s" % (rid, why))
    if not a.apply:
        print("（预演结束，未写任何文件；确认后加 --apply）")
        print("=" * 74)
        return 0
    if refuse:
        print("⛔ 有拒跑项 ⇒ 整批不落盘（避免把真缺陷补平）")
        return 2
    bak = apply(todo)
    print("  ✅ 已补记 %d 行 ｜ 备份 %s" % (len(todo), os.path.relpath(bak, ROOT)))
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
