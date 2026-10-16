#!/usr/bin/env python3
"""② C3 复算：这两条素材，题材闸门到底挡掉了哪些案例条款。

## 为什么要复算而不是读报告

报告只写「结论」与「问题清单」；`trace`（含 `coverage.case_theme_rejected`）**没进
`kb/l7/reports/<run>.json`**，而 `.md` 那侧也不是 `review.py` 的渲染器写的 ⇒
**「挡掉了什么」在产物里看不见**。
⇒ 这里用**引擎自己的零件**（同一份 `case_theme.py`、同一个 L6 BM25、
同一套 `load_case_clauses` 口径）把答案复算出来，**口径写在代码里，可复核**。

用法：`python3 采集-20261013/recheck_gate.py`
"""
import glob
import importlib.util
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    canon = os.path.join(ROOT, "kb/l4/canonical/sample_case.jsonl")
    rows = [json.loads(l) for l in open(canon, encoding="utf-8") if l.strip()]
    # 与 review.py::load_case_clauses 同口径（四个条件，见该函数）
    pool = [d for d in rows
            if d.get("polarity") == "反例"
            and (d.get("reason_category") or "").strip().lower() not in ("", "unknown")
            and d.get("anchor")
            and str(d.get("status") or "").lower() != "superseded"]
    case_anchors = {d["anchor"] for d in pool}
    by_anchor = {d["anchor"]: d for d in pool}
    print(f"依据池 {len(pool)} 条（superseded 已排除）")

    ct = load("kb/l7/review-engine/core/case_theme.py", "ct")
    l6 = load("kb/l6/retriever.py", "l6")
    bm = l6.BM25()
    print(f"L6 索引 {len(bm.docs)} 个单元")
    print()

    cutoff = time.mktime(time.strptime("2026-10-14 15:30", "%Y-%m-%d %H:%M"))
    files = sorted(f for f in glob.glob(os.path.join(ROOT, "kb/l7/reports/2026101*-*.json"))
                   if os.path.getmtime(f) > cutoff)
    print(f"本轮新报告 {len(files)} 份\n")

    tot_case = tot_rej = 0
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        txt = (d.get("input_manifest") or {}).get("text") or ""
        if not txt:
            continue
        seen = set()
        for _name, lst in bm.search(txt).items():
            for did, _sc, _r in lst[:5]:
                doc = bm.docs[did]
                if doc["anchor"] in case_anchors:
                    seen.add(doc["anchor"])
        ok, rej = [], []
        for a in seen:
            g, why = ct.case_thematic_ok(by_anchor[a], txt)
            (ok if g else rej).append((by_anchor[a].get("article_no"), why))
        cid = (d.get("content_id") or "")[:24]
        print(f"{os.path.basename(f)}  三态={str(d.get('decision')):<12} cid={cid}")
        print(f"    案例命中 {len(seen)} ｜ 放行 {len(ok)} ｜ **挡掉 {len(rej)}**")
        for a, w in rej[:4]:
            print(f"      ✗ {a} ｜ {w}")
        for a, w in ok[:4]:
            print(f"      ✓ {a} ｜ {w}")
        tot_case += len(seen)
        tot_rej += len(rej)
    print()
    print(f"★ 合计：案例命中 {tot_case} ｜ 题材闸门挡掉 {tot_rej}")
    print("★ 边界：这是**复算**，用的是引擎自己的零件；它证明「按现口径闸门会挡什么」，"
          "不证明「引擎当时确实走了这条分支」—— 后者要 trace 进报告才看得见，见交付件「缺口」一节。")


if __name__ == "__main__":
    sys.exit(main())
