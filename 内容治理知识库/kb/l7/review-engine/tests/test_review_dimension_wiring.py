"""「问题维度」的**接线**判据（`review.py` findings → `risk_items` → 报告）。

## 这一组在守什么（2026-10-12 实测缺陷，不是预防性设计）

PRD **§5.3**「Agent 输出三态结论时，必须**先标注问题所属维度**」／
PRD **§8.3**「完整问题清单，**每条包含：维度**、位置、问题描述、原因、依据文档链接、修改建议」
＋「**按维度分组展示**」。

链路上一共有三棒：

| # | 位置 | 状态（2026-10-12 改前） |
|---|---|---|
| ① | `review()` 返回前逐条盖章（`risk_category`） | ✅ 有（`trace.risk_category` 实测 `with_dimension: 3`） |
| ② | `with_kb_evidence._to_risk_item` | ✅ 搬了 |
| ③ | **`review.py::_finding_to_risk_item`** | ❌ **没搬** ← 本组判据钉的就是这一棒 |

③ 断掉的代价可量化（现读 `kb/l7/reports/*.json`，282 份 / 725 条 `risk_items`）：

```
risk_category        为 None : 725 / 725
risk_category_basis  非空    :   0 / 725      ← 盖过章就必然是非空串 ⇒ 这个 0 即证明没走到这一步
```

而 `report_memory.render_markdown` 正是按这一格分组（读不到才回落 `risk_type`）
⇒ **PRD §5.3/§8.3「按维度分组展示」在真报告上从未生效**。

## 两条反向对照（本组判据的价值全在这里）

1. **不许蒙**：未映射的类别（`原则性错误` / `文化禁忌` / `未分类` / `unknown`）
   ⇒ `risk_category` 必须是 `None`、且 `basis` 必须**带出来**说明「待裁」。
   把 ③ 写成「读不到就给个默认维度」⇒ 对应用例**精确变红**。
2. **优先级**：分组必须**维度优先**、`risk_type` 只在维度缺席时兜底。
   把 `render_markdown` 的分组键换回 `risk_type` ⇒ 对应用例**精确变红**。
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 本文件在 `<root>/kb/l7/review-engine/tests/` ⇒ 往 3 层到 `<root>`
ROOT = HERE.parents[3]
SCRIPTS = ROOT / "kb" / "l7" / "skills" / "kb-content-review" / "scripts"

# ★★ 必须在 import 之前设：`review.py` 顶部有**解释器守卫** ——
#    没有 `KB_INTERP_OK` 时它会 `os.execve` 把自己重跑一遍；
#    被 import 时那会把**测试进程**exec 掉 ⇒ pytest 卡在 collection。
#    （同 `test_review_report_robustness.py` 的处置；不改生产代码来迁就测试。）
import os                                                      # noqa: E402
os.environ["KB_INTERP_OK"] = "1"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE.parent))                           # 为了 import core.report_memory

import importlib.util                                          # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__name__ = name
    spec.loader.exec_module(mod)
    return mod


R = _load("kb_review_impl_dw", SCRIPTS / "review.py")
RC = _load("kb_risk_category_dw", SCRIPTS / "risk_category.py")

from core.report_memory import render_markdown                   # noqa: E402


def _finding(**kw):
    """造一条**最小** finding，并**用真模块盖章**（不是手写 `risk_category`）。

    ★ 用真模块的理由：手写维度只能证明「搬运」这一段；用真盖章才能证明
      「政策件 → 类别 → 维度」这一段也是通的（今天出过两次路径 bug 就在这一段）。
    """
    f = {
        "severity": "REVIEW",
        "layer": "规则层",
        "category": "功效宣称",
        "sub": "催乳与通乳宣称",
        "position": "全文",
        "excerpt": "x",
        "matched_term": "x",
        "anchor": "#某表/recX/某字段",
        "source_sha256": "a" * 64,
        "article_no": "W-1.1",
        "rule_id": "r-x",
        "library": "措辞表达库",
        "reason": "测试用",
        "advice": None,
        "advice_note": None,
        "fact_or_inference": "事实",
        "confidence": "中",
        "classification_basis": "测试",
    }
    f.update(kw)
    # 与 `review()` 返回前的盖章**同一个函数**（不是复刻一份口径）
    if "risk_category" not in kw:
        RC.stamp(f)
    return f


REG = {"citation_contract": {"libraries": {}}, "approvers": {}}


class DimensionWiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    # ── ③ 那一棒：findings → risk_items ────────────────────────────────────
    def test_finding_to_risk_item_carries_dimension(self):
        """★ 核心：盖章后的 finding 搬进 `risk_items` 时，两格必须**都在**。

        改前实测：`risk_category` = None、`risk_category_basis` = None（725/725）。
        **把这两行删掉 ⇒ 本用例精确变红。**
        """
        f = _finding(category="功效宣称", sub="催乳与通乳宣称")
        self.assertEqual(f["risk_category"], "合规", "夹具前提：真盖章给出「合规」")
        item = R._finding_to_risk_item(f, 1)
        self.assertEqual(item.get("risk_category"), "合规",
                         "risk_items 丢了维度 ⇒ PRD §5.3/§8.3 的两格少一格")
        self.assertTrue(item.get("risk_category_basis"),
                        "维度搬了、出处没搬 ⇒ 无法复核它凭什么算「合规」")

    def test_unmapped_category_keeps_none_and_carries_basis(self):
        """★★ 反向对照：未映射的类别**必须留 None**，且必须把「待裁」带出来。

        把搬运写成「读不到就给个默认维度」（蒙维度）⇒ 本用例精确变红。
        库规：**蒙错比留空更坏**（留空人会去补，错值人不会回头看）。
        """
        f = _finding(category="原则性错误", sub="事实性错误")
        self.assertIsNone(f["risk_category"], "夹具前提：该类未映射 ⇒ 盖章留空")
        item = R._finding_to_risk_item(f, 1)
        self.assertIsNone(item.get("risk_category"), "未映射的类别被蒙了一个维度")
        self.assertIn("待裁", str(item.get("risk_category_basis")),
                      "留空了却没写为什么 ⇒ 下一个人会以为是漏跑")

    # ── 报告里看得见（PRD §8.3「每条包含：维度、位置…」）──────────────────
    def _write(self, findings):
        R.write_report({"state": "REVIEW", "findings": findings,
                        "unmet_citation": [], "trace": {}}, REG, self.dir, "R-1", apply=True)
        return (Path(self.dir) / "R-1.review.md").read_text(encoding="utf-8")

    def test_report_renders_dimension_line(self):
        """完整问题清单每条要印出「维度」。改前**整份报告没有「维度」二字**。"""
        txt = self._write([_finding() for _ in range(3)])
        self.assertIn("- 维度：**合规**", txt, "报告没印维度")
        # ★ 只增不改：位置仍在标题行、其余各行不变
        self.assertIn("【功效宣称-催乳与通乳宣称】全文", txt, "标题行被改动了")

    def test_report_marks_unmapped_as_pending_not_fabricated(self):
        """反向对照：未映射的在**人看的报告**里也必须写「未标注维度（待裁）」，不许编一个。"""
        fs = [_finding() for _ in range(2)]
        fs.append(_finding(category="文化禁忌", sub="文化歧义"))
        txt = self._write(fs)
        self.assertIn("未标注维度（待裁）", txt, "未映射的类别在报告里没被如实标注")
        self.assertNotIn("- 维度：**合规**\n- 维度：**合规**", txt.replace("\n\n", "\n"))

    # ── PRD §5.3.2「问题 ≥ 3 个时，只输出分类汇总」：分的是**维度** ──────────
    def test_render_summary_groups_by_dimension(self):
        """★ ≥3 条时汇总行必须是「· 合规类问题：N 个」—— PRD §5.3.2 逐字示例的口径。

        改前按 `f["category"]`（库内类别）分组 ⇒ 印「· 功效宣称类问题：1 个」，
        与 PRD 示例**不是同一样东西**。
        **把分组键换回 `f["category"]` ⇒ 本用例精确变红。**
        """
        fs = [_finding(category="功效宣称", sub="催乳与通乳宣称"),
              _finding(category="绝对化与安全承诺", sub="虚假安全承诺"),
              _finding(category="背书与资质", sub="监管认证宣称")]
        txt = R.render({"state": "BLOCK", "findings": fs, "trace": {}}, REG)
        self.assertIn("· 合规类问题：3 个", txt, "没按维度汇总")
        self.assertNotIn("功效宣称类问题", txt, "仍在按库内类别汇总")

    def test_render_summary_unmapped_gets_own_bucket_last(self):
        """★★ 反向对照：未映射的类别**单成一桶**（不并进「合规」），且**排在最后**。

        把桶并进任一个真维度、或把桶名写成四维之一 ⇒ 本用例精确变红。
        库规：**「不知道」不许当「合规」**（蒙错比留空更坏）。
        """
        fs = [_finding(category="功效宣称", sub="催乳与通乳宣称"),
              _finding(category="原则性错误", sub="事实性错误"),
              _finding(category="文化禁忌", sub="文化歧义")]
        txt = R.render({"state": "REVIEW", "findings": fs, "trace": {}}, REG)
        self.assertIn("· 合规类问题：1 个", txt, "映射到维度的那一条没进「合规」")
        self.assertIn("· 未标注维度类问题：2 个", txt, "未映射的两条没单成一桶")
        body = [l for l in txt.splitlines() if l.startswith("· ")]
        self.assertTrue(body and body[-1].startswith("· 未标注维度"),
                        "桶没排在最后：%r" % (body,))

    # ── PRD §5.3「按维度分组展示」：维度优先、risk_type 兜底 ────────────────
    def test_report_memory_groups_by_dimension_not_risk_type(self):
        """★ 端到端：分组键必须是**维度**。

        `功效宣称`（⇒ 合规）与 `品牌一致性`（⇒ 措辞表达）两条，其 `risk_type`
        （`功效宣称-催乳与通乳宣称` / `品牌一致性-禁区（库内反例条款）`）都**不等于**维度名
        ⇒ 分组标题只能是「合规」「措辞表达」。
        **把 `report_memory` 的分组键换回 `risk_type` ⇒ 本用例精确变红。**
        """
        items = [R._finding_to_risk_item(_finding(category="功效宣称", sub="催乳与通乳宣称"), 1),
                 R._finding_to_risk_item(_finding(category="品牌一致性",
                                                  sub="禁区（库内反例条款）"), 2)]
        md = render_markdown({"review_id": "R-DIM", "decision": "REVIEW", "risk_items": items})
        self.assertIn("### 合规", md, "没按维度分组")
        self.assertIn("### 措辞表达", md, "没按维度分组")
        self.assertNotIn("### 功效宣称-催乳与通乳宣称", md, "分组回落成了库内类别")


if __name__ == "__main__":
    unittest.main()
