#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`l4_c8_base.py` —— **本次运行开始时**的 C8 对比基座（批次17 · A 块）。

## 修的是什么

`kb/.work/fix_l4_repromote.py:248` 的 C8 判据（发号幂等）读的是：

    :61   BACKUP = "kb/l8/_archive/fix-20260929-094703/l4-before-repromote"
    :248  _am_before = json.load(open(os.path.join(BACKUP, "l4.json"))))["assignments"]

⇒ 那是 **2026-09-24 13:22** 的一次**历史快照**，**不是「本次运行开始时」的状态**。
后果（批次17 实测）：那份 `l4.json` 的 `assignments` = **1242** 条，
而当前 registry 已是 **1365** 条（`r` 632 + `sc` 358 + `scl` 375）
⇒ **旧基座永久落后 123 条**，C8 的 `_num_added` 会把这 123 条当成「本次新发的号」，
**从第二次重推起永远是脏对比**（会误报「新发号 123」）。

## 本模块做什么

  `capture(dir)` —— 在**开工那一刻**把当前 C8 基座落一份到 `dir/l4.json`，
                     并附 `_CAPTURED_AT.txt` 记时刻。调用方（`fix_l4_repromote.py`）
                     应在**任何 canonical 写入之前**调用它，然后从**这份**基座读 C8。

  边界：**不改旧基座**（历史物证，`fix-20260929-094703` 那两份原样留着）；
        本模块只**新增**一份本次基座。

## 用法

    python3 kb/l8/l4_c8_base.py --capture kb/l7/_backups/batch17-20261002-1120
    python3 kb/l8/l4_c8_base.py --compare   # 报「旧基座 vs 本次基座」差多少
"""
import argparse
import datetime
import json
import os
import shutil
import sys

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.chdir(WS)

# 旧基座（**只读**，历史物证，不许删）
OLD_BASE = "kb/l8/_archive/fix-20260929-094703/l4-before-repromote/l4.json"
# 本次 canonical 的权威来源（registry 里的 assignments 是发号台账）
L4_REG = "kb/l4/registry/l4.json"
CANONICAL_DIR = "kb/l4/canonical"


def capture(dest_dir, quiet=False):
    """把**此刻**的 l4.json 落成本次 C8 基座。返回落盘路径。"""
    os.makedirs(dest_dir, exist_ok=True)
    dst = os.path.join(dest_dir, "l4.json")
    if not os.path.exists(L4_REG):
        raise SystemExit("❌ 找不到 %s —— 无法采集 C8 基座" % L4_REG)
    shutil.copy2(L4_REG, dst)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(dest_dir, "_CAPTURED_AT.txt"), "w", encoding="utf-8") as fh:
        fh.write("本次 C8 基座采集时刻：%s\n" % stamp)
        fh.write("来源：%s\n" % L4_REG)
        fh.write("用途：kb/.work/fix_l4_repromote.py 的 C8（发号幂等）应与**本份**比对，\n"
                 "      不再读 kb/l8/_archive/fix-20260929-094703/ 那份历史快照。\n")
    if not quiet:
        am = (json.load(open(dst, encoding="utf-8")).get("assignments") or {})
        print("✓ 本次 C8 基座 → %s（%s）｜assignments %d 条"
              % (dst, stamp, len(am)))
    return dst


def compare(quiet=False):
    """报「旧基座 vs 本次基座」的差异。"""
    if not os.path.exists(OLD_BASE):
        print("⚠️ 旧基座不存在：%s" % OLD_BASE)
        return None
    old = (json.load(open(OLD_BASE, encoding="utf-8")).get("assignments") or {})
    now = (json.load(open(L4_REG, encoding="utf-8")).get("assignments") or {})
    only_old = set(old) - set(now)
    only_now = set(now) - set(old)
    changed = [k for k in set(old) & set(now) if old[k] != now[k]]
    out = {"old_base": OLD_BASE, "old_base_entries": len(old),
           "current_entries": len(now),
           "only_in_old": len(only_old), "only_in_now": len(only_now),
           "key_same_value_diff": len(changed),
           "old_base_lagging_by": len(only_now) + len(changed)}
    if not quiet:
        print("=== 旧基座 vs 本次基座 ===")
        print("  旧基座 assignments：%d 条" % out["old_base_entries"])
        print("  当前  assignments：%d 条" % out["current_entries"])
        print("  旧有今无 %d ｜ 今有旧无 %d ｜ 键同值不同 %d"
              % (out["only_in_old"], out["only_in_now"], out["key_same_value_diff"]))
        print("  ⇒ **旧基座已落后 %d 条** ⇒ 用它做 C8 对比会误报「新发号 %d」"
              % (out["old_base_lagging_by"], out["old_base_lagging_by"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", metavar="DIR", help="把此刻的 l4.json 落成本次基座到 DIR/")
    ap.add_argument("--compare", action="store_true", help="报旧基座 vs 本次基座的差异")
    a = ap.parse_args()
    if a.capture:
        capture(a.capture)
        compare()
        return 0
    if a.compare:
        compare()
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
