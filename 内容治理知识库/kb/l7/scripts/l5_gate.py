#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l5_gate.py —— L5 层闸门（**包装 + 分类档**）：跑层的自检器，把「真失败」和「判据过期」分开。

## 为什么不直接用 kb/.work/l5_integrity.py

实测（2026-09-30）：它有 6 项，其中 **2 项在活库上必然 FAIL**，但都不是数据坏了：

  1. `frozen_layers` —— 它比的是「l5 首次写入那一刻」的 l0/l1/l2 指纹。
     活库每天在跑（实测 l0 最后修改 09-30 09:31、l1 09:43、l2 09:43），**必然不等**。
     layers.yaml 的 notes 里已经登记过这个道理（冻结基线项在活库模式下变红是合法的），
     但 `l5_integrity.py` 自己没有这条分类 —— 所以不能把它当日报闸门直接用。

  2. `l3_append_only` —— 判据是 `new_ids == base_ids`（第 509 行之后的 rule_id 集合
     必须等于前 509 行的集合），也就是「追加段必须覆盖基线」。实测当前
     `kb/l3/candidates/rules.jsonl` **正好 509 行**（09-29 14:46 的收敛步把追加段收敛掉了，
     历史版本留在 `kb/l3/history/rules-superseded-20260924-1230.jsonl`），
     于是 `new_rows = []` → `new_ids = ∅` ≠ base_ids → 必 FAIL。
     → 这是**判据过期**（为「未收敛」状态写的），不是丢了 509 条以外的规则。

## 所以本闸门做两件事

  1. 原样跑 `l5_integrity.py`（**它的输出一个字不改，全打出来**），解析 6 项的 PASS/FAIL；
  2. 分类：
       * 4 项实质判据（pattern_traceability / no_fabricated_words / version_discipline / offline）
         **必须 PASS**，FAIL = 红；
       * 2 项基线类判据（frozen_layers / l3_append_only）FAIL 时，必须逐项登记在
         `kb/l7/registry/l5-known-drift.yaml`（带证据 + 修法）→ 未登记 = 红。
         登记的只是**分类**，原始数照打，不抹掉。

## 副作用（如实声明）

`l5_integrity.py` 会写它自己的证据文件 `kb/.work/l5_integrity.json`（**不是层产物**，
不在 kb/l0…l6 里）。本闸门不写任何别的文件。日报的「零写」口径看的是 l0…l6 产物，不受影响。

用法：
    kb/kbpy l7/scripts/l5_gate.py [--json] [--quiet]
    KB_GATE_KB=<夹具目录> kb/kbpy l7/scripts/l5_gate.py      # 反测用（默认真库）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.environ.get("KB_GATE_KB") or os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(KB)
REGISTRY = os.environ.get("KB_GATE_L7") or os.path.join(KB, "l7/registry")
DRIFT_YAML = os.path.join(REGISTRY, "l5-known-drift.yaml")
CHECKER = "kb/.work/l5_integrity.py"
EVIDENCE = "kb/.work/l5_integrity.json"
SUBSTANTIVE = ("pattern_traceability", "no_fabricated_words", "version_discipline", "offline",
                # ★ 2026-10-15 加：P0 规则配置字段（PRD §6.5 适用内容类型 / 生效版本）。
                #   由 `l5_integrity.py` 算；「未出现」也判红（见本文件 :170 的 items.get(name)）。
                "p0_rule_config")
BASELINE_ITEMS = ("frozen_layers", "l3_append_only")
ITEM = re.compile(r"^\[(PASS|FAIL)\]\s+(\S+)\s*$")



