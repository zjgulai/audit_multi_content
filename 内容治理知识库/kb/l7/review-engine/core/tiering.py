#!/usr/bin/env python3
"""P0–P3 分级：把 PRD §6.2 / §6.3 的四层规则落成**可复用的一处实现**。

## 为什么要有这个模块

任务拆解 10/12–10/16 行**目标 12**（PRD §6.3）：

> 现状：引擎里**只有 `priority_tier == "P0"` 的执行分支**，非 P0 一律缺省写成 **P1**，
> **P2 / P3 无分支**。⇒ PRD §6.3 的第二层（安全准确性·语义）与第三层（通识常识·多模态）
> **没有实现**；而 PRD §7.2 九域里 **7 个域挂在 P1/P2**，等于这 7 个域目前判不了。

**病灶的形状和维度字段那次一样**：两个生产者各自**就地硬编码**「不是 P0 就是 P1」——

| 位置 | 原代码 | 后果 |
|---|---|---|
| `kb/l8/…` 无关 | — | — |
| `review.py:1553` | `"priority_tier": "P0" if "P0" in layer else "P1"` | **看文案里有没有「P0」二字**，不看规则的 `p_level` |
| `with_kb_evidence.py:750` | `"P0" if "P0" in str(f.get("layer")) else "P1"` | 同上；`f` 里**根本没有 `layer` 键** ⇒ 恒为 `P1` |

⇒ 于是 `p_level=P2` 的 11 条、`p_level=P3` 的 4 条规则，命中了也只报 `P1`。

本模块把分级收成**一份纯函数**，两个生产者共用 —— **不许在别处再写第二份**。

## 口径来源（不是自创）

| 层级 | 动作 | 出处 |
|---|---|---|
| **P0** | 命中即 BLOCK，**不走置信度分流** | PRD §6.3 执行规则 1；§6.6「P0 层级规则不适用置信度分流，命中即 BLOCK」 |
| **P1** | 命中红线 → BLOCK；**不确定 → REVIEW（转对应专业团队）** | PRD §6.3 第二层；§9「REVIEW 自动转对应专业团队」 |
| **P2** | 发现常识错误 → **BLOCK 或 REVIEW** | PRD §6.3 第三层 |
| **P3** | **只输出建议，不改变 PASS/BLOCK 结论** | PRD §6.3 执行规则 3 |

**P1 保守取 REVIEW**（不是 BLOCK）：PRD §6.3 第二层是「大模型语义理解」，
属**判断行为是否构成危险示范**那一类；判据不确定时按 §6.3 应转 REVIEW 给专业团队，
**不该由语义层直接下 BLOCK**。P0 那条「命中即拦、不交给 AI 推理」的硬约束不因此松动 ——
P0 走的是确定性匹配，不是语义。

## 用法

    python3 kb/l7/review-engine/core/tiering.py --selftest   # 判据自证（不碰真库）
"""

from __future__ import annotations

import argparse
import sys

#: PRD §6.2 四层。顺序即优先级，**P0 最高**。
TIER_ORDER = ("P0", "P1", "P2", "P3")

#: 每个层级的动作与它对三态结论的影响。**唯一口径表**。
TIER_POLICY = {
    "P0": {
        "action": "block",
        "effect": "block",
        "routing": None,
        "confidence_flow": False,
        "why": "PRD §6.3 执行规则1：命中即停止后续审查、直接 BLOCK；§6.6 不适用置信度分流",
    },
    "P1": {
        "action": "review",
        "effect": "review",
        "routing": "专业团队",
        "confidence_flow": True,
        "why": "PRD §6.3 第二层：语义理解层，判不准 → REVIEW 转对应专业团队（§9）",
    },
    "P2": {
        "action": "review",
        "effect": "review",
        "routing": "专业团队",
        "confidence_flow": True,
        "why": "PRD §6.3 第三层：多模态常识层，PRD 允许 BLOCK 或 REVIEW，本实现取保守侧 REVIEW",
    },
    "P3": {
        "action": "advice",
        "effect": "none",
        "routing": None,
        "confidence_flow": True,
        "why": "PRD §6.3 执行规则3：只输出建议，**不改变 PASS/BLOCK 结论**",
    },
}

