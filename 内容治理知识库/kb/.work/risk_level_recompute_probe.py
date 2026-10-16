#!/usr/bin/env python3
"""目标 6「风险等级按维度重算」—— **只读探针**（不写库、不改任何 l0–l7 文件）。

## 为什么要有它

任务拆解 10/12–10/16 行「必须做 #1」的判据是逐字的：

    风险等级须**逐条判定或按维度重算**，**不得用 p_level 映射顶替**。

现状实测：1018 条里 **840 条**走的是 `risk_level_basis = "源无 风险等级；按 p_level=P1
映射（PRD §6.2）"` ⇒ **整批同一档 High**，零区分度（复筛没有依据、只能靠 P0 兜底）。

## 重算口径 D1（草案，**待 Owner 签**；法务事后追认）

逐条按**优先级**取第一个能定的维度，并**逐条写明出处**：

| 序 | 维度 | 来源 | 映射 | 性质 |
|---|---|---|---|---|
| 1 | `风险等级` | 源记录字段 | `RISK_LEVEL_MAP`（既有换词表） | 硬：库内既有口径，不动 |
| 2 | `灯色状态` | 源记录字段（W1 表） | **复用既有色标口径**：红→Critical / 黄→High / 绿→Low | 硬：与 `风险等级` 的 `·红/·黄/·绿` 同一套语汇 |
| 3 | `修订类型` | 源记录字段（专家修订汇总表） | 按 `/` 拆 token → `REVISION_TYPE_TO_RISK`，**取最高档** | 软：按 PRD §6.2 四层语义归类，逐 token 带 PRD 出处 |
| 4 | 都取不到 | — | `unknown` | **不编** |

★ 纪律：**这不是「换一个批量映射」，是把严重度从「优先级轴」换回「严重度轴」**。
  `p_level` 是 PRD §6.2 的**优先级层级**，与 §6.5 的**风险等级**是两个轴；
  拿前者顶替后者，正是本次要修的病。`修订类型` 是专家**逐条**填的「这条修订是什么性质」，
  天然落在严重度轴上。

## 用法（全只读）

    python3 kb/.work/risk_level_recompute_probe.py            # 对照 + 分布 + 抽查
    python3 kb/.work/risk_level_recompute_probe.py --json     # 逐条 diff 落 kb/.work/
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

#: 本文件在 <root>/kb/.work/ ⇒ KB 指到 <root>/kb（与 kb/l3 同级那一层）
KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KB, "l3"))

from kb_rule_dimensions import (  # noqa: E402
    RISK_LEVEL_MAP, build_l0_index, l0_lookup, _first_scalar, NOT_DERIVABLE,
)

RULES = os.path.join(KB, "l3", "candidates", "rules.jsonl")
OUT_DIR = os.path.join(KB, ".work")

# ══════════════════════════════════════════════════════════════════
# 维度 2：源字段「灯色状态」—— **复用既有换词表色标**，不是新造
#   既有 `RISK_LEVEL_MAP` 吃的就是源侧色标后缀（`高危·红` / `审慎·黄` / `合规·绿`）
#   ⇒ 这里直接把色标映射成同一份四档，与维度 1 同一语汇。
# ══════════════════════════════════════════════════════════════════

LAMP_COLOR_TO_RISK = {
    "红": "Critical",   # 与 源「高危·红」同档（既有口径）
    "黄": "High",       # 与 源「审慎·黄」同档（既有口径）
    "绿": "Low",        # 与 源「合规·绿」同档（既有口径）
}

# ══════════════════════════════════════════════════════════════════
# 维度 3：源字段「修订类型」→ PRD §6.2 四档
#   hard=True  ⇒ 直接引 PRD 逐字（§6.2 表 / §7.3 一票否决）
#   hard=False ⇒ 按 §6.2 四层语义归类（**软判，需 Owner 签 + 法务追认**）
# ══════════════════════════════════════════════════════════════════

REVISION_TYPE_TO_RISK = {
    # ── Critical：PRD §7.3 一票否决第 3 条「绝对化用语（最、第一、最佳、100%、纯天然等）」──
    # ★★ 2026-10-12：**源里的「去绝对化」不判 Critical**（初版判了，实测推翻）——
    #   逐条读源里 6 条「去绝对化」（`kb/l0/records/专家修订汇总表/`），它们的原文/原因是：
    #     · 室温保持 20~22℃ 的表述过于绝对（气候差异）
    #     · 「解冻后的母乳不能再次冷冻」表述过于绝对
    #     · 「最核心的应对方式之一」表述过于绝对
    #     · 「2～3岁正是午睡逐渐不规律」表述过于绝对（个体差异）
    #     · 「规则越具体，孩子越容易理解」缺少适用边界
    #     · 「停止哺乳超过1年」没有充分依据设为统一节点
    #   ⇒ 指的是「**去掉一个不成立的适用边界/数值阈值**」，**不是**广告绝对化用语。
    #   据它判 Critical 会把 P0 红线档从 98 撑到 104，而 PRD §7.3-3 那条红线
    #   是「命中即驳回、不进入后续审查层级」的**一票否决** —— **错档比不分档更坏**。
    #   它们全部涉及婴儿护理/喂养的安全边界 ⇒ 归 P1（§6.2 消费者安全）。

    # ── High：PRD §6.2 P1「消费者安全、产品描述准确性」──
    "去绝对化": ("High", "PRD §6.2 P1 消费者安全（表述缺少适用边界；**非** §7.3-3 广告绝对化用语）", False),
    "安全警示强化": ("High", "PRD §6.2 P1 消费者安全", True),
    "安全提示补充": ("High", "PRD §6.2 P1 消费者安全", True),
    "安全提示": ("High", "PRD §6.2 P1 消费者安全", True),
    "禁忌说明补充": ("High", "PRD §6.2 P1 消费者安全", True),
    "高风险人群提示": ("High", "PRD §6.2 P1 消费者安全", True),
    "就医指征完善": ("High", "PRD §6.2 P1 消费者安全", False),
    "就医时间阈值收紧": ("High", "PRD §6.2 P1 消费者安全", False),
    "用药安全提示": ("High", "PRD §6.2 P1 消费者安全", False),
    "护理方式纠正": ("High", "PRD §6.2 P1 消费者安全", True),
    "护理方式修正": ("High", "PRD §6.2 P1 消费者安全", True),
    "动作指导补全": ("High", "PRD §6.2 P1 消费者安全（错误示范/危险使用）", True),
    "产品信息更新": ("High", "PRD §6.2 P1 产品描述准确性", True),
    "适用范围说明": ("High", "PRD §6.2 P1 产品描述准确性（功能边界/型号差异）", False),

    # ── Medium：PRD §6.2 P2「通识与常识」──
    "科学性纠错": ("Medium", "PRD §6.2 P2 通识与常识", True),
    "科学性补充": ("Medium", "PRD §6.2 P2 通识与常识", True),
    "科学性完善": ("Medium", "PRD §6.2 P2 通识与常识", True),
    "表述对齐指南": ("Medium", "PRD §6.2 P2 通识与常识（与权威指南一致）", False),
    "医学内容补充": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "内容补充": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "参考文献规范": ("Medium", "PRD §6.2 P2 通识与常识（依据来源）", False),
    "内容逻辑优化": ("Medium", "PRD §6.2 P2 通识与常识（场景合理性）", False),
    "逻辑清晰化": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "内容不准确": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "内容方向性修改": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "内容修订": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "概念澄清": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "决策支持完善": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "文章定位调整": ("Medium", "PRD §6.2 P2 通识与常识", False),

    # ── Low：PRD §6.2 P3「措辞与表达（不涉及硬性拦截）」──
    "表述精确化": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "表述完善": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "表述温和化": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "表述简化": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "术语规范": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "内容删减": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "删减": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "文章整体重写建议": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "内容分类调整": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "标题修改建议": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "过度警示修正": ("Low", "PRD §6.2 P3 措辞与表达（反向：降警示力度）", False),

    # ── unknown：**不编** —— 专家自己标了「存疑/待讨论」，我们不替它定级 ──
    "存疑/待讨论": (None, "源字段 修订类型=存疑/待讨论 ⇒ **不编**，留 unknown", True),
}

_ORDER = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}


def _lamp_of(l0_fields) -> str | None:
    raw = _first_scalar((l0_fields or {}).get("灯色状态"))
    if not raw:
        return None
    for c in ("红", "黄", "绿"):
        if c in str(raw):
            return c
    return None


def _revision_tokens(l0_fields) -> list[str]:
    """源「修订类型」→ token 列表。

    ★ 2026-10-12：**先整值查，再拆 `/`**。
      初版直接按 `/` 拆，于是 `存疑/待讨论`（它是映射表里的**一个整键**）
      被拆成 `存疑` ＋ `待讨论` 两个查不到的 token ⇒ 报成「全部不在映射表内」。
      两者结论恰好都是 unknown，**所以这个 bug 不会体现在分布上** ——
      这正是「哑失败」，靠分布看不出来，只有读 token 才看得见。
    """
    raw = _first_scalar((l0_fields or {}).get("修订类型"))
    if not raw:
        return []
    s = str(raw).strip()
    if s in REVISION_TYPE_TO_RISK:        # 整值命中优先（映射表里有复合键）
        return [s]
    return [t.strip() for t in s.split("/") if t.strip()]


def recompute(row: dict, l0_fields) -> tuple[str | None, str, dict]:
    """返回 (新 risk_level, 出处, 明细)。**逐条带出处；取不到就 None，不编。**"""
    detail = {"priority_used": None, "tokens": [], "unmapped_tokens": []}

    # 维度 1：源字段 风险等级（既有换词表，最高优先 —— 最细的证据）
    raw = _first_scalar((l0_fields or {}).get("风险等级"))
    if raw:
        key = str(raw).split("·")[0].strip()
        if key in RISK_LEVEL_MAP:
            detail["priority_used"] = 1
            return RISK_LEVEL_MAP[key], "源字段 风险等级=%s" % raw, detail
        return None, "源字段 风险等级=%s 不在映射表内（%s）" % (raw, "/".join(RISK_LEVEL_MAP)), detail

    # 维度 2：源字段 灯色状态（复用既有色标口径）
    lamp = _lamp_of(l0_fields)
    if lamp:
        detail["priority_used"] = 2
        return LAMP_COLOR_TO_RISK[lamp], "源字段 灯色状态=%s色（复用既有色标口径）" % lamp, detail

    # 维度 3：源字段 修订类型（按 '/' 拆 token，取最高档）
    toks = _revision_tokens(l0_fields)
    if toks:
        detail["tokens"] = toks
        best, why, tok_hits = None, [], []
        for t in toks:
            m = REVISION_TYPE_TO_RISK.get(t)
            if m is None:
                detail["unmapped_tokens"].append(t)
                continue
            lvl, basis, hard = m
            tok_hits.append("%s→%s" % (t, lvl or "unknown"))
            why.append("修订类型「%s」⇒ %s（%s%s）" % (t, lvl or "unknown", basis,
                                                   "" if hard else "，软判"))
            if lvl and (best is None or _ORDER[lvl] > _ORDER[best]):
                best = lvl
        detail["priority_used"] = 3
        if tok_hits:
            return best, "源字段 修订类型=%s ｜ %s" % ("/".join(toks), " ＋ ".join(why)), detail
        if detail["unmapped_tokens"]:
            return None, ("源字段 修订类型=%s 全部不在映射表内 ⇒ **不编**"
                          % "/".join(toks)), detail

    return None, "源无 风险等级 / 灯色状态 / 修订类型 ⇒ **不编**", detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="逐条 diff 落 kb/.work/")
    ap.add_argument("--sample", type=int, default=20)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(RULES, encoding="utf-8") if l.strip()]
    idx = build_l0_index()
    look = l0_lookup(idx)

    diffs, new_dist, basis_dist = [], collections.Counter(), collections.Counter()
    used = collections.Counter()
    for r in rows:
        l0_fields, _fld = look(r)
        lvl, why, det = recompute(r, l0_fields)
        old = r.get("risk_level")
        new_dist[str(lvl)] += 1
        basis_dist[why.split(" ｜")[0]] += 1
        used[det["priority_used"]] += 1
        diffs.append({
            "rule_id": r.get("rule_id"), "rule_code": r.get("rule_code"),
            "anchor": r.get("anchor"),
            "old_risk_level": old, "old_basis": r.get("risk_level_basis"),
            "new_risk_level": lvl, "new_basis": why,
            "priority_used": det["priority_used"],
            "unmapped_tokens": det["unmapped_tokens"],
            "rule_text": " ".join(str(r.get("rule_text") or "").split())[:110],
        })

    old_dist = collections.Counter(str(r.get("risk_level")) for r in rows)
    print("═" * 74)
    print("目标 6 · 风险等级按维度重算（只读探针）")
    print("═" * 74)
    print("规则总数 %d" % len(rows))
    print()
    print("【旧】" + " ｜ ".join("%s=%d" % kv for kv in old_dist.most_common()))
    print("【新】" + " ｜ ".join("%s=%d" % kv for kv in new_dist.most_common()))
    print()
    print("── 取了哪一维 ──")
    for k, v in used.most_common():
        print("   维度 %s : %4d" % (k, v))
    print()
    print("── 出处分布（前 12）──")
    for k, v in basis_dist.most_common(12):
        print("   %5d  %s" % (v, k[:96]))
    print()

    changed = [d for d in diffs if d["old_risk_level"] != d["new_risk_level"]]
    print("变动 %d / %d 条" % (len(changed), len(diffs)))
    unmapped = [d for d in diffs if d["unmapped_tokens"]]
    print("有未映射 token 的条数 %d（其 token：%s）"
          % (len(unmapped), sorted({t for d in unmapped for t in d["unmapped_tokens"]})))
    print()

    print("── 等距抽查 %d 条（旧 → 新 ＋ 出处）──" % a.sample)
    step = max(1, len(diffs) // a.sample)
    for i, d in enumerate(diffs[::step][:a.sample], 1):
        print("%2d. %-9s → %-9s ｜ %s" % (i, d["old_risk_level"], d["new_risk_level"],
                                          d["new_basis"][:104]))
        print("      %s" % d["rule_text"][:100])
    print()
    print("※ 只读：未写任何 l0–l7 文件。NOT_DERIVABLE 未动：%s" % ",".join(sorted(NOT_DERIVABLE)))

    if a.json:
        p = os.path.join(OUT_DIR, "risk_level_recompute_diff.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            for d in diffs:
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        print("逐条 diff 已落：%s（%d 行）" % (p, len(diffs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
