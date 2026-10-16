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


DECISIONS = {"PASS", "REVIEW", "BLOCK", "NEEDS_INPUT"}
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
    confirmed_p0 = [
        i for i in items
        if i["priority_tier"] == "P0" and i["status"] == "confirmed" and i["evidence_complete"]
    ]
    uncertain_p0 = [i for i in items if i["priority_tier"] == "P0" and i["status"] != "confirmed"]
    blocking = [
        i for i in items
        if i.get("action") == "block" and i["status"] == "confirmed" and i["evidence_complete"]
    ]
    review_items = [
        i for i in items
        if i.get("action") == "review" or i["status"] != "confirmed" or not i["evidence_complete"]
    ]

    if confirmed_p0 or blocking:
        decision = "BLOCK"
        confidence = 0.97 if confirmed_p0 else 0.93
        reasons = ["confirmed_p0" if confirmed_p0 else "confirmed_block_with_evidence"]
    elif uncertain_p0 or review_items:
        decision = "REVIEW"
        confidence = 0.78
        if uncertain_p0:
            confidence -= 0.05
        if any(not i["evidence_complete"] for i in review_items):
            confidence -= 0.05
        reasons = ["uncertain_or_review_item"]
    else:
        decision = "PASS"
        confidence = 0.99
        reasons = ["no_known_blocking_or_review_risk"]

    return _result(payload, decision, items, round(max(0.0, confidence), 2), reasons, report_url)


def _result(
    payload: Dict[str, Any],
    decision: str,
    items: List[Dict[str, Any]],
    confidence: float,
    reasons: List[str],
    report_url: str | None = None,
) -> Dict[str, Any]:
    categories = Counter(_category(item) for item in items if item.get("action") != "advice")
    summary = render_summary(decision, items, categories, report_url)
    result = {
        "review_id": payload.get("review_id"),
        "content_id": payload.get("content_id"),
        "content_version": payload.get("content_version"),
        "agent_version": payload.get("agent_version", "local-core-0.1.0"),
        "rule_version": payload.get("rule_version", "unfrozen"),
        "knowledge_version": payload.get("knowledge_version", "unfrozen"),
        "decision": decision,
        "confidence": confidence,
        "summary": summary,
        "issue_count": len(items),
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
        },
    }
    return result


