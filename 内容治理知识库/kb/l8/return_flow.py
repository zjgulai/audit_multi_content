#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""return_flow.py —— 「知识库回流」台账的**唯一写入器** ＋ 计数器 ＋ 反向对照。

口径真源：`kb/l7/registry/return-flow.yaml`（本脚本**不另立口径**，只实现它）。
PRD 出处：§9 末句（落点）｜§10 第 7 项（数量）｜§11.2（重复要求）。

## 它解决什么

`kb/l8/audit_metrics.mjs` 的第 7 项长期是 `no_data`，而它自己写着：
「本项**不是 0**，是**未接线** —— 写 0 会让人以为『核过了，没有回流』」。
⇒ 本脚本把「回流」接上，并且**把两态拆成三态**，任何时刻都读得出卡在哪一步：

    not_wired       台账/写入器不在            → no_data，「机制未接」
    wired_no_input  台账在、但没人判过          → no_data，「等首批人工复核」（**不报 0**）
    measured        有人判过                    → 数量 = 事件条数（按层分组）

★ `wired_no_input` 与 `measured(0)` 是**两件事**：前者是「没人判」，后者是「有人判了、
  而且全都与机器一致」—— 后者是**合法读数**，前者不是。

## 三条红线（详见 return-flow.yaml → redlines）

  ① `source == 我构造` ⇒ `applies_to = count_only`，**永远不许**进第二步（真写权重）；
     构造题会把规则朝不存在的素材上调（过拟合虚构样本）。
  ② 复核人为空 ⇒ `count_only`（追不到人 ⇒ 不得改库）。
  ③ **第一步不写 kb/l0…l6 任何字节**，只写 `kb/l7/registry/`；不碰飞书源。

## 用法

    sh kb/kbpy l8/return_flow.py status [--json]        # 读：三态 + 数量（默认只读）
    sh kb/kbpy l8/return_flow.py ingest --csv <path> --source <真实投放|历史打回|我构造> [--apply]
    sh kb/kbpy l8/return_flow.py --selftest             # 反向对照（10 例）

退出码：0 = 成功 ｜ 2 = 用法/输入错 ｜ 3 = 拒收（判据不过，**不落盘**）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
KB = HERE.parent.parent                      # …/kb
LEDGER = KB / "l7" / "registry" / "return-flow.ndjson"
SPEC = KB / "l7" / "registry" / "return-flow.yaml"

STATES = ("PASS", "REVIEW", "BLOCK", "NEEDS_INPUT")
SOURCES = ("真实投放", "历史打回", "我构造")

# 人判列的候选表头（两份输入源的写法不同，见 spec.inputs）
HUMAN_COLS = ("人判", "我的判断", "人工判断", "human_state")
MACHINE_COLS = ("机器结论", "机器判定", "machine_state")
ID_COLS = ("题号", "序号", "item_id", "id")
RUN_COLS = ("送审运行ID", "送审运行 ID", "run_id")
REASON_COLS = ("人判理由", "理由", "reason")
REVIEWER_COLS = ("复核人", "reviewer")

_ALIAS = {
    "pass": "PASS", "通过": "PASS", "可发": "PASS",
    "review": "REVIEW", "复核": "REVIEW", "待审": "REVIEW",
    "block": "BLOCK", "拦截": "BLOCK", "不可发": "BLOCK",
    "needs_input": "NEEDS_INPUT", "needsinput": "NEEDS_INPUT",
    "未判": "NEEDS_INPUT", "判不了": "NEEDS_INPUT", "缺料": "NEEDS_INPUT",
}


def norm_state(v) -> str | None:
    """把写法各异的判定归一成四态之一；认不出返回 None（**不许猜**）。"""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    up = s.upper().replace("-", "_").replace(" ", "")
    if up in STATES:
        return up
    if up in _ALIAS:
        return _ALIAS[up]
    low = s.lower()
    if low in _ALIAS:
        return _ALIAS[low]
    # 「拿不准，因为…」这类：明确表示判不了 ⇒ 归 NEEDS_INPUT（与业务侧口径第 5 条一致）
    if s.startswith("拿不准") or "拿不准" in s:
        return "NEEDS_INPUT"
    return None


def _pick(row: dict, cands) -> str | None:
    for c in cands:
        if c in row:
            return c
    return None


