"""报告渲染的健壮性判据（`kb-content-review/scripts/review.py::write_report`）。

## 这一组判据在守什么（2026-10-10 实测事故）

**全链在「③ 出结论」停住**：`review_run.sh` 报
`引擎输出无法解析 / 引擎退出码 2`，而真实原因是 `review.py:1392` 抛 `KeyError: 'l0_entry_url'`
—— **不是没查到，是报告写不出来**。

病灶的形状值得记下来（**判据与取值各写一遍，必然漂移**）：

```python
# 判据：带 get + 回落 —— 宽松
if (f.get("l0_entry_url") or (f.get("verbatim_source") or {}).get("entry_url"))
# 取值：直取第一个来源 —— 严格
{f['l0_entry_url']}
```

⇒ 当 **`l0_entry_url` 这个键本身不存在**、而 `verbatim_source.entry_url` 有值时：
**判据放行、取值 KeyError**。

**为什么一直没被发现**：`write_report` 只在 **findings ≥ 3** 时被调用
（`review.py::main()` 的 `len(res["findings"]) >= 3 or a.report_dir`）
⇒ **1–2 条问题的单子根本走不到那一行**。实测：同一段文案，
2 条时正常、**加一句变 3 条就崩**。

⇒ 本组判据因此**必须用 ≥3 条 findings 构造**，否则它自己也会「走不到那一行」。
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 本文件在 `<root>/kb/l7/review-engine/tests/` ⇒ 往上退 3 层才到 `<root>`
# （退 2 层会得到 `<root>/kb`，再拼 `kb/…` 就成了 `<root>/kb/kb/…` —— 实测踩过）
ROOT = HERE.parents[3]
SCRIPTS = ROOT / "kb" / "l7" / "skills" / "kb-content-review" / "scripts"

# ★★ 必须在 import 之前设：`review.py` 顶部有**解释器守卫**（:20-39）——
#    没有 `KB_INTERP_OK` 时它会 `os.execve` **把自己重跑一遍**。
#    在脚本形态下那是对的（换到 `kb/.kb-python` 指定的解释器）；
#    但**被 import 时**它会直接把测试进程 exec 掉 ⇒ pytest 卡在 collection、永远不返回
#    （实测：卡满 120 秒无输出，exit 0 但一条用例都没跑）。
#    ⇒ 测试里**先声明解释器已合格**再 import。**不改生产代码来迁就测试。**
import os                                                      # noqa: E402
os.environ["KB_INTERP_OK"] = "1"
sys.path.insert(0, str(SCRIPTS))

import importlib.util                                     # noqa: E402

_spec = importlib.util.spec_from_file_location("kb_review_impl", SCRIPTS / "review.py")
R = importlib.util.module_from_spec(_spec)
R.__name__ = "kb_review_impl"
_spec.loader.exec_module(R)


def _finding(**kw):
    """造一条**最小**的 finding：只要 write_report 渲染时用得到的那几格。"""
    f = {
        "severity": "REVIEW",
        "layer": "规则层",
        "category": "合规",
        "sub": "",
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
    return f


REG = {"citation_contract": {"libraries": {}}, "approvers": {}}


class WriteReportRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _report_path(self):
        """报告的真实落点。

        ⚠️ `write_report` **返回的是相对路径**（`../../../../…/R-1.review.md`）——
        本机 `/var` 是 `/private/var` 的软链，`tempfile` 给的是 `/var/...` 形态，
        于是相对路径要爬一长串 `../`。**按返回的路径直接 `exists()` 会得到假阴性**
        （实测：文件明明在目录里，`Path(p).exists()` 却是 False）。
        ⇒ 判据认**目录里的实际文件**，不认那个相对路径。
        """
        return Path(self.dir) / "R-1.review.md"

    def _write(self, findings):
        # `unmet_citation` 是 report_memory 契约要求的键（`write_report` 会读它）；
        # 缺了会自己在 :1416 抛 KeyError —— 那是**夹具不全**，不是被测缺陷。
        return R.write_report({"state": "REVIEW", "findings": findings,
                               "unmet_citation": [], "trace": {}},
                              REG, self.dir, "R-1", apply=True)

    def test_three_findings_baseline_writes(self):
        """基线：3 条 findings 能渲染出报告（**没有它，下面的判据会走不到那一行**）。"""
        self._write([_finding() for _ in range(3)])
        self.assertTrue(self._report_path().exists())

    def test_missing_l0_entry_url_key_does_not_crash(self):
        """★ 回归：**`l0_entry_url` 键不存在**、但 `verbatim_source.entry_url` 有值 ⇒ 不许崩。

        这正是 2026-10-10 那次全链停住的那一条（判据放行、取值 KeyError）。
        把取值改回直取 `f['l0_entry_url']` ⇒ 本用例**精确变红**（KeyError）。
        """
        fs = [_finding() for _ in range(2)]
        fs.append(_finding(layer="规则层（依据不可逐字回源）",
                           verbatim_source={"path": "kb/l0/x.json", "field": "命中片段",
                                            "entry_url": "https://example.feishu.cn/base/a?record=b"}))
        # 确认构造出了目标形状：**没有** l0_entry_url 键、**有** verbatim_source.entry_url
        self.assertNotIn("l0_entry_url", fs[2])
        self.assertTrue(fs[2]["verbatim_source"]["entry_url"])
        self._write(fs)                           # ← 修复前这里抛 KeyError
        txt = self._report_path().read_text(encoding="utf-8")
        self.assertIn("example.feishu.cn", txt, "回落来源的直链没被渲染出来")

    def test_entry_url_none_renders_no_link_line(self):
        """`l0_entry_url` 显式是 None、`verbatim_source` 也是 None ⇒ **不写那一行**（取不到不编）。"""
        fs = [_finding() for _ in range(2)]
        fs.append(_finding(l0_entry_url=None, verbatim_source=None))
        self._write(fs)
        txt = self._report_path().read_text(encoding="utf-8")
        self.assertNotIn("L0 飞书直链", txt, "取不到直链却写了一行 —— 库规：宁可空着也不编")

    def test_direct_link_wins_over_fallback(self):
        """两个来源都有 ⇒ 用**直接来源**（与判据的 or 顺序一致）。"""
        fs = [_finding() for _ in range(3)]
        fs[0]["l0_entry_url"] = "https://direct.example/1"
        # `verbatim_source` 要带 `path`/`field` —— 报告会渲染「原文出处」那一行（`:1384`）。
        # 缺了会 KeyError；那是**夹具不全**，不是被测缺陷（实测踩过）。
        fs[0]["verbatim_source"] = {"path": "kb/l0/x.json", "field": "命中片段",
                                    "entry_url": "https://fallback.example/2"}
        self._write(fs)
        txt = self._report_path().read_text(encoding="utf-8")
        self.assertIn("direct.example", txt)
        self.assertNotIn("fallback.example", txt)


if __name__ == "__main__":
    unittest.main()
