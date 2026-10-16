#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RT-20261005-IMG-06 —— 把「引擎拒答封套」+「按 Owner 2026-10-05 规则① 登记的 findings」
组装成 feishu_publish.py 认的形状。

不藏的三件事：
  1. 引擎 with_kb_evidence.py 本单**实际输出 = NEEDS_INPUT（拒答 / 退出码 3）**：
     P0 0 命中、509 条规则 0 命中、L6 召回 Top10 里**没有** S-1.2 的单元（f8e2ee3741a6d1b8c307，
     现跑复核）⇒ 引擎对「已定稿反例 / 禁区」没有消费者，按 no_hit fail-closed 拒答。
     本 BLOCK **不是引擎产出的**。
  2. Owner 2026-10-05 规则① 明示：自命中已定稿反例/禁区 = 该素材本身有定论，必须登记 findings
     并出三态结论（通常 BLOCK），不许以自命中 / 同源留痕 / 循环论证为由降级或拒答。
     本单据此由判定主体「图片安全审查」登记得出。
  3. **更正前两单（IMG-04/05）的一处不实陈述**：它们说「库内 sample_case 自带 not_proves / forbidden
     （案例只作参照、不许据本条直接判 BLOCK）」。本单现核：kb/l4/canonical/sample_case.jsonl 的
     S-1.2 / S-1.175 **没有** not_proves / forbidden 字段（全文 grep 0 命中）；那两段文字只在
     **派生视图生成器的旧备份**里（.work/hostlib.bak-20260928-182653/ 与
     kb/l7/_backups/interp-20260929-175116/.work/gen-host-library-l4.py:242-243），
     是宿主库视图给案例统一盖的「参照」章，不是权威 L4 字段；当前 live view 只有 3_措辞表达库、
     不含案例。⇒ 本单**不把它当活冲突上报**，只登记这条更正。

