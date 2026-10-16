#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l1_gate.py —— L1 层闸门（**独立复算档**）：把「OCR 缓存复用门槛」从函数声明变成可执行闸门。

## 它补的是哪个洞

`kb/l7/registry/layers.yaml` 里 L1 的闸门原文是一个**函数引用**：

    kb/.work/kb_ocr_gate.py::ocr_cache_reusable（OCR 缓存复用闸门 vision-jxa-2.0）

函数引用不是闸门：没人调用它，L1 就是「声明式」。本脚本把它**落到真实数据上**：
遍历 `kb/l1/media/_cache/*.json` 的**每一条**缓存，逐条调用 `ocr_cache_reusable(entry)`。

为什么这条值得红：`kb/l8/ocr_attachments.py:153` 的复用分支就是
「按 file sha256 命中缓存 → 若 `ocr_cache_reusable` 通过就复用」。
缓存里只要有一条不达标（坏引擎版本 / sha256_state 非 full / 正文含 U+FFFF / 整图丢失），
命中它的那张图就会把**坏的 OCR 正文**灌进 L1 —— 这是**脏数据入口**，比断链更隐蔽。

## 判据（红）

  C1 缓存条目可复用 —— `ocr_cache_reusable(entry)[0]` 必须为 True（逐条调用，不抽样）。
  C2 缓存键非空     —— 每条缓存必须有 `sha256`（文件名就是键，缺键=无法命中，也说不清它属于谁）。
  C3 缓存非空       —— 缓存目录里 `*.json`（不含 `_batch_*.json`）必须 > 0。
                        否则闸门会在空目录上**假过**（vacuous pass）→ 直接判 exit 2「无法计算」。

## 说明项（不是红）

  N1 `_batch_*.json` 批次文件数（它们是汇总、不是单图缓存，不参与逐条判定）。
  N2 缓存条目的 ocr_version 分布（一眼看出坏引擎的残留量）。

## 只读

只读 `kb/l1/media/_cache/*.json` 与 `kb/.work/kb_ocr_gate.py`（import 不执行 main），
**不写任何文件**。

用法：
    kb/kbpy l7/scripts/l1_gate.py [--json] [--quiet]
    KB_GATE_KB=<夹具目录> kb/kbpy l7/scripts/l1_gate.py     # 反测用（默认真库）
"""
from __future__ import annotations

import argparse
import collections
import glob
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.environ.get("KB_GATE_KB") or os.path.dirname(os.path.dirname(HERE))   # …/kb
ROOT = os.path.dirname(KB)
CACHE_DIR = os.path.join(KB, "l1/media/_cache")
GATE_FUNC = os.path.join(KB, ".work/kb_ocr_gate.py")
CAP = 8


def _load_gate_func():
    """import kb/.work/kb_ocr_gate.py 里的 ocr_cache_reusable（**用它，不重写**）。"""
    spec = importlib.util.spec_from_file_location("kb_ocr_gate", GATE_FUNC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ocr_cache_reusable


def compute():
    if not os.path.isdir(CACHE_DIR):
        return None, "缓存目录不存在：%s" % os.path.relpath(CACHE_DIR, ROOT)
    if not os.path.exists(GATE_FUNC):
        return None, "门槛函数不在位：%s" % os.path.relpath(GATE_FUNC, ROOT)
    reusable = _load_gate_func()

    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.json")))
    batch = [p for p in files if os.path.basename(p).startswith("_batch_")]
    single = [p for p in files if not os.path.basename(p).startswith("_batch_")]
    if not single:
        return None, "缓存目录里没有单图缓存（%d 个 _batch_ 文件）→ 空目录上判过是假过" % len(batch)

    bad_json, bad_reuse, bad_key = [], [], []
    ver = collections.Counter()
    for p in single:
        rel = os.path.relpath(p, ROOT)
        try:
            with open(p, encoding="utf-8") as fh:
                e = json.load(fh)
        except Exception as exc:                     # noqa: BLE001
            bad_json.append([rel, "%s" % exc])
            continue
        ver[str(e.get("ocr_version"))] += 1
        if not e.get("sha256"):
            bad_key.append(rel)
        ok, why = reusable(e)
        if not ok:
            bad_reuse.append([rel, why])

    rep = {
        "counts": {"cache_files": len(single), "batch_files": len(batch)},
        "C1_not_reusable": bad_reuse[:CAP], "C1_n": len(bad_reuse),
        "C2_missing_key": bad_key[:CAP], "C2_n": len(bad_key),
        "C3_empty": False,
        "bad_json": bad_json[:CAP], "bad_json_n": len(bad_json),
        "N2_versions": dict(ver),
    }
    rep["red_total"] = rep["C1_n"] + rep["C2_n"] + rep["bad_json_n"]
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
        print(json.dumps({"gate": "l1_gate", "ok": ok, **rep}, ensure_ascii=False, indent=1))
        return 0 if ok else 1

    c = rep["counts"]
    print("=" * 74)
    print("L1 闸门（OCR 缓存复用门槛落到实处：逐条调用 ocr_cache_reusable）")
    print("  单图缓存 %d 条 ｜ 批次文件 %d 个 ｜ 版本分布 %s"
          % (c["cache_files"], c["batch_files"], rep["N2_versions"]))
    print("-" * 74)
    if not a.quiet:
        if rep["bad_json_n"]:
            print("C1 坏 JSON %d 条：%s" % (rep["bad_json_n"], rep["bad_json"][:3]))
        if rep["C1_n"]:
            print("C1 缓存不可复用 %d 条（命中它就会把坏 OCR 灌进 L1）：" % rep["C1_n"])
            for rel, why in rep["C1_not_reusable"][:3]:
                print("   %s ｜ %s" % (os.path.basename(rel), why))
        if rep["C2_n"]:
            print("C2 缓存缺 sha256 键 %d 条：%s"
                  % (rep["C2_n"], [os.path.basename(x) for x in rep["C2_missing_key"][:3]]))
    print("-" * 74)
    print("说明项：_batch_ 汇总文件 %d 个不参与逐条判定（它们是批次聚合，不是单图缓存）"
          % c["batch_files"])
    print("=" * 74)
    print("结论：%s" % ("✅ 过（全部缓存可复用）" if ok else "❌ 未过（红 %d）" % rep["red_total"]))
    print("退出码：%d" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
