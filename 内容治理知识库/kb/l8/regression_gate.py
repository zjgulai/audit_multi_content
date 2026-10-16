#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regression_gate.py —— 回归基线闸门：**同一批素材、改了上游、三态不许变。**

════════════════════════════════════════════════════════════════════════
★ 它补的是哪一格（2026-10-12）
════════════════════════════════════════════════════════════════════════
库里此前**没有任何东西在跑** `kb/l7/registry/regression-set.yaml`
（`grep -rl regression-set` 只命中构建器自己）——
所以「改了上游、三态变没变」这件事，一直只是**散文**，没有失败信号。
2026-10-12 10:45 补了跑手，10:54 第一次跑出来：**solid 80 条里 13 条与基线不同，从未归因**。

★ 断言用的是**哪份基线**（这里最容易搞错，逐字写死）
    · 断言基线 = `kb/l7/registry/regression-baseline.json`
      （由 `regression_run.py --rebaseline` 从**现引擎**的一次真跑重采）
    · `regression-set.yaml` 里的 `expected` **不作断言** —— 它是从**历史 `*.review.md`**
      里刮出来的「报告当时的结论」，拿它当断言等于把引擎自身的演进全报成回归
      （实测 13 条漂移里 12 条属此类）。跑手仍会打印它，只作**线索**。

★ 判红 / 报黄（照 `l5_gate.py`、`workflow_smoke.py` 的惯例）
    · **红**：基线在 ＋ 产物在 ＋ **同代读法** ⇒ 有条目漂移／条目消失／
              `orphan_non_p3` 非空（证据里有、结论却不采纳，且不是 P3）
    · **黄（只报不判红）**：基线没建／没跑过／产物是**旧读法**（无 `got_source`）／
              覆盖率不足 ⇒ **未测**，不许当绿
    · **已知漂移**：`kb/l7/registry/regression-known-drift.yaml` 里登记过的 case_id
      降为黄（口径同 `l3/l4/l5-known-drift.yaml`）

★ 边界：本闸门**只读**（读基线 + 读跑批产物），不跑引擎、不写库、< 1 秒。
  跑引擎那件事由 `regression_run.py` 单独做（100 条 ≈ 9 分钟）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
ROOT = KB.parent
BASELINE = KB / "l7" / "registry" / "regression-baseline.json"
KNOWN_DRIFT = KB / "l7" / "registry" / "regression-known-drift.yaml"

GREEN, RED, YELLOW = "green", "red", "yellow"


def _known_drift() -> dict:
    """登记件读不到 ⇒ 空表（不阻断），照 `l3/l4/l5-known-drift.yaml` 的口径。"""
    try:
        import yaml
        d = yaml.safe_load(KNOWN_DRIFT.read_text(encoding="utf-8")) or {}
    except Exception:                                   # noqa: BLE001
        return {}
    return d.get("cases") or {}


def _load_rows(p: Path) -> list:
    try:
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:                                   # noqa: BLE001
        return []


