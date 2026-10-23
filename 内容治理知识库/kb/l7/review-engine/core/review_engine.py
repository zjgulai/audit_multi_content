#!/usr/bin/env python3
"""Deterministic decision and report layer for the local brand review workflow.

The engine intentionally consumes extracted evidence and risk items. OCR, ASR,
vision, policy retrieval, and Feishu transport remain replaceable adapters.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from .sla import resolve_sla
except ImportError:  # Allow direct script execution as well as package imports.
    from sla import resolve_sla

# ★ 2026-10-10：两个策略层的**唯一口径**（模块与 `sla` 一样支持包导入与直跑两种形态）。
#   · `tiering`         —— P0–P3 分级（PRD §6.2/§6.3）
#   · `confidence_flow` —— 置信度分流（PRD §6.6）
#   · `routing`         —— **按问题方向转对应专业团队**（PRD §9 / §5.3.2；2026-10-14 加）
try:
    import tiering
    import confidence_flow
    import routing
except ImportError:  # 直跑（脚本目录不在 sys.path）时按同目录再试一次
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import tiering
    import confidence_flow
    import routing


# ★ PRD §6.6 的阈值**从政策文件读**，不在代码里硬编码第二份。
#   读不到就用 PRD 默认值，并**把「用的是默认值」记进产物**（不许静默）。
_CONF_POLICY = confidence_flow.load_thresholds()
CONFIDENCE_THRESHOLDS = _CONF_POLICY["thresholds"]
CONFIDENCE_POLICY_SOURCE = ("kb/l7/registry/confidence-policy.json"
                            if _CONF_POLICY.get("from_policy_file")
                            else "PRD §6.6 默认值（政策文件读不到：%s）" % _CONF_POLICY.get("note"))

# ★★ 2026-10-19 第二轮（PRD §5.3.2 **rev 101**，Owner 当天改的口径）：
#   **SUGGEST 不 `decision` 的取值** —— 它是 PASS 的**附属标签**。
#   原文：「SUGGEST｜非强制性问题…。**作为 PASS 的附属标签**，不阻断流程。｜随 PASS 一起流转，提示内容方。」
#   同向三处：§6.3 规则4「只有 SUGGEST 时最终状态为 PASS（附 SUGGEST 建议）」、
#            §10.1 `decision` 三值、§11.2「准确率 = 三态一致数 ÷ 总审查数」。
#   ⇒ 落法：`decision` 三值 ＋ **`suggestions[]` / `suggest_count` / `suggest_label`**；
#      统计口径仍是「四态」= **四个桶**（PASS ／ PASS＋建议 ／ REVIEW ／ BLOCK），不是四个 `decision` 值。
#   ⚠️ 同日早些时候这里收过 `SUGGEST`（当第四态），已被 rev 101 覆盖；
#      留痕：`prd532-states.yaml::conflict_decision.superseded_by`。
DECISIONS = {"PASS", "REVIEW", "BLOCK", "NEEDS_INPUT"}
#: 曾经被当成结论态、现在**只作标签**的词。出现在 `decision` 里就算违约（给下游与判据一个可喊的名字）。
FORMER_STATE_AS_LABEL = {"SUGGEST": "PASS 的附属标签（PRD §5.3.2 rev101）"}
REQUIRED_FIELDS = {
    "review_id",
    "content_id",
    "content_type",
    "content_version",
    "input_manifest",
    "coverage",
    "risk_items",
}
REQUIRED_COVERAGE = ("text", "image", "audio", "video", "ocr", "asr", "keyframes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coverage_ready(coverage: Dict[str, Any], content_type: str) -> List[str]:
    required = {"text"}
    if content_type == "image":
        required |= {"image", "ocr"}
    elif content_type == "video":
        required |= {"video", "audio", "ocr", "asr", "keyframes"}
    missing = []
    for name in required:
        value = coverage.get(name)
        if value not in {"complete", "not_applicable"}:
            missing.append(name)
    return sorted(missing)


def _evidence_complete(item: Dict[str, Any]) -> bool:
    return bool(item.get("location") and (item.get("evidence_url") or item.get("evidence_id")))


def _category(item: Dict[str, Any]) -> str:
    return str(item.get("risk_type") or item.get("category") or "未分类")


#: A3 的兜底类名（12 类里的第 12 个；真源 `kb/l3/registry/rule-taxonomy.json`）。
TAX_UNCLASSED = "未归类"


def _tax_category(item: Dict[str, Any]) -> str:
    """**所属类别**（A3 12 类）；盖不到 ⇒ `未归类`（兜底类，**不编**）。

    ★★ 2026-10-19（Owner：「所属类别/所属子类」统一到 A3 12 类）：
      改前卡面首行印 **A1**（`risk_type`）、汇总印 **A2 四维**；两者都不是 Owner 指定的那套。
    """
    return str((item or {}).get("taxonomy_category") or "").strip() or TAX_UNCLASSED


def _tax_label(item: Dict[str, Any]) -> str:
    """`<所属类别>-<所属子类>`（卡面逐条首行）；子类没有就只印类别。"""
    cat = _tax_category(item)
    sub = str((item or {}).get("taxonomy_subcategory") or "").strip()
    return ("%s-%s" % (cat, sub)) if sub and cat != TAX_UNCLASSED else cat


_TAX_CLASSES = None


def _taxonomy_classes() -> List[str]:
    """A3 的 12 类**顺序**（真源 `kb/l3/registry/rule-taxonomy.json`）；读不到 ⇒ 空表（不编顺序）。"""
    global _TAX_CLASSES
    if _TAX_CLASSES is None:
        _TAX_CLASSES = []
        try:
            _p = Path(__file__).resolve().parents[3] / "l3" / "registry" / "rule-taxonomy.json"
            with open(_p, encoding="utf-8") as fh:
                reg = json.load(fh)
            _TAX_CLASSES = [str(c.get("name") or "").strip()
                            for c in (reg.get("classes") or []) if str(c.get("name") or "").strip()]
        except Exception as _e:                                     # noqa: BLE001
            print("[taxonomy] ⚠ 12 类注册表读不到 ⇒ 汇总顺序退回字典序：%s" % _e,
                  file=__import__("sys").stderr)
    return _TAX_CLASSES


# ── ★★ 2026-10-12：非权威候选（`rule_engine.scan_text()` 的产出）──────────────
#   声明早就有、**渲染侧一个读它的地方都没有** —— 实测 `grep authoritative` 只命中产者
#   与它自己的测试。于是库自己写着「不权威、已被取代」的候选，在输出里与库内依据
#   **长得一模一样**，还一起被计进「共发现 N 处」。这一节把声明读出来。
#   证据与实测见 `is_candidate` / `candidate_note` 的 docstring。

def is_candidate(item: Dict[str, Any]) -> bool:
    """这一条是不是**非权威候选**。

    ★ 判据是**显式 `False`**，不是「缺这个字段」：
      `with_kb_evidence._to_risk_item()` 造的**库内依据根本没有 `authoritative` 这个键**，
      把「缺字段」当候选会把全部库内依据一起打成候选 —— 自证 R2 钉着这一条。
    """
    return item.get("authoritative") is False


def _cat_key(name: str) -> str:
    """把分类名归并成大类（与 `render_summary` 里 `_agg` 的归一化**同一把尺子**）。"""
    return str(name).split("-")[0].split("－")[0].strip() or "未分类"


def candidate_item_note(item: Dict[str, Any]) -> str:
    """**逐条**的候选标记（摘要的逐条路径与发布件的报告**共用同一句**）；不是候选就返回空串。"""
    if not is_candidate(item):
        return ""
    sup = str(item.get("superseded_by") or "").strip()
    return ("⚠️ **非权威候选规则命中**（无库内条款号%s）—— 只作排查线索，**不构成依据**"
            % (("，源规则已被 `%s` 取代" % sup) if sup else ""))


def candidate_note(items: Iterable[Dict[str, Any]]) -> str:
    """非权威候选的**统一说明行**；没有候选就返回空串。

    ★ 为什么必须有（2026-10-12 实测，素材 `RC-160a343ee259`）：
      `knowledge-base/seed-rules.json` 自己写着 `authoritative: false`、
      `superseded_by: kb/l3/candidates/rules.jsonl`（**已被库内规则取代**），
      `rule_engine` 也逐条把它带进 `risk_items` —— 但**没人读**。实测输出：

          共发现 17 处必须修改。…… · Health or safety outcome claim lacks
          approved substantiation类问题：3 个    ← 英文标题，就是候选规则

      ⇒ 17 里 **5 处**是候选（其中 3 条还标着 `priority_tier=P0`），
        与 12 条库内依据**混在同一个计数、同一份分类汇总里**，读者分不出来。
      ⇒ 声明存在但没人读 = 注释；这一行就是把它读出来。
    ★ 一句口径**只写在这里**：摘要与发布件都调它，不许各写一份。
    """
    cand = [i for i in (items or []) if is_candidate(i)]
    if not cand:
        return ""
    sup = next((str(i.get("superseded_by") or "").strip()
                for i in cand if str(i.get("superseded_by") or "").strip()), "")
    return ("＋ **其中 %d 处来自非权威候选规则**%s —— 无库内条款号，"
            "只作排查线索，**不构成依据**。"
            % (len(cand), ("（源规则已被 `%s` 取代）" % sup) if sup else ""))


def route_owners(items: Iterable[Dict[str, Any]], decision: str) -> List[str]:
    """Return role-level owners when the submitter did not provide individuals."""
    if decision == "PASS":
        return ["Sign-off 负责人"]
    if decision == "BLOCK":
        return ["内容提交方"]
    owners: List[str] = []
    for item in items:
        text = f"{item.get('risk_type', '')} {item.get('reason', '')}".lower()
        if any(token in text for token in ("医疗", "health", "功效", "安全", "睡眠", "喂养")):
            owners.extend(["医学顾问", "法务"])
        if any(token in text for token in ("产品", "型号", "功能", "规格", "容量", "认证", "product")):
            owners.extend(["产品负责人", "法务"])
        if any(token in text for token in ("背书", "endorsement", "testimonial", "达人", "排名", "绝对化", "平台")):
            owners.extend(["法务", "渠道负责人"])
        if any(token in text for token in ("本地", "语境", "文化", "locale", "cultural")):
            owners.append("北美同事")
    return list(dict.fromkeys(owners or ["法务", "北美同事"]))


def _normalise_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalised = []
    for index, item in enumerate(items, start=1):
        row = dict(item)
        row.setdefault("risk_id", f"R{index}")
        row.setdefault("priority_tier", "P3")
        row.setdefault("severity", "low")
        row.setdefault("status", "confirmed")
        row.setdefault("action", "advice")
        row["evidence_complete"] = _evidence_complete(row)
        normalised.append(row)
    return normalised


def decide(payload: Dict[str, Any], report_url: str | None = None) -> Dict[str, Any]:
    missing_fields = sorted(REQUIRED_FIELDS - payload.keys())
    if missing_fields:
        return _result(payload, "NEEDS_INPUT", [], 0.0, [f"missing_fields:{','.join(missing_fields)}"])

    product_fact_gates = payload.get("product_fact_gate") or []
    if any(gate.get("decision") == "NEEDS_INPUT" for gate in product_fact_gates):
        return _result(
            payload,
            "NEEDS_INPUT",
            _normalise_items(payload.get("risk_items", [])),
            0.0,
            ["product_fact_evidence_gap"],
        )

    content_type = payload.get("content_type", "text")
    missing_coverage = _coverage_ready(payload.get("coverage") or {}, content_type)
    manifest = payload.get("input_manifest") or {}
    version_gate = payload.get("version_gate") or {}
    version_mismatch = bool(
        version_gate.get("reviewed_hash")
        and version_gate.get("release_hash")
        and version_gate["reviewed_hash"] != version_gate["release_hash"]
    )
    if missing_coverage or version_mismatch or manifest.get("status") in {"missing", "forbidden", "failed"}:
        reasons = []
        if missing_coverage:
            reasons.append(f"incomplete_coverage:{','.join(missing_coverage)}")
        if version_mismatch:
            reasons.append("release_hash_mismatch")
        if manifest.get("status") in {"missing", "forbidden", "failed"}:
            reasons.append(f"manifest_status:{manifest['status']}")
        return _result(payload, "NEEDS_INPUT", _normalise_items(payload["risk_items"]), 0.0, reasons, report_url)

    items = _normalise_items(payload["risk_items"])

    # ── P0–P3 四层决策（2026-10-10 接线 · 任务拆解 目标12 · PRD §6.3）──────────────
    # 改前只有 `priority_tier == "P0"` 一条分支，其余靠 `action` 兜 ——
    # PRD §6.3 的第二层（P1 安全准确性·语义）与第三层（P2 通识常识·多模态）
    # 在代码里**没有任何位置**，P3「只出建议、不改结论」也没有位置。
    # 现在三层各有显式分支，且**层级影响结论**这件事在代码里看得见。
    #
    # 判据来源（不是自创）：
    #   §6.3 执行规则1 → P0 命中即 BLOCK
    #   §6.3 第二层   → P1 不确定 ⇒ REVIEW（转对应专业团队）
    #   §6.3 第三层   → P2 发现问题 ⇒ BLOCK 或 REVIEW（本实现取保守侧 REVIEW）
    #   §6.3 执行规则3 → P3 只出建议，**不改变 PASS/BLOCK 结论**
    #   §6.3 执行规则4 → 多条命中按**最高优先级**输出
    confirmed_p0 = [
        i for i in items
        if i["priority_tier"] == "P0" and i["status"] == "confirmed" and i["evidence_complete"]
    ]
    uncertain_p0 = [i for i in items if i["priority_tier"] == "P0" and i["status"] != "confirmed"]
    # 第二层：P1（安全与准确性·语义）命中 ⇒ 至少 REVIEW，转对应专业团队
    p1_items = [i for i in items if i["priority_tier"] == "P1"]
    # 第三层：P2（通识与常识·多模态）命中 ⇒ 至少 REVIEW
    p2_items = [i for i in items if i["priority_tier"] == "P2"]
    # 第四层：P3（措辞与表达）**只出建议，不进结论**（§6.3 执行规则3）
    p3_items = [i for i in items if i["priority_tier"] == "P3"]
    # 层级之外仍按 action 兜：P0 之外的 block 动作（证据齐）照样拦得住，不因分层而放松
    blocking = [
        i for i in items
        if i.get("action") == "block" and i["status"] == "confirmed" and i["evidence_complete"]
    ]
    # ★ P3 不进 review_items —— 它就是「不改结论」那一层。
    #   改前 P3 只要被人填了 action=review 就会把整单拖成 REVIEW，与 §6.3 执行规则3 相反。
    review_items = [
        i for i in items
        if i["priority_tier"] != "P3"
        and (i.get("action") == "review" or i["status"] != "confirmed" or not i["evidence_complete"])
    ]

    tier_trace = {
        # ★ 计数口径：**数「命中的」，不是数「拦住的」**。
        #   首版写成 len(confirmed_p0)+len(uncertain_p0)，于是「P0 命中但证据不齐」
        #   那一单（判定走的是 REVIEW 分支）记成 P0=0 —— 明明是 P0 触发的却看不出来。
        #   判据 test_tier_trace_is_recorded_for_all_four 精确抓到了这一条。
        "P0": sum(1 for i in items if i["priority_tier"] == "P0"),
        "P1": len(p1_items),
        "P2": len(p2_items),
        "P3": len(p3_items),
        "p0_confirmed_blocking": len(confirmed_p0),   # 其中真能拦的（证据齐且 confirmed）
        "p0_without_evidence": sum(1 for i in items
                                   if i["priority_tier"] == "P0" and not i["evidence_complete"]),
        "p3_advice_only": True,          # §6.3 执行规则3：P3 不参与结论
        "p0_confidence_flow": False,     # §6.6：P0 不适用置信度分流
    }

    # ── 置信度：**派生量**（2026-10-12 改造；改前是**分支常量**）────────────────────
    # ★ 为什么改（实测，读数为证；`kb/l8/calibrate_confidence.py` 可复跑）：
    #   改前只有 3~4 个取值（0.97 / 0.93 / 0.78 / 0.99），在**自有标注集**（回归集 100 条 `expected`）上
    #   实测 **与正确率不同序**：0.99→67% ＜ 0.78→80% ＜ 0.97→83%
    #   ⇒ **那个数不携带信息**，阈值切它只是把"分支"换了个标签（政策件 `measured_20261012_selfcalib`）。
    #   现在按**引擎本来就在算的特征**派生，让它有分布 ⇒ 0.90 / 0.70 两条线才谈得上标定。
    # ★ 特征（全部出自 PRD 已定义的层级与证据要求，**不自创**）：
    #   ① 最高已确认层级 → 基础分（P0 确认 0.95 ／ 非 P0 拦截 0.94 ／ P1 0.86 ／ P2 0.80 ／ 其它 REVIEW 0.83）；
    #   ② **独立大类数**多的 ⇒ 多条不同大类独立命中＝互证（每个 +0.02，**上限 +0.04**）。
    #      ★ 大类用 `_cat_key(_category(i))` —— 与 `render_summary` 里 `_agg` 的归一化**同一把尺子**
    #        （实测教训：首版写成 `i.get("category")`，而引擎的类目是**从 `risk_type` 派生**的
    #         ⇒ 那个键根本不存在 ⇒ `cat_bonus` 恒为 0，特征**从未生效**；探针当场照出来了）。
    #   ③ 任一命中**证据不齐** ⇒ −0.05；
    #   ④ 存在**未确认的 P0**（命中但没站住）⇒ −0.06。
    # ★★ 本步的边界（**只让值有分布，不改结论**）：派生结果按**每个结论各自的档**截断 ——
    #   BLOCK / PASS 落在 [0.90, 0.99]（≥0.90 ⇒ §6.6 的"直接输出结论"，结论不变），
    #   REVIEW 落在 [0.70, 0.89]（⇒ §6.6 的"输出 REVIEW"，结论也不变）。
    #   为什么不直接让值自由落进别的档：那会**改结论**（§6.6 明文允许把 BLOCK 压成 REVIEW），
    #   而"动 0.90/0.70 这两条线"是**下一步** —— 得先用标注集量出误放/误转的代价再动。
    #   本步之后：三态与改造前一致（回归可核），但置信度**有分布、可标定**。
    _cats = {_cat_key(_category(i)) for i in items if i.get("priority_tier") != "P3"}
    _cat_bonus = round(0.02 * max(0, min(len(_cats) - 1, 2)), 2)
    _ev_incomplete = any(not i["evidence_complete"] for i in review_items)
    _ev_penalty = 0.05 if _ev_incomplete else 0.0
    _unc_penalty = 0.06 if uncertain_p0 else 0.0

    if confirmed_p0 or blocking:
        decision = "BLOCK"
        _base = 0.95 if confirmed_p0 else 0.94
        _raw = _base + _cat_bonus - _ev_penalty
        _lo, _hi = 0.90, 0.99
        confidence = round(min(_hi, max(_lo, _raw)), 2)
        reasons = ["confirmed_p0" if confirmed_p0 else "confirmed_block_with_evidence"]
    elif uncertain_p0 or review_items:
        decision = "REVIEW"
        _base = 0.86 if p1_items else (0.80 if p2_items else 0.83)
        _raw = _base + _cat_bonus - _ev_penalty - _unc_penalty
        _lo, _hi = 0.70, 0.89
        confidence = round(min(_hi, max(_lo, _raw)), 2)
        reasons = ["uncertain_or_review_item"]
        # 第二/第三层的理由分开记，让「这一单是 P1 还是 P2 触发的」查得出来
        if p1_items:
            reasons.append("p1_semantic_layer")
        if p2_items:
            reasons.append("p2_commonsense_layer")
    elif p3_items:
        # ★★ 2026-10-19 第二轮（PRD §5.3.2 **rev 101**）：**只有 P3 ⇒ 结论仍是 PASS，附建议**。
        #   原文：「SUGGEST｜…作为 PASS 的附属标签，不阻断流程。｜随 PASS 一起流转，提示内容方。」
        #   §6.3 执行规则4 同向：「只有 SUGGEST 时，最终状态为 PASS（**附 SUGGEST 建议**）」。
        #   ⚠️ 与同日早些时候那一版的差别：那版把结论改成 `SUGGEST`（第四态）；rev 101 覆盖了它。
        #      现在结论落 **PASS**，但建议**必须留在产物里**（`suggestions[]` / `suggest_label`，
        #      在 `_result` 之后统一挂，见本函数尾部）—— 否则「PASS 附建议」在数据上等于「PASS」，
        #      四态统计里第二个桶永远恒 0。
        #   置信度：仍属 §6.6「直接输出结论」档（0.90–0.99），与 PASS 同一档，**分流不改结论**。
        decision = "PASS"
        _base = 0.93
        _raw = _base + _cat_bonus - _ev_penalty
        _lo, _hi = 0.90, 0.99
        confidence = round(min(_hi, max(_lo, _raw)), 2)
        reasons = ["suggest_only_non_mandatory"]
    else:
        decision = "PASS"
        _base = 0.93
        _raw = _base + _cat_bonus - _ev_penalty
        _lo, _hi = 0.90, 0.99
        confidence = round(min(_hi, max(_lo, _raw)), 2)
        reasons = ["no_known_blocking_or_review_risk"]

    # ── 置信度分流（2026-10-10 接线 · 目标 11 · PRD §6.6）────────────────────────
    # 改前：三档策略**没有任何位置**（任务拆解 目标 11 现状原文：「无」）。
    # 现在按 §6.6 走：
    #   ≥0.90 直接出结论 ｜ 0.70–0.89 出 REVIEW +「建议人工确认」
    #   　　｜ <0.70 出 REVIEW +「不确定，建议人工重点看」｜ **P0 命中不适用分流**
    confidence = round(max(0.0, confidence), 2)
    _hit_tiers = [i["priority_tier"] for i in items if i.get("priority_tier")]
    cf = confidence_flow.route(decision, confidence, tiers=_hit_tiers,
                               thresholds=CONFIDENCE_THRESHOLDS)
    decision_before_cf = decision
    if cf.get("applies") and cf["decision"] != decision:
        # 分流把结论压成了 REVIEW ⇒ 理由里记明**是谁压的**，否则事后看不出
        # 「这单本来是 BLOCK」还是「本来就是 REVIEW」。
        reasons.append("confidence_flow_forced_review:%s" % cf["band"])
        decision = cf["decision"]

    _res = _result(payload, decision, items, confidence, reasons,
                   report_url, tier_trace=tier_trace, confidence_route=cf,
                   decision_before_confidence_flow=decision_before_cf,
                   conf_derivation={
                       "kind": "derived",           # 改前是分支常量（kind=constant）
                       "base": _base,               # ① 最高已确认层级
                       "cat_bonus": _cat_bonus,     # ② 独立类目互证（上限 +0.04）
                       "ev_penalty": _ev_penalty,   # ③ 证据不齐
                       "unc_p0_penalty": _unc_penalty,  # ④ 未确认的 P0
                       "raw": round(_raw, 2),
                       "clamped_to_keep_decision": [_lo, _hi] if round(_raw, 2) != confidence else None,
                       "final": confidence,
                       "note": "**只让值有分布、不改结论**（截断到本结论自己的档）；"
                               "动 0.90/0.70 两条线是下一步，先用 kb/l8/calibrate_confidence.py 量代价。",
                   })
    # 建议字段（`suggestions` / `suggest_count` / `suggest_label`）由 `_result` 统一挂 ——
    # 它是**唯一出口**，NEEDS_INPUT、P0 快路等其它返回路径也都从这里过，不会漏。
    return _res


def _suggestions(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把 `priority_tier=P3` 的条目收成**建议集**（PRD §5.3.2 rev101：SUGGEST 是 PASS 的附属标签）。

    为什么不复用 `_item_lines` 的四要素形状：问题条目要「原因 / 依据」（要溯源），
    而建议是**非强制**的改法提示 —— 硬塞依据行会让「没有依据」这件事看起来像缺陷。
    §17 对这一段的要求也只有「逐条列建议 + 不阻断说明」。

    返回逐条 dict（**机读**，报表/统计/看板直接取，不用解析文本）：
    `{i, tier, label, location, advice, reason}`
    """
    out: List[Dict[str, Any]] = []
    for i, it in enumerate([x for x in items
                            if str(x.get("priority_tier") or "") == "P3"], start=1):
        out.append({
            "i": i,
            "tier": "P3",
            "label": _tax_label(it),
            "location": str(it.get("location") or "").strip() or "未定位",
            "advice": str(it.get("suggestion") or "").strip(),
            "reason": str(it.get("reason") or "").strip(),
        })
    return out


