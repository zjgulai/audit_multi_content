import json
import sys
import re
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.review_engine import decide


ROOT = Path(__file__).parents[1]


def load(name):
    return json.loads((ROOT / "samples" / name).read_text(encoding="utf-8"))


class ReviewEngineTests(unittest.TestCase):
    def test_pass(self):
        result = decide(load("pass.json"))
        self.assertEqual(result["decision"], "PASS")
        self.assertIn("PASS", result["summary"])

    def test_review_for_uncertain_item(self):
        result = decide(load("review.json"))
        self.assertEqual(result["decision"], "REVIEW")
        self.assertEqual(result["issue_count"], 1)

    def test_block_for_confirmed_p0(self):
        result = decide(load("block.json"))
        self.assertEqual(result["decision"], "BLOCK")
        self.assertEqual(result["risk_items"][0]["evidence_complete"], True)

    def test_needs_input_for_coverage_or_version_gap(self):
        result = decide(load("needs_input.json"))
        self.assertEqual(result["decision"], "NEEDS_INPUT")
        self.assertIn("release_hash_mismatch", result["decision_trace"]["reasons"])

    def test_confirmed_p0_without_evidence_is_review(self):
        payload = load("pass.json")
        payload["risk_items"] = [{
            "risk_type": "合规-绝对化用语",
            "priority_tier": "P0",
            "status": "confirmed",
            "action": "block",
            "location": "caption",
            "reason": "命中候选词但没有可追溯依据"
        }]
        result = decide(payload)
        self.assertEqual(result["decision"], "REVIEW")

    def test_role_routing_for_health_review(self):
        payload = load("review.json")
        payload.pop("next_owners", None)
        result = decide(payload)
        self.assertIn("医学顾问", result["next_owners"])
        self.assertIn("法务", result["next_owners"])
        self.assertEqual(result["sla"]["target"], "4 business hours")


