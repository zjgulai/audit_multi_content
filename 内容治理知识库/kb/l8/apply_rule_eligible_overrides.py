#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_rule_eligible_overrides.py —— 目标 23 · fix_plan ②③ 的**定向落值**。

## 为什么不能靠「重跑 L1→L2（重切）」把这件事做成（实测，读代码得出）

登记件 `source-readonly.yaml → prd_scope_exclusions.implementation_status.fix_plan` 的第 ③ 步写的是
「重跑 L1→L2（重切），那 53 个单元的 `rule_eligible` 才会翻成 false」。**这句话不成立**，两条：

1. `kb/l8/l2_split_run.py:112` 的重切入口只吃 **`gap`**，而 `gap` 的判据是
   「`source_sha256` 无对应单元 / 切分器版本不在现有单元里 / 现有单元超尺寸」。
   这 3 份 Brief 的正文 sha 没变、切分器版本一致、单元不超尺寸 ⇒ **三条都不满足 ⇒ 不进重切**。
2. `rule_eligible` 由 `kb/l8/ingest_l0_new_records.py` 在**新记录入库**时写进 L1 manifest
   （`l0.get("rule_eligible")` ← `l2_split_run.py:223`）。
   而这 3 条**早已在 L0**，不在对账的 `only_feishu_ids` 里 ⇒ 那段**根本不会触发**。

⇒ **`rule_eligible` 是「记录的属性」，不是「切分的产物」** ⇒ 定向落值才是对的做法。
本件就是那把定向落值的刀，**判据仍用 C8 那一把尺子，不新造第二把**。

## 判据（与 `kb/l8/check_source_readonly.py::c8_prd_scope_exclusions` **逐字同源**）

    命中排除记录 ∧ rule_eligible is not False   的 L2 单元数  ==  0

## 用法

    python3 kb/l8/apply_rule_eligible_overrides.py              # 预演（默认，零写入）
    python3 kb/l8/apply_rule_eligible_overrides.py --apply      # 真写（备份 + 回执）
    python3 kb/l8/apply_rule_eligible_overrides.py --selftest   # 自证（在临时夹具上，不碰真库）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)                      # …/kb
ROOT = os.path.dirname(KB)                      # 工作区根
REG = os.path.join(KB, "l0/registry/kb.json")
UNITS = os.path.join(KB, "l2/units.jsonl")
L1MAN = os.path.join(KB, "l1/manifest_l1.jsonl")


def load_overrides(reg_path=REG):
    """读 kb.json → rule_eligible_overrides ⇒ (rids, reason_code)。

    ★ fail-closed：读不到 / 没有 records ⇒ **抛错**，不许静默当成「没有覆盖项」。
      静默的代价正是本库栽过的那一类 —— 尺子看着在守，其实什么都没守。
    """
    try:
        reg = json.load(io.open(reg_path, encoding="utf-8"))
    except Exception as e:                                   # noqa: BLE001
        raise SystemExit("[拒写] 读不到 %s（%r）—— fail-closed" % (reg_path, e))
    blk = reg.get("rule_eligible_overrides") or {}
    recs = blk.get("records") or []
    if not recs:
        raise SystemExit("[拒写] %s 里没有 rule_eligible_overrides.records —— 空清单会静默什么都不做" % reg_path)
    rids = [str(r["record_id"]) for r in recs if r.get("record_id")]
    if not rids:
        raise SystemExit("[拒写] rule_eligible_overrides.records 里没有带 record_id 的条目")
    return rids, (blk.get("reason_code") or "prd_scope_exclusion")


def scan(path, rids):
    """与 C8 逐字同源：`record_id` 子串命中 `resource_id` ⇒ 该行属于排除记录。"""
    hit, eligible, lines = 0, 0, []
    with io.open(path, encoding="utf-8") as fh:
        for ln in fh:
            if not ln.strip():
                continue
            lines.append(ln)
            try:
                u = json.loads(ln)
            except Exception:                                # noqa: BLE001
                continue
            rid = str(u.get("resource_id") or "")
            if any(r in rid for r in rids):
                hit += 1
                if u.get("rule_eligible") is not False:
                    eligible += 1
    return hit, eligible, lines


def flip(lines, rids, reason_code):
    """把命中行的 rule_eligible 落成 False。**只碰需要的键**，其余逐字保留。"""
    out, changed = [], 0
    for ln in lines:
        if not ln.strip():
            out.append(ln); continue
        u = json.loads(ln)
        rid = str(u.get("resource_id") or "")
        if any(r in rid for r in rids) and u.get("rule_eligible") is not False:
            u["rule_eligible"] = False
            u["rule_eligible_source"] = reason_code
            u["rule_eligible_run"] = u.get("rule_eligible_run") or "override-20261010"
            out.append(json.dumps(u, ensure_ascii=False, sort_keys=True) + "\n")
            changed += 1
        else:
            out.append(ln if ln.endswith("\n") else ln + "\n")
    return out, changed


