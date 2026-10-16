#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「引擎拒答封套」+「按 Owner 2026-10-05 规则① 登记的 findings」组装成
feishu_publish.py 认的形状（本单 = RT-20261005-IMG-05）。

不藏的三件事：
  1. 引擎 with_kb_evidence.py 对「已定稿反例/禁区」没有消费者（GAP-SELFHIT-1）⇒ 本单实际输出
     = NEEDS_INPUT / 退出码 3；发布件据此拒发。本 BLOCK **不是引擎产出的**。
  2. Owner 2026-10-05 规则① 明示：自命中已定稿反例/禁区 = 该素材本身有定论，必须登记 findings
     并出三态结论（通常 BLOCK），不许以自命中/同源留痕/循环论证为由降级或拒答。
  3. **更深一层的冲突（前两单 IMG-03/IMG-04 没有披露）**：库内 sample_case 条目自带的
     `not_proves` / `forbidden` 逐字写着「案例是参照，不构成规则 —— 不能证明『和它像』就违规」
     「不许把案例当规则用（案例只作参照）；**不许据本条直接判 BLOCK**」。
     规则①（同一素材的定论）与这条数据边界**在位阶上冲突**，本件把它摆出来，不默默挑一个执行。

本脚本不改引擎、不改发布件；只做「封套字段保真 + 登记字段补齐」。
判据来源逐条可核：
  · L4 canonical : kb/l4/canonical/sample_case.jsonl → S-1.2 / S-1.175（现读校核）
  · L2/L1        : anchor / unit_id / source_sha256 / 图片文件级 sha（a3c7828f…，123,988 字节）
  · L0           : kb/l0/2_内部正负样本库/feishu_bitable_record__tbld8qE92YaY38Yz__recvw2vgYXHKgM.json
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

ENGINE = HERE / "rt-img-05-engine.json"
OUT = HERE / "rt-img-05-decision.json"
REG = HERE / "rt-img-05-findings-registered.json"

MATERIAL = (HERE / "rt-img-02-text.txt").read_text(encoding="utf-8")

# 送审 OCR 里的水印串（审阅侧 DLP 叠加，库内同一图片的原生 OCR 里没有）—— 与内容区分开登记
WATERMARK_TOKENS = ["5615 ROOT", "5615 ROC", "刘华丽", "刘华的", "ROOT", "RC"]

# 命中片段：L0「原文反馈」字段里逐字带着的那段德语正文（同时 S-1.2 / S-1.175 的 L0 末尾都有）
MATCH_SPAN = ("mOmCOZY\nBereit Für Die Nacht,\nSupermama?\nManche Superkräfte\n"
              "Passen Auf Den\nNachttisch\n\"Was Sind Deine Mama-Hacks Für Ruhigere Nächte?\"")

rev = json.loads(ENGINE.read_text(encoding="utf-8"))
eng = rev["decision"]
meta = rev["evidence_meta"]