#: 从「层」的文案反推层级时的兜底（老路径仍传 `layer` 字符串）。
#: ⚠️ 这是**兜底**，不是主路：主路是直接读规则行的 `p_level`。
LAYER_HINTS = (("P0", "P0"), ("P1", "P1"), ("P2", "P2"), ("P3", "P3"))

#: 已知的「非 p_level」层类型 → 层级。案例层是 L4 定稿的反例/禁区，按 PRD §6.2 属 P1 安全与准确性。
LAYER_KIND_TO_TIER = {
    "案例": "P1",
}


def tier_of(p_level=None, layer=None, severity=None, risk_level=None) -> tuple[str, str]:
    """定层级。返回 (tier, 依据)。

    取值顺序（先准后粗，**不猜**）：

    1. `p_level` 直接给出 P0–P3 ⇒ 用它（**主路**：规则行本来就有这一列，509 条全有值）；
    2. `layer` 文案里含 `P0`–`P3` ⇒ 用命中的那个（**兼容老调用方**）；
    3. `layer` 属已知层类型（如「案例层」）⇒ 按 `LAYER_KIND_TO_TIER`；
    4. `severity == "BLOCK"` ⇒ 归 **P0**（能确定到 block 的，按最高层处理 —— 保守方向）；
    5. 都不给 ⇒ **`P1` 兜底**，与改动前逐字一致（改前就是「非 P0 即 P1」），
       但依据里**写明这是兜底**，不留一个看不出来的默认值。
    """
    p = str(p_level or "").strip().upper()
    if p in TIER_POLICY:
        return p, "规则行 p_level=%s" % p

    lay = str(layer or "")
    for token, tier in LAYER_HINTS:
        if token in lay:
            return tier, "层文案含 %s（老调用方兼容）" % token
    for kind, tier in LAYER_KIND_TO_TIER.items():
        if kind in lay:
            return tier, "层类型「%s」按 PRD §6.2 归 %s" % (kind, tier)

    if str(severity or "").strip().upper() == "BLOCK":
        return "P0", "severity=BLOCK ⇒ 按最高层处理（保守方向）"

    return "P1", "无 p_level / layer / severity 可用 ⇒ P1 兜底（与改动前一致）"


#: ★★ 2026-10-12：判定「这条命中是不是**源侧最高严重度**」的**唯一口径**。
#:
#: ## 病情（实测，不是推演）
#:
#: `kb/l7/skills/kb-content-review/scripts/review.py:982` 与 `:1015` 原写：
#:
#:     sev = "BLOCK" if (h.get("p_level") == "P0" or h.get("risk_level") == "高危·红") else "REVIEW"
#:
#: `h["risk_level"]` 取自 **L3 规则行**（`review.py:261`）。而 **2026-10-10 的换词表**
#: （`kb/l3/registry/dimension-policy.json → risk_level_map`）已把那一列改成**英文**——
#: 实测现行取值集合 = `Critical / High / Medium / Low / unknown` ⇒ `== "高危·红"` **恒假**，
#: 该子句**静默死掉**（哑失败：不抛异常、不报错、分布上看不出来）。
#:
#: 代价：**41 条**规则 `risk_level=Critical` 但 `p_level≠P0` ⇒ 本该 BLOCK 的落了 REVIEW
#: （改前也有 35 条；靠前半句 `p_level == "P0"` 兜住的只有 15 条）。
#:
#: ## 口径
#:
#: **两种形态都认** —— 换词表**前**的旧中文（`高危` / `高危·红`）与换词表**后**的英文
#: （`Critical`）。认两种**不是「宽松」**，是**不许再因为一次换词表就把判据弄哑**：
#: 词表可以换，判据不该跟着死。
#:
#: ## 为什么这仍然是「红线即 BLOCK」
#:
#: 该子句问的是「源侧自己判的严重度是不是最高档」。这一列只有四个来源
#: （见 `dimension-policy.json`）：源 `风险等级=高危`/`高危·红`、源 `灯色状态=红色**禁用**`、
#: 以及 P0 地板 —— **全都是源侧判定的「禁用 / 红线」**，命中即拦不算越权。
CRITICAL_RISK_LEVELS = frozenset({"Critical", "高危", "高危·红"})


