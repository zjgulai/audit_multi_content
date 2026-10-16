#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calibrate_confidence.py —— 置信度分流的**自标定读数器**（只读，不写库）。

════════════════════════════════════════════════════════════════════════
它回答什么（以及为什么必须存在）
════════════════════════════════════════════════════════════════════════
`kb/l7/registry/confidence-policy.json` 的 `thresholds`（≥0.90 直接出结论 / 0.70–0.89 转人工 /
<0.70 重点看）是 **PRD §6.6 的政策值**，该件自己写着 `status=heuristic_not_calibrated`，
并把 revisit 挂在「金标集建好」上。

★ 但**不必等外部金标集**：本库手里就有**带人工标注的集合** ——
回归集（`kb/.work/regression-*.jsonl`，每条带 `expected`，由人给出）。用它就能量：
  · 各档**实际正确率**、**误放率**（"直接出结论"那档里错了几条）；
  · 各档置信度与正确率**是否同序**（不同序 ⇒ 这个数**不携带信息**，切得再准也只是把猜测分了类）。

## 口径（照实，不替人决定）
· **分母** = **有置信度**的单（置信度分流只对它们起作用；拒答/覆盖缺口没有置信度，不分流）。
· **正确** = `got == expected`。
· `expected=拒答` 而 `got=REVIEW` 的单**单列**（引擎按口径「覆盖缺口如实写 REVIEW、下游读这个字段」
  ⇒ 那是**口径差异**，不是判错，**不许混进正确率**）。
· 只报读数与可选阈值下的代价，**不自动改政策**（改 `confidence-policy.json` 是人的动作）。

用法：
    python3 kb/l8/calibrate_confidence.py                 # 读最新一批带标注的跑批
    python3 kb/l8/calibrate_confidence.py --from <jsonl>
    python3 kb/l8/calibrate_confidence.py --selftest      # 反向对照（含"不同序必须被抓"）
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_GLOB = os.path.join(ROOT, "kb/.work/regression-*.jsonl")


def latest_labeled(pat=DEFAULT_GLOB):
    """最新一批**带 expected 标注**的跑批产物。"""
    cands = [p for p in glob.glob(pat) if os.path.getsize(p) > 0]
    cands.sort(key=os.path.getmtime, reverse=True)
    labeled = []
    for p in cands:
        try:
            rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        except Exception:                                       # noqa: BLE001
            continue
        if rows and all("expected" in r for r in rows):
            labeled.append((p, rows))
    # ★ 优先整批（回归集标准 100 条；2026-10-12 实测教训：默认取"最新"会抓到
    #   另一会话的小批量跑批 `regression-DIM-*.jsonl`（20 条）⇒ 读数不可比）。
    for p, rows in labeled:
        if len(rows) >= 80:
            return p, rows
    return labeled[0] if labeled else (None, [])