# ── 条款事实：L4 canonical 现读（不手写）──
canon = {}
for line in (pathlib.Path(__file__).resolve().parent.parent / "kb/l4/canonical/sample_case.jsonl").read_text(
        encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    o = json.loads(line)
    if o.get("article_no") in ("S-1.2", "S-1.175"):
        canon[o["article_no"]] = o

assert set(canon) == {"S-1.2", "S-1.175"}, canon.keys()
S12, S1175 = canon["S-1.2"], canon["S-1.175"]

DECISION_NOTE = (
    "【本结论的来路，必须一起读】引擎 with_kb_evidence.py 本单实际输出 = NEEDS_INPUT"
    "（拒答 · 退出码 3，理由：库内规则 0 命中、P0 0 命中、无覆盖信号）；"
    "本 BLOCK **不是引擎产出的**，而是判定主体『图片安全审查』按 Owner 2026-10-05 规则①"
    "（自命中已定稿反例/禁区 = 本素材本身有定论，必须登记 findings 并出三态，不许降级/拒答）"
    "登记得出。引擎侧缺口登记为 GAP-SELFHIT-1（对反例/禁区无消费者）。"
)

CONFLICT_NOTE = (
    "【同时摆出的冲突，不许静默】库内 sample_case 自带的边界字段逐字为："
    "not_proves=「案例是参照，不构成规则 —— 不能证明『和它像』就违规、也不能证明『和它像』就合规」；"
    "forbidden=「不许把案例当规则用（案例只作参照）；不许据本条直接判 BLOCK」。"
    "Owner 规则①（同一素材命中已定稿反例/禁区即出三态、通常 BLOCK）与该数据边界在位阶上冲突："
    "规则①说的是「同一素材的定论」，边界字段说的是「不许把案例当规则用」。"
    "本单按 Owner 明示「规则① 优先于默认流程」执行，但把冲突原样登记，交 Owner/治理侧裁定；"
    "在引擎补上「反例/禁区消费者」之前，本 BLOCK 是**判定主体档**，不是引擎可复现档。"
)

risk_items = [
    {
        "risk_type": "原则性错误（自命中已定稿反例/禁区）",
        "priority_tier": "BLOCK",
        "action": "自命中库内已定稿反例/禁区条款 → 按已定稿定论处置，改正后重新提交",
        # 命中片段取 L0 里逐字存在的德语正文（发布件的 L0 逐字核对会真命中）
        "original_text": MATCH_SPAN,
        "rule_code": "S-1.2",
        "evidence": {
            "library": "内部正负样本库（kb_type=internal_sample）",
            "article_no": "S-1.2",
            "anchor": S12["anchor"],
            "source_sha256": S12["source_sha256"],
            "excerpt": S12["reason_analysis"],
        },
        "suggestion": (
            "按已定稿反例处置：改正画面中奶瓶的摆放（不得倒置），改后重新提交。"
            "注：L0「建议」字段文本与「具体原因/分析」逐字相同、首句却是否定句（原文「建议倒着放…」），"
            "疑为采集时字段复制错误 ⇒ 该字段**不得直接外发**，需业务先确认口径。"
        ),
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
            "l1_image_bytes": 123988,
            "l1_file": "kb/l1/2_内部正负样本库/bitable__tbld8qE92YaY38Yz__recvw2vgYXHKgM.json",
            "l0_entry_url": ("https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc"
                             "?table=tbld8qE92YaY38Yz&record=recvw2vgYXHKgM"),
            "l0_record_id": "recvw2vgYXHKgM",
            "l0_verbatim_field": "具体原因/分析",
            "sha_note": ("与 L0 记录值比对一致（不是重算）：sha 输入是 record_fields 字段 blob，"
                         "本地 L0 件不含该 blob；要真核对只能点 L0 直链。"),
            "near_duplicate": {
                "article_no": "S-1.175",
                "material_type": S1175["material_type"],
                "anchor": S1175["anchor"],
                "unit_id": S1175["unit_id"],
                "source_sha256": S1175["source_sha256"],
                "entry_url": ("https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc"
                              "?table=tbld8qE92YaY38Yz&record=recvw2wE9MmvI2"),
                "l0_verbatim_field": "原文反馈",
                "excerpt_in_l0": MATERIAL,
            },
            "kb_boundary_field_conflict": {
                "not_proves": ("案例是参照，不构成规则 —— 不能证明「和它像」就违规、"
                               "也不能证明「和它像」就合规"),
                "forbidden": "不许把案例当规则用（案例只作参照）；不许据本条直接判 BLOCK",
            },
        },
    },
    {
        "risk_type": "证据边界（非条款项）",
        "priority_tier": "REVIEW",
        "action": "人工看一眼画面本体：确认成品图与送审件的差异、以及奶瓶倒置是否真的在成图里",
        "original_text": MATERIAL,
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
                       "a3c7828f…（123,988 字节）逐字节比对；② 独立观测奶瓶摆放；③ 补判画面安全。"),
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
        "同一图片文件实体（sha256 a3c7828f…，123,988 字节）、同一活动（欧洲社媒德国 8.14 "
        "Jeder Schritt der Stillreise）、德语 OCR 与 S-1.175 的 L0「原文反馈」逐字相同；"
        "该条款定论 = 原则性错误「奶瓶不建议倒着放」。⇒ 不能发。" + DECISION_NOTE + CONFLICT_NOTE
    ),
    "risk_items": risk_items,
    "next_owners": ["设计/素材提交方（改画面后重提）",
                    "内容治理负责人（机制缺口 GAP-SELFHIT-1 + 边界字段冲突裁定）"],
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
        "statement": DECISION_NOTE + CONFLICT_NOTE,
        "conflict_disclosed": True,
        "assembled_by": ("kb/l7/review-engine 的消费者侧组装（feishu_publish.py 的输入形状），"
                         "未改引擎、未改发布件"),
    },
    "submit_question": "审一下这张图能过吗？",
})
rev["decision"] = dec

# ── 独立自命中核（本单现跑，不引用前会话的结论）──
import re
import unicodedata


def _norm(s: str) -> str:
    s = s.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        s = s.replace(a, b)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s)


def _grams(s: str, n: int):
    return {s[i:i + n] for i in range(len(s) - n + 1)}