def run(apply_now, reg_path=REG, units_path=UNITS, quiet=False):
    rids, reason = load_overrides(reg_path)
    hit_u, elig_u, lines_u = scan(units_path, rids)
    tgt = [("L2 units", units_path, hit_u, elig_u, lines_u)]
    if os.path.exists(L1MAN) and os.path.abspath(L1MAN) != os.path.abspath(units_path):
        hit_m, elig_m, lines_m = scan(L1MAN, rids)
        tgt.append(("L1 manifest", L1MAN, hit_m, elig_m, lines_m))
    print("规则：rule_eligible_overrides 共 %d 条记录｜reason_code=%s" % (len(rids), reason))
    for name, path, hit, elig, _ in tgt:
        print("  [%s] 命中 %d 行 ｜ 其中待覆盖 %d 行 ｜ %s"
              % (name, hit, elig, os.path.relpath(path, ROOT)))
    total_changed = 0
    if not apply_now:
        print("\n预演（零写入）。要落盘加 --apply。")
        return {"dry_run": True, "targets": {n: {"hit": h, "eligible": e} for n, _, h, e, _ in tgt}}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for name, path, hit, elig, lines in tgt:
        if not elig:
            continue
        shutil.copy(path, path + ".bak-pre-t23-" + stamp)
        new, ch = flip(lines, rids, reason)
        tmp = path + ".swtmp." + stamp
        with io.open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(new)
        os.replace(tmp, path)                                # 原子替换
        total_changed += ch
        print("  ✅ %s 落盘 %d 行（备份 %s）" % (name, ch, os.path.basename(path) + ".bak-pre-t23-" + stamp))
    rec = {"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "target": "23 rule_eligible overrides",
           "records": rids, "reason_code": reason, "changed": total_changed,
           "targets": {n: {"hit": h, "eligible": e} for n, _, h, e, _ in tgt}}
    rp = os.path.join(KB, "l8/runs/%s-rule-eligible-override.json" % stamp)
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    json.dump(rec, io.open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("  回执：%s" % os.path.relpath(rp, ROOT))
    return rec


def selftest():
    """在**临时夹具**上自证，不碰真库。含反向对照与变异测试。"""
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    tmp = tempfile.mkdtemp(prefix="t23apply-")
    reg = os.path.join(tmp, "kb.json")
    uni = os.path.join(tmp, "units.jsonl")
    D = "bitable__tblMGtPfe8ZUsEdP__recvvrLzQETJyc"      # 声明的
    N = "bitable__tblMGtPfe8ZUsEdP__recvvg2wL2qE3K"      # **没声明**的
    json.dump({"rule_eligible_overrides": {"reason_code": "prd_scope_exclusion",
                                           "records": [{"record_id": "recvvrLzQETJyc"}]}},
              io.open(reg, "w", encoding="utf-8"), ensure_ascii=False)
    with io.open(uni, "w", encoding="utf-8") as fh:
        for i in range(3):
            fh.write(json.dumps({"unit_id": "u%d" % i, "resource_id": D, "rule_eligible": True,
                                 "text": "声明记录"}) + "\n")
        fh.write(json.dumps({"unit_id": "n0", "resource_id": N, "rule_eligible": True,
                             "text": "未声明记录"}) + "\n")
    rids, _ = load_overrides(reg)
    hit, elig, lines = scan(uni, rids)
    ck("① 预演数得准（命中 3 / 待覆盖 3）", (hit, elig) == (3, 3), "实际 %s" % ((hit, elig),))
    # ② 反向对照：**未声明的记录不许被改**
    new, ch = flip(lines, rids, "prd_scope_exclusion")
    keep = [json.loads(l) for l in new if json.loads(l)["unit_id"] == "n0"][0]
    ck("② 反向对照：未声明的记录一个字没动",
       ch == 3 and keep.get("rule_eligible") is True and "rule_eligible_source" not in keep, "changed=%d" % ch)
    # ③ 幂等：再翻一次 = 0 改动
    _n2, ch2 = flip(new, rids, "prd_scope_exclusion")
    ck("③ 幂等：重跑 0 改动", ch2 == 0, "changed=%d" % ch2)
    # ④ 判据真的转绿：翻完后「命中 ∧ Ë≠False」必须为 0（= C8 的判据）
    io.open(uni, "w", encoding="utf-8").writelines(new)
    _h2, e2, _l2 = scan(uni, rids)
    ck("④ 落值后 C8 判据归零（命中 ∧ rule_eligible≠False == 0）", e2 == 0, "残留=%d" % e2)
    # ⑤ fail-closed：空清单 ⇒ 拒（不许静默什么都不做）
    json.dump({"rule_eligible_overrides": {"records": []}},
              io.open(reg, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        load_overrides(reg); ck("⑤ 反向对照：空清单 ⇒ 拒", False, "竟然没抛错")
    except SystemExit:
        ck("⑤ 反向对照：空清单 ⇒ 拒", True, "")
    # ⑥ 变异测试：不落值（还原成 True）⇒ ④ 精确变假
    with io.open(uni, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"unit_id": "u0", "resource_id": D, "rule_eligible": True}) + "\n")
    _h3, e3, _l3 = scan(uni, rids)
    ck("⑥ 变异测试：把值还原 ⇒ ④ 的判据精确变假", e3 == 1, "残留=%d" % e3)
    shutil.rmtree(tmp, ignore_errors=True)
    print("apply_rule_eligible_overrides --selftest（目标 23 · 定向落值）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + ex) if ex else ""))
    bad = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad, len(res), "" if not bad else "  ← 有失败"))
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真写（默认预演，零写入）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    run(a.apply)
