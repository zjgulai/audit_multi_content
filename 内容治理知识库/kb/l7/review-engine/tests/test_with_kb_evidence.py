"""test_with_kb_evidence.py —— 依据缓存（--findings-from / --findings-out）的回归用例。

为什么要有这组用例（2026-10-01）：

同一条「这个评审一下」按 kb-review 的正文执行，会让 `review.py` 被跑两遍 ——
一遍给 agent 看依据（§3 调 kb-content-review），一遍给适配器转契约（§144 的
`with_kb_evidence.py`，它 subprocess 再跑一次）。每次现跑都要付一次依据侧全量加载。

于是加了「同一 RUN 内算一次、两处读」的缓存。缓存最容易出的错**不是读不到，而是读错**：
把 A 文案的依据算到 B 文案上 —— 那会让结论看起来有据可查、实际张冠李戴。
因此这组用例的重点是**校验**，不是省时间。

约定：这些用例**不写权威库**（run_record 被替换成空实现）。
"""
import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # …/kb/l7/review-engine —— 与其它用例同约定

from core import with_kb_evidence as W  # noqa: E402

TEXT = "FDA approved breast pump. 100% safe."

#: 一条形状取自真实产物的依据（`kb/l7/reports/20261001-084931-test.review.md` 的检索轨迹）
FINDING = {
    "rule_id": "r-15a607c4457c8b55",
    "library": "措辞表达库",
    "article_no": "W-1.8",
    "anchor": "#品线内容边界规则库/recvuJP1LVW6E0/检测关键词",
    "source_sha256": "c77f576dcc392cb3e763e6462d0259e50fb039f924a4af8e100321197e5be577",
    "excerpt": "FDA approved",
    "category": "背书与资质",
    "sub": "医疗场景宣称",
    "layer": "L3-规则层",
    "severity": "BLOCK",
    "reason": "P0 规则命中（BLOCK）",
    "advice": "可改为 FDA cleared",
    "position": "全文",
    "confidence": "高",
    "fact_or_inference": "事实",
    "rule_code": "",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_cache(path, text=TEXT, payload=None, schema=W.CACHE_SCHEMA, sha=None):
    Path(path).write_text(json.dumps({
        "schema": schema,
        "cached_at": "2026-10-01T10:55:00",
        "text_sha256": sha if sha is not None else _sha(text),
        "source": "test",
        "payload": payload if payload is not None else {"run_id": "20261001-105500-test",
                                                        "state": "BLOCK",
                                                        "findings": [FINDING]},
    }, ensure_ascii=False), encoding="utf-8")


class FindingsCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = str(Path(self.tmp.name) / "findings.json")

    def test_cache_roundtrip_keeps_payload(self):
        """写出去的缓存必须能原样读回来（payload 不带 `_` 开头的内部键）。"""
        W._write_findings_cache(self.cache, TEXT, {"run_id": "r1", "_findings_source": {"mode": "live"}})
        ev, err = W._read_findings_cache(self.cache, TEXT)
        self.assertIsNone(err)
        self.assertEqual(ev["run_id"], "r1")
        self.assertNotIn("_findings_source", {k: v for k, v in ev.items() if k != "_findings_source"})
        self.assertEqual(ev["_findings_source"]["mode"], "cache")

    def test_text_mismatch_is_refused(self):
        """★ 核心用例：文本对不上就必须拒用 —— 否则会把另一条文案的依据算到这条上。"""
        _write_cache(self.cache, text="别的一段文案")
        ev, err = W._read_findings_cache(self.cache, TEXT)
        self.assertIsNone(ev)
        self.assertIn("不符", err)

    def test_schema_mismatch_is_refused(self):
        _write_cache(self.cache, schema="kb-evidence-findings-cache/0")
        ev, err = W._read_findings_cache(self.cache, TEXT)
        self.assertIsNone(ev)
        self.assertIn("schema", err)

    def test_missing_file_is_a_clear_error(self):
        ev, err = W._read_findings_cache(str(Path(self.tmp.name) / "不存在.json"), TEXT)
        self.assertIsNone(ev)
        self.assertIn("读不到", err)

    def test_run_from_cache_never_spawns_review_py(self):
        """走缓存时不得再 subprocess 跑 review.py —— subprocess.run 被替换成会炸的实现。"""
        _write_cache(self.cache)
        stub = types.ModuleType("run_record")
        stub.record = lambda **kw: None          # 不写 kb/l7/runs/
        saved_mod, saved_run = sys.modules.get("run_record"), W.subprocess.run
        sys.modules["run_record"] = stub

        def _boom(*a, **k):
            raise AssertionError("走缓存时不该再跑 review.py")

        W.subprocess.run = _boom
        try:
            res, err = W.run(TEXT, findings_from=self.cache)
        finally:
            W.subprocess.run = saved_run
            if saved_mod is None:
                sys.modules.pop("run_record", None)
            else:
                sys.modules["run_record"] = saved_mod

        self.assertIsNone(err)
        self.assertEqual(res["evidence_meta"]["findings"], 1)
        self.assertEqual(res["evidence_meta"]["findings_source"]["mode"], "cache")
        self.assertTrue(res["decision"])

    def test_findings_from_missing_file_fails_loudly(self):
        """缓存不在位时必须报错返回，不许静默降级成"没有发现"。"""
        res, err = W._evidence_findings(TEXT, findings_from=str(Path(self.tmp.name) / "缺.json"))
        self.assertIsNone(res)
        self.assertIsNotNone(err)


class TierWiringTests(unittest.TestCase):
    """`_to_risk_item` 的 P0–P3 接线判据（任务拆解 目标12 · PRD §6.2）。

    ★ 为什么单给这一个函数写用例：**原 bug 就在这一行**。
      改前是 `"P0" if "P0" in str(f.get("layer") or "") else "P1"`，而 `f` 是依据层的
      finding、**它没有 `layer` 键** ⇒ **恒为 `P1`，连 P0 都报 P1**。
      实测变异（把这一行退回旧写法）：`p_level=P0 → priority_tier=P1`、
      `p_level=P2 → P1`、`p_level=P3 → P1` —— 三个全错。
      没有判据守着，这种「一行退回」没人会发现。
    """

    def _item(self, **kw):
        f = dict(FINDING)
        f.update(kw)
        f.pop("layer", None)               # 依据层 finding 的真实形状：没有 layer 键
        return W._to_risk_item(f)[0] if isinstance(W._to_risk_item(f), tuple) else W._to_risk_item(f)

    def test_p_level_drives_tier(self):
        """四个层级都要原样出来（改前全塌成 P1）。"""
        for p in ("P0", "P1", "P2", "P3"):
            item = self._item(p_level=p)
            self.assertEqual(item["priority_tier"], p, "p_level=%s 被报成 %s"
                             % (p, item["priority_tier"]))

    def test_no_layer_key_does_not_collapse_to_p1(self):
        """★ 核心回归：`f` 没有 `layer` 键时，**不许**因此把所有层级都塌成 P1。

        这条就是原 bug 的正面判据 —— 只要有人把那一行退回「看 layer 文案」，
        `p_level=P0` 会得到 P1，本用例立刻红。
        """
        item = self._item(p_level="P0")
        self.assertNotEqual(item["priority_tier"], "P1",
                            "没有 layer 键 ≠ 该报 P1（原 bug：恒为 P1）")
        self.assertEqual(item["priority_tier"], "P0")

    def test_basis_is_written_for_every_item(self):
        """每条都要能说清「凭什么定这一层」—— 不许留一个看不出来的默认值。"""
        for p in ("P0", "P2", "P3", None):
            item = self._item(p_level=p)
            self.assertTrue(item.get("priority_tier_basis"), "p_level=%s 缺依据" % p)

    def test_severity_block_falls_back_to_p0_and_says_so(self):
        """没有 p_level、但 severity=BLOCK ⇒ 按最高层处理，**并写明是这条兜底路径**。

        ⚠️ 这条判据曾写成「没有 p_level 就必须出现『兜底』二字」，被自证抓出来是
        **断言写错**：本条输入带 `severity=BLOCK`，走的是「BLOCK ⇒ 按最高层」这条
        合法路径，不是 P1 兜底。⇒ 拆成两条，各守一条路径，**都要求写明**。
        """
        item = self._item(p_level=None, severity="BLOCK")
        self.assertEqual(item["priority_tier"], "P0")
        self.assertIn("severity=BLOCK", item["priority_tier_basis"])

    def test_no_signal_at_all_lands_p1_and_says_it_is_a_fallback(self):
        """三层信号全无 ⇒ P1 兜底（与改动前逐字一致），且依据**写明这是兜底**。"""
        item = self._item(p_level=None, severity=None)
        self.assertEqual(item["priority_tier"], "P1")
        self.assertIn("兜底", item["priority_tier_basis"])

    def test_tier_action_separate_from_evidence_severity(self):
        """层级政策动作与逐条 severity **分两格存**，不互相覆盖。

        `action` 保留依据层逐条判出的严重度（P0 命中即 BLOCK 那条硬约束靠它）；
        `tier_action` 才是「该层级通常给什么动作」。混成一格就分不清
        「层级说了什么」与「这一条判了什么」。
        """
        item = self._item(p_level="P1", severity="BLOCK")
        self.assertEqual(item["priority_tier"], "P1")
        self.assertEqual(item["tier_action"], "review")     # P1 的层级政策
        self.assertEqual(item["action"], "block")           # 但这一条判的是 BLOCK，保留


if __name__ == "__main__":
    unittest.main(verbosity=2)