本脚本不改引擎、不改发布件；只做「封套字段保真 + 登记字段补齐」，所有判据现读现核、可复算。
"""
import json
import pathlib
import re
import unicodedata

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

ENGINE = HERE / "rt-img-06-engine.json"
OUT = HERE / "rt-img-06-decision.json"
REG = HERE / "rt-img-06-findings-registered.json"

MATERIAL = (HERE / "rt-img-06-text.txt").read_text(encoding="utf-8")

# 送审 OCR 里的水印串（审阅侧叠加，库内同一图片的原生 OCR 里没有）—— 与内容区分开登记
WATERMARK_TOKENS = ["5615", "5615 ROOT", "5615 ROC", "RC", "ROOT", "刘华丽", "刘华的"]

# ── 图片文件级实体：L1 media cache（原生 OCR 7 行，无任何水印）──
IMG_SHA = "a3c7828f2f66554dfa574e112d66026473023265f771df1d63410de11423ff8a"
MEDIA_CACHE = ROOT / "kb/l1/media/_cache" / f"{IMG_SHA}.json"
_media = json.loads(MEDIA_CACHE.read_text(encoding="utf-8"))
MATCH_SPAN = _media["ocr_text"].strip()
assert "Bereit Für Die Nacht" in MATCH_SPAN, MATCH_SPAN

# ── 条款事实：L4 canonical 现读（不手写）──
canon = {}
for line in (ROOT / "kb/l4/canonical/sample_case.jsonl").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    o = json.loads(line)
    if o.get("article_no") in ("S-1.2", "S-1.175"):
        canon[o["article_no"]] = o
assert set(canon) == {"S-1.2", "S-1.175"}, canon.keys()
S12, S1175 = canon["S-1.2"], canon["S-1.175"]

# 断言：送审德语内容逐字在两条 L4 案例的 sample_body 里
for s in ("Bereit Für Die Nacht,", "Supermama?", "Manche Superkräfte",
          "Was Sind Deine Mama-Hacks Für Ruhigere Nächte?"):
    assert s in S12["sample_body"], ("S-1.2 missing", s)
    assert s in S1175["sample_body"], ("S-1.175 missing", s)

# 断言：live L4 案例**不带** not_proves / forbidden（更正前单）
assert "not_proves" not in S12 and "forbidden" not in S12
assert "not_proves" not in S1175 and "forbidden" not in S1175

# ── L0 源记录（已归档，不在 kb/l0/records/ 下）──
L0 = {}
for art, rid in (("S-1.2", "recvw2vgYXHKgM"), ("S-1.175", "recvw2wE9MmvI2")):
    p = ROOT / "kb/l0/_archive/正面和负面样本-superseded-20260929-1045" / f"{rid}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    L0[art] = {
        "record_id": rid,
        "entry_url": d["entry_url"],
        "observed_at": d["observed_at"],
        "local_archive": str(p.relative_to(ROOT)),
        # 归档件本身没有 sha256 字段 ⇒ 只列引用值、不做 sha 比对
        "archive_has_sha256": ("sha256" in d),
    }

S12_VERBATIM = S12["reason_analysis"]          # 逐字 = L0「具体原因/分析」
S1175_FIELD = "原文反馈"

rev = json.loads(ENGINE.read_text(encoding="utf-8"))
eng = rev["decision"]
meta = rev["evidence_meta"]

DECISION_NOTE = (
    "【本结论的来路，必须一起读】引擎 with_kb_evidence.py 本单实际输出 = NEEDS_INPUT"
    "（拒答 · 退出码 3）：P0 0 命中、509 条规则 0 命中、L6 召回 Top10 未召回 S-1.2 的单元"
    "（f8e2ee3741a6d1b8c307，本单现跑复核）。⇒ 引擎对「已定稿反例/禁区」没有消费者，"
    "按 no_hit fail-closed 拒答。本 BLOCK **不是引擎产出的**，而是判定主体『图片安全审查』"
    "按 Owner 2026-10-05 规则①（自命中已定稿反例/禁区 = 本素材本身有定论，必须登记 findings "
    "并出三态，不许降级/拒答）登记得出。引擎侧缺口本单记作 GAP-SELFHIT-1"
    "（**未登记进 kb/l7/registry；前单也未登记**）。"
)

BOUNDARY_NOTE = (
    "【更正前两单的一处不实陈述】IMG-04/05 报告称「库内 sample_case 自带 not_proves / forbidden"
    "（案例只作参照、不许据本条直接判 BLOCK）」。本单现核：kb/l4/canonical/sample_case.jsonl 的"
    "S-1.2 / S-1.175 **没有** not_proves / forbidden 字段（全文 grep 0 命中）；那两段文字只在"
    "**派生视图生成器的旧备份**（.work/hostlib.bak-20260928-182653/、"
    "kb/l7/_backups/interp-20260929-175116/.work/gen-host-library-l4.py:242-243）里，"
    "是宿主库视图给案例统一盖的「参照」章，不是权威 L4 字段；当前 live view 只有 3_措辞表达库、"
    "不含案例。⇒ 本单不把它当「活冲突」上报。**权威 L4 对该两条的定性是**："
    "polarity=反例 · semantics=禁区：不能这么做 + 为什么 · status=stable · "
    "evidence_strength=禁区可复现：有完整样本本体 + 原因分析（rule_eligible 单元可在 L2 解析）。"
)

risk_items = [
    {
        "risk_type": "原则性错误（自命中已定稿反例/禁区）",
        "priority_tier": "BLOCK",
        "action": "自命中库内已定稿反例/禁区条款 S-1.2 → 按已定稿定论处置，改正后重新提交",
        "original_text": MATCH_SPAN,
        "rule_code": "S-1.2",
        "evidence": {
            "library": "内部正负样本库（kb_type=internal_sample）",
            "article_no": "S-1.2",
            "anchor": S12["anchor"],
            "source_sha256": S12["source_sha256"],
            "excerpt": S12_VERBATIM,
            "trace": {
                "form": S12["form"],
                "polarity": S12["polarity"],
                "semantics": S12["semantics"],
                "reason_category": S12["reason_category"],
                "status": S12["status"],
                "owner": S12["owner"],
                "valid_until": S12["valid_until"],
                "effective_from": S12["effective_from"],
                "material_type": S12["material_type"],
                "channel": S12["channel"],
                "l4_anchor": S12["anchor"],
                "l2_unit_id": S12["unit_id"],
                "l2_media_anchor": S12["media_refs"][0]["anchor"],
                "l1_source_sha256": S12["source_sha256"],
                "l1_image_file_sha256": S12["media_refs"][0]["source_sha256"],
                "l1_file": "kb/l1/2_内部正负样本库/bitable__tbld8qE92YaY38Yz__recvw2vgYXHKgM.json",
                "l2_file": "kb/l2/units.jsonl（unit_id=f8e2ee3741a6d1b8c307）",
                "l0_entry_url": L0["S-1.2"]["entry_url"],
                "l0_record_id": L0["S-1.2"]["record_id"],
                "l0_local_archive": L0["S-1.2"]["local_archive"],
                "l0_observed_at": L0["S-1.2"]["observed_at"],
                "l0_verbatim_field": "具体原因/分析",
                "sha_note": ("与 L0 记录值比对一致（**不是重算**）：sha 输入是 record_fields 字段 blob，"
                             "本地 L0 件不含该 blob；归档件本身也没有 sha256 字段，"
                             "要真核对只能点 L0 直链。"),
            },
            "near_duplicate": {
                "article_no": "S-1.175",
                "material_type": S1175["material_type"],
                "anchor": S1175["anchor"],
                "unit_id": S1175["unit_id"],
                "source_sha256": S1175["source_sha256"],
                "entry_url": L0["S-1.175"]["entry_url"],
                "l0_verbatim_field": S1175_FIELD,
                "excerpt_in_l0": MATCH_SPAN,
                "reason_analysis": S1175["reason_analysis"],
            },
        },
        "suggestion": ("按已定稿反例处置：改正画面中奶瓶的摆放（不得倒置），改后重新提交。"
                       "注：L0「建议」字段文本与「具体原因/分析」逐字相同、首句却是否定句"
                       "（原文「建议倒着放…」），疑为采集时字段复制错误 ⇒ 该字段**不得直接外发**，"
                       "需业务先确认口径。"),
    },
    {
        "risk_type": "证据边界（非条款项）",
        "priority_tier": "REVIEW",
        "action": "人工看一眼画面本体：确认成品图与送审件的差异、以及奶瓶倒置是否真的在成图里",
        "original_text": MATCH_SPAN,
        "rule_code": None,
        "evidence": {
            "library": "（无条款号：本项不是规则命中，是画面证据边界）",
            "article_no": None,
            "anchor": None,
            "source_sha256": None,
            "excerpt": ("送审到达审查链的只有宿主 OCR 文本，没有图片文件本体／URL／content_hash ⇒ "
                        "画面安全（婴幼儿 / 睡眠 / 隐私 / 换脸合成）本次未判；"
                        "「奶瓶倒着放」这一画面事实来自已定稿条款的记录，不是本次独立观测。"),
        },
        "suggestion": ("补送图片文件本体（或可访问 URL / file_token），以便：① 对送审件复算 sha256 与 "
                       f"{IMG_SHA[:8]}…（123,988 字节）逐字节比对；② 独立观测奶瓶摆放；③ 补判画面安全。"),
    },
]

dec = dict(eng)
dec.update({
    "state": "BLOCK",
    "decision": "BLOCK",
    "confidence": None,
    "issue_count": len(risk_items),
    "summary": (
        "【审查结论：BLOCK】送审图片与库内已定稿反例/禁区条款 S-1.2（近重复 S-1.175）实质同一："
        f"同一图片文件实体（sha256 {IMG_SHA[:8]}…，123,988 字节）、同一活动（欧洲社媒德国 8.14 "
        "Jeder Schritt der Stillreise）、德语 OCR 与 S-1.2 / S-1.175 的样本正文逐字相同；"
        "该条款定论 = 原则性错误「奶瓶不建议倒着放」。⇒ 不能发。" + DECISION_NOTE + BOUNDARY_NOTE
    ),
    "risk_items": risk_items,
    "next_owners": ["设计/素材提交方（改画面后重提）",
                    "内容治理负责人（机制缺口 GAP-SELFHIT-1 登记 + 前单不实陈述更正）"],
    "issue_summary_by_category": {
        "原则性错误（自命中已定稿反例/禁区 S-1.2，近重复 S-1.175）": 1,
        "证据边界（画面本体未到本机，非条款项）": 1,
    },
    "decision_provenance": {
        "engine_state": eng.get("state"),
        "engine_review_id": eng.get("review_id"),
        "engine_content_version": eng.get("content_version"),
        "engine_refusal_detail": (eng.get("refusal") or {}).get("detail"),
        "rule": "Owner 2026-10-05 规则①（自命中是反面依据，不是拒答的理由）",
        "statement": DECISION_NOTE + BOUNDARY_NOTE,
        "conflict_disclosed": False,
        "correction_of_prior_claim": True,
        "assembled_by": ("kb/l7/review-engine 的消费者侧组装（feishu_publish.py 的输入形状），"
                         "未改引擎、未改发布件"),
    },
    "submit_question": "审一下这张图能过吗？",
})
rev["decision"] = dec

# ── 独立自命中核（本单现跑，不引用前会话的结论）──
def _norm(s: str) -> str:
    s = s.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        s = s.replace(a, b)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s)


def _grams(s: str, n: int):
    return {s[i:i + n] for i in range(len(s) - n + 1)}


_M = _norm(MATCH_SPAN)
_selfhit = []
for line in (ROOT / "kb/l4/canonical/sample_case.jsonl").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    o = json.loads(line)
    if not (o.get("polarity") == "反例" or str(o.get("semantics") or "").startswith("禁区")):
        continue
    blob = _norm(" ".join(str(o.get(k) or "") for k in
                          ("sample_body", "reason_analysis", "advice", "anchor")))
    _selfhit.append((o.get("article_no"), len(_grams(_M, 16) & _grams(blob, 16)),
                     len(_grams(_M, 12) & _grams(blob, 12)), len(_grams(_M, 24) & _grams(blob, 24))))
_selfhit.sort(key=lambda x: (-x[1], -x[2], -x[3]))
assert _selfhit and _selfhit[0][0] in ("S-1.2", "S-1.175"), _selfhit[:5]

registration = {
    "review_id": dec["review_id"],
    "review_base": meta.get("layer_preflight", {}).get("base"),
    "content_id": None,          # 发布件按 PRD §5.4 自动发号 AD-YYYYMMDD-NNN
    "content_version": dec["content_version"],
    "content_type": "社媒图片",
    "channel": "社媒",
    "product_line": "洗瓶机/喂养",
    "version": "v1.0",
    "submit_question": "审一下这张图能过吗？",
    "submitted_text_sha256": dec["content_version"],
    "submitted_text_verbatim": MATERIAL,
    "submitted_watermark_tokens": WATERMARK_TOKENS,
    "decision": "BLOCK",
    "issue_count": len(risk_items),
    "decision_provenance": dec["decision_provenance"],
    "findings": risk_items,
    "self_hit": {
        "method": ("对 kb/l4/canonical/sample_case.jsonl 中全部 polarity=反例 / semantics 以「禁区」开头"
                   "的条款做规范化字符 n-gram 重叠（n=12/16/24）；本单现跑，不引用前会话结论"),
        "top": [{"article_no": a, "shared_16": g16, "shared_12": g12, "shared_24": g24}
                for a, g16, g12, g24 in _selfhit[:5]],
        "conclusion": ("S-1.2 / S-1.175 断层领先 ⇒ 命中成立，且不是泛用词撞车"),
    },
    "identity_evidence": {
        "submitted_ocr_german": MATCH_SPAN,
        "kb_l1_ocr_cache_sha256": IMG_SHA,
        "kb_l1_image_bytes": 123988,
        "kb_l1_ocr_cache": f"kb/l1/media/_cache/{IMG_SHA}.json（原生 OCR 7 行，无任何水印文字）",
        "l4_media_refs_both_point_to_same_file": [r["source_sha256"] for r in S12["media_refs"]],
        "match": "德语 7 行逐字相同（送审侧 OCR 把 ä/ü 读成 a/u、逗号读成全角，属 OCR 归一化差异）",
        "extra_tokens_in_submission": WATERMARK_TOKENS,
        "extra_tokens_note": ("这些串在库内同一图片的原生 OCR 里没有，是审阅侧水印叠加，"
                              "不是烧进成图的内部标识；本单未独立观测画面，故按「未复核项」处理，"
                              "不计入问题数量。"),
        "residual_uncertainty": ("图片文件本体未到本机 ⇒ 无法对送审件复算 sha256 与 "
                                 f"{IMG_SHA[:8]}… 逐字节比对；同一性由「德语 OCR 逐字相同 + 同一活动 + "
                                 "库内两条记录引用同一图片实体」确立，**不是字节级证明**。"),
    },
    "screened_out": {
        "p0_hits": 0,
        "rules_hits": 0,
        "rules_scanned": 509,
        "l6_selfhit_unit_in_top10": False,
        "l6_note": ("查询德语正文，L6 双索引 Top10 里没有 S-1.2 的单元 f8e2ee3741a6d1b8c307 ⇒ "
                    "引擎侧没有把反例/禁区送进裁决，故按 no_hit 拒答（GAP-SELFHIT-1）。"),
        "why_not": "未命中 ≠ 合规（库内统一口径）；但本次也没有任何规则/P0 命中可用作依据。",
    },
    "engine_envelope": {
        "engine_json": "_rt-img-20261005/rt-img-06-engine.json",
        "engine_state": eng.get("state"),
        "engine_review_id": eng.get("review_id"),
        "engine_exit_code": 3,
        "layer_preflight": meta.get("layer_preflight"),
        "decision_owner": meta.get("decision_owner"),
        "run_id": meta.get("run_id"),
    },
}

OUT.write_text(json.dumps(rev, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
REG.write_text(json.dumps(registration, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("wrote:", OUT)
print("wrote:", REG)
print("decision:", dec["state"], "| issue_count:", dec["issue_count"], "| review_id:", dec["review_id"])
print("selfhit top5:", _selfhit[:5])