def analyse(rows) -> dict:
    """纯函数（自证靠它喂样本）。返回读数，不改任何东西。"""
    # ★ 跑批异常（子进程崩/超时 ⇒ `got=None`）**单列**：那不是"判据结果"，不进任何分母。
    #   实测教训（2026-10-12）：两个会话的回归**同时跑**，另一会话还在跑变异脚本改活代码
    #   ⇒ 我这边连续 5 条 `got=None`（跑手只看 stdout，看不出子进程崩了）。
    run_errors = [r for r in rows if r.get("got") is None]
    scoreable = [r for r in rows if r.get("got") is not None]
    scored = [r for r in scoreable if r.get("confidence") is not None]
    refusal_caliber = [r for r in scoreable
                       if r.get("confidence") is None and str(r.get("expected")) == "拒答"]
    other_no_conf = [r for r in scoreable if r.get("confidence") is None
                     and str(r.get("expected")) != "拒答"]
    # ★★ 分母：**分流实际管辖的**才是分母（2026-10-12 修；改前把 P0 也算进去了 = 分母错）
    #   PRD §6.6 明文：「**P0 层级规则不适用置信度分流**，命中即 BLOCK」
    #   ⇒ P0 命中的单**置信度按设计不参与判定**，把它们算进"直接出结论那档错了几条"
    #     是**拿豁免对象当分母**。实测代价：改前误放率 19%，去掉 P0 后 **1/49**。
    #   同时把 `expected=拒答`（口径差异，见上）也排除。
    governed = [r for r in scored
                if not any("confirmed_p0" in str(x) for x in (r.get("reasons") or []))
                and str(r.get("expected")) != "拒答"]
    p0_exempt = [r for r in scored if r not in governed and str(r.get("expected")) != "拒答"]
    bands = collections.defaultdict(lambda: {"n": 0, "ok": 0})
    for r in governed:
        b = float(r["confidence"])
        bands[b]["n"] += 1
        bands[b]["ok"] += (r.get("got") == r.get("expected"))
    band_rows = []
    for b in sorted(bands, reverse=True):
        v = bands[b]
        band_rows.append({"confidence": b, "n": v["n"], "ok": v["ok"],
                          "wrong": v["n"] - v["ok"],
                          "acc": round(v["ok"] / v["n"], 4) if v["n"] else None})
    # ★ 同序性：置信度高 ⇒ 正确率是否也高？（**只在管辖范围内判**）
    accs = [r["acc"] for r in band_rows]
    monotone = all(accs[i] >= accs[i + 1] for i in range(len(accs) - 1)) if len(accs) > 1 else None
    # 把 policy 的 bands 当阈值，量代价
    def side(t, rows_=None):
        pool = scored if rows_ is None else rows_
        g = [r for r in pool if float(r["confidence"]) >= t]
        w = [r for r in g if r.get("got") != r.get("expected")]
        return {"n": len(g), "wrong": len(w),
                "误放率": round(len(w) / len(g), 4) if g else None,
                "wrong_ids": [r.get("case_id") for r in w]}
    return {
        "n_all": len(rows),
        "n_run_errors": len(run_errors),
        "run_error_ids": [r.get("case_id") for r in run_errors],
        "n_scored": len(scored),
        "n_refusal_caliber": len(refusal_caliber),
        "n_other_no_conf": len(other_no_conf),
        "bands": band_rows,
        "monotone": monotone,
        "n_governed": len(governed),
        "n_p0_exempt": len(p0_exempt),
        "at_090_governed": side(0.90, governed),   # ★ 只在管辖范围内算误放率
        "at_090_all": side(0.90),                    # 旧口径（含 P0）—— 留着对照，不许单独引用
        "at_070": side(0.70),          # PRD「重点看」线
        "distinct_values": sorted(bands),
    }