def _next_action(decision: str) -> str:
    return {
        "PASS": "转 sign-off 负责人确认送审版本与发布版本一致",
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


def _at(role_key: str) -> str:
    node = _approvers().get(role_key)
    node = node if isinstance(node, dict) else {}
    handle = node.get("handle")
    role = node.get("role") or _FALLBACK_ROLE.get(role_key, "责任人")
    return f"@{handle}" if handle else f"@{role}（未配置）"


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
    out = [f"{index}.【{_category(item)}】{loc}，{_quote_label}：{_safe(quote)}",
           f"  **原因**：{_safe(reason)}",
           f"  **依据**：{_evidence_line(item)[len('依据：'):]}"]

    anchor = str(ev.get("anchor") or "").strip()
    sha = str(ev.get("source_sha256") or "").strip()
    if anchor or sha:
        out.append(f"  **锚点**：{anchor or '（来源未给锚点）'}｜source_sha256：{sha or '（来源未给指纹）'}")
    fact = str(item.get("fact_or_inference") or "").strip() or "未判定"
    conf = str(item.get("confidence") or "").strip() or "未给"
    out.append(f"  **判定**：{fact}｜置信度：{conf}")

    sug = str(item.get("suggestion") or "").strip()
    # BLOCK 的「建议」是 PRD §5.3.3 的必备项 ⇒ 没有也要把「没有」写出来；
    # REVIEW 的模板里没有这一行 ⇒ 有才写（库规：一个格，一行，没有就不写）。
    if sug or want_suggestion:
        out.append(f"  **建议**：{sug or '（来源未给修改建议）'}")
    return out


def render_summary(decision: str, items: List[Dict[str, Any]], categories: Counter, report_url: str | None) -> str:
    """PRD §5.3 三态结论输出规范。**措辞逐字照 PRD，不许同义替换。**

    ★ 2026-10-06 改。此前 REVIEW 与 BLOCK **共用同一句话**「共发现 N 处需处理问题」，
      而 PRD §5.3.2 / §5.3.3 是两句不同的（「需人工确认」/「必须修改」）。
      为什么长期没被发现：`kb/.work/l7_integrity.py` 的 `template_conformance`
      只断言到 `【审查结论：REVIEW】共发现` 为止 —— **后半句它没查**。
      判据存在，但没盖住出事的那一跳（AGENTS.md §2.4）。现在两边一起改：
      这里出对的措辞，那里把后半句也断言上。
    """
    if decision == "PASS":
        return f"【审查结论：PASS】未发现已知底线风险，可转交 {_at('pass_signoff')} 进行 sign-off。"
    if decision == "NEEDS_INPUT":
        return "【审查结论：NEEDS_INPUT】当前素材、版本或证据不完整，补齐后再审。"

    n = len(items)
    # PRD §5.3.2 与 §5.3.3 的两句**不一样**，这正是原先被抹平的那一处。
    head = (f"【审查结论：REVIEW】共发现 {n} 处需人工确认。"
            if decision == "REVIEW" else
            f"【审查结论：BLOCK】共发现 {n} 处必须修改。")

    if n <= 2:  # 分流阈值 3（PRD §5.3.4），逐条展开
        lines = [head]
        for i, item in enumerate(items, start=1):
            lines.extend(_item_lines(i, item, want_suggestion=(decision == "BLOCK")))
        lines.append(f"建议转 {_at('review_reviewers')} 复核。" if decision == "REVIEW" else "请修改后重新提交。")
        return "\n".join(lines)

    lines = [head]
    # ★ 2026-10-06 修：PRD §5.3.2/5.3.3 的 ≥3 汇总形状是 `· <大类>类问题：N 个`，
    #   而这里原先只写 `· {category}：{count} 个` —— **少「类问题」三字**。
    #   同一个库里另一个产者（`l7/skills/kb-content-review/scripts/review.py:803`）
    #   写的是 `· {k}类问题：{v} 个`，两边不一致，而实测发出去的那条正是缺字这一版。
    #   同时把**子类归并到大类**（`平台与促销-促销紧迫感表述` ⇒ `平台与促销`）——
    #   PRD 的例子是 `合规类问题：3 个`，按大类计。
    _agg = Counter()
    for _c, _n in categories.items():
        _agg[str(_c).split("-")[0].split("－")[0].strip() or "未分类"] += _n
    lines.extend(f"· {category}类问题：{count} 个" for category, count in _agg.items())
    # PRD §5.3.4：≥3 个时**只出分类汇总 + 报告链接**，完整清单必须真的写进报告文件。
    # 报告没落盘时不许写「查看完整清单」（那会指向一个不存在的东西）—— 照实说没写。
    # ★ 2026-10-06：链接必须是**能点开的东西**才算「查看」。
    #   实测发出去的那条 REVIEW（3 个问题）写的是 `kb/l7/reports/….md` ——
    #   那是个**本地路径**，群里的人点不开，而 PRD §5.3.2 的原话是
    #   `→ 查看完整问题清单与修改建议：https://feishu.cn/review/xxx`。
    #   给不了 URL 时**照实说它是本地件**，不许拿一句「查看…」把人引到一个打不开的东西上。
    if report_url and str(report_url).startswith(("http://", "https://")):
        lines.append(f"→ 查看完整问题清单与修改建议：{report_url}")
    elif report_url:
        lines.append(f"→ 完整问题清单与修改建议在**本地报告**里（不是可点链接）：{report_url}")
    else:
        lines.append("→ 查看完整问题清单与修改建议：（本次未写报告，见 --report-dir）")
    lines.append(f"建议转 {_at('review_reviewers')} 复核。" if decision == "REVIEW" else "请修改后重新提交。")
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
