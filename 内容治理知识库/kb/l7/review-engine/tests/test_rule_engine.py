import os
import sys
import unittest

# ★ 2026-10-09 修：原先直接 `from core.rule_engine import ...` —— 而 `core/` 下**没有
#   `__init__.py`**（不是包），且这里**没有把 `core/` 加进 `sys.path`** ⇒ 无论从哪个目录跑
#   都必然 `ModuleNotFoundError: No module named 'core'`。
#   代价不是"这条判据不好看"：**规则层（`rule_engine`）整整一层没有任何可跑的判据** ——
#   改坏了没人告诉你，与当天反复出现的「改了但没人读」是同一个形状。
#   修法与同目录能跑的判据同形（见 `test_kb_hits.py` 的 `HERE/CORE` 三行）。
#   ⚠️ 要加的是**上一级 `review-engine/`**（`core` 是**包**，它下面有 `__init__.py`）
#      ⇒ `from core.rule_engine import ...` 才解析得到；加 `core/` 自己**没用**（第一版就这么写错的）。
#      与能跑的判据同形：`sys.path.insert(0, str(Path(__file__).parents[1]))`。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rule_engine import scan_text  # noqa: E402


class RuleEngineTests(unittest.TestCase):
    def test_health_and_ranking_candidates_are_review(self):
        findings = scan_text("This pump treats plugged ducts and is the best-selling choice.", product_line="吸奶器", channel="TikTok")
        self.assertEqual(len(findings), 2)
        self.assertTrue(all(item["action"] == "review" for item in findings))
        self.assertTrue(all(item["status"] == "uncertain" for item in findings))
        self.assertTrue(all(item["evidence_id"].startswith("TEXT:") for item in findings))

    def test_warning_context_is_uncertain(self):
        findings = scan_text("Warning: do not use this product to treat plugged ducts.", product_line="吸奶器", channel="TikTok")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["status"], "uncertain")

    def test_unrelated_product_line_is_ignored(self):
        findings = scan_text("This is the best-selling choice.", product_line="其他", channel="TikTok")
        self.assertEqual(findings, [])

    def test_candidates_are_marked_non_authoritative(self):
        """种子扫描器的输出必须自带「非真源」标注 —— 否则它会被当成库内依据用。

        背景（2026-10-01）：本扫描器扫的 5 条 US 种子规则与库内 509 条规则是
        **两份不同编号体系**的清单，曾出现「依据侧 10 处 BLOCK、种子扫描 0 候选 →
        倾向 PASS」的相反结论。带 `authoritative=false` 是为了让下游（裁决引擎、
        报告、人工复核）一眼看出这一条**不能**顶替带条款号的依据。
        """
        findings = scan_text("This pump treats plugged ducts.", product_line="吸奶器", channel="TikTok")
        self.assertTrue(findings)
        for item in findings:
            self.assertIs(item["authoritative"], False)
            self.assertIn("非规则真源", item["authority"])
            self.assertEqual(item["superseded_by"], "kb/l3/candidates/rules.jsonl")


if __name__ == "__main__":
    unittest.main()