class CandidateAuthorityTests(unittest.TestCase):
    """★ 2026-10-12：**非权威候选**（`rule_engine.scan_text()` 的产出）必须在输出里被认出来。

    病灶（实测素材 `RC-160a343ee259`）：库自己写着 `authoritative: false`、
    `superseded_by: kb/l3/candidates/rules.jsonl`，`rule_engine` 也逐条带着它 ——
    而**渲染侧一个读它的地方都没有**（`grep authoritative` 只命中产者与它自己的测试）。
    于是摘要写「共发现 17 处必须修改」，其中 **5 处**是这种候选，
    与 12 条库内依据混在同一个计数与同一份分类汇总里，读者分不出来。
    """

    @staticmethod
    def _payload(*items):
        # `REQUIRED_FIELDS` 与 `coverage` 必须齐 —— 缺任一项 `decide()` 直接 NEEDS_INPUT/0 条，
        # 那时**判据根本走不到**（第一版就是这么红的：4 条 case 全报 `0 != N`，
        # 看着像"标记没生效"，其实是**前置没过**。这一条本身就是个教训）。
        return {"review_id": "rv-test", "content_id": "AD-TEST-001",
                "content_version": "x", "content_type": "text",
                "input_manifest": {"text": "x", "sha256": "0" * 64, "modality": ["text"]},
                "coverage": {"text": "complete", "image": "not_applicable",
                             "audio": "not_applicable", "video": "not_applicable",
                             "ocr": "not_applicable", "asr": "not_applicable",
                             "keyframes": "not_applicable"},
                "risk_items": list(items)}

    @staticmethod
    def _evidenced(**over):
        it = {"risk_id": "r-1", "risk_type": "功效宣称", "priority_tier": "P1",
              # ★ 2026-10-19：真 `risk_items` **带 `risk_category`**（`review.py` 返回前统一盖章，
              #   真单实测 4/4 都有）—— 夹具必须跟着，否则分类汇总只能落「未标注维度」桶，
              #   量不到 PRD §5.3.4 那一行。维度取值与 `risk-category-policy.json` 一致（功效宣称 ⇒ 合规）。
              "risk_category": "合规",
              # ★ 2026-10-19（A3 12 类）：真 `risk_items` 带 `taxonomy_category`
              "taxonomy_category": "合规与受监管宣称",
              "taxonomy_subcategory": "生理功效与效果承诺",
              "status": "confirmed", "action": "review", "location": "全文",
              "original_text": "more milk", "reason": "库内规则命中",
              "evidence": {"library": "措辞表达库", "article_no": "W-1.18",
                           "anchor": "#广告文案明细/rec1/命中片段",
                           "source_sha256": "a" * 64, "excerpt": "more milk",
                           "l0_entry_url": "https://example.invalid/rec1"}}
        it.update(over)
        return it

    @staticmethod
    def _candidate(**over):
        it = {"risk_id": "US-CLAIM-HEALTH-001:0",
              "risk_type": "Health claim lacks substantiation",
              "priority_tier": "P0", "status": "uncertain", "action": "review",
              "location": "text characters 0-8", "original_text": "more milk",
              "reason": "命中美国市场规则候选", "evidence_id": "TEXT:0:9",
              "authoritative": False, "superseded_by": "kb/l3/candidates/rules.jsonl",
              "evidence_complete": True}
        it.update(over)
        return it

    def test_c1_summary_names_the_candidates_and_counts_only_library(self):
        """① 候选要**被点名**，且**不算进问题数**（Owner 2026-10-12 裁定的新语义）。"""
        r = decide(self._payload(self._evidenced(), self._candidate()))
        self.assertEqual(r["issue_count"], 1)                       # 只算库内依据
        self.assertEqual(r["issue_count_including_candidates"], 2)  # 旧口径留了出口
        self.assertEqual(r["candidate_count"], 1)
        self.assertIn("共发现 1 处", r["summary"])                   # 句子与字段同口径
        # 候选没被藏起来 —— 但要说在**独立那行**上（`candidate_note`），不许挂在 PRD 那句尾巴上（c9 钉着）
        self.assertNotIn("需人工确认。（", r["summary"])
        self.assertIn("其中 1 处来自非权威候选规则", r["summary"])
        self.assertIn("kb/l3/candidates/rules.jsonl", r["summary"])
        self.assertIn("不构成依据", r["summary"])

    def test_c2_evidenced_items_are_never_marked(self):
        """② **反向对照**：库内依据**没有** `authoritative` 这个键 ⇒ 一个字都不许标。

        判据写成「缺字段算候选」会把全部库内依据一起打成候选 —— 这一条钉死它。
        """
        r = decide(self._payload(self._evidenced(), self._evidenced(risk_id="r-2")))
        self.assertNotIn("非权威候选", r["summary"])
        self.assertEqual(r["issue_count"], 2)                       # 全是依据 ⇒ 两个口径同值
        self.assertEqual(r["issue_count_including_candidates"], 2)
        self.assertEqual(r["candidate_count"], 0)

    def test_c3_aggregated_path_counts_only_library_categories(self):
        """③ ≥3 条走汇总路径时：**分类汇总只数库内依据**，候选改由**合计那行**说。

        ★ 2026-10-12（按 PRD §5.4 修后的必然结果，**有意为之**）：
          分类汇总与 `issue_count` 必须是**同一批条目**（PRD 的例子把两者钉成等式），
          所以候选**不再出现在逐类那一行**上；它的可见性由
          ① `candidate_count` ② 合计那行「＋ 其中 N 处来自非权威候选规则…」③ 完整清单逐条承担。
          本用例把这三条**一起**钉住 —— 免得日后有人为了让候选出现在分类里，
          又把 PRD §5.4 的等式弄破（c10 钉着那个等式）。
        """
        # ★ 新口径下「≥3」数的是**库内依据** ⇒ 夹具给 4 条依据 ＋ 1 条候选（n=4 才过阈值）
        items = [self._evidenced(risk_id="r-1"), self._evidenced(risk_id="r-2"),
                 self._evidenced(risk_id="r-3"), self._evidenced(risk_id="r-4"),
                 self._candidate(risk_type="Absolute or ranking claim requires context and proof")]
        r = decide(self._payload(*items))
        self.assertEqual(r["issue_count"], 4)
        self.assertEqual(r["issue_count_including_candidates"], 5)
        self.assertEqual(r["candidate_count"], 1)
        # ★★ 2026-10-19（Owner：分类汇总必须跟 PRD §5.3 对齐）：轴是**四维**、形状是 §5.3.4 的一行。
        # ★★ 2026-10-19：轴 = **A3 12 类**，形状 = 每类一行
        self.assertIn("· 合规与受监管宣称类问题：4 个", r["summary"])
        # A1 库内类别与 A2 四维都**不许**再出现在汇总行里
        self.assertNotIn("功效宣称类", r["summary"])
        self.assertNotIn("合规类问题", r["summary"])
        self.assertNotRegex(r["summary"], r"个 · [^\n]*类问题：")
        # ① 候选那一类**不许**出现在分类汇总里（否则 PRD §5.4 的等式就破了）
        self.assertNotIn("Absolute or ranking claim", r["summary"])
        # ② 但合计那行必须说清候选有多少、且不构成依据
        self.assertIn("其中 1 处来自非权威候选规则", r["summary"])
        self.assertIn("不构成依据", r["summary"])
        # ③ 完整清单里逐条都在（不算问题 ≠ 不给你看）
        self.assertEqual(len(r["risk_items"]), 5)
        self.assertIn("其中 1 处来自非权威候选规则", r["summary"])

    def test_c4_detailed_path_marks_the_item(self):
        """④ 走逐条路径时，候选那一条自己要带标记（否则读者只看到依据"空了"）。

        ★ 新口径下这一单 `issue_count = 0`（一条依据都没有）⇒ 仍走逐条（0 ≤ 2），
          而**候选必须照样被列出来并标注** —— "不算问题数" 不等于 "不给你看"。
        """
        r = decide(self._payload(self._candidate()))
        self.assertEqual(r["issue_count"], 0)
        self.assertEqual(r["issue_count_including_candidates"], 1)
        self.assertIn("非权威候选规则命中", r["summary"])
        self.assertIn("不构成依据", r["summary"])

    # ── ★★ 2026-10-12（Owner **裁定**）：`issue_count` = **只算库内依据** ──────────────
    #   这是一次**破坏性语义变更**（旧值 = 全部条目）。三处行为按它分流：
    #   报告链接门槛 / 守衡合并卡 / PRD §5.3.3 的 ≥3 分流 ⇒ 所以同时留了旧口径的出口
    #   `issue_count_including_candidates`，谁也不许静默地少了一个数。
    #   c6 钉新语义、c7 钉四个数的自洽、c8 是**反向对照**（把声明真改一遍，数必须跟着动）。

    def test_c6_issue_count_counts_only_library_basis(self):
        """c6：`issue_count` **只算库内依据**；完整清单条数走旧口径出口。"""
        r = decide(self._payload(self._evidenced(), self._candidate(),
                                 self._evidenced(risk_id="r-2")))
        self.assertEqual(r["issue_count"], 2)                        # 3 条里 1 条是候选
        self.assertEqual(r["issue_count_including_candidates"], 3)
        self.assertEqual(r["candidate_count"], 1)
        # ★ 2026-10-12：兼容别名 `authoritative_issue_count` **已撤** —— 这条判据改成**不许它回来**。
        #   为什么值得钉：它是「同一个数两个名字」，一旦有人顺手再加一个兼容名，
        #   就又变成两处真源，而**没有任何东西会红**（本库栽过太多次同形状的坑）。
        #   要读旧口径那个数，出口是 `issue_count_including_candidates`（下一行断言它必须在）。
        self.assertNotIn("authoritative_issue_count", r)
        self.assertEqual(r["issue_count_including_candidates"], 3)

    def test_c7_the_four_numbers_must_reconcile(self):
        """c7：四个数必须自洽 —— 5 条 = 3 依据 ＋ 2 候选。"""
        r = decide(self._payload(self._evidenced(risk_id="r-1"), self._evidenced(risk_id="r-2"),
                                 self._evidenced(risk_id="r-3"),
                                 self._candidate(risk_id="c-1"), self._candidate(risk_id="c-2")))
        self.assertEqual(r["issue_count"], 3)
        self.assertEqual(r["candidate_count"], 2)
        self.assertEqual(r["issue_count_including_candidates"], 5)
        self.assertEqual(r["issue_count"] + r["candidate_count"],
                         r["issue_count_including_candidates"])
        self.assertIn("库内依据", r["issue_count_basis"])
        self.assertIn("非权威候选 2", r["issue_count_basis"])

    def test_c8_reverse_control_flipping_the_declaration_moves_the_numbers(self):
        """c8 **反向对照**：把候选声明**真改成权威** ⇒ 四个数必须跟着动。

        若判据写成「恒等于 0」或「恒等于条目总数」，这里会红。
        同时钉住「缺 `authoritative` 键 ≠ 候选」（库内依据本来就没有这个键）。
        """
        cand = self._candidate()
        r1 = decide(self._payload(self._evidenced(), cand))
        self.assertEqual((r1["issue_count"], r1["candidate_count"],
                          r1["issue_count_including_candidates"]), (1, 1, 2))
        promoted = dict(cand, authoritative=True)          # 变异：声明改成权威
        r2 = decide(self._payload(self._evidenced(), promoted))
        self.assertEqual((r2["issue_count"], r2["candidate_count"],
                          r2["issue_count_including_candidates"]), (2, 0, 2))
        # 全候选（0 条库内依据）：issue_count 必须是 0，**但清单仍要把候选列出来**
        r3 = decide(self._payload(self._candidate(risk_id="c-1")))
        self.assertEqual((r3["issue_count"], r3["candidate_count"],
                          r3["issue_count_including_candidates"]), (0, 1, 1))
        self.assertIn("非权威候选规则命中", r3["summary"])
        self.assertEqual(len(r3["risk_items"]), 1)         # 候选项**不许**被从清单里摘掉

    def test_c9_prd_verdict_line_must_stay_verbatim(self):
        """c9：摘要**首行**必须逐字等于 PRD §5.3.2/§5.3.3 那句 —— **带候选时也一样**。

        判据是**整行锚定**（`^…$`），不是子串：
        守衡那侧的 `prd53.conforms()` 就是 `$` 锚定的，而它的 `LINE_RE` 取到**行尾**
        ⇒ 往这一行尾巴上挂任何东西，卡面标题就不再是 PRD 的那一句。
        """
        import re as _re
        pat = _re.compile(r"^【审查结论：(REVIEW|BLOCK)】共发现 \d+ 处(需人工确认|必须修改)。$")

        # ① 带候选（有过一次真事故的形状）：首行仍须逐字合规
        r = decide(self._payload(self._evidenced(), self._candidate()))
        first = r["summary"].split("\n")[0]
        self.assertRegex(first, pat)
        # ② 纯候选（issue_count=0）与全依据，两个边界也要合规
        self.assertRegex(decide(self._payload(self._candidate()))["summary"].split("\n")[0], pat)
        self.assertRegex(decide(self._payload(self._evidenced()))["summary"].split("\n")[0], pat)
        # ③ 候选仍然要在**别的行**上说出来（修的是位置，不是把话删掉）——
        #    ★ Owner 2026-10-12「同意加」：那行候选提示**保留**，但必须**独立成行**。
        lines = r["summary"].split("\n")
        self.assertNotIn("非权威候选", first)              # 结论行里不许有候选字样
        self.assertIn("非权威候选", "\n".join(lines[1:]))   # 但必须出现在**后续行**上

    def test_c9b_reverse_control_the_judge_is_not_a_substring_check(self):
        """c9b **反向对照**：把上一批那个写法**真造一遍** ⇒ 判据必须红。

        造法就是当时那一版：在 PRD 那句尾巴上接一个候选括号。
        """
        import re as _re
        pat = _re.compile(r"^【审查结论：(REVIEW|BLOCK)】共发现 \d+ 处(需人工确认|必须修改)。$")
        bad = "【审查结论：REVIEW】共发现 2 处需人工确认。（另有 **1 处非权威候选线索**，见完整清单）"
        self.assertIsNone(pat.match(bad))                 # 整行锚定 ⇒ 红
        self.assertIn("共发现 2 处", bad)                  # 而**子串**判据会放过它 —— 这正是当时的漏洞
        # 守衡那侧的同一条尺子是 `$` 锚定的正则：两种写法一起钉，免得两边口径漂
        self.assertIsNone(_re.match(r"^【审查结论：REVIEW】共发现 \d+ 处需人工确认。$", bad))

    # ── ★★ 2026-10-12（按 PRD §5.4 修）：**问题数 == 分类汇总合计** ──────────────
    #   PRD §5.4 的例子把「summary 里的共发现 N 处」「issue_count」「分类汇总合计」钉成同一个数。
    #   病灶（我上一批引入）：改了 `issue_count`（只算库内依据）却没动 `categories`
    #   ⇒ 同一份 JSON 自相矛盾（实测 5/5 条候选单不成立）。下面的判据按构造成立，c10b 反向对照。

    def test_c10_issue_count_equals_category_total_prd_54(self):
        """c10：**PRD §5.4 等式** —— `issue_count` == 分类汇总合计（含候选与 P3 建议的混合单）。"""
        items = [self._evidenced(risk_id="r-1"), self._evidenced(risk_id="r-2"),
                 self._evidenced(risk_id="r-3"),
                 self._evidenced(risk_id="r-4", action="advice", priority_tier="P3"),  # P3 建议：不算问题
                 self._candidate(risk_id="c-1")]                                       # 候选：不算问题
        r = decide(self._payload(*items))
        self.assertEqual(r["issue_count"], 3)                                   # 4 依据里 1 条是 advice
        self.assertEqual(r["issue_count"], sum(r["issue_summary_by_category"].values()))
        # ★ 三方等式（PRD §5.4 的例子把这三个数钉成同一个数）：
        #   抬头那句「共发现 N 处」 ==  `issue_count`  ==  分类汇总合计
        #   病灶（同日实测的第二处残留）：这句原先**没跟着**排除 advice ⇒ 2 依据 + 1 建议时
        #   `issue_count=2` 而这句话说 3。c10c 反向对照钉着这条。
        _head_n = int(re.search(r"共发现 (\d+) 处", r["summary"].split("\n")[0]).group(1))
        self.assertEqual(_head_n, r["issue_count"])
        self.assertEqual(_head_n, sum(r["issue_summary_by_category"].values()))
        self.assertEqual(r["candidate_count"], 1)
        # 候选那一类**不许**出现在分类汇总里（它与 issue_count 必须是同一批条目）
        self.assertNotIn("Health", "".join(r["issue_summary_by_category"].keys()))
        # 但它**仍在完整清单里**（不算问题 ≠ 不给你看）
        self.assertEqual(len(r["risk_items"]), 5)

    def test_c10c_reverse_control_head_sentence_counted_advice(self):
        """c10c **反向对照**：把「抬头那句没排除 advice」的旧写法**真造一遍** ⇒ 三方等式必须破。

        造法就是当时那一版：`n = len(items) - 候选数`（**不排 advice**）。
        这里用同一批条目把两个数**都算出来**，证明判据能分辨 —— 而不是恒真。
        """
        items = [self._evidenced(risk_id="r-1"), self._evidenced(risk_id="r-2"),
                 self._evidenced(risk_id="r-3", action="advice", priority_tier="P3")]
        r = decide(self._payload(*items))
        _cand = r["candidate_count"]
        old_style_n = len(r["risk_items"]) - _cand          # 旧写法：只减候选，不减 advice
        self.assertEqual(r["issue_count"], 2)
        self.assertNotEqual(old_style_n, r["issue_count"])  # 旧写法会多算 1 ⇒ 判据能分辨
        _head_n = int(re.search(r"共发现 (\d+) 处", r["summary"].split("\n")[0]).group(1))
        self.assertEqual(_head_n, r["issue_count"])         # 现在的写法三者同批

    def test_c10b_reverse_control_the_equation_is_not_trivially_true(self):
        """c10b **反向对照**：把上一批那种写法**真造一遍**（分类里算上候选）⇒ 等式必须破。

        造法就是当时那一版：`categories` 数**全部**非 advice 条目。用一个纯候选单来验：
        那单 `issue_count` 应为 0，而「算上候选」的合计是 1 ⇒ 两个数对不上 ⇒ 判据能分辨。
        """
        r = decide(self._payload(self._candidate(risk_id="c-1")))
        self.assertEqual(r["issue_count"], 0)
        self.assertEqual(sum(r["issue_summary_by_category"].values()), 0)
        # 真造一遍旧写法：把候选也算进分类 ⇒ 合计 1 ≠ issue_count 0
        old_style_total = r["issue_count"] + r["candidate_count"]
        self.assertNotEqual(old_style_total, sum(r["issue_summary_by_category"].values()))
        # 口径也在文本里说清楚（免得人只看到 0 个问题却不知道还有线索）
        self.assertIn("非权威候选", r["summary"])
        self.assertIn("与分类汇总同一个数", r["issue_count_basis"])

    def test_c5_no_candidates_no_noise(self):
        """⑤ **反向对照**：没有候选 ⇒ 一个字都不许多（不许恒加一行）。"""
        r = decide(self._payload(self._evidenced()))
        self.assertNotIn("非权威候选", r["summary"])
        self.assertNotIn("其中", r["summary"])


if __name__ == "__main__":
    unittest.main()