def read_csv_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def default_target_layer(m: str, h: str) -> tuple[str, str]:
    """口径件 target_layer_default 的实现。返回 (layer, 依据)。"""
    if m == "PASS" and h in ("BLOCK", "REVIEW"):
        return "L1-L2", "机器放行而人拦下 ⇒ 漏放 ⇒ 缺负样本"
    if m in ("BLOCK", "REVIEW") and h == "PASS":
        return "L3", "机器拦下而人放行 ⇒ 误报 ⇒ 规则过严"
    if m == "NEEDS_INPUT" and h in STATES[:3]:
        return "L3", "机器判不了而人判了 ⇒ 规则覆盖不到"
    return "L3", "默认（差异方向未命中两条显式规则）"


def classify(source: str, reviewer: str | None) -> tuple[str, str | None]:
    """红线判定：返回 (applies_to, count_only_reason)。"""
    if source not in SOURCES:
        raise ValueError("source 必须是 %s 之一，收到 %r" % ("/".join(SOURCES), source))
    if source == "我构造":
        return "count_only", "constructed-items-count-only（构造题不得改权重）"
    if not (reviewer or "").strip():
        return "count_only", "no-reviewer-count-only（追不到人 ⇒ 不得改库）"
    return "weight_eligible", None


def load_ledger(path: Path) -> tuple[list[dict], list[str]]:
    """读台账。返回 (事件, 坏行描述)。坏行**不静默**。"""
    if not path.exists():
        return [], []
    evs, bad = [], []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            o = json.loads(s)
        except Exception as e:
            bad.append("第 %d 行不是 JSON：%s" % (i, e))
            continue
        if not isinstance(o, dict) or "event_id" not in o:
            bad.append("第 %d 行缺 event_id" % i)
            continue
        evs.append(o)
    return evs, bad


def scan_inputs(kb: Path) -> tuple[int, list[dict]]:
    """扫已知输入源，数「可判定的对照样本」（机器结论 + 人判 都非空）。

    ★ 这个数是 `wired_no_input` 与 `measured(0)` 的**分界**：
      0 ⇒ 没人判过（no_data）；>0 ⇒ 有人判过（合法读数，哪怕事件为 0）。
    """
    n, detail = 0, []
    for rel in ("l7/reports/audit-sample-ALL.csv", "l7/reports/gold-set-60.csv"):
        p = kb / rel
        if not p.exists():
            detail.append({"input": rel, "exists": False, "comparable": 0})
            continue
        try:
            rows = read_csv_rows(p)
        except Exception as e:
            detail.append({"input": rel, "exists": True, "error": str(e), "comparable": 0})
            continue
        if not rows:
            detail.append({"input": rel, "exists": True, "comparable": 0})
            continue
        hc, mc = _pick(rows[0], HUMAN_COLS), _pick(rows[0], MACHINE_COLS)
        c = 0
        if hc and mc:
            for r in rows:
                if norm_state(r.get(hc)) and norm_state(r.get(mc)):
                    c += 1
        detail.append({"input": rel, "exists": True, "comparable": c,
                       "human_col": hc, "machine_col": mc, "rows": len(rows)})
        n += c
    return n, detail


def status_payload(kb: Path) -> dict:
    ledger = kb / "l7" / "registry" / "return-flow.ndjson"
    spec = kb / "l7" / "registry" / "return-flow.yaml"
    if not spec.exists() or not ledger.exists():
        return {"state": "not_wired", "audit_status": "no_data",
                "reason": "机制未接（台账或口径件不在）",
                "ledger": str(ledger.relative_to(kb)), "n_events": 0,
                "by_target_layer": {}, "n_comparable_samples": 0, "inputs": []}
    evs, bad = load_ledger(ledger)
    n_cmp, detail = scan_inputs(kb)
    by = {}
    for e in evs:
        by[e.get("target_layer", "?")] = by.get(e.get("target_layer", "?"), 0) + 1
    by_apply = {}
    for e in evs:
        by_apply[e.get("applies_to", "?")] = by_apply.get(e.get("applies_to", "?"), 0) + 1

    base = {"ledger": str(ledger.relative_to(kb)), "n_events": len(evs),
            "by_target_layer": by, "by_applies_to": by_apply,
            "n_comparable_samples": n_cmp, "inputs": detail,
            "bad_lines": bad, "spec": str(spec.relative_to(kb))}

    if n_cmp == 0:
        base.update({
            "state": "wired_no_input", "audit_status": "no_data",
            "reason": "机制已接线；台账在建；**等首批人工复核**"
                      "（台账 %d 条事件，对照样本 0 条）" % len(evs),
            "why_not_zero": "机制接线 ≠ 有读数；此时报 measured:0 会退回「核过了，没有回流」那个错读法",
        })
    else:
        base.update({
            "state": "measured", "audit_status": "measured",
            "value": len(evs),
            "reason": "对照样本 %d 条，回流事件 %d 条（按 target_layer 分组：%s）"
                      % (n_cmp, len(evs), by or "{}"),
            "note": ("有人判过 %d 条、且全部与机器一致 ⇒ 事件 0 是**合法读数**" % n_cmp)
                    if not evs else "",
        })
    return base


