"""P0–P3 四层分级的接线判据（任务拆解 目标12 · PRD §6.2 / §6.3）。

## 这一组判据在守什么

改前引擎里**只有 `priority_tier == "P0"` 一条分支**，其余就地硬编码「不是 P0 就是 P1」——
于是 `p_level=P2` 的 11 条、`p_level=P3` 的 4 条规则命中了也只报 P1，
PRD §6.3 的第二层（P1 安全准确性·语义）与第三层（P2 通识常识·多模态）**在代码里没有位置**，
P3「只出建议、不改结论」也没有位置。

判据分两组：
* **A 组（回归）**：P0 那条硬约束一个字没松 —— 改动最怕的就是把「命中即拦」搞软。
* **B 组（新行为）**：三层各有位置，且**层级真的影响结论**。
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from core.review_engine import decide          # noqa: E402
import core.tiering as T                       # noqa: E402


def load(name):
    return json.loads((ROOT / "samples" / name).read_text(encoding="utf-8"))


def item(tier, **kw):
    """造一条 risk_item。默认证据齐全（有 location + evidence_id），便于隔离层级变量。"""
    base = {
        "risk_id": "R1",
        "risk_type": "合规-医疗宣称",
        "priority_tier": tier,
        "status": "confirmed",
        "action": "review",
        "location": "caption",
        "evidence_id": "《内部样本库 v0》第 W-1.1 条",
        "reason": "测试用",
    }
    base.update(kw)
    return base


class TieringModuleTests(unittest.TestCase):
    """分级实现本身的判据（唯一口径 `core/tiering.py`）。"""

    def test_p_level_is_the_main_path(self):
        """四个层级都要认得出。改前只有 P0 认得出，P1/P2/P3 全塌成 P1。"""
        for p in ("P0", "P1", "P2", "P3"):
            self.assertEqual(T.tier_of(p_level=p)[0], p, p)

    def test_layer_text_must_not_override_p_level(self):
        """★ 反向对照：不许看层文案里有没有「P0」二字。

        改前生产代码就是 `"P0" if "P0" in layer else "P1"` ⇒
        `p_level=P2` 的规则只要 layer 里带个「P0」就被抬成 P0，反之全塌成 P1。
        """
        self.assertEqual(T.tier_of(p_level="P2", layer="P0 确定性匹配")[0], "P2")
        self.assertEqual(T.tier_of(p_level="P3", layer="规则层")[0], "P3")

    def test_unknown_p_level_does_not_guess_high(self):
        """未知 p_level 不许猜成 P0 —— 落 P1 兜底且**依据写明是兜底**。"""
        tier, why = T.tier_of(p_level="P9")
        self.assertEqual(tier, "P1")
        self.assertIn("兜底", why)

    def test_p0_has_no_confidence_flow(self):
        """PRD §6.6 明文：P0 不适用置信度分流。"""
        self.assertFalse(T.confidence_flow_applies("P0"))
        self.assertTrue(T.confidence_flow_applies("P1"))

    def test_highest_tier_wins(self):
        """PRD §6.3 执行规则4：多条命中按最高优先级输出（P0+P2 ⇒ BLOCK）。

        ★ 2026-10-19 第二轮（PRD §5.3.2 **rev 101**）：**仅 P3 ⇒ `none`**（结论不变）。
          rev 101 原文：「SUGGEST｜…**作为 PASS 的附属标签**，不阻断流程。｜随 PASS 一起流转，提示内容方。」
          ＋ §6.3 规则4「只有 SUGGEST 时，**最终状态为 PASS**（附 SUGGEST 建议）」。
          ⇒ P3 **不改结论**；它的痕迹落在 `suggestions[]`（见下面那条 decide 用例），不在 `effect` 上。
          ⚠️ 同日早些时候这里断言过 `suggest`（把 SUGGEST 当第四态），那是 rev 96 的读法，已作废。
        """
        self.assertEqual(T.decide_effect(["P0", "P2"])[0], "block")
        self.assertEqual(T.decide_effect(["P1", "P2"])[0], "review")
        self.assertEqual(T.decide_effect(["P3"])[0], "none")
        # ★ 反向对照（单调性）：P3 与任何更重的层级同时出现 ⇒ 仍由更重的那层定结论
        self.assertEqual(T.decide_effect(["P3", "P1"])[0], "review")
        self.assertEqual(T.decide_effect(["P3", "P2"])[0], "review")
        self.assertEqual(T.decide_effect(["P3", "P0"])[0], "block")


class DecideRegressionTests(unittest.TestCase):
    """A 组 · 回归：P0 硬约束不许松。"""

    def test_confirmed_p0_still_blocks(self):
        r = decide(load("block.json"))
        self.assertEqual(r["decision"], "BLOCK")

    def test_p0_without_evidence_is_still_review(self):
        """P0 命中但证据不齐 ⇒ REVIEW（原来就有这条，分层不许把它搞丢）。"""
        p = load("pass.json")
        p["risk_items"] = [item("P0", action="block", evidence_id=None, location=None)]
        self.assertEqual(decide(p)["decision"], "REVIEW")

    def test_no_hits_is_pass(self):
        self.assertEqual(decide(load("pass.json"))["decision"], "PASS")
        self.assertEqual(decide(load("review.json"))["decision"], "REVIEW")

    def test_p0_non_confirmed_is_review(self):
        p = load("pass.json")
        p["risk_items"] = [item("P0", status="uncertain")]
        r = decide(p)
        self.assertEqual(r["decision"], "REVIEW")
        self.assertTrue(any("uncertain" in x for x in r["decision_trace"]["reasons"]))


class TierDecisionTests(unittest.TestCase):
    """B 组 · 新行为：第二/第三/第四层各有位置。"""

    def test_p1_hit_reaches_review_and_says_so(self):
        """PRD §6.3 第二层：P1 命中 ⇒ 至少 REVIEW，且理由里看得出是 P1 触发的。"""
        p = load("pass.json")
        p["risk_items"] = [item("P1")]
        r = decide(p)
        self.assertEqual(r["decision"], "REVIEW")
        self.assertIn("p1_semantic_layer", r["decision_trace"]["reasons"])
        self.assertEqual(r["decision_trace"]["tier_trace"]["P1"], 1)

    def test_p2_hit_reaches_review_and_says_so(self):
        """PRD §6.3 第三层：P2 命中 ⇒ 至少 REVIEW，理由里标明是常识层。"""
        p = load("pass.json")
        p["risk_items"] = [item("P2")]
        r = decide(p)
        self.assertEqual(r["decision"], "REVIEW")
        self.assertIn("p2_commonsense_layer", r["decision_trace"]["reasons"])
        self.assertEqual(r["decision_trace"]["tier_trace"]["P2"], 1)

    def test_p3_advice_only_does_not_change_conclusion(self):
        """★ **只有 P3 ⇒ 结论 PASS ＋ 建议集**（PRD §5.3.2 rev101：SUGGEST 是 PASS 的附属标签）。

        这条用例的**防护意图一个字没改**：P3 是「非强制」层，**不许把整单拖成 REVIEW/BLOCK**
        （改前 P3 只要被填了 action=review 就会把结论拖成 REVIEW —— 与 §6.3 执行规则3 相反）。
        变的只是「干净那一档」的**落点与其痕迹**：
          · 落点：`decision` 仍是 **PASS**（不是第四态）；
          · 痕迹：`suggestions[]` 非空、`suggest_count ≥ 1`、`suggest_label` 为 True ——
            这三条就是「四态统计」第二个桶（PASS＋建议）的判定式，缺了它那个桶永远恒 0。
        """
        p = load("pass.json")
        p["risk_items"] = [item("P3", action="review", severity="REVIEW")]
        r = decide(p)
        self.assertEqual(r["decision"], "PASS", "只有 P3 时结论仍是 PASS（SUGGEST 是标签不是态）")
        self.assertNotIn(r["decision"], ("REVIEW", "BLOCK", "SUGGEST"),
                         "P3 既不许把整单拖成 REVIEW/BLOCK，也不许变成第四个 decision 值")
        self.assertGreaterEqual(r["suggest_count"], 1, "P3 必须留下建议集，否则「PASS 附建议」等于 PASS")
        self.assertTrue(r["suggest_label"], "PASS ＋ 建议 ⇒ 标签为 True（四态第二个桶的判定式）")
        self.assertIn("suggest_only_non_mandatory", r["decision_trace"]["reasons"])
        self.assertTrue(r["decision_trace"]["tier_trace"]["p3_advice_only"])

    def test_p3_does_not_rescue_a_review(self):
        """P3 也不能把已成立的 REVIEW 拉回 PASS（只许不改结论，不许撤销）。"""
        p = load("pass.json")
        p["risk_items"] = [item("P1", risk_id="R1"), item("P3", risk_id="R2")]
        self.assertEqual(decide(p)["decision"], "REVIEW")

    def test_p0_still_dominates_p3(self):
        """PRD §6.3 执行规则4：P0 与 P3 同时命中 ⇒ BLOCK。"""
        p = load("pass.json")
        p["risk_items"] = [item("P0", action="block", risk_id="R1"), item("P3", risk_id="R2")]
        r = decide(p)
        self.assertEqual(r["decision"], "BLOCK")
        self.assertEqual(r["decision_trace"]["tier_trace"]["P0"], 1)
        self.assertEqual(r["decision_trace"]["tier_trace"]["P3"], 1)

    def test_tier_trace_is_recorded_for_all_four(self):
        """四层计数都要落进 decision_trace —— 分层落了地必须看得出来。"""
        p = load("pass.json")
        p["risk_items"] = [item("P0", action="block", evidence_id=None, risk_id="R1"),
                           item("P1", risk_id="R2"), item("P2", risk_id="R3"),
                           item("P3", risk_id="R4")]
        tt = decide(p)["decision_trace"]["tier_trace"]
        self.assertEqual([tt["P0"], tt["P1"], tt["P2"], tt["P3"]], [1, 1, 1, 1])
        self.assertFalse(tt["p0_confidence_flow"])


class ConfidenceFlowTests(unittest.TestCase):
    """置信度分流的接线判据（任务拆解 目标11 · PRD §6.6）。

    改前现状原文就是「**无**」—— 三档策略在代码里没有任何位置。
    """

    def test_route_recorded_for_every_decision(self):
        """每次判定都要落 `confidence_route`，且 `calibrated` 恒为 false。"""
        for name in ("pass.json", "review.json", "block.json"):
            r = decide(load(name))
            cr = r["decision_trace"]["confidence_route"]
            self.assertIn("applies", cr, name)
            self.assertIs(cr.get("calibrated"), False,
                          "阈值是 PRD 政策值、不是标定值 —— calibrated 不许被写成 true")

    def test_p0_hit_is_never_downgraded_by_confidence(self):
        """★★ PRD §6.6：「P0 层级规则**不适用**置信度分流，命中即 BLOCK」。

        这条是**安全侧**判据：若拿掉 `route()` 里的 P0 override，
        一个 P0 命中 + 低置信度会被压成 REVIEW ⇒ **红线降级**。
        与 PRD §15「P0 层漏报率 = 0」直接冲突。
        """
        p = load("pass.json")
        p["risk_items"] = [item("P0", action="block")]
        r = decide(p)
        self.assertEqual(r["decision"], "BLOCK", "P0 命中被置信度压降级了")
        cr = r["decision_trace"]["confidence_route"]
        self.assertFalse(cr["applies"])
        self.assertTrue(cr["p0_override"])
        self.assertIn("不适用", cr["why"])

    def test_confirm_band_is_reachable_and_annotated(self):
        """§6.6 0.70–0.89 ⇒ REVIEW +「建议人工确认」。

        ⚠️ 本条断言曾写成 `band == "focus"`，被自证抓出来是**断言写错**：
        引擎「有一条 P1、证据不齐」算出的置信度是 **0.78**，落在 **confirm** 档。
        （0.78 = REVIEW 基线；证据不齐只在 `review_items` 非空时再扣 0.05，
         而该扣分条件与「这条不齐」是同一件事，不会重复扣。）
        """
        p = load("pass.json")
        p["risk_items"] = [item("P1", evidence_id=None, location=None)]
        r = decide(p)
        cr = r["decision_trace"]["confidence_route"]
        self.assertEqual(r["decision"], "REVIEW")
        self.assertTrue(cr["applies"], "非 P0 单必须走分流")
        self.assertEqual(cr["band"], "confirm")
        self.assertEqual(cr["annotate"], "建议人工确认")
        self.assertIn("建议人工确认", r["summary"])

    def test_focus_band_rule_is_correct_at_module_level(self):
        """PRD **v1.3** §6.6「<0.60 且未命中 P0 ⇒ 输出 PASS」——**在模块层直接判**。

        ★ 为什么不在 `decide()` 层造这条：**当前引擎造不出来**。
        引擎把 REVIEW 单的置信度截断到 [0.70, 0.89] ⇒ **最低 0.70，都 ≥ 0.60**
        ⇒ `focus` 档在现有引擎下**不可达**。
        这是**实情**，判据照实写 —— 不为了「三档都测到」去编一个到不了的输入。
        到不到得了是**引擎截断/标定**的事，策略对不对是**本模块的事**。

        ⚠️ v1.2 时这一档是「REVIEW + 不确定，建议人工重点看」；**v1.3 改成 PASS**
        —— 方向相反（fail-open）。所以这条用例同时钉住两件事：
        ① 结论确实变成 PASS；② **放行必须留 machine-readable 痕迹**（`warning`）。
        """
        import sys as _s
        _s.path.insert(0, str(ROOT))
        from core import confidence_flow as CF
        for c in (0.59, 0.5, 0.0):
            rr = CF.route("REVIEW", c, tiers=["P1"])
            self.assertEqual(rr["band"], "focus", c)
            self.assertEqual(rr["decision"], "PASS", c)          # ★ v1.3
            self.assertIsNone(rr["annotate"])                    # 不再写那句提示
            self.assertIn("低置信度放行", rr["warning"] or "", c)
        # ★ 边界：0.60 属 confirm（仍 REVIEW），0.59 才是 focus
        self.assertEqual(CF.route("REVIEW", 0.60, tiers=["P1"])["band"], "confirm")
        self.assertEqual(CF.route("REVIEW", 0.60, tiers=["P1"])["decision"], "REVIEW")

    def test_engine_non_p0_confidence_never_reaches_focus_band(self):
        """★ 反向登记：把「focus 档当前不可达」这件事**钉成判据**。

        哪天有人调了启发式的扣分逻辑、让非 P0 单真的掉进 <0.70，
        本用例会**变红** —— 那正是该回来看「标定做了没有」的时候，
        而不是让它悄悄发生。
        """
        lows = []
        for tail in ([item("P1")],
                     [item("P1", evidence_id=None, location=None)],
                     [item("P0", status="uncertain")],
                     [item("P1", evidence_id=None, location=None),
                      item("P1", status="uncertain", risk_id="R2")]):
            p = load("pass.json")
            p["risk_items"] = tail
            r = decide(p)
            if r["decision"] == "REVIEW":
                lows.append(r["confidence"])
        self.assertTrue(lows, "一个 REVIEW 单都没造出来，判据失去意义")
        # ★ PRD v1.3 的 focus 边界是 **0.60**（v1.2 是 0.70）——
        #   守卫的线必须跟着政策走，否则"守着一个已经不存在的边界"。
        self.assertGreaterEqual(min(lows), 0.60,
                                "非 P0 单掉进了 <0.60（v1.3 的 focus 档）—— 引擎变了，"
                                "该回来看标定与截断（PRD v1.3 §6.6）")

    def test_downgrade_is_recorded_so_it_can_be_audited(self):
        """★ 分流把结论压过时，**原结论必须看得见** —— 否则事后分不清
        「这单本来是 BLOCK」与「本来就是 REVIEW」。"""
        import sys as _s
        _s.path.insert(0, str(ROOT))
        from core import confidence_flow as CF
        # 造一次「BLOCK 被 confirm 档压成 REVIEW」的分流结果，直接查 route 的记账
        rr = CF.route("BLOCK", 0.80, tiers=["P1"])
        self.assertEqual(rr["decision_before"], "BLOCK")
        self.assertEqual(rr["decision"], "REVIEW")
        self.assertEqual(rr["effect"], "force_review")

    def test_p3_advice_does_not_trigger_confidence_downgrade(self):
        """只有 P3 ⇒ **PASS ＋ 建议**，**置信度分流也不许把它拉成 REVIEW**（§5.3.2：不阻断）。

        ★ 2026-10-19 第二轮（PRD §5.3.2 rev101：SUGGEST 是 PASS 的附属标签）：
          落点回到 **PASS**（同日早些时候曾落 SUGGEST，那是 rev 96 读法），防护意图一个字没改 ——
          PASS／建议都属 §6.6「直接输出结论」那一档（0.90–0.99），分流不改结论。
          同时钉住**标签仍在**：结论是 PASS 但 `suggest_label` 必须为 True，否则
          「PASS 附建议」在数据上退化成「PASS」，「四态」第二个桶就永远数不出来。
        """
        p = load("pass.json")
        p["risk_items"] = [item("P3", action="review")]
        r = decide(p)
        self.assertEqual(r["decision"], "PASS")
        self.assertTrue(r["suggest_label"], "PASS 带建议 ⇒ 标签为 True")
        self.assertGreaterEqual(r["confidence"], 0.90, "PASS／建议应落在直接出结论那一档")
        self.assertNotEqual(r["decision"], "REVIEW", "分流把不阻断的建议拉成了 REVIEW")

    def test_summary_gets_the_prd_annotation_and_is_idempotent(self):
        """标注语逐字取 PRD §6.6；重复追加不叠加。"""
        import sys as _s
        _s.path.insert(0, str(ROOT))
        from core import confidence_flow as CF
        r = CF.route("BLOCK", 0.80, tiers=["P1"])
        s = CF.annotate_summary("【审查结论：REVIEW】", r)
        self.assertIn("建议人工确认", s)
        self.assertEqual(CF.annotate_summary(s, r), s)


if __name__ == "__main__":
    unittest.main()
