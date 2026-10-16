#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_run_count.py —— 「累计评审单数」的**可复算口径**（只读，不写任何东西）。

════════════════════════════════════════════════════════════════════════
★ 为什么需要它（2026-10-12）
════════════════════════════════════════════════════════════════════════
xlsx 的 G 列与多份交付件里写着「**文字链路跑通 · 累计评审单数 562 / 580**」，
来源逐字是 `.work/task_xlsx_g_values*.py`：

    「评审 run 累计 **562 条**（`kb/l7/runs/index.jsonl` 的 `source=review_machine`）」

也就是**数行数**。而那份台账：

  · 引擎**每跑一单**都 `run_record.record(source="review_machine")`（`with_kb_evidence.py`）；
  · **回归跑批**（`kb/l8/regression_run.py`）一次 subprocess 跑 **100 单**
    ⇒ 跑一次回归就往台账灌 **100 行**；
  · 2026-10-12 实测：`review_machine` **1102 行**，其中 **316 行**的 `trigger`
    与 `regression-set.yaml` 的素材**逐字相同**（**今天 268 行**）——
    那些**不是新的评审单**，是**同一条素材被重跑**。

⇒ **「累计单数」被测量行为本身抬高了。** 本件把口径落成可复算的读数：
  · **原始行数**（会被重跑与回归跑批抬高，**不该单独引用**）；
  · **按素材去重的单数**（同一 `trigger` 只算一单）—— 这才是「受理过多少条**不同**素材」；
  · 以及**重跑行数**（= 原始 − 去重），并拆出「其中来自回归集素材的」。

★ 边界：本件**只读**，**不回洗** `index.jsonl`（它是"发生过什么"的审计台账，
  抹掉重跑记录等于抹掉证据）。可复算的读数才是要交的东西。
★ 相关的写入侧隔离：`kb/l7/scripts/run_record.py::record()` 的 `KB_RUN_RECORD_SKIP`
  ＋ `regression_run.py` 默认开启它 ⇒ **今后的回归跑批不再进台账**。
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
ROOT = KB.parent
INDEX = KB / "l7" / "runs" / "index.jsonl"
SET = KB / "l7" / "registry" / "regression-set.yaml"


def regression_texts(set_path: Path = SET) -> set:
    """回归集的 100 条素材（`trigger` 是 `text[:60]`，同一构造 ⇒ 同口径）。"""
    try:
        import yaml
        d = yaml.safe_load(Path(set_path).read_text(encoding="utf-8")) or {}
    except Exception:                                          # noqa: BLE001
        return set()
    out = set()
    for layer in ("solid", "fragile"):
        for c in (d.get(layer) or []):
            t = c.get("text")
            if t:
                out.add(t[:60])
    return out


def summarise(rows, reg_texts) -> dict:
    """纯函数：给 run 记录行 ⇒ 读数。**不读盘**（自证靠它喂样本）。"""
    rm = [r for r in rows if r.get("source") == "review_machine"]
    by_key = collections.defaultdict(list)
    for r in rm:
        by_key[str(r.get("trigger") or "")].append(r)
    dup_rows = len(rm) - len(by_key)
    reg_keys = {k for k in by_key if k in reg_texts}
    reg_rows = sum(len(v) for k, v in by_key.items() if k in reg_keys)
    per_day = collections.Counter(str(r.get("at") or "")[:10] for r in rm)
    per_day_uniq = collections.Counter(
        str(v[0].get("at") or "")[:10] for v in by_key.values())
    return {
        "raw_rows": len(rm),
        "distinct_materials": len(by_key),
        "rerun_rows": dup_rows,
        "regression_material_rows": reg_rows,
        "regression_distinct_materials": len(reg_keys),
        "max_group": max((len(v) for v in by_key.values()), default=0),
        "per_day_raw": dict(sorted(per_day.items())),
        "per_day_distinct": dict(sorted(per_day_uniq.items())),
        # ── ★ 2026-10-12：素材 ID 覆盖率（**只报，不参与去重**）──────────────────
        #   为什么单列而**不拿去当去重键**（关键，别误用）：
        #     `content_id` 是**送审号**（`AD-YYYYMMDD-NNN`，一次送审一个），**不是素材身份** ——
        #     同一段文案明天再送审 ⇒ 新号 ⇒ 按它去重会**把一条素材算成两条**（正好反了）。
        #     而本件的口径要的是「受理过多少条**不同**素材」⇒ 仍按 `trigger`（text[:60]）去重。
        #   ⇒ 它补的是**回指**：让台账行能对上业务行（结论去向表的「内容 ID」），
        #     这是 `audit_metrics.mjs` 里 `coverage_rate` 的前置②（逐字：「送审侧每条素材带唯一素材 ID」）。
        "rows_with_content_id": sum(1 for r in rm if str(r.get("content_id") or "").strip()),
    }


