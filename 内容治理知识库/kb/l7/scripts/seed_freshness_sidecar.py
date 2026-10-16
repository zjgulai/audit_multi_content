#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seed_freshness_sidecar.py —— 给**已有落章**的层补出三字段的水位落章（一次性）。

## 为什么要有它

`measure()`（`layer_freshness.py`）是**包住一次运行**测的：它取「测前水位 / 测前产物指纹」，
跑命令，再取测后值 ⇒ 三字段是**观测值**。

但库里**已经跑过**的那些层（L0…L7 各自 12:50–13:21 的落章）**没有**这三字段 ——
它们是本机制落地**之前**跑的。**不能重跑它们**（L3/L4 会写 canonical、L0 要飞书 token、
L6 是重活），所以只能**补记**。

## ★ 这份补记诚实在哪（必须读）

1. `change_state` **不是**调用方声称的，是**现算推出来的**：
   比较「该层 data 产物的 mtime」与「该层最近一次成功落章的 mtime」——
   产物**不早于**落章 ⇒ 这一跑**改变了产物** ⇒ `produced_changes`；
   产物**明显早于**落章 ⇒ 这一跑**没动产物**（幂等）⇒ `no_new_input`。
2. `input_watermark` 记的是**此刻**的上游水位，并在 `provenance` 里**明写是 seeded**。
   ⇒ **它不构成「该次运行当时上游是什么」的证明** —— 那只能由 `measure()` 观测。
   **本条是已知的弱环，如实写在这里，不掩盖。**
3. 因此本脚本产出的落章带 `provenance: seeded_from_disk`；
   `measure()` 产出的带 `provenance: measured`。**读的人能分辨**。
   ⇒ 之后每一跑都走 `measure()`，seeded 会被**真观测覆盖**，弱环随使用自然消失。

## 用法

    kb/kbpy l7/scripts/seed_freshness_sidecar.py --dry-run   # 先看要写什么
    kb/kbpy l7/scripts/seed_freshness_sidecar.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layer_freshness as lf                              # noqa: E402


def _latest_run_mtime(kb_root: str, layer: str):
    d = os.path.join(kb_root, layer.lower(), "runs")
    if not os.path.isdir(d):
        return None, None
    best = None
    for fn in os.listdir(d):
        if not fn.endswith(".json") or "dryrun" in fn or "dry-run" in fn:
            continue
        p = os.path.join(d, fn)
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if best is None or m > best[0]:
            best = (m, fn)
    return best if best else (None, None)


def _read_run_rec(kb_root: str, layer: str):
    m, fn = _latest_run_mtime(kb_root, layer)
    if m is None:
        return None, None, None
    p = os.path.join(kb_root, layer.lower(), "runs", fn)
    try:
        with open(p, encoding="utf-8") as fh:
            return m, fn, json.load(fh)
    except Exception:                                      # noqa: BLE001
        return m, fn, None