# ══════════════════════════════════════════════════════════════════════════════
# 批次18 · 4-1：**P0 条数可复算**（用户口径「乙」，已挂四轮）
# ══════════════════════════════════════════════════════════════════════════════
# 为什么需要（批12-D + 批15/16 的教训）：
#   `l5_gate` 原先只核**内部一致性**（自检器那几项）⇒ **P0 丢规则它看不见**。
#   实测事故：`W-1.8/H06` 曾因 `rule_code` 丢失而**静默不出现在** `p0_patterns.jsonl`，
#   而闸门照样 ✅ 过 —— 与批12-D「该 BLOCK 却给 PASS」同族（**丢规则不被闸门抓到**）。
# 复算式（用户裁定「乙」口径，写死）：
#   expected = |{ r : r.p_level==P0 ∧ r.rule_kind=='atomic' ∧ r.authority ∈ (expert,legal) }|
#              ∪ { r : r.rule_code ∈ P0_CODE_ALLOWLIST({"H06"}) }
#   数据源 = `kb/l3/candidates/rules.jsonl`（生行）+ `kb/l3/manifest_l3.jsonl`（富化字段唯一真源）；
#   **P0_CODE_ALLOWLIST 从 `kb/.work/l5_export.py` 读**（那次导出的唯一真源，不在此处另抄一份）。
# 只报不修；不符 ⇒ 判红（本闸门原本就没有「P0 相关」判据，故是**新增**而非放松）。
def _p0_recompute():
    import json as _json
    import re as _re
    L3 = os.path.join(ROOT, "kb/l3")
    exp_src = os.path.join(ROOT, "kb/.work/l5_export.py")
    out = {"expected": None, "actual": None, "ok": None, "why": ""}
    # ① 读 ALLOWLIST（唯一真源）
    allow = set()
    try:
        txt = open(exp_src, encoding="utf-8").read()
        m = _re.search(r"P0_CODE_ALLOWLIST\s*=\s*\{([^}]*)\}", txt)
        if m:
            allow = {x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()}
    except Exception as e:                                        # noqa: BLE001
        out["why"] = "读 l5_export.py 的 ALLOWLIST 失败：%r" % e
        return out
    # ② 富化字段（唯一真源 = manifest_l3）
    enr = {}
    try:
        for l in open(os.path.join(L3, "manifest_l3.jsonl"), encoding="utf-8"):
            if l.strip():
                r = _json.loads(l)
                if r.get("rule_id") and r.get("rule_kind"):
                    enr[r["rule_id"]] = r
    except Exception as e:                                        # noqa: BLE001
        out["why"] = "读 manifest_l3 失败：%r" % e
        return out
    # ③ 生行（提供 rule_code）
    codes = {}
    try:
        # ★ 2026-10-13：`codes` 读**两个**候选件。
        #   为什么：外部标准规则住 `candidates/external_standard.jsonl`（`rules.jsonl` 是措辞库的件，
        #   塞进去会让本库 l7_gate 的 C2「现行规则库名（1）」判不出唯一库名）。
        #   而 `l5_export.py` 是**两个源合成视图**的 ⇒ 这里只读一个会让
        #   `expected` 与 `actual` 对不上（实测 11 ≠ 17，直接判红）。
        for _src in ("candidates/rules.jsonl", "candidates/external_standard.jsonl"):
            for l in open(os.path.join(L3, _src), encoding="utf-8"):
                if l.strip():
                    r = _json.loads(l)
                    codes[r.get("rule_id")] = (r.get("rule_code") or "").strip()
    except Exception as e:                                        # noqa: BLE001
        out["why"] = "读 candidates/rules.jsonl 失败：%r" % e
        return out
    exp = set()
    for rid, r in enr.items():
        if r.get("p_level") == "P0":
            if r.get("rule_kind") == "atomic" and r.get("authority") in ("expert", "legal"):
                exp.add(rid)
            elif codes.get(rid, "") in allow:
                exp.add(rid)
    out["expected"] = len(exp)
    out["allowlist"] = sorted(allow)
    # ④ 实际导出条数
    try:
        p0p = os.path.join(ROOT, "kb/l5/p0_patterns.jsonl")
        act = sum(1 for l in open(p0p, encoding="utf-8") if l.strip())
    except Exception as e:                                        # noqa: BLE001
        out["why"] = "读 p0_patterns.jsonl 失败：%r" % e
        return out
    out["actual"] = act
    out["ok"] = (act == len(exp))
    if not out["ok"]:
        out["why"] = ("P0 导出条数 %d ≠ 按「乙」口径可复算的 %d —— "
                      "**丢规则或多发规则**，必须逐条查" % (act, len(exp)))
    return out