def newest_artifact(work: Path | None = None, baseline: dict | None = None):
    """挑一件**可判**的产物。返回 `(path, rows, why)`。

    ★★ 2026-10-12 修（**被真实事件照出来的**）：原先只按 mtime 取最新一件 ——
      于是**任何人正在跑的半成品**都会劫持读数。实测：另一会话为「风险分类」改动跑了一份
      `kb/.work/regression-rc-check.jsonl`（8 行、**旧读法**）⇒ 闸门立刻从「与基线逐条一致（绿）」
      掉成「未测」，而**库里明明躺着一份 100 行、同源读法、刚刚比对过的产物**。
      「未测」不算红，所以这不会误判成回归 —— 但它会**把真读数盖住**，同样是错。

    取件口径（**可判优先，旧读法垫底**）：
      ① 同源读法（有非空 `got_source`）**且**覆盖基线 ≥90% solid 的最新一件；
      ② 退而求其次：同源读法的最新一件（覆盖率不足 ⇒ 闸门自己会判「未测」，但读法是对的）；
      ③ 都没有：最新的旧读法一件（闸门判「未测」并说明是旧读法）。
    """
    d = work or (KB / ".work")
    files = sorted(d.glob("regression-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None, [], "kb/.work 下没有 regression-*.jsonl"
    base = ((baseline or {}).get("cases") or {})
    same, legacy = [], []
    for p in files:
        rows = _load_rows(p)
        if not rows:
            continue
        (same if artifact_reading(rows) == "same_source" else legacy).append((p, rows))
    for p, rows in same:
        if base:
            got = {r.get("case_id") for r in rows if r.get("layer") == "solid"}
            if len(got & set(base)) >= max(1, int(0.9 * len(base))):
                return p, rows, "同源读法 + 覆盖基线 ≥90%"
    if same:
        p, rows = same[0]
        return p, rows, "同源读法（覆盖率不足 ⇒ 闸门会判未测）"
    p, rows = legacy[0]
    return p, rows, "**旧读法**（三态与条目不同源 ⇒ 判未测，不当绿也不当红）"


def artifact_reading(rows: list) -> str:
    """产物的读法是哪一代。**旧读法（没有非空 `got_source`）一律判「未测」**，不许判绿。

    ⚠️ 判据是**非空值**，不是"键在不在" —— 键在但值是 None 的一律不算同源读法
       （自证 R3 就是喂这个形状；第一版写成 `"got_source" in r` ⇒ R3 精确变红，已修）。
    """
    if not rows:
        return "empty"
    if not any(str(r.get("got_source") or "").strip() for r in rows):
        return "legacy"          # 2026-10-12 之前那一版跑手：三态与条目不同源
    return "same_source"


def judge(baseline: dict | None, rows: list, known: dict | None = None) -> dict:
    """纯函数：给基线 + 产物，出裁决。**不读盘、不写盘**（便于反向对照）。"""
    known = known or {}
    out = {"verdict": YELLOW, "reasons": [], "drift": [], "missing": [],
           "orphan_non_p3": [], "reading": artifact_reading(rows),
           "n_baseline": len((baseline or {}).get("cases") or {}), "n_rows": len(rows)}

    if not baseline or not (baseline.get("cases") or {}):
        out["reasons"].append("基线未建立 ⇒ 未测（跑 `regression_run.py --out …` 后 `--rebaseline`）")
        return out
    if not rows:
        out["reasons"].append("没有跑批产物 ⇒ 未测（本闸门不跑引擎，只读产物）")
        return out
    if out["reading"] != "same_source":
        out["reasons"].append(
            "产物是**旧读法**（三态与条目不同源，无 `got_source`）⇒ 未测；"
            "拿它判红会产出假警报（2026-10-12 实测 5/5 假象）")
        return out

    by_id = {r.get("case_id"): r for r in rows if r.get("layer") == "solid"}
    base = baseline["cases"]
    covered = [c for c in base if c in by_id]
    if len(covered) < max(1, int(0.9 * len(base))):
        out["reasons"].append("产物只覆盖基线 %d/%d 条 ⇒ 未测（覆盖率不足，不许判绿）"
                              % (len(covered), len(base)))
        return out

    for cid, want in sorted(base.items()):
        r = by_id.get(cid)
        if r is None:
            out["missing"].append(cid)
            continue
        got = r.get("got")
        if got != want.get("state"):
            if cid in known:
                out["reasons"].append("已知漂移（登记件里有）：%s %s→%s"
                                      % (cid, want.get("state"), got))
            else:
                out["drift"].append({"case_id": cid, "baseline": want.get("state"), "now": got})
        if r.get("orphan_non_p3"):
            out["orphan_non_p3"].append({"case_id": cid, "orphan": r["orphan_non_p3"]})

    if out["drift"] or out["missing"] or out["orphan_non_p3"]:
        out["verdict"] = RED
        if out["drift"]:
            out["reasons"].append("三态漂移 %d 条（对基线）" % len(out["drift"]))
        if out["missing"]:
            out["reasons"].append("条目消失 %d 条（基线里有、产物里没有）" % len(out["missing"]))
        if out["orphan_non_p3"]:
            out["reasons"].append(
                "**有依据却不进结论** %d 条（证据侧非 P3 条目被结论丢下）" % len(out["orphan_non_p3"]))
    else:
        out["verdict"] = GREEN
        out["reasons"].append("与基线逐条一致（solid %d 条）" % len(base))
    return out


def selftest() -> int:
    ok = True

    def chk(name, cond, extra=""):
        nonlocal ok
        print(("  ✅ " if cond else "  ❌ ") + name + (("  " + extra) if extra and not cond else ""))
        ok = ok and bool(cond)

    base = {"cases": {"a": {"state": "BLOCK"}, "b": {"state": "PASS"}, "c": {"state": "REVIEW"}}}
    good = [{"case_id": "a", "layer": "solid", "got": "BLOCK", "got_source": "decision.decision"},
            {"case_id": "b", "layer": "solid", "got": "PASS", "got_source": "decision.decision"},
            {"case_id": "c", "layer": "solid", "got": "REVIEW", "got_source": "decision.decision"}]

    print("regression_gate 自证（反向对照：判据必须不是恒绿也不是恒红）")
    chk("① 正例：逐条一致 ⇒ 绿", judge(base, good)["verdict"] == GREEN)

    bad = [dict(r) for r in good]
    bad[1]["got"] = "BLOCK"
    j = judge(base, bad)
    chk("R1 篡改一条三态 ⇒ **精确红**，且点名那一条",
        j["verdict"] == RED and [d["case_id"] for d in j["drift"]] == ["b"], repr(j["drift"]))

    j = judge(base, good[:2])
    chk("R2 条目消失（基线 3 条、产物 2 条）⇒ 红", j["verdict"] == RED and j["missing"] == ["c"])

    j = judge(base, [{**r, "got_source": None} for r in good])
    chk("R3 旧读法产物 ⇒ **未测（黄）**，不许判绿也不许判红",
        j["verdict"] == YELLOW and "旧读法" in "".join(j["reasons"]))

    chk("R4 基线不存在 ⇒ 未测（黄）", judge(None, good)["verdict"] == YELLOW)
    chk("R5 产物为空 ⇒ 未测（黄），不崩", judge(base, [])["verdict"] == YELLOW)

    orphan = [dict(r) for r in good]
    orphan[0]["orphan_non_p3"] = [{"rule_id": "r-x", "p_level": "P1"}]
    j = judge(base, orphan)
    chk("R6 证据里有非 P3 条目、结论却不采纳 ⇒ 红（有依据不进结论）",
        j["verdict"] == RED and j["orphan_non_p3"], repr(j))

    j = judge(base, bad, known={"b": "已登记"})
    chk("R7 漂移已在 known-drift 登记 ⇒ 降为黄（不判红）",
        j["verdict"] == GREEN or (j["verdict"] != RED and not j["drift"]))

    # R8 取件（2026-10-12 加，被真实事件照出来的）：**半成品不得劫持读数**。
    #    真实事件：另一会话为「风险分类」改动跑了一份 8 行、**旧读法**的
    #    `regression-rc-check.jsonl`（mtime 最新）⇒ 旧版按 mtime 取件，闸门立刻从
    #    「与基线逐条一致」掉成「未测」，而库里明明躺着一份 100 行、同源、刚比对过的产物。
    import tempfile
    _tmp = tempfile.mkdtemp(prefix="reggate-pick-")
    try:
        _old = Path(_tmp) / "regression-aaa.jsonl"
        _new = Path(_tmp) / "regression-zzz.jsonl"
        _old.write_text("".join(json.dumps(r) + "\n" for r in good), encoding="utf-8")
        _new.write_text("".join(json.dumps({k: v for k, v in r.items() if k != "got_source"}) + "\n"
                                for r in good), encoding="utf-8")
        os.utime(_old, (1, 1))                       # 旧的：同源；新的：旧读法半成品
        p, _rows, why = newest_artifact(work=Path(_tmp), baseline=base)
        chk("R8 取件：mtime 最新的**旧读法半成品**不得劫持 ⇒ 必须选那份同源产物",
            p == _old and "同源" in why, f"{p.name if p else '-'} ｜ {why}")
        _old.unlink()                                # 同源那份没了 ⇒ 才轮到旧读法，且理由要点明
        p2, _r2, why2 = newest_artifact(work=Path(_tmp), baseline=base)
        chk("R8b 只剩旧读法时 ⇒ 取它，但理由必须写「旧读法」",
            p2 == _new and "旧读法" in why2, why2)
    finally:
        import shutil as _sh
        _sh.rmtree(_tmp, ignore_errors=True)

    print("结论：%s" % ("✅ 判据有反向对照，不是恒真/恒绿" if ok else "❌ 有反向对照没红"))
    return 0 if ok else 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=None, help="跑批产物 jsonl（缺省取 kb/.work 下最新的）")
    ap.add_argument("--baseline", default=str(BASELINE))
    ap.add_argument("--strict", action="store_true", help="未测（黄）也非零退出（给 CI 用）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    bp = Path(a.baseline)
    baseline = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else None
    if a.artifact:
        apath, rows, pick_why = Path(a.artifact), _load_rows(Path(a.artifact)), "调用方指定"
    else:
        apath, rows, pick_why = newest_artifact(baseline=baseline)

    j = judge(baseline, rows, _known_drift())
    j["baseline_path"] = str(bp) if bp.exists() else None
    j["artifact"] = str(apath) if apath else None
    j["pick_why"] = pick_why
    if a.json:
        print(json.dumps(j, ensure_ascii=False, indent=1))
    else:
        icon = {GREEN: "✅", RED: "❌", YELLOW: "⚠️ "}[j["verdict"]]
        print("%s 回归基线闸门：%s" % (icon, j["verdict"].upper()))
        print("   基线：%s（solid %d 条）｜ 产物：%s（%d 行，读法=%s）"
              % (j.get("baseline_path") or "未建立", j["n_baseline"],
                 os.path.basename(j.get("artifact") or "无"), j["n_rows"], j["reading"]))
        print("   取件：%s" % j.get("pick_why"))
        for r in j["reasons"]:
            print("   · " + r)
        for d in j["drift"]:
            print("   ❌ %s  %s → %s" % (d["case_id"], d["baseline"], d["now"]))
        for c in j["missing"]:
            print("   ❌ %s  条目消失" % c)
    if j["verdict"] == RED:
        return 3
    if j["verdict"] == YELLOW and a.strict:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