def is_critical_risk_level(v) -> bool:
    """源侧最高严重度？**两种形态都认**（旧中文 / 新英文），详见 `CRITICAL_RISK_LEVELS`。"""
    s = str(v or "").strip()
    if not s:
        return False
    if s in CRITICAL_RISK_LEVELS:
        return True
    # 源侧带色标后缀（`高危·红` / `审慎·黄`）⇒ 取 `·` 前那一段再比一次
    return s.split("·")[0].strip() in CRITICAL_RISK_LEVELS


#: ★★ 2026-10-12：允许走「**源侧最高严重度 ⇒ BLOCK**」这条路的**层级**。
#:
#: 为什么**不含 P2/P3**（这一格是回归集逼出来的，不是拍的）：
#:   · PRD §7.3 —— 只有 **P0** 是「一票否决 / **命中即驳回**」；
#:   · PRD §6.3 第二层 —— 「**P1** 安全与准确性：命中红线 → BLOCK」⇒ P1 有明文依据；
#:   · PRD §6.3 第三层 —— 「**P2** 通识与常识：发现常识错误 → **BLOCK 或 REVIEW**」，
#:     是**二选一**；本实现取**保守侧 REVIEW**（§11.1「BLOCK 精确率 ≥ 95%，**避免误伤**」）。
#:
#: 实测（`kb/.work/regression-BEFORE/AFTER-20261012.jsonl`，100 条回归集）：
#:   把 P2 也纳入 ⇒ 唯一动到的单 `RC-4d2c823edcca`（`rule_code=M01, p_level=P2`）
#:   从「期望 REVIEW」变成 BLOCK ⇒ **solid 一致数 67 → 66**。
#:   而收窄到 P1 后，全库受影响 41 条里的 **37 条 P1** 保留，**4 条 P2 被排除**。
SEVERITY_BLOCK_TIERS = frozenset({"P0", "P1"})


def severity_for(p_level, risk_level) -> tuple[str, str]:
    """**命中该判 BLOCK 还是 REVIEW 的唯一口径**。返回 (severity, 依据)。

    修的是 `review.py:982/1015` 那条**静默死掉的红线子句**（详见 `CRITICAL_RISK_LEVELS` 抬头）。
    口径逐字对 PRD：

      · P0 ⇒ BLOCK            —— §7.3「命中即驳回，不进入后续审查层级」（一票否决）
      · P1 ＋ 源侧最高严重度 ⇒ BLOCK —— §6.3 第二层「命中红线 → BLOCK」
      · 其余 ⇒ REVIEW         —— §6.3 第二/三层「不确定 ⇒ REVIEW（转对应专业团队）」
    """
    p = str(p_level or "").strip().upper()
    if p == "P0":
        return "BLOCK", "P0 一票否决（PRD §7.3「命中即驳回」）"
    if p in SEVERITY_BLOCK_TIERS and is_critical_risk_level(risk_level):
        return "BLOCK", "层级 %s ＋ 源侧最高严重度（%s）（PRD §6.3 第二层「命中红线 → BLOCK」）" % (p, risk_level)
    if p == "P2" and is_critical_risk_level(risk_level):
        return "REVIEW", ("层级 P2 ＋ 源侧最高严重度（%s）⇒ **保守取 REVIEW**"
                          "（PRD §6.3 第三层是「BLOCK 或 REVIEW」二选一；§11.1 要求避免误伤）" % risk_level)
    return "REVIEW", "非一票否决层级 ⇒ 转人工（PRD §6.3 第二/三层）"


def action_of(tier: str) -> str:
    """该层级该给什么动作。未知层级按 P1（保守：转 REVIEW，不放行也不误拦）。"""
    return TIER_POLICY.get(tier, TIER_POLICY["P1"])["action"]