# ══════════════════════════════════════════════════════════════════
def cmd_status(kb: Path, as_json: bool) -> int:
    p = status_payload(kb)
    if as_json:
        print(json.dumps(p, ensure_ascii=False, indent=2))
        return 0
    icon = {"not_wired": "⛔", "wired_no_input": "🔌", "measured": "✅"}[p["state"]]
    print("%s 回流状态：%s（audit_metrics 记为 %s）" % (icon, p["state"], p["audit_status"]))
    print("   台账：%s ｜ 事件 %d 条 %s" % (p["ledger"], p["n_events"], p["by_target_layer"] or ""))
    print("   对照样本（机器结论+人判 都非空）：%d 条" % p["n_comparable_samples"])
    for d in p["inputs"]:
        print("     · %s  exists=%s comparable=%s" % (d["input"], d.get("exists"), d.get("comparable", "-")))
    print("   原因：%s" % p["reason"])
    if p.get("bad_lines"):
        print("   ⚠ 坏行 %d 条：%s" % (len(p["bad_lines"]), p["bad_lines"][:3]))
    return 0


def cmd_ingest(kb: Path, csv_path: Path, source: str, reviewer: str | None,
               apply_: bool, ledger: Path) -> int:
    if not csv_path.exists():
        print("找不到输入：%s" % csv_path)
        return 2
    rows = read_csv_rows(csv_path)
    if not rows:
        print("输入为空：%s" % csv_path)
        return 2
    hc, mc = _pick(rows[0], HUMAN_COLS), _pick(rows[0], MACHINE_COLS)
    if not hc or not mc:
        print("❌ 输入缺列：需要「人判」与「机器结论」两栏；实得 %s" % list(rows[0].keys()))
        return 3
    idc = _pick(rows[0], ID_COLS)
    rc = _pick(rows[0], RUN_COLS)
    rsn = _pick(rows[0], REASON_COLS)
    rvc = _pick(rows[0], REVIEWER_COLS)

    existing, bad = load_ledger(ledger)
    seen = {(e.get("run_id"), e.get("item_id")) for e in existing}
    today = datetime.now().strftime("%Y%m%d")
    seq = sum(1 for e in existing if str(e.get("event_id", "")).startswith("RF-%s-" % today))

    new, skipped = [], {"same": 0, "no_human": 0, "human_needs_input": 0, "unparsable": 0, "dup": 0}
    for i, r in enumerate(rows, 2):                       # 2 = 表头占第 1 行
        m, h = norm_state(r.get(mc)), norm_state(r.get(hc))
        if not h:
            skipped["no_human"] += 1
            continue
        if not m:
            skipped["unparsable"] += 1
            continue
        if h == "NEEDS_INPUT":
            skipped["human_needs_input"] += 1             # 口径：判不了 ⇒ 无纠错依据
            continue
        if h == m:
            skipped["same"] += 1                          # 一致 ⇒ 无回流价值
            continue
        item = (r.get(idc) or "").strip() if idc else ""
        run = (r.get(rc) or "").strip() if rc else ""
        if not item:
            item = "row%d" % i
        if (run, item) in seen:
            skipped["dup"] += 1
            continue
        rev = (r.get(rvc) or "").strip() if rvc else ""
        rev = rev or (reviewer or "")
        try:
            applies, why_co = classify(source, rev)
        except ValueError as e:
            print("❌ %s" % e)
            return 2
        layer, basis = default_target_layer(m, h)
        seq += 1
        ev = {
            "event_id": "RF-%s-%04d" % (today, seq),
            "at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "source": source, "applies_to": applies, "count_only_reason": why_co,
            "target_layer": layer, "target_layer_basis": basis,
            "run_id": run, "item_id": item,
            "machine_state": m, "human_state": h,
            "reviewer": rev or None,
            "reason": (r.get(rsn) or "").strip() if rsn else "",
            "evidence": {"csv": csv_path.name, "row": i},
        }
        new.append(ev)
        seen.add((run, item))

    print("输入：%s（%d 行）｜source=%s" % (csv_path.name, len(rows), source))
    print("  可判定对照：%d ｜ 跳过：一致 %d / 人判 NEEDS_INPUT %d / 无人判 %d / 机器值认不出 %d / 重复 %d"
          % (len(new), skipped["same"], skipped["human_needs_input"],
             skipped["no_human"], skipped["unparsable"], skipped["dup"]))
    if bad:
        print("  ⚠ 台账已有坏行 %d 条（不静默）：%s" % (len(bad), bad[:3]))
    for e in new[:5]:
        print("   + %s %s→%s [%s] %s" % (e["event_id"], e["machine_state"],
                                         e["human_state"], e["target_layer"], e["item_id"]))
    if len(new) > 5:
        print("   … 另有 %d 条" % (len(new) - 5))
    if not apply_:
        print("\n预演（零写入）。落盘加 --apply。")
        return 0
    if not new:
        print("\n无新事件 ⇒ **零写入**（台账逐字节不变）。")
        return 0
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a", encoding="utf-8") as f:         # append-only
        for e in new:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    after, _ = load_ledger(ledger)
    print("\n✅ 已追加 %d 条到 %s（原 %d → 现 %d）" % (len(new), ledger, len(existing), len(after)))
    return 0


