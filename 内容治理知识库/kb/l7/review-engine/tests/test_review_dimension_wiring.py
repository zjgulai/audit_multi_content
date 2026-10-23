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
    # ★★ 2026-10-19（Owner：「所属类别/所属子类」统一到 A3 12 类）：
    #   夹具也带上 A3 两格（真单的 `risk_items` 都带 —— `review.py::stamp_taxonomy` 盖的）。
    #   不带的后果：分类汇总只能落「未归类」，量不到 A3 的那几行。
    if "taxonomy_category" not in kw:
        f["taxonomy_category"] = kw.pop("taxonomy_category", None) or "合规与受监管宣称"
        f.setdefault("taxonomy_subcategory", "生理功效与效果承诺")
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

        ★★ 2026-10-20 改夹具（**判据一个字没动**）：Owner 已裁定「必须归类」，
           `原则性错误` / `文化禁忌` 从 `unmapped` 移进了 `map`（见
           `kb/l7/registry/risk-category-policy.json`）⇒ 它们**不再是**未映射类。
           仍留在 `unmapped` 的是 `unknown`（反例体系里「还没判」，实测 214 行）——
           拿它当夹具，"蒙维度即红" 这条防护照样成立。
        """
        f = _finding(category="unknown", sub="")
        self.assertIsNone(f["risk_category"], "夹具前提：该类未映射 ⇒ 盖章留空")
        item = R._finding_to_risk_item(f, 1)
        self.assertIsNone(item.get("risk_category"), "未映射的类别被蒙了一个维度")
        self.assertIn("待裁", str(item.get("risk_category_basis")),
                      "留空了却没写为什么 ⇒ 下一个人会以为是漏跑")

    def test_owner_20261020_case_vocab_now_mapped(self):
        """★ 2026-10-20（Owner：「未归类问题：2 个，不属于所属类别12类中的吗？

        图片提取规则的时候要归类」）：这两类**必须给出维度**，不再留空。
        反向对照：把 `map` 里这两条删掉 ⇒ 本用例精确变红。
        """
        for cat in ("原则性错误", "文化禁忌"):
            f = _finding(category=cat, sub="")
            self.assertEqual(f["risk_category"], "措辞表达",
                             "%s 仍未映射 —— Owner 2026-10-20 已要求归类" % cat)
            item = R._finding_to_risk_item(f, 1)
            self.assertEqual(item.get("risk_category"), "措辞表达",
                             "%s 的维度没搬进 risk_items" % cat)

    # ── 报告里看得见（PRD §8.3「每条包含：维度、位置…」）──────────────────
    def _write(self, findings):
        R.write_report({"state": "REVIEW", "findings": findings,
                        "unmet_citation": [], "trace": {}}, REG, self.dir, "R-1", apply=True)
        return (Path(self.dir) / "R-1.review.md").read_text(encoding="utf-8")

    def test_report_renders_dimension_line(self):
        """★ 2026-10-19（Owner：「报告要同步 卡上 12 类呀，**整个知识库都要同步**」）：
        **四维那一行整行撤掉**，报告里只留 A3 那一格 `- 所属类别 / 所属子类：**…**`。

        防护意图照旧：完整清单里**每条必须能看出它归哪一类**（不许只有标题行、正文没有）；
        新增半条反向对照：**`- 维度：**` 不许再出现**（两套分类并排正是 Owner 报的那个问题）。
        """
        txt = self._write([_finding() for _ in range(3)])
        self.assertNotIn("- 维度：", txt, "四维那一行又回来了（报告只许有一个轴：A3 12 类）")
        self.assertIn("- 所属类别 / 所属子类：**合规与受监管宣称** / 生理功效与效果承诺", txt,
                      "报告没印「所属类别 / 所属子类」")
        self.assertIn("【合规与受监管宣称-生理功效与效果承诺】全文", txt, "标题行没换成 A3")

    def test_report_marks_unmapped_as_pending_not_fabricated(self):
        """反向对照：盖不到 A3 的条目在**人看的报告**里必须写 `未归类`，**不许编一个类**。

        ★ 2026-10-19：原先这条盯的是四维的「未标注维度（待裁）」。四维撤掉后，
          同一件防护换到 A3 上 —— 兜底类名就是 12 类里的 `未归类`（**不是**四维的桶名）。
        """
        fs = [_finding() for _ in range(2)]
        fs.append(_finding(category="文化禁忌", sub="文化歧义", taxonomy_category=None,
                           taxonomy_subcategory=None))
        txt = self._write(fs)
        self.assertIn("未归类", txt, "盖不到 A3 的条目在报告里没被如实标成 `未归类`")
        self.assertNotIn("未标注维度", txt, "四维的桶名「未标注维度」又出现了")

    # ── PRD §5.3.2「问题 ≥ 3 个时，只输出分类汇总」：分的是**维度** ──────────
    def test_render_summary_groups_by_dimension(self):
        """★ ≥3 条时汇总行必须是 **PRD §5.3.4 的形状**：`· 合规类：N 个 · …`（一行、按维度）。

        ⚠️ **2026-10-19 更正本用例的引文口径**：它原来写「PRD §5.3.2 逐字示例是
        `· 合规类问题：3 个`」——**引错了**。实际核过 PRD v1.4：
          · §5.3.2 那张内嵌表（`xcdTpv`）只有 `状态/定义/动作` 三列，**没有**分类汇总样张；
          · 样张在 **§5.3.4**，逐字是 `· 合规类：X 个 · 消费者安全类：X 个 · 措辞类：X 个`
            （一行、`·` 分隔、**没有「问题」二字**）。
        ⇒ 断言随之改成 PRD 原样。**把分组键换回 `f["category"]`（库内类别）⇒ 本用例精确变红。**
        """
        fs = [_finding(category="功效宣称", sub="催乳与通乳宣称"),
              _finding(category="绝对化与安全承诺", sub="虚假安全承诺"),
              _finding(category="背书与资质", sub="监管认证宣称")]
        txt = R.render({"state": "BLOCK", "findings": fs, "trace": {}}, REG)
        # ★★ 2026-10-19：轴 = **A3 12 类**（`· <所属类别>类问题：N 个`，每类一行）
        self.assertIn("· 合规与受监管宣称类问题：3 个", txt, "没按 A3 汇总")
        self.assertNotIn("功效宣称类", txt, "仍在按 A1 库内类别汇总")
        self.assertNotIn("合规类问题", txt, "仍在按 A2 四维汇总")
        self.assertNotRegex(txt, r"个 · [^\n]*类问题：", "汇总被缩成一行了（应每类一行）")

    def test_render_summary_unmapped_gets_own_bucket_last(self):
        """★★ 反向对照：未映射的类别**单成一桶**（不并进「合规」），且**排在最后**。

        把桶并进任一个真维度、或把桶名写成四维之一 ⇒ 本用例精确变红。
        库规：**「不知道」不许当「合规」**（蒙错比留空更坏）。
        """
        # 一条有 A3（真单里规则层命中就有），两条**没有**（模型侧/反例层盖不到）⇒ 必须进兜底类
        fs = [_finding(category="功效宣称", sub="催乳与通乳宣称"),
              _finding(category="原则性错误", sub="事实性错误",
                       taxonomy_category=None, taxonomy_subcategory=None),
              _finding(category="文化禁忌", sub="文化歧义",
                       taxonomy_category=None, taxonomy_subcategory=None)]
        txt = R.render({"state": "REVIEW", "findings": fs, "trace": {}}, REG)
        self.assertIn("· 合规与受监管宣称类问题：1 个", txt, "带 A3 的那条没进它的类")
        self.assertIn("· 未归类问题：2 个", txt, "没有 A3 的两条没并进「未归类」兜底类")
        # 每类一行：兜底类必须是**最后一个汇总行**
        rows = [l for l in txt.splitlines() if l.startswith("· ")]
        self.assertTrue(rows and rows[-1].startswith("· 未归类问题：2 个"),
                        "兜底类没排在最后：%r" % (rows,))

    # ── PRD §5.3「按维度分组展示」：维度优先、risk_type 兜底 ────────────────
    def test_report_memory_groups_by_dimension_not_risk_type(self):
        """★ 端到端：分组键必须是 **A3 12 类**（既不是库内 `risk_type`，也不是 A2 四维）。

        ★ 2026-10-19（Owner：「报告要同步 卡上 12 类呀，**整个知识库都要同步**」）：
          这条用例原先钉的是四维（`合规` / `措辞表达`）。四维撤掉后，同一件防护换成 A3：
          两条条目分别给 `合规与受监管宣称` 与 `推广与价格透明`，其 `risk_type`
          （`功效宣称-…` / `品牌一致性-…`）都**不等于**类名 ⇒ 分组标题只能是那两个类名。
        **把 `report_memory` 的分组键换回 `risk_type` 或换回四维 ⇒ 本用例精确变红。**
        """
        items = [R._finding_to_risk_item(_finding(category="功效宣称", sub="催乳与通乳宣称"), 1),
                 R._finding_to_risk_item(_finding(category="品牌一致性", sub="禁区（库内反例条款）",
                                                  taxonomy_category="推广与价格透明",
                                                  taxonomy_subcategory="促销紧迫感与施压表述"), 2)]
        md = render_markdown({"review_id": "R-DIM", "decision": "REVIEW", "risk_items": items})
        self.assertIn("### 合规与受监管宣称", md, "没按 A3 12 类分组")
        self.assertIn("### 推广与价格透明", md, "没按 A3 12 类分组")
        self.assertNotIn("### 功效宣称-催乳与通乳宣称", md, "分组回落成了库内类别")
        self.assertNotIn("### 措辞表达", md, "分组又回到 A2 四维")
        self.assertNotIn("### 合规\n", md, "分组又回到 A2 四维（裸「合规」）")


if __name__ == "__main__":
    unittest.main()