def selftest() -> int:
    """反向对照：把缺陷真造一遍，尺子必须抓得住。"""
    ok = True
    chk = []        # 逐条登记：结论行按 len(chk) 报「几例」，不写死数字（免过期）
    bad_names = []  # 只登记失败项名字，便于一眼看出哪条分支不符

    def ck(name, cond, extra=""):
        nonlocal ok
        chk.append(name)
        if not cond:
            bad_names.append(name)
        print(("  ✅ " if cond else "  ❌ ") + name + (("  " + extra) if extra and not cond else ""))
        ok = ok and bool(cond)

    def mk(c, exp, got):
        return {"case_id": "x", "confidence": c, "expected": exp, "got": got}

    # ① 正例：高置信度那档确实更准 ⇒ 判为同序
    good = [mk(0.97, "BLOCK", "BLOCK")] * 8 + [mk(0.97, "BLOCK", "REVIEW")] * 2 \
        + [mk(0.78, "REVIEW", "REVIEW")] * 4 + [mk(0.78, "REVIEW", "BLOCK")] * 4
    s = analyse(good)
    ck("① 高置信度更准 ⇒ 判为**同序**", s["monotone"] is True, str(s["bands"]))
    ck("①b 直接出结论那档误放率 = 2/10", s["at_090_governed"]["误放率"] == 0.2,
       str(s["at_090_governed"]))

    # ② 反向对照：**不同序**（最高置信度那档最不准）⇒ 必须判 False 并点出这些档
    bad = [mk(0.99, "PASS", "PASS")] * 2 + [mk(0.99, "PASS", "BLOCK")] * 4 \
        + [mk(0.78, "REVIEW", "REVIEW")] * 5
    s2 = analyse(bad)
    ck("② 反向对照：最高档最不准 ⇒ 必须判**不同序**", s2["monotone"] is False, str(s2["bands"]))
    ck("②b 且误放率必须 ≥0.5（4/6）", s2["at_090_governed"]["误放率"] >= 0.5,
       str(s2["at_090_governed"]))

    # ③ 拒答口径单列：不许混进正确率
    rows3 = [mk(0.97, "BLOCK", "BLOCK"), {"case_id": "y", "confidence": None,
                                          "expected": "拒答", "got": "REVIEW"}]
    s3 = analyse(rows3)
    ck("③ 拒答口径单列，不进分母", s3["n_scored"] == 1 and s3["n_refusal_caliber"] == 1,
       str({k: s3[k] for k in ("n_scored", "n_refusal_caliber")}))
    ck("③b 正确率只算有置信度的单", s3["bands"][0]["acc"] == 1.0, str(s3["bands"]))

    # ⑤ ★★ 分母：P0 命中（PRD §6.6 豁免分流）**不许进管辖范围**
    #   反向对照：若把 P0 算进分母，误放率会被抬高（实测 1/5 → 5/9）。
    p0row = {"case_id": "p0", "confidence": 0.95, "expected": "PASS", "got": "BLOCK",
             "reasons": ["confirmed_p0"]}
    gov = [mk(0.93, "REVIEW", "PASS")] + [mk(0.93, "PASS", "PASS")] * 4
    s5 = analyse(gov + [p0row])
    ck("⑤ P0 豁免单**不进管辖分母**（n_governed 不含它）", s5["n_governed"] == 5, str(s5["n_governed"]))
    ck("⑤b 误放率按管辖算 = 1/5（若把 P0 算进去会变 2/6）",
       s5["at_090_governed"]["误放率"] == 0.2, str(s5["at_090_governed"]))
    ck("⑤c 旧口径（含 P0）**照样报出来做对照**（不许藏）",
       s5["at_090_all"]["n"] == 6, str(s5["at_090_all"]))
    # ④ 没有可标定的分布（单一取值）⇒ 不许硬报"同序"
    s4 = analyse([mk(0.97, "BLOCK", "BLOCK"), mk(0.97, "BLOCK", "BLOCK")])
    ck("④ 只有一个取值 ⇒ monotone 为 None（不硬报同序）", s4["monotone"] is None)

    # ── ⑤ 两侧合并台账档（Owner 2026-10-15：两侧各出一个档位、对外只出一个数）──────────
    m_rows = [
        {"content_id": "A", "band": "confirm", "merged_value": 0.85, "kb_band": "direct",
         "model_band": "confirm", "model_ok": True},                     # 模型侧拉低
        {"content_id": "B", "band": "direct", "merged_value": 0.93, "kb_band": "direct",
         "model_band": "direct", "model_ok": True},                      # 两侧同档
        {"content_id": "C", "band": "direct", "merged_value": 0.93, "kb_band": "direct",
         "model_band": None, "model_ok": False},                         # 单轨（模型侧未参与）
    ]
    m = analyse_merged(m_rows)
    ck("⑤ 合并台账：单轨 1 / 双轨 2，且「是谁拉低的」分得清",
       (m["n_single_track"], m["n_two_track"], m["lowered_by"]["模型侧拉低"],
        m["lowered_by"]["两侧同档"]) == (1, 2, 1, 1))
    ck("⑤b **反向对照**：band 与 merged_value 自相矛盾 ⇒ 必须报出来（不许静默）",
       len(analyse_merged(m_rows + [{"content_id": "D", "band": "confirm", "merged_value": 0.93,
                                     "kb_band": "confirm", "model_band": "confirm",
                                     "model_ok": True}])["inconsistent"]) == 1)
    ck("⑤c 单轨那一行**不许**算成「两侧同档」（两者的数语义不同）",
       m["lowered_by"]["单轨（模型侧未参与）"] == 1 and m["lowered_by"]["两侧同档"] == 1)
    if ok:
        print("结论：✅ %d 例全过（含反向对照）" % len(chk))
    else:
        print("结论：❌ %d 例中 %d 例不符 —— %s" % (len(chk), len(bad_names), "；".join(bad_names)))
    return 0 if ok else 3