def effect_of(tier: str) -> str:
    """该层级对三态结论的影响：`block` / `review` / `none`。"""
    return TIER_POLICY.get(tier, TIER_POLICY["P1"])["effect"]


def routing_of(tier: str):
    """该层级该转给谁；不需要转的返回 None。"""
    return TIER_POLICY.get(tier, TIER_POLICY["P1"])["routing"]


def confidence_flow_applies(tier: str) -> bool:
    """该层级适不适用 PRD §6.6 的置信度分流。**P0 不适用**。"""
    return bool(TIER_POLICY.get(tier, TIER_POLICY["P1"])["confidence_flow"])


def decide_effect(tiers) -> tuple[str, str]:
    """按 PRD §6.3 执行规则 4「按最高优先级输出」汇总一批层级。

    返回 (effect, 依据)，effect ∈ {"block","review","none"}。

    规则 4 原话：「当多条规则同时命中时，按最高优先级输出；例如同时命中 P0 和 P2，
    结论为 BLOCK，报告中列出全部问题供参考。」
    """
    seen = [t for t in (tiers or []) if t]
    if not seen:
        return "none", "无命中层级"
    for t in TIER_ORDER:                      # P0 → P3，第一个出现的就是最高
        if t in seen:
            if t == "P3" and all(x == "P3" for x in seen):
                return "none", "仅 P3 命中 ⇒ 只出建议，不改结论（PRD §6.3 执行规则3）"
            return effect_of(t), "最高层级=%s ⇒ effect=%s（PRD §6.3 执行规则4）" % (t, effect_of(t))
    return "review", "层级不在 P0–P3 内 ⇒ 保守取 review"