def selftest() -> int:
    ok = True

    def chk(name, cond, extra=""):
        nonlocal ok
        print(("  ✅ " if cond else "  ❌ ") + name + (("  " + extra) if extra and not cond else ""))
        ok = ok and bool(cond)

    print("review_run_count 自证（口径判据的反向对照）")
    rows = [
        {"source": "review_machine", "trigger": "A", "at": "2026-10-12T09:00:00"},
        {"source": "review_machine", "trigger": "A", "at": "2026-10-12T10:00:00"},
        {"source": "review_machine", "trigger": "A", "at": "2026-10-12T11:00:00"},
        {"source": "review_machine", "trigger": "B", "at": "2026-10-11T09:00:00"},
        {"source": "daily_health", "trigger": "x", "at": "2026-10-12T09:00:00"},
    ]
    s = summarise(rows, reg_texts={"A"})
    chk("① 原始行数**只数 review_machine**（别的 source 不许混进来）", s["raw_rows"] == 4,
        str(s["raw_rows"]))
    chk("② 按素材去重：A×3 + B ⇒ **2 条不同素材**", s["distinct_materials"] == 2)
    chk("③ 重跑行数 = 原始 − 去重（且**不是**把它当新单）", s["rerun_rows"] == 2)
    chk("④ 回归集素材那部分单独计（A 的 3 行全算重跑）",
        s["regression_material_rows"] == 3 and s["regression_distinct_materials"] == 1)
    chk("⑤ 单素材最大重复组可见（不许只给一个总数）", s["max_group"] == 3)
    # 反向对照：把「按天去重」也钉一下（同一天 A×3 ⇒ 1）
    chk("⑥ 按天去重与总量去重**不是**一个数（不许混用）",
        s["per_day_distinct"].get("2026-10-12") == 1 and s["distinct_materials"] == 2)
    chk("⑦ 反向对照：没有 review_machine 行 ⇒ 全 0，不崩",
        summarise([], set())["raw_rows"] == 0)
    # ── 素材 ID（`content_id`）：只报，**不许当去重键**（2026-10-12 加）──────────
    chk("⑧ 带 content_id 的行数单列出来（只报数）",
        summarise([{"source": "review_machine", "trigger": "A", "content_id": "AD-20261012-001"},
                   {"source": "review_machine", "trigger": "B"}], set())["rows_with_content_id"] == 1)
    # ★ 反向对照：**同一 trigger、不同 content_id** ⇒ 必须仍算 **1 条素材**。
    #   若有人把去重键换成 content_id，这里会变 2 ⇒ 精确变红。
    chk("⑨ 反向对照：同一素材两次送审（trigger 同、content_id 不同）**只算 1 条素材**",
        summarise([{"source": "review_machine", "trigger": "同一段文案", "content_id": "AD-20261012-001"},
                   {"source": "review_machine", "trigger": "同一段文案", "content_id": "AD-20261013-007"}],
                  set())["distinct_materials"] == 1)
    print("结论：%s" % ("✅ 判据有反向对照" if ok else "❌ 有反向对照没红"))
    return 0 if ok else 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    rows = [json.loads(l) for l in INDEX.read_text(encoding="utf-8").splitlines() if l.strip()]
    s = summarise(rows, regression_texts())
    s["index"] = str(INDEX)
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    print("「累计评审单数」可复算读数 ｜ 源：%s" % INDEX)
    print("  · 原始行数（`source=review_machine`）        ：**%d**  ← 会被重跑与回归跑批抬高"
          % s["raw_rows"])
    print("  · **按素材去重的单数**（同一 trigger 算一单）：**%d**  ← 该引用的是这个"
          % s["distinct_materials"])
    print("  · 重跑行数（原始 − 去重）                  ：%d" % s["rerun_rows"])
    print("      其中来自**回归集素材**的行             ：%d（涉及 %d 条不同素材）"
          % (s["regression_material_rows"], s["regression_distinct_materials"]))
    print("  · 单条素材最大重复次数                      ：%d" % s["max_group"])
    print("  · 带素材 ID（`content_id`）的行             ：%d / %d  ← 送审号，**只用于回指业务行，"
          "不用于去重**" % (s["rows_with_content_id"], s["raw_rows"]))
    print("  · 按天（原始 / 去重）：")
    for d in sorted(s["per_day_raw"], reverse=True)[:8]:
        print("      %s  %4d / %4d" % (d, s["per_day_raw"][d], s["per_day_distinct"].get(d, 0)))
    print("\n★ 口径：**引用「累计单数」一律用「按素材去重的单数」**；"
          "原始行数量的是「跑过多少次」，不是「受理过多少条」。")
    print("★ 本件只读，**不回洗** index.jsonl（审计台账抹重跑 = 抹证据）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
