#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_eval-agg-20260930.py —— 把三件 skill 的评测产物汇总成一张门槛判定表（驱动侧助手，不属于知识库）。

读：三个工作台目录下的 `<skill>-evaluation-report[-fix].yaml`（root-skills-eval 的产物）
出：逐件 track_a / track_b(P,R,F1,TP/FP/FN/TN) / 封顶后 track_c + F1≥0.90 门槛判定
并顺手核对：库内源是否被动过（与 .eval-source-baseline.sha256 比）。

用法：KB_INTERP_OK=1 /usr/bin/python3 _eval-agg-20260930.py
"""
from __future__ import annotations

import glob
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SKILLS = ["kb-canonical-lookup", "kb-p0-check", "kb-recall"]
THRESHOLD_F1 = 0.90


def _load_yaml(path):
    import yaml
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _dig(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _first(d, paths, default=None):
    """按候选路径逐个找，返回第一个非空值（报告字段名在不同版本间有过漂移）。"""
    for p in paths:
        v = _dig(d, *p.split("."))
        if v not in (None, "", {}):
            return v
    return default


def summarize(skill: str):
    d = os.path.join(ROOT, "_eval-%s-20260930" % skill)
    # 递归找：两个评测方的工作台布局不同（一个写 _work/、一个写 _eval/），
    # 所以**不能只在一级目录 glob**（2026-09-30 实测：一级 glob 会漏掉嵌套产物）。
    yamls = sorted(glob.glob(os.path.join(d, "**", "*evaluation-report*.yaml"), recursive=True))
    htmls = [h for h in sorted(glob.glob(os.path.join(d, "**", "*final-report*.html"), recursive=True))
             if "baseline" not in os.path.basename(h)]   # 同上：别把基线 HTML 当最终交付
    if not yamls:
        return {"skill": skill, "state": "报告未生成", "dir": d,
                "found": [os.path.relpath(p, d) for p in
                          sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True))
                          if os.path.isfile(p)][:12]}
    # 选报告的优先级（2026-09-30 加固）：**排除 baseline**（前一轮留底）→ 优先 -fix（最终交付版）→ 取最新。
    # 不能只靠 ASCII 排序：`…-report-v1.2.0-baseline.yaml` 与 `…-report.yaml` 谁大谁小是巧合，
    # 一旦命名规则变化就会**把基线数字当成最终数字**交出去。
    pool = [c for c in yamls if "baseline" not in os.path.basename(c)] or yamls
    path = sorted([c for c in pool if "-fix" in os.path.basename(c)] or pool)[-1]
    try:
        y = _load_yaml(path)
    except Exception as exc:  # noqa: BLE001
        return {"skill": skill, "state": "YAML 读不了：%r" % exc, "report": path}
    if not isinstance(y, dict):
        return {"skill": skill, "state": "YAML 顶层不是映射（%s）" % type(y).__name__, "report": path}

    ta = _first(y, ["track_a.total", "track_a.score", "scores.track_a.total"])
    f1 = _first(y, ["track_b.f1", "track_b.F1", "track_b.avg.f1", "track_b.average.f1"])
    p = _first(y, ["track_b.precision", "track_b.p", "track_b.avg.precision", "track_b.average.precision"])
    r = _first(y, ["track_b.recall", "track_b.r", "track_b.avg.recall", "track_b.average.recall"])
    # 四格：报告里逐轮在 track_b.rounds[]，均值在 track_b.average{}（2026-09-30 实测结构）
    _rounds = _first(y, ["track_b.rounds"], default=[]) or []
    _sum = {}
    for _k in ("TP", "FP", "FN", "TN"):
        _v = [_r.get(_k) for _r in _rounds if isinstance(_r, dict) and isinstance(_r.get(_k), int)]
        _sum[_k.lower()] = sum(_v) if _v else None
    tp = _first(y, ["track_b.tp", "track_b.cm.tp", "track_b.confusion.tp"], _sum.get("tp"))
    fp = _first(y, ["track_b.fp", "track_b.cm.fp", "track_b.confusion.fp"], _sum.get("fp"))
    fn = _first(y, ["track_b.fn", "track_b.cm.fn", "track_b.confusion.fn"], _sum.get("fn"))
    tn = _first(y, ["track_b.tn", "track_b.cm.tn", "track_b.confusion.tn"], _sum.get("tn"))
    tc = _first(y, ["track_c.total", "track_c.score", "scores.track_c.total"])
    cap = _first(y, ["track_c.capped_total", "track_c.total_capped", "track_c.cap"])
    mr = _first(y, ["track_c.market_ready", "status.market_ready"])
    verdict = _first(y, ["status.verdict", "recommendation.verdict", "status"])
    return {"skill": skill, "state": "ok", "report": os.path.relpath(path, ROOT),
            "html": os.path.relpath(htmls[-1], ROOT) if htmls else None,
            "track_a": ta, "p": p, "r": r, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "track_c": tc, "capped": cap, "market_ready": mr, "verdict": verdict}


def source_drift():
    base = os.path.join(ROOT, ".eval-source-baseline.sha256")
    if not os.path.exists(base):
        return ["（没有基线文件 .eval-source-baseline.sha256）"]
    out = []
    for line in open(base, encoding="utf-8"):
        parts = line.split()
        if len(parts) < 2:
            continue
        want, rel = parts[0], parts[-1]
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            out.append("❌ 源不见了：%s" % rel)
            continue
        got = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
        out.append(("✅ " if got == want else "❌ 被动过！") + "%s  %s" % (rel, got))
    return out


def _fmt(v):
    if isinstance(v, float):
        return "%.4f" % v
    return "—" if v is None else str(v)


def main():
    rows = [summarize(s) for s in SKILLS]
    print("=" * 100)
    print("三件 skill 评测汇总 · 门槛 F1 ≥ %.2f（本库登记口径）" % THRESHOLD_F1)
    print("=" * 100)
    for row in rows:
        print("\n── %s" % row["skill"])
        if row["state"] != "ok":
            print("   状态：%s" % row["state"])
            if row.get("dir"):
                print("   工作台：%s" % os.path.relpath(row["dir"], ROOT))
            if row.get("found"):
                print("   工作台里已有：%s" % "、".join(row["found"][:8]))
            continue
        print("   报告：%s%s" % (row["report"], ("  ｜ HTML：%s" % row["html"]) if row.get("html") else ""))
        print("   track_a = %s ｜ track_b: P=%s R=%s F1=%s ｜ TP/FP/FN/TN = %s/%s/%s/%s"
              % (_fmt(row["track_a"]), _fmt(row["p"]), _fmt(row["r"]), _fmt(row["f1"]),
                 _fmt(row["tp"]), _fmt(row["fp"]), _fmt(row["fn"]), _fmt(row["tn"])))
        print("   track_c = %s%s ｜ market_ready = %s ｜ verdict = %s"
              % (_fmt(row["track_c"]), ("（封顶 %s）" % _fmt(row["capped"])) if row["capped"] is not None else "",
                 _fmt(row["market_ready"]), _fmt(row["verdict"])))
        if isinstance(row["f1"], (int, float)):
            print("   → F1 %s 门槛：%s" % ("过" if row["f1"] >= THRESHOLD_F1 else "未过",
                                          "✅" if row["f1"] >= THRESHOLD_F1 else "❌"))
        else:
            print("   → F1 未在报告里找到（字段名可能与预期不同，需人工看报告）")
    print("\n" + "-" * 100)
    print("源基线核对（评测期间源不许变）：")
    for line in source_drift():
        print("   " + line)
    print("-" * 100)
    done = [r for r in rows if r["state"] == "ok"]
    print("进度：%d/%d 件已出报告" % (len(done), len(SKILLS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
