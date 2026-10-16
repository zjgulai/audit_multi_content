#!/usr/bin/env python3
"""置信度分流（PRD §6.6）—— 三档处理策略的**唯一实现**。

## PRD §6.6 原文

| 置信度区间 | 处理策略 |
|---|---|
| ≥ 0.90 | 直接输出结论（PASS / BLOCK） |
| 0.70 - 0.89 | 输出 REVIEW，标注"建议人工确认" |
| < 0.70 | 输出 REVIEW，标注"不确定，建议人工重点看" |

> **P0 层级规则不适用置信度分流，命中即 BLOCK。**

任务拆解 目标 11 的现状原文：「**无**（PRD §6.6 三档；P0 不适用分流、命中即 BLOCK）」。

## 本模块做什么、不做什么（**这条必须说清**）

**做**：把 §6.6 的**策略层**落成代码 —— 给定 `(置信度, 命中的层级)`，输出该走哪一档、
该标注什么话、以及**这个档位是不是真的生效了**。

**不做**：**标定阈值**。§6.6 的 0.90 / 0.70 是**政策值**，不是从数据算出来的。
引擎当前的置信度仍是启发式（`decision_trace.confidence_status = heuristic_not_calibrated`）。
把未标定的数按三档切开，切得再准也只是**把猜测分了类** ——
所以本模块**不声称分流是「准的」**，只声称「策略按 PRD 落地说得清了」。

⇒ 阈值可从政策文件 `kb/l7/registry/confidence-policy.json` 覆盖。

★★ 2026-10-12 更正（两处，都有实测为证）：
  ① 「**标定要等金标集**（11/30 那行）」**不成立** —— 本库自有**带人工标注**的集合
     （回归集 100 条 `expected`）已可用于标定；读数器 `kb/l8/calibrate_confidence.py`。
     外部金标集仍是**误报／漏报**那一项的前置，与置信度标定**不是同一件事**。
  ② 引擎的置信度**已由分支常量改成派生量**（同一分支内会随独立类目数 / 证据完整度变化）
     ⇒ 它**有分布**了，0.90 / 0.70 才谈得上标定。改前的实测：3~4 个取值、
     **与正确率不同序**（0.99→67% ＜ 0.78→80% ＜ 0.97→83%）⇒ 那个数不携带信息
     （见政策件 `measured_20261012_selfcalib`）。

## 用法

    python3 kb/l7/review-engine/core/confidence_flow.py --selftest   # 判据自证（不碰真库）
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# ── 阈值：PRD §6.6 的政策值。**可从政策文件覆盖，不在别处再写第二份。** ──────────
DEFAULT_THRESHOLDS = {"direct": 0.90, "confirm": 0.70}

#: 三档。顺序即从严到宽；`band_of()` 按这个顺序判。
BAND_POLICY = {
    "direct": {
        "range": ">= 0.90",
        "annotate": None,
        "effect": "keep",
        "why": "PRD §6.6：≥0.90 直接输出结论（PASS / BLOCK）",
    },
    "confirm": {
        "range": "0.70 - 0.89",
        "annotate": "建议人工确认",
        "effect": "force_review",
        "why": "PRD §6.6：0.70-0.89 输出 REVIEW，标注「建议人工确认」",
    },
    "focus": {
        "range": "< 0.70",
        "annotate": "不确定，建议人工重点看",
        "effect": "force_review",
        "why": "PRD §6.6：<0.70 输出 REVIEW，标注「不确定，建议人工重点看」",
    },
}

#: 不适用的情形 —— 命中它们时**不分流**，且必须写明为什么
NO_FLOW = {
    "p0": "PRD §6.6 明文「P0 层级规则不适用置信度分流，命中即 BLOCK」",
    "refusal": "拒答态（NEEDS_INPUT）不是判定结果，没有置信度可分流",
    "no_confidence": "引擎没给出置信度 ⇒ 不猜一个档位",
}


#: 政策文件落点：`<kb>/l7/registry/confidence-policy.json`。
#: 本文件在 `<kb>/l7/review-engine/core/` ⇒ 从 `__file__` 往上退 **4** 层到 `<kb>`。
#: ⚠️ 首版写成往上退 3 层，得到 `<kb>/l7/l7/registry/…`（**不存在的路径**），
#:   于是「阈值从政策文件读」这句话是**假的** —— 一直静默在用默认值，
#:   而返回值里那句「政策文件读不到」还被我自己当成正常兜底看过去了。
#:   现在有判据守着：`_selftest ⑨` 要求**真政策文件必须读得到**（读不到就红）。
POLICY_REL = ("l7", "registry", "confidence-policy.json")


def policy_path() -> str:
    kb = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    return os.path.join(kb, *POLICY_REL)


def load_thresholds(path: str | None = None) -> dict:
    """读政策文件；读不到就用 PRD 默认值并**声明用的是默认值**。"""
    p = path or policy_path()
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        t = d.get("thresholds") or {}
        out = dict(DEFAULT_THRESHOLDS)
        for k in out:
            v = t.get(k)
            if isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0:
                out[k] = float(v)
        return {"thresholds": out, "source": p, "from_policy_file": True}
    except Exception as e:                                        # noqa: BLE001
        return {"thresholds": dict(DEFAULT_THRESHOLDS), "source": p,
                "from_policy_file": False, "note": "政策文件读不到（%s）⇒ 用 PRD §6.6 默认值" % e}


def band_of(confidence: float, thresholds: dict | None = None) -> str:
    """置信度 → 档位名。**不返回「不分流」** —— 那是 `route()` 的职责（它要看层级）。"""
    t = thresholds or DEFAULT_THRESHOLDS
    c = float(confidence)
    if c >= t["direct"]:
        return "direct"
    if c >= t["confirm"]:
        return "confirm"
    return "focus"


def route(decision: str, confidence, tiers=None, thresholds: dict | None = None) -> dict:
    """PRD §6.6 分流。

    返回 `{applies, band, effect, annotate, decision, why}`。

    * `applies=False` 的三种情形见 `NO_FLOW` —— 此时 `band=None`，
      **不许**硬塞一个档位（那会让「P0 不分流」这句 PRD 在报告里看不出来）。
    * `effect="force_review"` 表示**该档位要把结论压成 REVIEW**（§6.6 的 0.70-0.89 与 <0.70
      两档，PRD 原文都写「输出 REVIEW」）。`decision` 给的是**分流后**的结论。
    """
    t = thresholds or DEFAULT_THRESHOLDS
    tiers = [x for x in (tiers or []) if x]

    # ① P0 命中 ⇒ 不适用分流（PRD §6.6 明文）
    if "P0" in tiers:
        return {
            "applies": False, "band": None, "effect": "keep", "annotate": None,
            "decision": decision, "why": NO_FLOW["p0"],
            "p0_override": True,
            "calibrated": False,      # ★ 与走哪个分支无关：阈值永远是政策值，不是标定值
        }
    # ② 拒答态没有置信度可分流
    if str(decision or "").upper() in ("NEEDS_INPUT", "拒答"):
        return {
            "applies": False, "band": None, "effect": "keep", "annotate": None,
            "decision": decision, "why": NO_FLOW["refusal"], "p0_override": False,
            "calibrated": False,
        }
    # ③ 没给置信度 ⇒ 不猜档位
    if confidence is None or confidence == "":
        return {
            "applies": False, "band": None, "effect": "keep", "annotate": None,
            "decision": decision, "why": NO_FLOW["no_confidence"], "p0_override": False,
            "calibrated": False,
        }

    band = band_of(float(confidence), t)
    pol = BAND_POLICY[band]
    out_decision = decision
    if pol["effect"] == "force_review":
        out_decision = "REVIEW"
    return {
        "applies": True,
        "band": band,
        "range": pol["range"],
        "effect": pol["effect"],
        "annotate": pol["annotate"],
        "decision_before": decision,
        "decision": out_decision,
        "why": pol["why"],
        "p0_override": False,
        "thresholds": dict(t),
        "calibrated": False,      # ★ 阈值是政策值，不是标定值 —— 这一格永远如实
    }


def annotate_summary(summary: str, r: dict) -> str:
    """把 §6.6 的标注语**追加**到摘要上。不分流时原样返回。"""
    if not r.get("applies") or not r.get("annotate"):
        return summary
    s = str(summary or "").rstrip()
    if r["annotate"] in s:                     # 幂等：重复调用不叠加
        return s
    return "%s（%s）" % (s, r["annotate"])


# ══════════════════════════════════════════════════════════════════
# 判据自证
# ══════════════════════════════════════════════════════════════════

def _selftest() -> int:
    ok = fail = 0
    fails: list[str] = []

    def ck(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (name, detail))

    T = dict(DEFAULT_THRESHOLDS)

    # ①a–c 三档边界（**边界值本身要判对**：0.90 属 direct，0.70 属 confirm）
    ck("①a 0.90→direct", band_of(0.90, T) == "direct", band_of(0.90, T))
    ck("①b 0.89→confirm", band_of(0.89, T) == "confirm", band_of(0.89, T))
    ck("①c 0.70→confirm", band_of(0.70, T) == "confirm", band_of(0.70, T))
    ck("①d 0.69→focus", band_of(0.69, T) == "focus", band_of(0.69, T))
    ck("①e 0.99→direct", band_of(0.99, T) == "direct", band_of(0.99, T))
    ck("①f 0.0→focus", band_of(0.0, T) == "focus", band_of(0.0, T))

    # ②a ★ P0 命中 ⇒ 不分流（PRD §6.6 明文），且**不许塞档位**
    r = route("BLOCK", 0.60, tiers=["P0"])
    ck("②a P0 不分流", r["applies"] is False and r["band"] is None and r["p0_override"] is True
       and r["decision"] == "BLOCK", "得到 %r" % r)
    ck("②a2 P0 依据写明", "P0" in r["why"] and "不适用" in r["why"], r["why"])
    # ②b P0 命中时**低置信度也不许把 BLOCK 压成 REVIEW**（这正是 §6.6 那条的意思）
    r = route("BLOCK", 0.10, tiers=["P0", "P3"])
    ck("②b P0 压不住", r["decision"] == "BLOCK" and r["effect"] == "keep", "得到 %r" % r)

    # ③a–b 两档 force_review
    r = route("BLOCK", 0.80, tiers=["P1"])
    ck("③a confirm 压 REVIEW", r["decision"] == "REVIEW" and r["effect"] == "force_review"
       and r["annotate"] == "建议人工确认", "得到 %r" % r)
    r = route("PASS", 0.50, tiers=["P2"])
    ck("③b focus 压 REVIEW", r["decision"] == "REVIEW"
       and r["annotate"] == "不确定，建议人工重点看", "得到 %r" % r)
    # ③c direct 不压
    r = route("BLOCK", 0.97, tiers=["P1"])
    ck("③c direct 不动", r["decision"] == "BLOCK" and r["effect"] == "keep"
       and r["annotate"] is None, "得到 %r" % r)

    # ④a–b 不适用分流另两种情形
    r = route("NEEDS_INPUT", 0.95, tiers=["P1"])
    ck("④a 拒答不分流", r["applies"] is False and r["decision"] == "NEEDS_INPUT", "得到 %r" % r)
    r = route("PASS", None, tiers=["P1"])
    ck("④b 无置信度不猜档", r["applies"] is False and r["band"] is None, "得到 %r" % r)

    # ⑤a 标注追加 + 幂等
    r = route("BLOCK", 0.80, tiers=["P1"])
    s = annotate_summary("【审查结论：REVIEW】共发现 2 处需人工确认。", r)
    ck("⑤a 标注上了", "建议人工确认" in s, s)
    ck("⑤b 幂等不叠加", annotate_summary(s, r) == s, annotate_summary(s, r))
    # ⑤c 不分流时摘要**一个字不改**（P0 那单不许被加标注）
    r0 = route("BLOCK", 0.60, tiers=["P0"])
    ck("⑤c P0 不加标注", annotate_summary("原文", r0) == "原文", annotate_summary("原文", r0))

    # ⑥a 阈值可覆盖（政策文件能力）——**这条是「不许硬编码」的判据**
    r = route("BLOCK", 0.80, tiers=["P1"], thresholds={"direct": 0.75, "confirm": 0.60})
    ck("⑥a 阈值可覆盖", r["band"] == "direct" and r["decision"] == "BLOCK", "得到 %r" % r)
    # ⑥b 覆盖后**边界仍按新阈值**判
    ck("⑥b 新边界", band_of(0.75, {"direct": 0.75, "confirm": 0.60}) == "direct",
       band_of(0.75, {"direct": 0.75, "confirm": 0.60}))

    # ⑦ ★ `calibrated` 必须恒为 False —— 阈值是政策值不是标定值，不许被说成"标定过"
    ck("⑦ 未标定要说实话", route("PASS", 0.95, tiers=["P1"])["calibrated"] is False,
       "calibrated 被写成了 True")

    # ⑦b ★ **所有分支**都要带 `calibrated` —— 早退分支漏了它，
    #     判据就查不到「阈值到底标定过没有」（首版实测：不分流的三个分支都缺这一格）。
    for name, rr in (("P0", route("BLOCK", 0.60, tiers=["P0"])),
                     ("拒答", route("NEEDS_INPUT", 0.9, tiers=["P1"])),
                     ("无置信度", route("PASS", None, tiers=["P1"])),
                     ("分流中", route("BLOCK", 0.80, tiers=["P1"]))):
        ck("⑦b[%s] 带 calibrated" % name, rr.get("calibrated") is False,
           "得到 %r" % rr.get("calibrated"))

    # ⑨ ★ **真政策文件必须读得到** —— 这条守的是「可配置」不是空话。
    #    首版路径算错（多退一层）⇒ 一直静默走默认值，而自证全绿。
    #    现在路径错或文件缺 ⇒ 本条精确变红。
    lp = load_thresholds()
    ck("⑨ 真政策文件读到了", lp.get("from_policy_file") is True,
       "读不到：%s" % lp.get("note"))
    ck("⑨b 路径指向 kb/l7/registry", policy_path().endswith("kb/l7/registry/confidence-policy.json"),
       policy_path())
    ck("⑨c 阈值与 PRD §6.6 一致", lp["thresholds"] == {"direct": 0.90, "confirm": 0.70},
       "得到 %r" % lp["thresholds"])

    # ⑧ 读不到政策文件 ⇒ 用默认值**并声明**
    lp = load_thresholds("/nonexistent/confidence-policy.json")
    ck("⑧ 兜底可辨认", lp["from_policy_file"] is False and lp["thresholds"] == DEFAULT_THRESHOLDS,
       "得到 %r" % lp)

    print("confidence_flow --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="置信度分流（PRD §6.6）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