def derive_change_state(kb_root: str, layer: str):
    """现算 `change_state`。**优先用该层自己落章里的计数**，mtime 只作最后退路。

    ★ 为什么不用 mtime 当主判据（我第一版就是这么写的，**是错的**）：
      「产物 mtime 早于落章 mtime」**推不出**「这一跑没改产物」——
      引擎完全可以**原地重写同内容**，而 mtime 又被后写的别的产物覆盖。
      L3 实际就是这样：产物 `rejected.jsonl` 12:51:36、落章 12:51:39（差 3 秒），
      mtime 判据说「没动产物」，**但 L3 确实重写了 candidates/rules.jsonl**。
      ⇒ 拿 mtime 当主判据会**把「有产出」误报成「无产出」**，进而放松新鲜度判据。
      ⇒ 改用**落章里引擎自己记的计数**（那是引擎对自身行为的陈述），mtime 降为退路。

    返回 `(change_state, detail)`；**判不出来就返回 None，不猜**。
    """
    run_m, run_fn, rec = _read_run_rec(kb_root, layer)
    if run_m is None:
        return None, "该层没有成功落章 ⇒ 推不出"
    rec = rec or {}

    def _num(*keys):
        for k in keys:
            v = rec.get(k)
            if isinstance(v, int):
                return v
        return None

    # ── 各层引擎自己的「有没有产出」陈述（逐条给依据行）──────────────
    if layer == "L1":
        md = rec.get("manifest_dedup") or {}
        a = _num_in(md, "appended")
        if a is not None:
            return (("produced_changes" if a else "no_new_input"),
                    "落章 `manifest_dedup.appended=%s` ⇒ %s"
                    % (a, "有追加" if a else "无追加（幂等）"))
    if layer == "L2":
        nu, rf = _num("new_units", "refilled"), _num("refilled")
        cb, ca = rec.get("cov_before"), rec.get("cov_after")
        if nu is not None:
            same_cov = (cb == ca) if isinstance(cb, dict) else None
            if nu == 0 and _num("refilled") == 0:
                return ("no_new_input",
                        "落章 `new_units=0` / `refilled=0` / `cov_before==cov_after=%s`"
                        " ⇒ 无新增单元（幂等）" % same_cov)
            return "produced_changes", "落章 `new_units=%s` ⇒ 有新增单元" % nu
        _ = rf
    if layer == "L3":
        # L3 的落章记的是「产出了多少条」；>0 即产出变化
        n = _num("rules", "kept")
        if n is not None:
            return ("produced_changes",
                    "落章 `rules=%s`（本层产出条数 >0 ⇒ 这一跑产出了规则）" % n)
    if layer in ("L4", "L5", "L6"):
        n = _num("patterns", "applied_rows", "assigned", "docs")
        if n is not None:
            return (("produced_changes" if n else "no_new_input"),
                    "落章 `%s` ⇒ %s" % (n, "有产出" if n else "无产出"))
    if layer == "L0":
        # L0 落章有两支：reconcile（对账/认领）与 emit（**真正写 manifest**）。
        # `manifest_rows_delta` 是 emit 那支写的 —— 它在 reconcile 落章里**显式为 None**，
        # 语义 = 「这一支没记行数变化」，**不是**「字段缺失」（字段在 keys 里，实测）。
        if "manifest_rows_delta" in rec:
            d = rec.get("manifest_rows_delta")
            if d is None:
                return ("no_new_input",
                        "落章显式记 `manifest_rows_delta=None`（对账/认领这一支不改 manifest）"
                        " 且 `verdict=%s` ⇒ 无行数变化" % rec.get("verdict"))
            if isinstance(d, int):
                return (("produced_changes" if d else "no_new_input"),
                        "落章 `manifest_rows_delta=%s`" % d)
        a = rec.get("reconcile_applied")
        if a is not None:
            return (("no_new_input" if rec.get("dry_run") else "produced_changes"),
                    "落章 `reconcile_applied=%s` / `dry_run=%s` / `write_gate=%s`"
                    % (a, rec.get("dry_run"), rec.get("write_gate")))

    # ── 退路：mtime 比较（**弱证据**，detail 里标明）──────────────────
    outs = lf.OUTPUT_SOURCES.get(layer) or []
    if not outs:
        # 跨层闸门层（L7）：**没有 data 产物** ⇒ 「有没有产出变化」这个问法不适用。
        # 它的执行事实由 `kb/l7/runs/` 的本次 run 记账证明（已在上面 `_latest_run_mtime` 取到）。
        # ⇒ 记 `produced_changes` 并**写明依据是 run 记账，不是产物**，不冒充有产物。
        return ("produced_changes",
                "**跨层闸门层**：无 data 产物；本次执行事实由 run 记账 `kb/l7/runs/%s` 证明" % run_fn)
    newest, newest_rel = None, None
    for rel in outs:
        p = os.path.join(kb_root, rel)
        if os.path.isfile(p):
            m = os.path.getmtime(p)
            if newest is None or m > newest:
                newest, newest_rel = m, rel
    if newest is None:
        return None, "该层 data 产物一个都不存在 ⇒ 推不出"
    if newest >= run_m - 2:
        return ("produced_changes",
                "**弱证据·mtime**：产物 `%s` mtime %s ≥ 落章 `%s` mtime %s"
                % (newest_rel, time.strftime("%H:%M:%S", time.localtime(newest)),
                   run_fn, time.strftime("%H:%M:%S", time.localtime(run_m))))
    return (None, "**弱证据·mtime 不足以判定**：产物 `%s`(%s) 早于落章 `%s`(%s)，"
                  "但「原地重写同内容」也会长这样 ⇒ **不拿它当判据，如实不补**"
            % (newest_rel, time.strftime("%H:%M:%S", time.localtime(newest)),
               run_fn, time.strftime("%H:%M:%S", time.localtime(run_m))))