def _suggestion_lines(items: List[Dict[str, Any]]) -> List[str]:
    """建议集 → 卡面/报告里的**建议段**逐条文本（每条一行，≤150 字口径见 §17）。"""
    lines: List[str] = []
    for i, it in enumerate([x for x in items
                            if str(x.get("priority_tier") or "") == "P3"], start=1):
        loc = str(it.get("location") or "").strip() or "未定位"
        adv = str(it.get("suggestion") or "").strip()
        why = str(it.get("reason") or "").strip()
        tail = ("，建议：%s" % adv) if adv else (
            ("，问题：%s（建议按维度口径改写）" % why) if why else "，建议：按维度口径改写")
        lines.append("%d.【%s】%s%s" % (i, _tax_label(it), loc, tail))
    return lines


def _result(
    payload: Dict[str, Any],
    decision: str,
    items: List[Dict[str, Any]],
    confidence: float,
    reasons: List[str],
    report_url: str | None = None,
    tier_trace: Dict[str, Any] | None = None,
    confidence_route: Dict[str, Any] | None = None,
    decision_before_confidence_flow: str | None = None,
    conf_derivation: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    # ★★ 2026-10-12（按 PRD §5.4 修）：**「问题数」与「分类汇总」必须是同一批条目**。
    #   PRD §5.4 的例子把两者钉成等式：`issue_count: 5` == 分类 2+1+1+1 = 5，
    #   且 `summary` 那句「共发现 5 处」也是同一个数。
    #   实测缺陷（我上一批引入）：改了 `issue_count`（只算库内依据）却没动 `categories`，
    #   后者仍在数全部条目 ⇒ `issue_count=12` / 分类合计 `=17`，同一份 JSON 自相矛盾（5/5 条不成立）。
    #   ⇒ 现在**一处定义**：被计数的条目 = ① 不是 `advice`（P3 建议，PRD §6.3 执行规则3「不改变结论」）
    #     ② 不是非权威候选。`issue_count` 与 `categories` **都从它来**，等式按构造成立。
    #   ★ 候选与建议**都不隐藏**：它们仍在 `risk_items`（完整清单逐条都在），
    #     并各自有计数（`candidate_count`）与就地标注。
    _counted = [item for item in items
                if item.get("action") != "advice" and not is_candidate(item)]
    categories = Counter(_category(item) for item in _counted)
    _cand_n = sum(1 for item in items if is_candidate(item))   # 非权威候选条数（见下方拆解）
    _advice_n = sum(1 for item in items if item.get("action") == "advice")   # P3 建议（不进问题数）
    # ★★ 2026-10-19（Owner：「必须给建议」）：**在渲染之前**把库内没给的建议补进数据 ——
    #   卡（`render_summary`）与报告 / 表 / 下游（`risk_items`）读的是**同一格**，
    #   只在渲染层补一句会造成「卡上有、报告没有」的两端不一致。
    _backfilled = _backfill_advice(items, only_block=(decision == "BLOCK"))
    if _backfilled:
        print("[review_engine] 建议兜底补入 %d 条（库内无原话改法，按 kb/l5/advice_book.py 给）"
              % _backfilled, file=__import__("sys").stderr)
    summary = render_summary(decision, items, categories, report_url)
    # ★ PRD §6.6：0.70–0.89 标注「建议人工确认」；<0.70 标注「不确定，建议人工重点看」。
    #   P0 命中时不适用分流 ⇒ `annotate_summary` 原样返回（一个字不改）。
    summary = confidence_flow.annotate_summary(summary, confidence_route or {})
    result = {
        "review_id": payload.get("review_id"),
        "content_id": payload.get("content_id"),
        # ★ 2026-10-10：`content_id` 的**出处**跟着走。PRD §5.4 要业务编号
        #   （`AD-YYYYMMDD-NNN`），而拿不到业务号时是**指纹兜底**（`AUTO-<sha12>`）。
        #   两者形态不同、各有原因 —— 不跟着走的话，下游只看得到一个字符串，
        #   分不清「发了号」还是「发了号但表读不到」。
        "content_id_basis": payload.get("content_id_basis"),
        "content_version": payload.get("content_version"),
        "agent_version": payload.get("agent_version", "local-core-0.1.0"),
        "rule_version": payload.get("rule_version", "unfrozen"),
        "knowledge_version": payload.get("knowledge_version", "unfrozen"),
        "decision": decision,
        "confidence": confidence,
        "summary": summary,
        # ── ★★ 2026-10-12（Owner 裁定 · 推荐 A）：`issue_count` 的**语义**改成「只算库内依据** ──
        #   病灶（实测，见 `candidate_note` 的 docstring）：原先 `issue_count = len(items)` 把
        #   **非权威候选**（`authoritative is False`，源里自己写着「已被 kb/l3 取代」）
        #   和库内依据**混在同一个数**里 —— 素材 RC-160a343ee259 实测「共发现 17 处」，
        #   其中 **5 处是候选**（3 条还标着 priority_tier=P0）。
        #   ⇒ Owner 2026-10-12 裁定：**「问题数」就是库内依据的条数**，候选不是问题。
        #
        #   ★ 这是一次**破坏性语义变更**，所以同时给出过渡字段（缺一个都要挨骂）：
        #     · `issue_count`                      = 库内依据条数（**新语义**）
        #     · `issue_count_including_candidates` = 完整清单条数（**旧语义**，原样保留一个出口）
        #     · `candidate_count`                  = 非权威候选条数
        #   ★ 2026-10-12 稍后：`authoritative_issue_count`（`issue_count` 的兼容别名）**已撤** ——
        #     它与 `issue_count` 恒等（同一个数两个名字），而全库含守衡那仓**外部读方为 0**（grep 两遍）。
        #     撤的是**重复的名字**，不是出口：要读旧口径那个数，用 `issue_count_including_candidates`。
        #     判据：引擎测试 c6 断言它**不许回来**（有人再加一个兼容名 ⇒ 精确变红）。
        #   为什么要留旧口径的出口：三处行为按这个数分流，**静默改**就是事故 ——
        #     · `feishu_publish` 的报告链接门槛（PRD：<3 不建云文档）；
        #     · 守衡 `dual_track.mjs` 的合并卡（"另有 N 条未并进本卡"的算式）；
        #     · PRD §5.3.3「问题数 ≥3 只出汇总」的逐条/汇总分流。
        #   留了旧口径 ⇒ 任何一处觉得新口径不合用，都能**显式**读回旧数，而不是回头改引擎。
        "issue_count": len(_counted),
        "issue_count_including_candidates": len(items),
        "candidate_count": _cand_n,
        "issue_count_basis": (
            "issue_count（%d = 库内依据，**与分类汇总同一个数**，见 PRD §5.4）= 完整清单 %d "
            "− 非权威候选 %d%s；候选无库内条款号、只作排查线索，不构成依据"
            % (len(_counted), len(items), _cand_n,
               " − P3 建议 %d" % _advice_n if _advice_n else "")),
        "issue_summary_by_category": dict(categories),
        "risk_items": items,
        "report_url": report_url,
        "next_action": _next_action(decision),
        "next_owners": payload.get("next_owners") or route_owners(items, decision),
        "sla": resolve_sla(decision, items),
        "version_gate": payload.get("version_gate", {}),
        "coverage": payload.get("coverage", {}),
        "decision_trace": {
            "reasons": reasons,
            "confidence_status": "heuristic_not_calibrated",
            "evaluated_at": _now(),
            # ★ 2026-10-10：四层命中计数（PRD §6.3）。**只记数、不参与判定** ——
            #   判定用上面那几条显式分支；这里是让「这一单到底哪一层触发的」查得出来，
            #   不然分层落了地也看不出来。
            "tier_trace": tier_trace or {},
            # ★ PRD §6.6 置信度分流（2026-10-10 接线）。`calibrated` 恒为 false ——
            #   阈值是 **PRD 政策值**，不是标定值；这一格不许被写成 true。
            "confidence_route": dict(confidence_route or {},
                                     thresholds_source=CONFIDENCE_POLICY_SOURCE),
            # ★ 2026-10-12：置信度**怎么算出来的**（改前是分支常量，没什么可记的）。
            #   一个数要有分布、要能标定，就必须**看得出它是哪几项加出来的** ——
            #   否则标定完也解释不了「为什么这单是 0.86」。
            "confidence_derivation": dict(conf_derivation or {}),
            # 分流压过结论时，**原结论必须看得见**（否则事后分不清「本来 BLOCK」与「本来就 REVIEW」）
            "decision_before_confidence_flow": decision_before_confidence_flow or decision,
        },
    }
    # ── SUGGEST 作为 **PASS 的附属标签**（PRD §5.3.2 rev101）━━━━━━━━━━━━━━━━━━━━━━
    #   三条字段各管一件事，缺一条就有一半看不见：
    #     `suggestions[]`  —— 建议本体（逐条：层级/维度/位置/建议/原因）。**任何结论下都挂**
    #                         （§6.3 规则2：「同一内容可同时有 BLOCK 和 SUGGEST」，最终状态取 BLOCK）。
    #     `suggest_count`  —— 建议条数（统计用；与 `issue_count` **不是一个数**：
    #                         问题数只算库内依据、不含 advice，这一条数的是 advice）。
    #     `suggest_label`  —— **只在 `decision=PASS` 且建议非空** 时为 True。
    #                         它就是「四态」第二个桶的判定式：`PASS+SUGGEST ≡ decision=PASS ∧ suggest_label`。
    #   ⚠️ 不许写成「有建议就 True」：§5.3.2 说的是 **PASS 的**附属标签；
    #      BLOCK 单里带建议**不叫 SUGGEST**（§6.3 规则2 最终状态就是 BLOCK）。
    result["suggestions"] = _suggestions(result.get("risk_items") or [])
    result["suggest_count"] = len(result["suggestions"])
    result["suggest_label"] = bool(result["suggest_count"]) and result.get("decision") == "PASS"
    return result


def _next_action(decision: str) -> str:
    return {
        "PASS": "转 sign-off 负责人确认送审版本与发布版本一致",
        # ★ 2026-10-19 第二轮：`SUGGEST` **不再是结论态**（PRD §5.3.2 rev101：PASS 的附属标签）。
        #   这一条**保留**只为兼容存量旧 JSON 的重渲染（那些老产物里 `decision` 可能是 SUGGEST）；
        #   新产物不会再走到它。措辞照 PRD 的动作列：「随 PASS 一起流转，提示内容方」。
        "SUGGEST": "随 PASS 一起流转、提示内容方按建议优化（不阻断流程，PRD §5.3.2 rev101）",
        "REVIEW": "转法务、医学、专家或北美本地同事人工复核",
        "BLOCK": "修改内容后以新版本重新提交",
        "NEEDS_INPUT": "补齐素材、权限、SKU、版本或证据后重新提交",
    }[decision]


# ── 责任人：**从 kb/l7/registry/l7.json 的 approvers 读，不写死人名** ──────────
#
# 这是 `kb/l7/output_template.md` 开头那条硬规矩。组织一变动，写死的人名就变成假话；
# 而这里读不到配置时**不许编**一个句柄 —— 按库规输出「角色名（未配置）」，
# 让「还没配」这件事在结论里看得见（AGENTS.md §2.4.4：未测/未配不许长得像已配）。
_KB_ROOT = Path(__file__).resolve().parents[3]

_FALLBACK_ROLE = {
    "pass_signoff": "sign-off 责任人",
    "review_reviewers": "复核责任人",
    "block_owner": "内容方修改责任人",
}


def _approvers() -> Dict[str, Any]:
    """读 approvers；**任何异常都当作未配置**（判据是「拿到的句柄」，不是「文件在不在」）。"""
    try:
        raw = json.loads((_KB_ROOT / "kb" / "l7" / "registry" / "l7.json").read_text(encoding="utf-8"))
        node = raw.get("approvers")
        return node if isinstance(node, dict) else {}
    except Exception:
        return {}


def _at(role: str) -> str:
    """角色（**key 或角色名**）→ `@句柄` ／ `@角色名（未配置）`。

    两种入参都要吃（2026-10-14 加第二种）：

      · **key**（`pass_signoff` / `review_reviewers` / `block_owner`）——
        `l7.json` 的 `approvers` 那几个桶的键；
      · **角色名**（`法务` / `医学顾问` / `北美同事` …）——
        `routing-policy.json` 的 `roles` 收敛名，由 `routing` 按问题方向算出来。

    ★★ 为什么必须加第二种（**当天抓到的真缺陷**）：路由把「法务」传进来，
      旧实现拿它当 key 去 `_approvers()` 查 ⇒ 查不到 ⇒ 走 `_FALLBACK_ROLE`
      兜底成 **`@责任人（未配置）`** —— **角色名丢了**，业务侧看到的是
      「转责任人复核」，比改动前更没法用。

    ★ 本条注释原先就写着「读不到配置时不许编一个句柄 —— 按库规输出**角色名**（未配置）」，
      而实现把**角色名**换成了兜底词「责任人」。**注释与实现不一致**，
      这次把实现对齐注释：拿到的名字是什么就输出什么。
    """
    node = _approvers().get(role)
    node = node if isinstance(node, dict) else {}
    handle = node.get("handle")
    if handle:
        return f"@{handle}"
    # 没配句柄：**保留传进来的那个名字**（角色名或 key 的声明名），
    # 只有传进来的是个查不到的 key 时才退回兜底词。
    name = node.get("role") or role
    if not node and role in _FALLBACK_ROLE:
        name = _FALLBACK_ROLE[role]
    return f"@{name}（未配置）"


# ── 收尾动作行：**按问题方向转对应专业团队**（PRD §9 / §5.3.2）─────────────────
#
# ★★ 2026-10-14（Owner 报「与 PRD 不符」）—— 这一行原先是 `_at('review_reviewers')`：
#   一个**通用桶**（`l7.json` 里 `review_reviewers.role = "复核责任人"`），
#   所有方向的问题都转给同一个人。而 PRD §5.3.2 **两处**逐字写着
#   `建议转 @法务 @医学顾问 复核。`，§9 写「REVIEW 自动转**对应**专业团队」。
#
#   现在：方向词 → `routing-policy.json` → owners → 逐个渲染句柄。
#   `_at` 仍是**句柄的唯一口径**（本函数不自己读 `l7.json`）。
#   ⚠️ 只改了**收件人**；句式 `建议转 … 复核。` 与「一个方向都没命中时回落」都是原样。
#      `prd53.mjs::conforms()` 只核**结论行**（`共发现 N 处…`），不核这一行 ⇒ 不打架。
def _review_action_line(items: Any) -> str:
    return routing.review_action_line(items or [], _at)


# `《措辞表达库 v0》第 W-1.40 条 @ …` —— 引用契约里库名与版本就在这一串里，能解析就用原文。
_EVIDENCE_ID_RE = re.compile(r"^《(?P<lib>[^》]+)》\s*第\s*(?P<art>\S+?)\s*条")


def _evidence_line(item: Dict[str, Any]) -> str:
    """`依据：《库名 版本》第 X 条（链接：…）` —— 三个槽位缺哪个就**明说缺哪个**，不代填。"""
    ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    lib = str(ev.get("library") or "").strip()
    art = str(ev.get("article_no") or "").strip()
    url = str(item.get("evidence_url") or ev.get("url") or "").strip()

    m = _EVIDENCE_ID_RE.match(str(item.get("evidence_id") or "").strip())
    if m:  # 引用契约自己那串最权威：库名与版本都在里面
        lib_with_ver = m.group("lib")
        art = art or m.group("art")
    else:
        lib_with_ver = f"{lib} v0（试用版，未发布）" if lib else "（来源未给库名）"
    art = art or "（来源未给条款号）"
    url = url or "（来源未给链接）"
    # ── ★ 2026-10-08（Owner：「输出的依据这里，展示**溯源命中文案 + 飞书源链接**」）──────
    #
    #   改前这里印的是 `（链接：{url}）`，而实测那个 url 是
    #   **`kb/l3/candidates/rules.jsonl#W-1.16`** —— 库内相对路径、指向 **L3 规则候选层**：
    #   业务同事点不开，而且 L1–L3 是库的**内部加工层**，看完没有下一步动作。
    #
    #   要的两样东西库里**早就有现成函数**（只是没接到这一行）：
    #     · `feishu_publish.l0_verbatim(anchor, excerpt)` —— **逐字命中文案**（并与 L0 原文核对）
    #     · `feishu_publish.l0_locate(anchor, sha)`      —— L0 坐标 + **`entry_url`（飞书记录直链）**
    #   惰性 import：`feishu_publish` 与本案同目录，顶层 import 有循环风险，这里按需取。
    anchor = str(item.get("anchor") or ev.get("anchor") or "").strip()
    sha = str(item.get("source_sha256") or ev.get("source_sha256") or "").strip()
    excerpt = str(item.get("excerpt") or item.get("matched_term") or "").strip()
    hit = f"逐字命中「{excerpt}」" if excerpt else "（来源未给命中片段）"
    link = None
    vv = None
    try:
        from feishu_publish import l0_locate, l0_verbatim     # noqa: PLC0415
        loc = l0_locate(anchor, sha) if anchor else None
        vv = l0_verbatim(anchor, excerpt) if anchor else None
        link = (loc or {}).get("entry_url") or (vv or {}).get("entry_url")
    except Exception:                                        # noqa: BLE001
        link = None                                          # 取不到就说取不到，不假装
    # 飞书源链接优先；给不出时**照实说这是库内路径**，不许拿它冒充「原始出处」。
    src = (f"原始出处：{link}" if link
           else (f"原始出处：（L0 未定位到飞书直链，库内路径 {url}）" if url
                 else "原始出处：（来源未给链接）"))
    # 逐字核对结论（verbatim_hit / partial / mismatch / no_excerpt）—— 只在**不是**逐字命中时报，
    # 命中是常态，报了是噪音。
    vnote = ""
    if isinstance(vv, dict) and vv.get("verdict") not in (None, "verbatim_hit"):
        vnote = f"（L0 逐字核对：{vv.get('verdict')}）"
    return f"依据：《{lib_with_ver}》第 {art} 条 ← {hit}{vnote}｜{src}"


def _item_lines(index: int, item: Dict[str, Any], *, want_suggestion: bool) -> List[str]:
    """PRD §5.3.2 / §5.3.3 的**逐条四要素**：类别-子类 · 位置 · 引文 · 原因 · 依据（+引用契约 + 建议）。

    ★ 为什么每一格都要有一个「来源未给 X」的兜底：这一段的病从来不是「少写一行」，
      而是**缺了也看不出来** —— 读者以为「没有原因」等于「没有原因可写」。
      写出来，缺口才是可核对的读数（库规：缺前置必须可见，不许静默）。
    """
    ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    loc = str(item.get("location") or "").strip() or "未定位"
    quote = str(item.get("original_text") or "").strip() or "（来源未给引文）"
    reason = str(item.get("reason") or "").strip() or "（来源未给判定理由）"
    # ★★ 2026-10-09（Owner：「报告里那两条『命中』根本不是我的图上文字」）──────────────
    #   病灶：引文那一段的标签**写死了「命中」**，而**案例层（L4 定稿的「反例/禁区」）**的
    #   `excerpt` 取自**案例记录正文**（`review.py` 明写「该锚点的 L0 件本地无字段值 ⇒
    #   摘录取自案例记录本身」）—— 那不是本素材里的字，是**库里某条历史案例**的原话。
    #   实测（图单 `M7DbdQUvbopAkmxGdsRccGstnTg`）报告里印出来是：
    #     「原因：库内反例条款 S-1.209（措辞表达）与本素材**同源/同题材**：
    #       【措辞表达】图片 P21 【终审- @吴礼芳 】麻烦看看呀～…亚马逊多语言修改…figma.com」
    #   ⇒ 读者会以为**自己图上写着这些**（实测 Owner 当场就问「这是我吗」）。
    #   ⇒ 按 `layer` 分档给标签：案例层**不许再说「命中」**，如实说「同类案例（非本素材命中）」。
    #   ⚠️ 只改**标签**，引文内容一个字不改 —— 它仍是可回源的库内原文（溯源要用）。
    _layer = str(item.get("layer") or "")
    _is_case = "案例" in _layer
    _quote_label = "同类案例（**非本素材命中**，可回源核对）" if _is_case else "命中"
    # ★ 2026-10-09：引文与原因也要过 `md_text_safe` —— 库内原文**含原始 HTML**，
    #   而飞书 `docs +create` 会把 markdown 里的 `<…>` 当 HTML 解析
    #   （实测：整份 12,877 字节的报告因一个 `<img …>` 被**整体拒收**）。
    #   ⚠️ 复用 `with_kb_evidence.md_text_safe`（**唯一产者**），惰性 import ——
    #      那边顶层 import 本模块，直接引会成环（与 `feishu_publish.l0_locate` 同一套做法）。
    def _safe(s):
        try:
            from with_kb_evidence import md_text_safe      # noqa: PLC0415
            return md_text_safe(s)
        except Exception:                                  # noqa: BLE001
            return str(s if s is not None else "")         # 拿不到就原样，不静默改内容
    # ★★ 2026-10-19（Owner：「所属类别/所属子类」统一到 A3 12 类）：首行标签改用 A3。
    out = [f"{index}.【{_tax_label(item)}】{loc}，{_quote_label}：{_safe(quote)}"]
    # ★ 2026-10-12：候选条目在**逐条**这一层也要认出来 —— 否则下面「依据」那行会印成
    #   `（来源未给库名）/（来源未给条款号）/（来源未给链接）`，读者只看到"空了"，看不到"为什么空"。
    _ci = candidate_item_note(item)
    if _ci:
        out.append("  " + _ci)
    out += [f"  **原因**：{_safe(reason)}",
            f"  **依据**：{_evidence_line(item)[len('依据：'):]}"]

    # ★★ 2026-10-19（Owner 逐字：「**去掉锚点**」＋「**卡片信息必须按照 PRD 字段执行**」）——
    #   **逐条块不再输出 `**锚点**：…#sha` 那一行**（这一处与 `kb/l5/p0_fastpath.py`
    #   的 `_prd_block` 是同一批改，两处都是守衡卡片的产者，只改一处会剩一条腿）。
    #   为什么删：锚点是**库内坐标**（`#广告文案明细/rec…/命中片段`），业务侧读不懂也不该读；
    #   PRD §5.3.3/§5.3.4 的逐条字段只有【维度-子类】位置·原文·原因·依据（含链接）·建议。
    #   ⚠️ **溯源没有丢**：`evidence.anchor` / `evidence.source_sha256` 仍在
    #      `risk_items` / 报告 JSON / `_evidence_line` 的定位链路里（`l0_locate` 用的就是它），
    #      `kb/l8/e2e_acceptance.py` 的四段溯源与 `workflow_smoke` S4 读的也是**报告与 JSON**，
    #      不是这张卡。删的是**卡上那一行**，不是证据。
    #   ⚠️ 别把 `_evidence_line` 里那串「原始出处：https://…」当锚点顺手删了 ——
    #      那是 PRD「依据…（链接）」里的**链接**，是必填格。

    # ★★ 2026-10-14（Owner 裁定）：**逐条块不再输出 `**判定**` 行**。
    #   口径：PRD §5.3 的逐条模板只有 `原因` / `依据` /（BLOCK 才有）`建议`，
    #   三态只出现在**结论行** `【审查结论：X】` 一处 —— 逐条再挂一个「判定」，
    #   同一张卡上就有两个「判定」，业务侧分不清哪个是结论。
    #   ⇒ 取值侧 `fact_or_inference` / `confidence` **仍在 JSON 与报告里**（只改版式，不改数据），
    #     只是不再渲染进 §5.3 逐条块。

    sug = str(item.get("suggestion") or "").strip()
    # BLOCK 的「建议」是 PRD §5.3.3 的必备项 ⇒ 没有也要把「没有」写出来；
    # REVIEW 的模板里没有这一行 ⇒ 有才写（库规：一个格，一行，没有就不写）。
    #
    # ★★ 2026-10-19（Owner：「**必须给建议**」）：**不再印「（来源未给修改建议）」**。
    #   改前这一格是两个取值口（`item.suggestion` → 占位符），实测 17 条 P0 模式里 10 条
    #   走到占位符 ⇒ 收卡人看完还是不知道改什么。现在第三个口 = 兜底改法表
    #   `kb/l5/advice_book.py`（与 P0 快路**同一份**，不各写一套）。
    if sug:
        out.append(f"  **建议**：{sug}")
    elif want_suggestion:
        _adv, _src = _fallback_advice(item)
        # ⚠️ 卡上**不加来源说明**（PRD §5.3.3/§5.3.4 的「建议」就一格，且 ≤30 字）；
        #   出处落在数据里（`suggestion_source`，见 `_backfill_advice`）与报告 JSON，
        #   与 P0 快路那一侧同口径（那边标在**报告**的「建议」格尾，卡上同样干净）。
        out.append(f"  **建议**：{_adv}")
    return out


def _backfill_advice(items: List[Dict[str, Any]], *, only_block: bool = True) -> int:
    """把「建议」补进**数据**（不只是渲染）—— 卡与报告才可能逐字一致。

    ★ 2026-10-19（Owner：「必须给建议」）。为什么要补在数据层：
      改前 `item["suggestion"]` 为空时，**卡**上印占位符、**报告**（`risk_items`）里也是空 ——
      现在若只在渲染层给一句，就会出现「卡上有建议、报告里没有」的两端不一致
      （本库为这类形状返工过：⑥f 就是钉这个的）。所以在这一层补，
      `render_summary`（卡）与 `risk_items`（报告 / 表 / 下游）**读同一格**。

    - `only_block=True`（默认）只补 **BLOCK** 单：PRD §5.3.4 的 REVIEW 模板里**没有**逐条
      「建议」那一行（改法是 `建议转 @… 复核。`），给 REVIEW 逐条补建议＝改 PRD 版式。
    - 只补 `action != 'advice'` 的条目（P3 建议行的 `suggestion` 是它自己的正文，不动）；
    - **已有建议一个字不改**（库内原话优先）；
    - 补进来的那句同时记 `suggestion_source`（`p0_advice_book:<CODE>` / `generic_*`），
      让人查得到「这句是库规原文还是我们按边界给的」。

    @returns 补了几条（写日志用，不改变结论）。
    """
    n = 0
    for item in items or []:
        if not isinstance(item, dict) or item.get("action") == "advice":
            continue
        if only_block and str(item.get("action") or "").lower() != "block":
            continue
        if str(item.get("suggestion") or "").strip():
            continue
        adv, src = _fallback_advice(item)
        if not str(adv or "").strip():
            continue
        item["suggestion"] = adv
        item["suggestion_source"] = src
        n += 1
    return n


_ADVICE_BOOK = None


def _advice_book():
    """兜底改法表（唯一来源 = `kb/l5/advice_book.py`）。加载失败 ⇒ 空壳（不静默：打日志）。"""
    global _ADVICE_BOOK
    if _ADVICE_BOOK is not None:
        return _ADVICE_BOOK
    try:
        import importlib.util as _ilu                        # noqa: PLC0415
        _kb = Path(__file__).resolve().parents[3]            # …/kb
        _p = _kb / "l5" / "advice_book.py"
        _spec = _ilu.spec_from_file_location("kb_advice_book_re", str(_p))
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _ADVICE_BOOK = _mod
    except Exception as e:                                  # noqa: BLE001
        import sys as _sys                                  # noqa: PLC0415
        print("[advice_book] ⚠ 兜底改法表加载失败 ⇒ 建议降级为通用句：%s" % e, file=_sys.stderr)

        class _Empty:
            @staticmethod
            def fallback(rule_code=None, rule_id=None, hits=()):
                return ("删去命中的违规表述后再提交。", "generic_no_book")

        _ADVICE_BOOK = _Empty()
    return _ADVICE_BOOK


def _fallback_advice(item: Dict[str, Any]) -> tuple:
    """这一条的兜底改法 → `(text, source)`。

    ★ 取键：评审链的 `risk_item` **只有 `risk_id`（= rule_id）**（见
      `review.py::_finding_to_risk_item`），没有 `rule_code` ⇒ 必须两把键都传，
      兜底表按 `rule_id → rule_code` 归一（`advice_book.code_of`）。只传一个键，
      这一侧就永远取不到表（"接了一半"是本库栽过多次的形状）。
    """
    ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    hits = [str(item.get("original_text") or "").strip(),
            str(ev.get("excerpt") or "").strip()]
    return _advice_book().fallback(rule_code=item.get("rule_code"),
                                   rule_id=item.get("risk_id") or item.get("rule_id"),
                                   hits=[h for h in hits if h])


def render_summary(decision: str, items: List[Dict[str, Any]], categories: Counter, report_url: str | None) -> str:
    """PRD §5.3 三态结论输出规范。**措辞逐字照 PRD，不许同义替换。**

    ★ 2026-10-06 改。此前 REVIEW 与 BLOCK **共用同一句话**「共发现 N 处需处理问题」，
      而 PRD §5.3.2 / §5.3.3 是两句不同的（「需人工确认」/「必须修改」）。
      为什么长期没被发现：`kb/.work/l7_integrity.py` 的 `template_conformance`
      只断言到 `【审查结论：REVIEW】共发现` 为止 —— **后半句它没查**。
      判据存在，但没盖住出事的那一跳（AGENTS.md §2.4）。现在两边一起改：
      这里出对的措辞，那里把后半句也断言上。
    """
    if decision == "SUGGEST":
        # ★★ 2026-10-19 第二轮（PRD §5.3.2 **rev 101**）：**SUGGEST 不是结论态**，不许再渲染结论行。
        #   硬失败而不是"悄悄降级"：这一行要是还能印出来，卡面就又长出第四态，
        #   而 `decision` 三值、统计四桶的口径会被它悄悄破掉（最坏的一种：看不出来）。
        raise ValueError(
            "SUGGEST 不是结论态：PRD §5.3.2（rev 101）把它定为「**PASS 的附属标签**」"
            "（`decision` 只取 PASS / REVIEW / BLOCK，+ 拒答 NEEDS_INPUT）。"
            "要出建议请走 `decision=PASS` ＋ `risk_items` 里 `priority_tier=P3` 的条目 —— "
            "`render_summary` 会把它们渲染成「建议（不阻断，随 PASS 流转）」附段。"
            "留痕：kb/l7/registry/prd532-states.yaml::conflict_decision.superseded_by。"
        )
    if decision == "PASS":
        head = f"【审查结论：PASS】未发现已知底线风险，可转交 {_at('pass_signoff')} 进行 sign-off。"
        # ★★ 2026-10-19 第二轮（PRD §5.3.2 rev101）：PASS 定义原文「**可包含 SUGGEST 建议**」，
        #   动作「随 PASS 一起流转，提示内容方」。
        #   ⇒ 结论行**恒为 PASS**，建议作为**附段**（不另起结论行、不派单、不进问题数）。
        #   §17 对这一段的要求：「逐条列建议 + 不阻断说明」≤150 字/条（按条量）——
        #   所以每条只写「维度 + 位置 + 建议」，不硬塞「原因 / 依据」两行（那是问题条目的事）。
        adv = [i for i in items if str(i.get("priority_tier") or "") == "P3"]
        if not adv:
            return head
        return "\n".join([
            head,
            "",
            "建议（不阻断，随 PASS 流转，共 %d 条）：" % len(adv),
            "",
            "\n\n".join(_suggestion_lines(adv)),
        ])
    if decision == "NEEDS_INPUT":
        return "【审查结论：NEEDS_INPUT】当前素材、版本或证据不完整，补齐后再审。"

    # ★★ 2026-10-12（Owner 裁定）：**这个数也改成「只算库内依据」** —— 与 `issue_count` 同口径。
    #   为什么必须一起改（不然就是自己跟自己打架）：逐条路径会把 `items` **全部**列出来，
    #   若句子里的数还是 `len(items)`、而字段是小口径，同一份输出就出现两个"问题数"。
    #   口径**只有一处**：`is_candidate()`（判显式 `authoritative: False`）。
    # ★★ 2026-10-12（按 PRD §5.4 的第二处残留）：**这句的数必须与 `issue_count` 同批**。
    #   PRD §5.4 的例子把「summary 里共发现 N 处」「issue_count」「分类汇总合计」钉成**同一个数**。
    #   上一处（`issue_count` vs `categories`）已修；这一处当时**漏了** ——
    #   实测：2 依据 ＋ 1 条 P3 建议(advice) ⇒ `issue_count=2`、分类合计=2，而**这句话说 3**。
    #   口径与 `_result` 里的 `_counted` **逐字一致**：排除 `advice`（§6.3 规则3「不改变结论」）＋ 排除候选。
    _cand_n = sum(1 for i in items if is_candidate(i))
    n = sum(1 for i in items if i.get("action") != "advice" and not is_candidate(i))
    # ★★ 2026-10-12 修（**我自己上一批引入的缺陷**，Owner 一问戳出来）：
    #   上一版把候选说明**接在 PRD 那句同一行**（`…需人工确认。（另有 N 处候选线索…）`）。
    #   实测代价：守衡 `prd53.mjs::conforms()` 用 **`$` 锚定**逐字校验这一行 ——
    #     /^【审查结论：REVIEW】共发现 \d+ 处需人工确认。$/
    #   而 `LINE_RE` 是 `[^\n]*`（**取到行尾**）⇒ 取到的行带着我那半句 ⇒ `conforms` 判 **false**，
    #   卡面标题也就不再是 PRD 的那一句。实测判定原文：
    #     {"ok":false,"why":"REVIEW 行必须是「共发现 N 处需人工确认。」"}
    #   两边测试都没红的原因也清楚：kb 侧只断言**子串**（`assertIn("共发现 1 处")`），
    #    守衡 `verify_cards.mjs` 用的是**夹具**（喂的是手写的那句），盖不到真输出。
    #   ⇒ 现在这一行**逐字不动**；候选改由**独立一行**说（`candidate_note(items)`，
    #     逐条路径与汇总路径**本来就已经各有一句**，所以上一版那半句其实**是多余的**）。
    # PRD §5.3.2 与 §5.3.3 的两句**不一样**，这正是原先被抹平的那一处。
    head = (f"【审查结论：REVIEW】共发现 {n} 处需人工确认。"
            if decision == "REVIEW" else
            f"【审查结论：BLOCK】共发现 {n} 处必须修改。")

    if n <= 2:  # 分流阈值 3（PRD §5.3.4），逐条展开 —— 与 `feishu_publish` 的报告门槛**同一个数**
        # ★★ 2026-10-14（Owner：「审核结论中 1，2...每条之间需要空一行的 …… 都要跟 prd 对齐」）
        #
        #   PRD §5.3.2 的逐字形状（`␤` = 空行）：
        #       【审查结论：REVIEW】共发现 2 处需人工确认。
        #       ␤
        #       1.【合规-医疗宣称】……
        #         原因：…… ／ 依据：……
        #       ␤
        #       2.【消费者安全-使用姿势】……
        #       ␤
        #       建议转 @法务 @医学顾问 复核。
        #
        #   ⇒ **结论行之后一个空行 · 每条之间一个空行 · 动作行之前一个空行**。
        #   改前实测：**一条空行都没有**（`lines.extend(...)` 直接首尾相接）。
        #   口径：`_item_lines` 保持「返回一个条目的若干行」不变 ⇒ 空行**只在这里加一处**。
        # ⚠️ 组块口径（第一版写错过，这里记下来）：每个条目先 `"\n".join(...)` 收成**一个字符串**，
        #   块与块之间用 `"\n\n"` 接 —— 那是**一个**空行。若改成「往 `lines` 里逐块 extend、
        #   块尾再补 `""`、最后 `"\n".join(lines)`」，空行会**变成两个**（实测过）。
        blocks = ["\n".join(_item_lines(i, item, want_suggestion=(decision == "BLOCK")))
                  for i, item in enumerate(items, start=1)]
        blocks = [b for b in blocks if b.strip()]
        # 末尾那个 `""` = **动作行之前的空行**（PRD：`…依据…` ␤ `建议转 …`）
        lines = [head, "", "\n\n".join(blocks), ""]
        # ★ 2026-10-12：逐条路径也要那一行合计说明（`_item_lines` 里已有**逐条**的标记，
        #   这一行给的是**合计**；两条路径共用同一句，不许各写一份）。
        _cn = candidate_note(items)
        if _cn:
            lines.extend([_cn, ""])
        lines.append(_review_action_line(items) if decision == "REVIEW" else "请修改后重新提交。")
        return "\n".join(lines)

    lines = [head]
    # ★ 2026-10-06 修：PRD §5.3.2/5.3.3 的 ≥3 汇总形状是 `· <大类>类问题：N 个`，
    #   而这里原先只写 `· {category}：{count} 个` —— **少「类问题」三字**。
    #   同一个库里另一个产者（`l7/skills/kb-content-review/scripts/review.py:803`）
    #   写的是 `· {k}类问题：{v} 个`，两边不一致，而实测发出去的那条正是缺字这一版。
    #   同时把**子类归并到大类**（`平台与促销-促销紧迫感表述` ⇒ `平台与促销`）——
    #   PRD 的例子是 `合规类问题：3 个`，按大类计。
    #
    # ★★ 2026-10-19（Owner：「问题数量≥3 时要有分类汇总 `· 合规类：X 个 · 消费者安全类：X 个
    #   · 措辞类：X 个`……卡片所有的回复必须跟 PRD 5.3 对齐」）—— **这一格的轴改成 PRD 四维**：
    #   上面那条 2026-10-06 的口径按的是**库内类别**（`功效宣称` / `平台与促销` …），
    #   与 PRD §5.3 的维度**不是一套**；而这一单的卡上印出 `· 功效宣称类问题：4 个`，
    #   与 Owner 要的那一行对不上。轴的口径**只读** `item["risk_category"]`
    #   （由 `review.py` 统一盖章，唯一真源 `risk-category-policy.json`），取不到落
    #   `未标注维度` 桶（与 `risk_category.UNMAPPED_BUCKET` 同一个词），**不猜**。
    #   形状照 PRD §5.3.4：**一行**、`·` 分隔、`<维度>类：N 个`；条数降序 → 并列按四维顺序
    #   → 未标注维度压最后。
    #   ⚠️ 候选不计入这一行（`categories` 那份本来就是只含库内依据的计数，口径不变）；
    #      候选的合计说明仍由下一段的 `candidate_note(items)` 独立一行承担。
    # ★★ 2026-10-19（Owner：「所属类别/所属子类」统一到 A3 12 类）：汇总轴从 **A2 四维**
    #   换成 **A3**（`taxonomy_category`）—— 与逐条首行、规则行、报告同一套；盖不到的落 `未归类`。
    _counted = [i for i in items if i.get("action") != "advice" and not is_candidate(i)]
    _tax_agg = Counter()
    for _i in _counted:
        _tax_agg[_tax_category(_i)] += 1
    if not _tax_agg:                       # 兜底：没有条目时与老行为一致（按传入的类别数）
        for _c, _n in categories.items():
            _tax_agg[str(_c).split("-")[0].split("－")[0].strip() or TAX_UNCLASSED] += _n
    _tax_order = {n: i for i, n in enumerate(_taxonomy_classes())}
    # 顺序照 12 类注册表的固定次序；未归类压最后
    _tax_keys = sorted(_tax_agg, key=lambda k: (k == TAX_UNCLASSED, _tax_order.get(k, 99), k))
    lines.append("")
    # ★ 形状（Owner 2026-10-19 给的格式）：**每类一行**，行间不空行；兜底写 `· 未归类问题：N 个`。
    lines.extend("· %s问题：%d 个"
                 % (k if k == TAX_UNCLASSED else k + "类", _tax_agg[k]) for k in _tax_keys)
    # 候选的合计说明行（逐条路径与汇总路径**共用一句**，见 `candidate_note`）
    _cn = candidate_note(items)
    if _cn:
        lines.extend([_cn, ""])
    # PRD §5.3.4：≥3 个时**只出分类汇总 + 报告链接**，完整清单必须真的写进报告文件。
    # 报告没落盘时不许写「查看完整清单」（那会指向一个不存在的东西）—— 照实说没写。
    # ★ 2026-10-06：链接必须是**能点开的东西**才算「查看」。
    #   实测发出去的那条 REVIEW（3 个问题）写的是 `kb/l7/reports/….md` ——
    #   那是个**本地路径**，群里的人点不开，而 PRD §5.3.2 的原话是
    #   `→ 查看完整问题清单与修改建议：https://feishu.cn/review/xxx`。
    #   给不了 URL 时**照实说它是本地件**，不许拿一句「查看…」把人引到一个打不开的东西上。
    # ★★ 2026-10-14：链接与动作行**各自成块**（PRD：汇总行 ␤ 链接 ␤ 动作行 —— 各一个空行）。
    lines.append("")
    if report_url and str(report_url).startswith(("http://", "https://")):
        lines.append(f"→ 查看完整问题清单与修改建议：{report_url}")
    elif report_url:
        lines.append(f"→ 完整问题清单与修改建议在**本地报告**里（不是可点链接）：{report_url}")
    else:
        lines.append("→ 查看完整问题清单与修改建议：（本次未写报告，见 --report-dir）")
    lines.append("")
    lines.append(_review_action_line(items) if decision == "REVIEW" else "请修改后重新提交。")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local brand review decision engine")
    parser.add_argument("input", type=Path, help="Review payload JSON")
    parser.add_argument("--report-url", default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = decide(payload, args.report_url)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