def _declared():
    if not os.path.exists(DRIFT_YAML):
        return set(), {}
    try:
        import yaml
        with open(DRIFT_YAML, encoding="utf-8") as fh:
            d = yaml.safe_load(fh) or {}
    except Exception:                                # noqa: BLE001
        return set(), {}
    raw = d.get("stale_criteria") or []
    keys = {str(x.get("item")) for x in raw if isinstance(x, dict)}
    return keys, {str(x.get("item")): x for x in raw if isinstance(x, dict)}


def compute():
    if not os.path.exists(os.path.join(ROOT, CHECKER)):
        return None, "自检器不在位：%s" % CHECKER
    py = os.environ.get("KB_PYTHON") or sys.executable
    r = subprocess.run([py, CHECKER], cwd=ROOT, capture_output=True, text=True)
    items = {}
    for line in (r.stdout or "").splitlines():
        m = ITEM.match(line.strip())
        if m:
            items[m.group(2)] = m.group(1)

    declared, detail = _declared()
    red, classified = [], []
    for name in SUBSTANTIVE:
        if items.get(name) != "PASS":
            red.append([name, items.get(name, "未出现"), "实质判据必须 PASS"])
    for name in BASELINE_ITEMS:
        st = items.get(name)
        if st == "PASS":
            continue
        if name in declared:
            classified.append([name, st, detail[name].get("why", "")[:80]])
        else:
            red.append([name, st, "基线类判据 FAIL 且**未登记**在 %s"
                        % os.path.relpath(DRIFT_YAML, ROOT)])

    # ── 批次18 · 4-1：P0 条数可复算 ─────────────────────────────────────────
    p0 = _p0_recompute()
    if p0.get("ok") is False:
        red.append(["C_p0_count_recomputable", "FAIL", p0.get("why", "")])
    elif p0.get("ok") is None:
        red.append(["C_p0_count_recomputable", "未判定", p0.get("why", "")])

    rep = {
        "p0_recompute": p0,
        "items": items, "checker_exit": r.returncode,
        "substantive_red": [x for x in red if x[0] in SUBSTANTIVE],
        "classified_baseline": classified,
        "declared_items": sorted(declared),
        "red": red, "red_total": len(red),
        "raw_tail": (r.stdout or "").strip().splitlines()[-3:],
        "evidence_file": EVIDENCE,
    }
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
        print(json.dumps({"gate": "l5_gate", "ok": ok, **rep}, ensure_ascii=False, indent=1))
        return 0 if ok else 1

    print("=" * 74)
    print("L5 闸门（跑 kb/.work/l5_integrity.py 的 6 项，按「实质 / 基线」分类）")
    for name in SUBSTANTIVE + BASELINE_ITEMS:
        print("  %-22s %s" % (name, rep["items"].get(name, "未出现")))
    print("-" * 74)
    if not a.quiet:
        for name, st, why in rep["red"]:
            print("  ❌ %s = %s ｜ %s" % (name, st, why))
        for name, st, why in rep["classified_baseline"]:
            print("  ⚠️ %s = %s（已登记为**判据过期**，不判红）｜ %s" % (name, st, why))
    _p0 = rep.get("p0_recompute") or {}
    if _p0.get("ok") is True:
        print("  ✓ C_p0_count_recomputable：P0 导出 %s 条 == 按「乙」口径可复算 %s 条"
              % (_p0.get("actual"), _p0.get("expected")))
    else:
        print("  ❌ C_p0_count_recomputable：%s" % (_p0.get("why") or "未判定"))
    print("-" * 74)
    print("说明：本闸门会触发自检器写它自己的证据文件 %s（不是层产物）" % rep["evidence_file"])
    print("      自检器退出码 %d ｜ 末行：%s" % (rep["checker_exit"], " / ".join(rep["raw_tail"])))
    print("=" * 74)
    # ★ 2026-10-15：项数**不写死** —— 原先写死「实质 4 项」，加第 5 项后提示语就成了假话。
    #   判据仍以 SUBSTANTIVE 为准（:169 那条），这里只是把同一个真源读出来显示。
    print("结论：%s" % ("✅ 过（实质 %d 项全 PASS，基线项异常已登记）" % len(SUBSTANTIVE) if ok
                       else "❌ 未过（红 %d）" % rep["red_total"]))
    print("退出码：%d" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