def _num_in(d, *keys):
    for k in keys:
        v = (d or {}).get(k)
        if isinstance(v, int):
            return v
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--layers", default="L0,L1,L2,L3,L4,L5,L6,L7")
    a = ap.parse_args()
    if not (a.apply or a.dry_run):
        print("必须显式 --dry-run 或 --apply")
        return 2

    kb_root = os.path.dirname(os.path.dirname(HERE))       # …/kb
    sc = lf.load_sidecar(kb_root)
    print("库根：%s" % kb_root)
    print("现有 sidecar 键：%s\n" % sorted(sc.keys()))

    for layer in [x.strip() for x in a.layers.split(",") if x.strip()]:
        # ★ 已有 **measured** 落章的层不许被 seeded 覆盖（真观测 > 补记）
        old = sc.get(layer) or {}
        if old.get("provenance") == "measured":
            print("  %-3s 跳过：已有 measured 落章（真观测优先）change_state=%s"
                  % (layer, old.get("change_state")))
            continue
        cs, detail = derive_change_state(kb_root, layer)
        run_m, run_fn = _latest_run_mtime(kb_root, layer)
        if cs is None:
            print("  %-3s **不补**（%s）" % (layer, detail))
            continue
        wm = lf.watermark_digest(lf.current_watermark(kb_root, layer))
        rec = {
            "executed_at": run_m,                 # 用落章 mtime，**不是 now**（不许伪造执行时刻）
            "input_watermark": wm,
            "input_watermark_sources": sorted(lf.WATERMARK_SOURCES.get(layer) or []),
            "change_state": cs,
            "run_id": (run_fn or "").replace(".json", ""),
            "run_record": "kb/%s/runs/%s" % (layer.lower(), run_fn),
            "output_watermark": lf.watermark_digest(lf.output_fingerprint(kb_root, layer)),
            "provenance": "seeded_from_disk",
            "provenance_note": ("**补记，非观测**：`input_watermark` 记的是**此刻**水位，"
                                "不是该次运行当时的水位 ⇒ **不构成当时上游是什么的证明**。"
                                "`change_state` 由「产物 mtime vs 落章 mtime」现算得出（见 detail）。"),
            "change_state_detail": detail,
            "note": "批次18 第0块：机制落地前跑的落章，补记三字段",
        }
        print("  %-3s %-16s executed_at=%s  %s" % (
            layer, cs, time.strftime("%m-%d %H:%M:%S", time.localtime(run_m)), detail))
        if a.apply:
            sc[layer] = rec

    if a.apply:
        p = lf.sidecar_path(kb_root)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(sc, fh, ensure_ascii=False, indent=1, sort_keys=True)
        print("\n已写 → %s（%d 层）" % (p, len(sc)))
    else:
        print("\n[dry-run] 未写盘")
    return 0


if __name__ == "__main__":
    sys.exit(main())
