#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prune_gone_units.py —— 把「源里已删的记录」从 L2/L6 里退掉（2026-10-20；串图修复 ③）

## 为什么（实测）

L0 早就把删掉的记录标成 `status=gone`（原因写「飞书侧整批替换 / Record not found」，
20260929、20261002 两批），**但下游没跟着退**：

  · L2 `units.jsonl`：441 条 unit 属于**已不在源表**的记录（其中 240 条 L0 从未登记）；
  · L6 `bm25/docs.jsonl`：410 条文档里 **237 条**来自 **127** 条已删记录。

后果实测（2026-10-20 用户报「链接是其他图片的」那一单）：召回 top1/top2 是
`#素材/recvw2vgYXmEKH/…` 与 `recvw2wE9MJl8j` —— 这两条**在飞书里已经不存在**
（`base +record-get` 返回 `record_not_found`）。它们拼出来的链接点开就是空记录。

## 判据

一条 unit/doc 的「记录」由三处取（取到即用，取不到不猜）：
  `resource_id` 的 `__tbl__(rec…)` / `media_tbl_(rec…)` / `bitable_tbl_(rec…)`，或
  `anchor` 的 `#素材/<rec>/…` / `#负面样本/<rec>/…`。
记录 ∈ **现存集合**（L0 `records/负面样本/*.json` 且 manifest 最新状态不是 gone）⇒ 保留；
否则 ⇒ **退掉**（写进 `kb/l2/retired_units.jsonl`，一条不静默丢）。

★ 边界：本件**只动 L2 的单元台账**（+ 由 L6 重建消化），**不碰飞书源**、不改 L0 的任何判读。

## 用法

    python3 kb/l8/prune_gone_units.py              # 预演：只打数字
    python3 kb/l8/prune_gone_units.py --apply      # 真退（写 retired_units.jsonl + 重写 units.jsonl）
    python3 kb/l8/prune_gone_units.py --selftest   # 判据自证（含反向对照）