def apply_tier(item: dict) -> dict:
    """就地为一条 risk_item 写 `priority_tier` / `priority_tier_basis` / `action`。

    返回 item（方便链式）。**只动这三个键**，不碰 evidence / reason 等承载证据的字段。
    """
    tier, basis = tier_of(item.get("p_level"), item.get("layer"),
                          item.get("severity"), item.get("risk_level"))
    item["priority_tier"] = tier
    item["priority_tier_basis"] = basis
    item["action"] = action_of(tier)
    return item


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

    # ①a–d p_level 主路：四个层级都要认得出（改前只有 P0 认得出，其余全塌成 P1）
    for p, want in (("P0", "P0"), ("P1", "P1"), ("P2", "P2"), ("P3", "P3")):
        got, why = tier_of(p_level=p)
        ck("①[%s]" % p, got == want and "p_level" in why, "得到 %r（%s）" % (got, why))
    # ①e p_level 优先于 layer（主路压过兼容路）
    got, why = tier_of(p_level="P2", layer="P0 确定性匹配")
    ck("①e p_level 优先", got == "P2", "得到 %r（%s）" % (got, why))
    # ①f–h layer 兼容：老调用方（只传 layer）
    for lay, want in (("P0 确定性匹配", "P0"), ("规则层", "P1"), ("P2 通识", "P2")):
        got, why = tier_of(layer=lay)
        ck("①[%s]" % lay, got == want, "得到 %r（%s）" % (got, why))
    # ①i 案例层 → P1
    got, why = tier_of(layer="案例层（L4 定稿「反例/禁区」）")
    ck("①i 案例层→P1", got == "P1", "得到 %r（%s）" % (got, why))
    # ①j severity=BLOCK 兜底 → P0（保守）
    got, why = tier_of(severity="BLOCK")
    ck("①j BLOCK→P0", got == "P0", "得到 %r（%s）" % (got, why))
    # ①k 全空 → P1 兜底，且**依据写明是兜底**（与改前行为一致）
    got, why = tier_of()
    ck("①k 兜底可辨认", got == "P1" and "兜底" in why, "得到 %r（%s）" % (got, why))
    # ①l **未知 p_level 不许猜成 P0**，落到兜底并写明
    got, why = tier_of(p_level="P9")
    ck("①l 未知不猜高", got == "P1" and "兜底" in why, "得到 %r（%s）" % (got, why))

    # ②a–d 动作表
    for t, want in (("P0", "block"), ("P1", "review"), ("P2", "review"), ("P3", "advice")):
        ck("②[%s].action" % t, action_of(t) == want, "得到 %r" % action_of(t))
    # ②e–f P3 不改结论，P0 走 block
    ck("②e P3 不改结论", effect_of("P3") == "none", "得到 %r" % effect_of("P3"))
    ck("②f P0 effect", effect_of("P0") == "block", "得到 %r" % effect_of("P0"))
    # ②g 未知层级保守取 review（不放行、也不误拦）
    ck("②g 未知保守", action_of("P9") == "review" and effect_of("P9") == "review",
       "得到 %r/%r" % (action_of("P9"), effect_of("P9")))
    # ②h P0 不适用置信度分流（PRD §6.6 明文）
    ck("②h P0 不分流", confidence_flow_applies("P0") is False, "得到 %r" % confidence_flow_applies("P0"))
    ck("②h2 P1 适用分流", confidence_flow_applies("P1") is True, "得到 %r" % confidence_flow_applies("P1"))
    # ②i P1/P2 要转专业团队，P0/ P3 不转
    ck("②i 路由", routing_of("P1") == "专业团队" and routing_of("P2") == "专业团队"
       and routing_of("P0") is None and routing_of("P3") is None,
       "得到 %r" % [routing_of(t) for t in TIER_ORDER])

    # ③a–e 执行规则 4：按最高优先级输出
    ck("③a P0+P2→block", decide_effect(["P0", "P2"])[0] == "block", "得到 %r" % (decide_effect(["P0", "P2"]),))
    ck("③b P1+P2→review", decide_effect(["P1", "P2"])[0] == "review", "得到 %r" % (decide_effect(["P1", "P2"]),))
    ck("③c 仅 P3→none", decide_effect(["P3"])[0] == "none", "得到 %r" % (decide_effect(["P3"]),))
    ck("③d P3+P2→review", decide_effect(["P3", "P2"])[0] == "review", "得到 %r" % (decide_effect(["P3", "P2"]),))
    ck("③e 空→none", decide_effect([])[0] == "none", "得到 %r" % (decide_effect([]),))

    # ④a apply_tier 只动三个键
    #     ⚠️ 断言口径：`action` **原本就在字典里**（本条输入给了它）⇒ 判「键集合不变」，
    #     不是判「新增了 action」。（首版断言写成 set 差集，把这条判红 —— 是**断言写错**，代码对。）
    it = {"p_level": "P2", "severity": "REVIEW", "action": "review", "reason": "keep-me",
          "evidence": {"a": 1}}
    keys_before = set(it)
    apply_tier(it)
    ck("④a 键集合不变且值正确",
       it["priority_tier"] == "P2" and it["action"] == "review"
       and it["reason"] == "keep-me" and it["evidence"] == {"a": 1}
       and set(it) == keys_before | {"priority_tier", "priority_tier_basis"},
       "得到 %r" % it)
    # ④b ★ 反向对照：**不许看 layer 文案里有没有「P0」二字**
    #     改前就是这个错（`"P0" if "P0" in layer else "P1"`）⇒ p_level=P2 的规则被报成 P1。
    it = {"p_level": "P2", "layer": "P0 确定性匹配（依据不可逐字回源）"}
    apply_tier(it)
    ck("④b layer 文案不覆盖 p_level", it["priority_tier"] == "P2", "得到 %r" % it["priority_tier"])

    # ⑤a–e ★ 2026-10-12：源侧最高严重度的唯一口径（修 `review.py` 那条**死掉的红线子句**）
    #   病情见 `CRITICAL_RISK_LEVELS` 抬头：换词表把 L3 那列改成英文后，
    #   `== "高危·红"` 恒假 ⇒ 41 条规则的命中共不上报 BLOCK。
    # ⑤a 换词表**后**的英文形态必须认（**本条就是病灶**：只认旧中文 ⇒ 精确变红）
    ck("⑤a 英文 Critical 认", is_critical_risk_level("Critical") is True,
       "得到 %r" % is_critical_risk_level("Critical"))
    # ⑤b 换词表**前**的旧中文形态也认（向后兼容：历史单/老旁挂里的中文值仍判得出）
    for v in ("高危·红", "高危"):
        ck("⑤b 旧中文 %s 认" % v, is_critical_risk_level(v) is True, "得到 %r" % is_critical_risk_level(v))
    # ⑤c 非最高档一律**不许**认
    for v in ("High", "Medium", "Low", "unknown", "", None, "审慎·黄", "合规·绿"):
        ck("⑤c[%r] 不认" % v, is_critical_risk_level(v) is False,
           "得到 %r" % is_critical_risk_level(v))
    # ⑤d ★ 反向对照：把判定放大成「含『高危』二字就算」⇒ 本条必须变红
    #     （`审慎·黄` 的色标后缀里没有「高危」，但 `高风险人群提示` 那类文本有 —— 不许按子串判）
    ck("⑤d 不按子串宽松判", is_critical_risk_level("非高危·红但不能算") is False,
       "得到 %r" % is_critical_risk_level("非高危·红但不能算"))
    # ⑤e ★ 反向对照：**两种形态必须都在常量里** —— 缺任何一种，下一次换词表又会把它弄哑
    ck("⑤e 常量含两种形态", {"Critical", "高危", "高危·红"} <= CRITICAL_RISK_LEVELS,
       "得到 %r" % sorted(CRITICAL_RISK_LEVELS))

    # ⑥a–f 命中判 BLOCK 还是 REVIEW 的**唯一口径**（修 `review.py` 死分支的落点）
    # ⑥a P0 一票否决：与 risk_level 无关（PRD §7.3）
    for rl in ("Critical", None, "Low"):
        ck("⑥a P0⇒BLOCK[%r]" % rl, severity_for("P0", rl)[0] == "BLOCK",
           "得到 %r" % (severity_for("P0", rl),))
    # ⑥b P1 ＋ 源侧最高严重度 ⇒ BLOCK（PRD §6.3 第二层「命中红线 → BLOCK」）
    ck("⑥b P1+Critical⇒BLOCK", severity_for("P1", "Critical")[0] == "BLOCK",
       "得到 %r" % (severity_for("P1", "Critical"),))
    ck("⑥b2 P1+旧中文⇒BLOCK", severity_for("P1", "高危·红")[0] == "BLOCK",
       "得到 %r" % (severity_for("P1", "高危·红"),))
    # ⑥c ★★ P2 是**二选一**，本实现取保守侧 REVIEW（回归集逼出来的：见 SEVERITY_BLOCK_TIERS 抬头）
    got, why = severity_for("P2", "Critical")
    ck("⑥c P2+Critical⇒REVIEW", got == "REVIEW" and "保守" in why, "得到 %r（%s）" % (got, why))
    # ⑥d ★ 反向对照：把 P2 放进 SEVERITY_BLOCK_TIERS ⇒ ⑥c 必须精确变红
    ck("⑥d 白名单不含 P2/P3", not ({"P2", "P3"} & SEVERITY_BLOCK_TIERS),
       "得到 %r" % sorted(SEVERITY_BLOCK_TIERS))
    # ⑥e P1 但不是最高严重度 ⇒ REVIEW
    for rl in ("High", "Medium", "Low", "unknown", None):
        ck("⑥e P1+%r⇒REVIEW" % rl, severity_for("P1", rl)[0] == "REVIEW",
           "得到 %r" % (severity_for("P1", rl),))
    # ⑥f 层级缺失 ⇒ 保守 REVIEW（不靠「没给层级」蒙一个 BLOCK）
    ck("⑥f 无层级⇒REVIEW", severity_for(None, "Critical")[0] == "REVIEW",
       "得到 %r" % (severity_for(None, "Critical"),))

    print("tiering --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="P0–P3 分级（PRD §6.2 / §6.3）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