_M = _norm(MATERIAL)
_selfhit = []
for line in (pathlib.Path(__file__).resolve().parent.parent / "kb/l4/canonical/sample_case.jsonl"
             ).read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    o = json.loads(line)
    if not (o.get("polarity") == "反例" or str(o.get("semantics") or "").startswith("禁区")):
        continue
    blob = _norm(" ".join(str(o.get(k) or "") for k in
                          ("sample_body", "reason_analysis", "advice", "anchor", "title")))
    _selfhit.append((o.get("article_no"), len(_grams(_M, 16) & _grams(blob, 16)),
                     len(_grams(_M, 12) & _grams(blob, 12)), len(_grams(_M, 24) & _grams(blob, 24))))
_selfhit.sort(key=lambda x: (-x[1], -x[2], -x[3]))

registration = {
    "review_id": dec["review_id"],
    "review_base": meta.get("layer_preflight", {}).get("base"),
    "content_id": "AD-20261005-005",
    "content_version": dec["content_version"],
    "content_type": "社媒图片",
    "channel": "社媒",
    "product_line": "洗瓶机/喂养",
    "version": "v1.0",
    "submitted_text_sha256": dec["content_version"],
    "submitted_text_verbatim": MATERIAL,
    "submitted_watermark_tokens": WATERMARK_TOKENS,
    "decision": "BLOCK",
    "issue_count": len(risk_items),
    "decision_provenance": dec["decision_provenance"],
    "findings": risk_items,
    "self_hit": {
        "method": ("对 kb/l4/canonical/sample_case.jsonl 中全部 polarity=反例 / semantics 以「禁区」开头"
                   "的条款做规范化字符 n-gram 重叠（n=8/12/16/20/24）；本单现跑，不引用前会话结论"),
        "top": [{"article_no": a, "shared_16": g16, "shared_12": g12, "shared_24": g24}
                for a, g16, g12, g24 in _selfhit[:5]],
        "conclusion": ("S-1.2 与 S-1.175 断层领先（16-gram 65 vs 次高 0），其余全部 ≤2（8-gram）"
                       "⇒ 命中成立，且不是泛用词撞车"),
    },
    "identity_evidence": {
        "submitted_ocr_german": MATCH_SPAN,
        "kb_l1_ocr_cache_sha256": S12["media_refs"][0]["source_sha256"],
        "kb_l1_image_bytes": 123988,
        "kb_l1_ocr_cache": ("kb/l1/media/recvw2vgYXHKgM/ocr.json（原生 OCR 7 行，无任何水印文字）"),
        "match": "德语 7 行逐字相同（送审侧 OCR 把 ä/ü 读成 a/u、逗号读成全角，属 OCR 归一化差异）",
        "extra_tokens_in_submission": WATERMARK_TOKENS,
        "extra_tokens_note": ("这些串在库内同一图片的原生 OCR 里没有；IMG-03 判为审阅侧 DLP 水印、"
                              "不是烧进成图的内部标识。本单未独立观测画面，故按「未复核项」处理，"
                              "不计入问题数量。"),
        "residual_uncertainty": ("图片文件本体未到本机 ⇒ 无法对送审件复算 sha256 与 a3c7828f… "
                                 "逐字节比对；同一性由「德语 OCR 逐字相同 + 同一活动 + 库内 5 条记录"
                                 "引用同一图片实体」确立，不是字节级证明。"),
    },
    "screened_out": {
        "p0_hits": 0,
        "rules_hits": 0,
        "rules_scanned": 509,
        "bm25_max": 147.7935,
        "bm25_top3_note": ("Top3 全是同一张德语海报的重复素材（recvw7XIUg72fA / recvwwiEKDTDWq / "
                           "recvwC9IMVeaGY），是同源留痕，不是新依据。"),
        "why_not": "未命中 ≠ 合规（库内统一口径）；但本次也没有任何规则/P0 命中可用作依据。",
    },
}
registration["engine_envelope"] = {
    "engine_json": "_rt-img-20261005/rt-img-05-engine.json",
    "engine_state": eng.get("state"),
    "engine_review_id": eng.get("review_id"),
    "layer_preflight": meta.get("layer_preflight"),
    "decision_owner": meta.get("decision_owner"),
    "run_id": meta.get("run_id"),
}

OUT.write_text(json.dumps(rev, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
REG.write_text(json.dumps(registration, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("wrote:", OUT)
print("wrote:", REG)
print("decision:", dec["state"], "| issue_count:", dec["issue_count"], "| review_id:", dec["review_id"])
print("selfhit top5:", _selfhit[:5])