# ══════════════════════════════════════════════════════════════════
def selftest() -> int:
    """反向对照：把每条判据的缺陷**真造一遍**，尺子必须精确变红。"""
    ok = fail = 0

    def chk(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1; print("  ✅ %s" % name)
        else:
            fail += 1; print("  ❌ %s  ← 判据没生效" % name)

    print("① 归一化：不许猜")
    chk("①a 'BLOCK' → BLOCK", norm_state("BLOCK") == "BLOCK")
    chk("①b '拿不准，因为素材不全' → NEEDS_INPUT", norm_state("拿不准，因为素材不全") == "NEEDS_INPUT")
    chk("①c 空串 → None（不猜）", norm_state("") is None)
    chk("①d '大概可以吧' → None（**认不出就不认**）", norm_state("大概可以吧") is None)

    print("② target_layer 映射")
    chk("②a 机PASS/人BLOCK → L1-L2（漏放⇒缺负样本）", default_target_layer("PASS", "BLOCK")[0] == "L1-L2")
    chk("②b 机BLOCK/人PASS → L3（误报⇒规则过严）", default_target_layer("BLOCK", "PASS")[0] == "L3")
    chk("②c 机NEEDS_INPUT/人REVIEW → L3", default_target_layer("NEEDS_INPUT", "REVIEW")[0] == "L3")

    print("③ 红线：构造题 ⇒ count_only")
    chk("③a 我构造 ⇒ count_only", classify("我构造", "张三")[0] == "count_only")
    chk("③b 真实投放 + 有复核人 ⇒ weight_eligible", classify("真实投放", "张三")[0] == "weight_eligible")
    chk("③c 真实投放 + 复核人空 ⇒ count_only（追不到人）", classify("真实投放", "")[0] == "count_only")
    try:
        classify("随便写的", "张三"); chk("③d 非法 source 必须抛", False)
    except ValueError:
        chk("③d 非法 source 必须抛", True)

    print("④ 端到端 ingest（真造缺陷）")
    with tempfile.TemporaryDirectory() as td:
        kb = Path(td); (kb / "l7/registry").mkdir(parents=True); (kb / "l7/reports").mkdir(parents=True)
        led = kb / "l7/registry/return-flow.ndjson"; led.write_text("", encoding="utf-8")
        (kb / "l7/registry/return-flow.yaml").write_text("id: return-flow\n", encoding="utf-8")
        # 对照样本 0 ⇒ wired_no_input
        p = status_payload(kb)
        chk("④a 台账在、无人判 ⇒ wired_no_input（**不是 measured:0**）", p["state"] == "wired_no_input")
        chk("④b 它报的 audit_status 仍是 no_data", p["audit_status"] == "no_data")

        csvp = kb / "l7/reports/audit-sample-ALL.csv"
        with open(csvp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["序号", "机器结论", "人判", "人判理由", "复核人"])
            w.writerow(["1", "PASS", "PASS", "", "张三"])            # 一致 ⇒ 不落
            w.writerow(["2", "PASS", "BLOCK", "漏放", "张三"])        # 漏放 ⇒ 落，L1-L2
            w.writerow(["3", "BLOCK", "PASS", "误报", "李四"])        # 误报 ⇒ 落，L3
            w.writerow(["4", "REVIEW", "NEEDS_INPUT", "判不了", "王五"])  # 人判判不了 ⇒ 不落
            w.writerow(["5", "", "", "", ""])                        # 没机器结论 ⇒ 不落
        n0 = led.stat().st_size
        rc = cmd_ingest(kb, csvp, "历史打回", None, False, led)
        chk("④c 预演不落盘", rc == 0 and led.stat().st_size == n0)
        cmd_ingest(kb, csvp, "历史打回", None, True, led)
        evs, badl = load_ledger(led)
        chk("④d 只落 2 条（一致/人判NEEDS_INPUT/无机器结论 都排除）", len(evs) == 2)
        chk("④e 漏放落 L1-L2", any(e["target_layer"] == "L1-L2" for e in evs))
        chk("④f 误报落 L3", any(e["target_layer"] == "L3" for e in evs))
        chk("④g 事件带 machine/human 两态", all(e.get("machine_state") and e.get("human_state") for e in evs))
        before = led.read_text(encoding="utf-8")
        cmd_ingest(kb, csvp, "历史打回", None, True, led)
        chk("④h 幂等：重跑追加 0 行（台账逐字节不变）", led.read_text(encoding="utf-8") == before)
        # 有人判过 ⇒ measured
        p2 = status_payload(kb)
        chk("④i 有人判过 ⇒ measured，数量=2", p2["state"] == "measured" and p2["value"] == 2)
        chk("④j 按层分组", p2["by_target_layer"] == {"L1-L2": 1, "L3": 1})
        # 坏行不许静默
        with open(led, "a", encoding="utf-8") as f:
            f.write("{不是json\n")
        evs2, badl2 = load_ledger(led)
        chk("④k 坏行被报出来（不静默吞）", len(badl2) == 1 and len(evs2) == 2)
        # 缺列 ⇒ 拒收
        bad = kb / "l7/reports/bad.csv"
        with open(bad, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(["序号", "备注"]); csv.writer(f).writerow(["1", "x"])
        chk("④l 缺「机器结论」列 ⇒ 拒收 exit 3", cmd_ingest(kb, bad, "我构造", None, True, led) == 3)
        # 构造题 ⇒ count_only
        csv2 = kb / "l7/reports/g.csv"
        with open(csv2, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f); w.writerow(["题号", "机器结论", "我的判断", "理由"])
            w.writerow(["GT-001", "PASS", "BLOCK", "漏放"])
        cmd_ingest(kb, csv2, "我构造", "张三", True, led)
        evs3, _ = load_ledger(led)
        last = [e for e in evs3 if e.get("item_id") == "GT-001"][0]
        chk("④m 构造题落台账但 applies_to=count_only", last["applies_to"] == "count_only")
        # 文件不在 ⇒ not_wired
        (kb / "l7/registry/return-flow.yaml").unlink()
        chk("④n 口径件不在 ⇒ not_wired", status_payload(kb)["state"] == "not_wired")

    print("\n%s  %d 过 / %d 败" % ("✅ 全过" if fail == 0 else "❌ 有败", ok, fail))
    return 0 if fail == 0 else 3


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库回流台账（口径真源 kb/l7/registry/return-flow.yaml）")
    ap.add_argument("cmd", nargs="?", default="status", choices=["status", "ingest"])
    ap.add_argument("--csv")
    ap.add_argument("--source", default="真实投放", choices=list(SOURCES))
    ap.add_argument("--reviewer", default=None)
    ap.add_argument("--kb", default=str(KB))
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    kb = Path(a.kb)
    if a.cmd == "status":
        return cmd_status(kb, a.as_json)
    if not a.csv:
        print("ingest 需要 --csv <path>")
        return 2
    led = Path(a.ledger) if a.ledger else kb / "l7/registry/return-flow.ndjson"
    return cmd_ingest(kb, Path(a.csv), a.source, a.reviewer, a.apply, led)


if __name__ == "__main__":
    sys.exit(main())