"""
import json
import os
import re
import sys
import datetime
import tempfile

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
L0_RECORDS = os.path.join(KB, "l0", "records", "负面样本")
L0_MANIFEST = os.path.join(KB, "l0", "manifest.jsonl")
UNITS = os.path.join(KB, "l2", "units.jsonl")
RETIRED = os.path.join(KB, "l2", "retired_units.jsonl")
TABLE = "tbld8qE92YaY38Yz"
TAG = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def live_records():
    """现存记录集合：以 L0 的逐条件为准，再用 manifest 的**最新状态**剔掉标了 gone 的。"""
    live, gone = set(), set()
    if os.path.isdir(L0_RECORDS):
        for fn in os.listdir(L0_RECORDS):
            if fn.endswith(".json"):
                rid = fn[:-5]
                try:
                    d = json.load(open(os.path.join(L0_RECORDS, fn), encoding="utf-8"))
                except Exception:                      # noqa: BLE001
                    continue
                if str(d.get("status") or "").lower() in ("gone", "retracted"):
                    gone.add(rid)
                else:
                    live.add(rid)
    latest = {}
    if os.path.exists(L0_MANIFEST):
        for line in open(L0_MANIFEST, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:                          # noqa: BLE001
                continue
            if d.get("table_id") != TABLE or not d.get("record_id"):
                continue
            rid, at = d["record_id"], d.get("observed_at") or ""
            if rid not in latest or at >= (latest[rid].get("observed_at") or ""):
                latest[rid] = d
    for rid, d in latest.items():
        if str(d.get("status") or "").lower() in ("gone", "retracted"):
            gone.add(rid)
            live.discard(rid)
    return live, gone


def record_of(row):
    res = str(row.get("resource_id") or "")
    m = re.search(r"__%s__(rec\w+)" % TABLE, res) or re.match(r"^(?:media|bitable)_%s_(rec\w+)" % TABLE, res)
    if m:
        return m.group(1)
    a = str(row.get("anchor") or "")
    m = re.match(r"^#(?:素材|负面样本)/(rec\w+)/", a)
    return m.group(1) if m else None


def plan(rows, live):
    keep, drop = [], []
    for r in rows:
        rid = record_of(r)
        if rid and rid not in live:
            drop.append((r, rid))
        else:
            keep.append(r)
    return keep, drop


def _write_atomic(path, rows):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-prune-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def run(apply=False):
    live, gone = live_records()
    rows = [json.loads(l) for l in open(UNITS, encoding="utf-8") if l.strip()]
    keep, drop = plan(rows, live)
    print("现存记录 %d 条 ｜ manifest 标 gone %d 条" % (len(live), len(gone)))
    print("L2 单元 %d 条 ⇒ 保留 %d ／ **退掉 %d**" % (len(rows), len(keep), len(drop)))
    by = {}
    for r, rid in drop:
        by[r.get("kb_type")] = by.get(r.get("kb_type"), 0) + 1
    print("  退掉按 kb_type：", by)
    if drop:
        print("  退掉样例：", [(record_of(r), (r.get("anchor") or "")[:40]) for r, _ in drop[:3]])
    if not apply:
        print("\n（预演：未落盘；--apply 才写 retired_units.jsonl 并重写 units.jsonl）")
        return 0
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(RETIRED, "a", encoding="utf-8") as fh:
        for r, rid in drop:
            fh.write(json.dumps({
                "unit_id": r.get("unit_id"), "resource_id": r.get("resource_id"),
                "kb_type": r.get("kb_type"), "retired_at": now,
                "reason": "源记录已不在飞书侧（L0 manifest 最新状态=gone / records 目录无此件）"
                          "—— 串图修复 ③：陈旧的 unit 会把召回引到不存在的记录上",
                "record_id": rid, "anchor": r.get("anchor"),
                "char_count": r.get("char_count"), "retired_by": "kb/l8/prune_gone_units.py",
                "run": "prune-" + TAG}, ensure_ascii=False) + "\n")
    _write_atomic(UNITS, keep)
    print("\n已写：%s（+%d 行）／重写 %s（%d 行）" % (RETIRED, len(drop), UNITS, len(keep)))
    print("下一步（必须）：重建 L6，否则索引里仍然留着这 %d 条" % len(drop))
    print("  python3 kb/.work/l6_build.py <run_id> --apply")
    return 0


def selftest():
    live = {"rec_live"}
    rows = [
        {"unit_id": "u1", "resource_id": "bitable__%s__rec_live" % TABLE, "anchor": "#负面样本/rec_live/建议"},
        {"unit_id": "u2", "resource_id": "media_%s_rec_dead" % TABLE, "anchor": "#素材/rec_dead/图片素材/#img.1"},
        {"unit_id": "u3", "resource_id": "x", "anchor": "#素材/rec_dead2/图片素材/#img.2"},
        {"unit_id": "u4", "resource_id": "other", "anchor": "#l.1-1"},
    ]
    keep, drop = plan(rows, live)
    cases = [
        ("正例：现存记录的 unit 保留", {r["unit_id"] for r in keep} == {"u1", "u4"}, [r["unit_id"] for r in keep]),
        ("反例：已删记录的 unit 退掉（两种 resource_id 写法都认）",
         sorted(r["unit_id"] for r, _ in drop) == ["u2", "u3"], [r["unit_id"] for r, _ in drop]),
        ("反例：取不到记录的 unit **不动**（不猜、不误删）", any(r["unit_id"] == "u4" for r in keep), None),
        ("记录 id 解析：resource_id 三种写法", record_of(rows[0]) == "rec_live"
         and record_of(rows[1]) == "rec_dead" and record_of(rows[2]) == "rec_dead2", None),
    ]
    ok = all(c[1] for c in cases)
    for name, okc, detail in cases:
        print(("  ✅ " if okc else "  ❌ ") + name + ("" if okc else "  ← " + str(detail)))
    print("prune_gone_units --selftest %s（%d/%d）"
          % ("PASS" if ok else "FAIL", sum(1 for c in cases if c[1]), len(cases)))
    return 0 if ok else 3


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(run(apply="--apply" in sys.argv))