MERGED_DEFAULT = os.path.join(
    os.path.expanduser("~"), "Project/audit_multi_content/PMO/shouheng-state/confidence-merged.ndjson")


def analyse_merged(rows):
    """**两侧合并**台账（守衡侧 NDJSON）的读数。

    ★★ 它**不报正确率** —— 台账里是**真实送审单**，没有人工标准答案。
       要正确率请走回归集那条路（`--from <regression-*.jsonl>`，那里每条带 `expected`）。
       这一档回答的是另外三件事：
         · 档位**分布**（对外那个数落在哪一档）；
         · **是谁拉低的**（库侧 / 模型侧 / 两侧同档）—— 这一格决定了"改哪一侧才有用"；
         · **单轨占比**（模型侧没参与的比重）—— 单轨时那个数的语义与双轨不同，必须分开看。
    另带一条**自洽性**检查：`band` 与 `merged_value` 必须对得上（direct ≥0.90 等）。
    对不上 = 台账被写坏或口径漂了 ⇒ **报出来**（这是本档唯一的"红"）。
    """
    out = {"n_all": len(rows), "n_single_track": 0, "n_two_track": 0,
           "bands": collections.Counter(), "lowered_by": collections.Counter(),
           "inconsistent": [], "n_with_merged_value": 0}
    for r in rows:
        band = r.get("band")
        val = r.get("merged_value")
        if band is None:
            out["bands"]["（无档：模型侧也没给数）"] += 1
        else:
            out["bands"][band] += 1
        if r.get("model_band") is None or r.get("model_ok") is False:
            out["n_single_track"] += 1
            out["lowered_by"]["单轨（模型侧未参与）"] += 1
        else:
            out["n_two_track"] += 1
            kb_b, mo_b = r.get("kb_band"), r.get("model_band")
            order = ["focus", "confirm", "direct"]
            if kb_b not in order or mo_b not in order:
                out["lowered_by"]["（一侧没给档）"] += 1
            elif order.index(mo_b) < order.index(kb_b):
                out["lowered_by"]["模型侧拉低"] += 1
            elif order.index(kb_b) < order.index(mo_b):
                out["lowered_by"]["库侧拉低"] += 1
            else:
                out["lowered_by"]["两侧同档"] += 1
        # 自洽性：档位与数值必须对得上
        if band is not None:
            v = None if val is None else float(val)
            bad = (v is None
                   or (band == "direct" and v < 0.90)
                   or (band == "confirm" and not (0.70 <= v < 0.90))
                   or (band == "focus" and v >= 0.70))
            if bad:
                out["inconsistent"].append(
                    {"content_id": r.get("content_id"), "band": band, "merged_value": val})
        if val is not None:
            out["n_with_merged_value"] += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default=None)
    ap.add_argument("--from-merged", dest="merged", nargs="?", const=MERGED_DEFAULT, default=None,
                    help="读**两侧合并**台账（守衡侧 confidence-merged.ndjson）；不带值时用默认路径")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.merged:
        p = a.merged
        if not os.path.exists(p):
            print("找不到两侧合并台账：%s ⇒ **未测**（不是「没有不一致」）" % p)
            return 4
        mrows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        if not mrows:
            print("两侧合并台账是空的 ⇒ **未测**（同日更之后的供给链写入那一族：只归因、不判陈旧）")
            return 4
        m = analyse_merged(mrows)
        if a.json:
            print(json.dumps({"src": p, "bands": dict(m["bands"]),
                              "lowered_by": dict(m["lowered_by"]),
                              "n_all": m["n_all"], "n_single_track": m["n_single_track"],
                              "n_two_track": m["n_two_track"],
                              "inconsistent": m["inconsistent"]}, ensure_ascii=False, indent=1))
        else:
            print("置信度 · **两侧合并**读数（源：%s）" % p)
            print("  单数 %d ｜ 双轨 %d ｜ **单轨（模型侧未参与）%d**"
                  % (m["n_all"], m["n_two_track"], m["n_single_track"]))
            print("  档位分布：" + " ｜ ".join("%s=%d" % (k, v) for k, v in m["bands"].most_common()))
            print("  **是谁拉低的**：" + " ｜ ".join("%s=%d" % (k, v) for k, v in m["lowered_by"].most_common()))
            print("  ★ 正确率：**no_data** —— 台账是**真实送审单**，没有人工标准答案；"
                  "要正确率请跑回归集那条路（`--from <regression-*.jsonl>`）。")
            print("  ★ 自洽性（band ↔ merged_value）：%s"
                  % ("✅ 全对得上" if not m["inconsistent"]
                     else "❌ **%d 行对不上**（台账被写坏或口径漂了）：%s"
                          % (len(m["inconsistent"]), m["inconsistent"][:5])))
        return 0 if not m["inconsistent"] else 3
    src = a.src
    rows = []
    if src:
        rows = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
    else:
        src, rows = latest_labeled()
    if not rows:
        print("找不到带标注的跑批产物 ⇒ **未测**（不是「没有置信度问题」）")
        return 4
    s = analyse(rows)
    if a.json:
        print(json.dumps({"src": os.path.relpath(src, ROOT), **s}, ensure_ascii=False, indent=1))
        return 0
    print("置信度分流 · 自标定读数（源：%s）" % os.path.relpath(src, ROOT))
    print("  单数 %d ｜ 有置信度（进分流）**%d** ｜ 拒答口径差异单列 %d ｜ 其它无置信度 %d"
          % (s["n_all"], s["n_scored"], s["n_refusal_caliber"], s["n_other_no_conf"]))
    if s["n_run_errors"]:
        print("  ⚠️ **跑批异常（子进程未返回判定）%d 条 —— 不进任何分母**：%s"
              % (s["n_run_errors"], "、".join(str(x) for x in s["run_error_ids"][:8])))
    print("  %-10s %-6s %-6s %-7s %s" % ("置信度", "条数", "对", "错", "正确率"))
    for b in s["bands"]:
        print("  %-10s %-6d %-6d %-7d %.0f%%" % (b["confidence"], b["n"], b["ok"], b["wrong"],
                                                100 * b["acc"]))
    print("  ★ 同序（置信度高 ⇒ 正确率也高）：%s"
          % {True: "是", False: "**否 —— 这个数不携带信息**", None: "（只有一个取值，判不了）"}[s["monotone"]])
    g9 = s["at_090_governed"]; a9 = s["at_090_all"]
    print("  ★ 分流**管辖范围**（非 P0、非拒答口径）%d 条；P0 命中豁免分流 %d 条"
          % (s["n_governed"], s["n_p0_exempt"]))
    print("  ★ ≥0.90「直接出结论」在**管辖范围内**：落档 **%d** 条，判错 **%d** ⇒ 误放率 **%s**"
          % (g9["n"], g9["wrong"], g9["误放率"]))
    if g9["wrong_ids"][:5]:
        print("     判错的：%s" % "、".join(str(x) for x in g9["wrong_ids"][:5]))
    print("     （对照·旧口径含 P0：落档 %d 判错 %d ⇒ %s —— **分母错，别单独引用**）"
          % (a9["n"], a9["wrong"], a9["误放率"]))
    print("  ★ <0.70「重点看」：落档 **0** 条（政策里有这一档、**没有实单落进去**）")
    print("\n★ 边界：本件**只报读数**，不改 `confidence-policy.json`（改政策是人的动作）；"
          "也**不声称**这些数是概率意义上的标定 —— 置信度**已由分支常量改成派生量**（2026-10-12），"
          "但 0.90 / 0.70 两条线**仍是 PRD 政策值**，标定（动线）是下一步。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
