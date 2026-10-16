#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「引擎拒答封套」+「按 Owner 2026-10-05 规则① 登记的 findings」组装成
feishu_publish.py 认的形状。

为什么要有这一步（不藏）：
  · 引擎 with_kb_evidence.py 对「已定稿反例/禁区」**没有消费者**（登记为 GAP-SELFHIT-1），
    本单实际输出 = NEEDS_INPUT / 退出码 3；发布件据此**拒发**（feishu_publish.py:416-418）。
  · Owner 2026-10-05 规则① 明示：自命中已定稿反例/禁区 = 该素材本身有定论，
    必须登记 findings 并据此出三态结论（通常 BLOCK），不许以自命中为由降级/拒答。
  · 本脚本**不改引擎、不改发布件**：只做「封套字段保真 + 登记字段补齐」，并把
    engine_state / 冲突 如实写进 summary 与 issue_summary_by_category（会随报告与表行外发）。

判据来源（逐条可核，不手写条款号）：
  · L4 canonical: kb/l4/canonical/sample_case.jsonl → S-1.2 / S-1.175
  · L2/L1: anchor / unit_id / source_sha256（图片文件级 a3c7828f…）
  · L0: kb/l0/_archive/正面和负面样本-superseded-20260929-1045/{recvw2vgYXHKgM,recvw2wE9MmvI2}.json
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

ENGINE = HERE / "rt-img-04-engine.json"
OUT = HERE / "rt-img-04-decision.json"
REG = HERE / "rt-img-04-findings-registered.json"

MATERIAL = (HERE / "rt-img-04-text.txt").read_text(encoding="utf-8")

rev = json.loads(ENGINE.read_text(encoding="utf-8"))
eng = rev["decision"]
meta = rev["evidence_meta"]

# ── 字号：条款事实取自 L4 canonical 现读（此处只放脚本可核的常量，值逐条在报告里给抄录）──
S12 = {
    "article_no": "S-1.2",
    "anchor": "#正面和负面样本/recvw2vgYXHKgM/原文反馈",
    "unit_id": "f8e2ee3741a6d1b8c307",
    "media_anchor": "#素材/recvw2vgYXHKgM/图片素材/#img.1",
    "record_sha256": "9f39a37061cf6d1e33af111127156a9a38e69d2cfd6de70e6c71f3e8685c5136",
    "file_sha256": "a3c7828f2f66554dfa574e112d66026473023265f771df1d63410de11423ff8a",
    "entry_url": "https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc?table=tbld8qE92YaY38Yz&record=recvw2vgYXHKgM",
    "excerpt": ("【原则性错误】图片 奶瓶不建议倒着放，对于宝宝和妈妈来说，奶瓶的卫生重要至极，所。\n"
                "原因：我们的产品才会有奶瓶消毒器，喝完奶、喝之前都要消毒杀菌的，所以随意倒着放这个行为不符合用户习惯"),
    "l1_file": "kb/l1/2_内部正负样本库/bitable__tbld8qE92YaY38Yz__recvw2vgYXHKgM.json",
}
S1175 = {
    "article_no": "S-1.175",
    "anchor": "#正面和负面样本/recvw2wE9MmvI2/原文反馈",
    "unit_id": "ce49d00481ce3e18785e",
    "media_anchor": "#素材/recvw2wE9MmvI2/图片素材/#img.1",
    "record_sha256": "a39db867fa9cdd73bc2013dcb5d4639209d0974cf36ce6700c635f674cfbe773",
    "file_sha256": "a3c7828f2f66554dfa574e112d66026473023265f771df1d63410de11423ff8a",
    "entry_url": "https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc?table=tbld8qE92YaY38Yz&record=recvw2wE9MmvI2",
    "excerpt": MATERIAL,          # L0「原文反馈」字段末尾就逐字带着这段德语（逐字命中）
    "l1_file": "kb/l1/2_内部正负样本库/bitable__tbld8qE92YaY38Yz__recvw2wE9MmvI2.json",
}

DECISION_NOTE = (
    "【本结论的来路，必须一起读】引擎 with_kb_evidence.py 本单实际输出 = NEEDS_INPUT（拒答 · 退出码 3，"
    "理由：库内规则 0 命中、无覆盖信号）；本 BLOCK **不是引擎产出的**，"
    "而是判定主体『图片安全审查』按 Owner 2026-10-05 规则①（自命中已定稿反例/禁区 = 本素材本身有定论，"
    "必须登记 findings 并出三态，不许降级/拒答）登记得出。引擎侧缺口已登记为 GAP-SELFHIT-1（对反例/禁区无消费者）。"
)

risk_items = [
    {
        "risk_type": "原则性错误",
        "priority_tier": "BLOCK",
        "action": "自命中库内已定稿反例/禁区条款 → 按已定稿定论处置，改正后重新提交",
        # 命中片段用德语正文里那串逐字文本：它同时出现在 L0「原文反馈」（关键词 = 德语 OCR 串）
        # 与 L0「具体原因/分析」（奶瓶定论）里 ⇒ 发布件的 L0 逐字核对能真命中，不会显示成 ❌。
        "original_text": ("mOmCOZY\nBereit Für Die Nacht,\nSupermama?\nManche Superkräfte\n"
                          "Passen Auf Den\nNachttisch\n\"Was Sind Deine Mama-Hacks Für Ruhigere Nächte?\""),
        "rule_code": "S-1.2",
        "evidence": {
            "library": "内部正负样本库（kb_type=internal_sample）",
            "article_no": "S-1.2",
            "anchor": S12["anchor"],
            "source_sha256": S12["record_sha256"],
            "excerpt": S12["excerpt"],
        },
        "suggestion": ("按已定稿反例处置：改正画面中奶瓶的摆放（不得倒置），改后重新提交。"
                       "注：L0「建议」字段文本与「具体原因/分析」逐字相同（首句为否定句），"
                       "疑为采集时字段复制错误 ⇒ 该字段不得直接外发，需业务先确认。"),
        "trace": {
            "form": "sample_case",
            "polarity": "反例",
            "semantics": "禁区：不能这么做 + 为什么",
            "reason_category": "原则性错误",
            "status": "stable",
            "owner": "刘华丽",
            "valid_until": "2027-03-28",
            "effective_from": "2026-09-29",
            "material_type": "图片",
            "channel": "社媒",
            "l4_anchor": S12["anchor"],
            "l2_unit_id": S12["unit_id"],
            "l2_media_anchor": S12["media_anchor"],
            "l1_source_sha256": S12["record_sha256"],
            "l1_image_file_sha256": S12["file_sha256"],
            "l1_file": S12["l1_file"],
            "l0_entry_url": S12["entry_url"],
            "l0_record_id": "recvw2vgYXHKgM",
            "l0_verbatim_field": "具体原因/分析",
            "sha_note": ("与 L0 记录值比对一致（不是重算）：sha 输入是 record_fields 字段 blob，"
                         "本地 L0 件不含该 blob。"),
            "near_duplicate": {
                "article_no": "S-1.175",
                "material_type": "文字",
                "anchor": S1175["anchor"],
                "unit_id": S1175["unit_id"],
                "source_sha256": S1175["record_sha256"],
                "entry_url": S1175["entry_url"],
                # 该字段值末尾逐字带着送审的德语 OCR 串（发布件会做 L0 逐字核对）
                "l0_verbatim_field": "原文反馈",
                "excerpt_in_l0": S1175["excerpt"],
            },
        },
    },
    {
        "risk_type": "证据边界（非条款项）",
        "priority_tier": "REVIEW",
        "action": "人工看一眼画面本体：确认成品图与送审截图的差异、以及奶瓶倒置是否真的在成图里",
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
        "suggestion": ("补送图片文件本体（或可访问 URL / file_token），以便：① 复算 sha256 与 "
                       "a3c7828f… 逐字节比对；② 独立观测奶瓶摆放；③ 补判画面安全。"),
    },
]

dec = dict(eng)
dec.update({
    "state": "BLOCK",
    "decision": "BLOCK",
    "confidence": None,
    "issue_count": len(risk_items),
    "summary": ("【审查结论：BLOCK】送审图片与库内已定稿反例/禁区条款 S-1.2（近重复 S-1.175）实质同一："
                "同一图片文件实体（sha256 a3c7828f…，123,988 字节）、同一活动（欧洲社媒德国 8.14 "
                "Jeder Schritt der Stillreise）、德语 OCR 与 S-1.175 的 L0「原文反馈」逐字相同；"
                "该条款定论 = 原则性错误「奶瓶不建议倒着放」。⇒ 不能发。" + DECISION_NOTE),
    "risk_items": risk_items,
    "next_owners": ["设计/素材提交方（改画面后重提）", "内容治理负责人（机制缺口 GAP-SELFHIT-1）"],
    "issue_summary_by_category": {
        "原则性错误（已定稿反例/禁区 S-1.2，近重复 S-1.175）": 1,
        "证据边界（画面本体未到本机，非条款项）": 1,
    },
    "decision_provenance": {
        "engine_state": eng.get("state"),
        "engine_review_id": eng.get("review_id"),
        "engine_content_version": eng.get("content_version"),
        "engine_refusal_detail": (eng.get("refusal") or {}).get("detail"),
        "rule": "Owner 2026-10-05 规则①（自命中是反面依据，不是拒答的理由）",
        "statement": DECISION_NOTE,
        "conflict_disclosed": True,
        "assembled_by": "kb/l7/review-engine 的**消费者侧**组装（kb/l7/review-engine/core/feishu_publish.py "
                        "的输入形状），未改引擎、未改发布件",
    },
    "submit_question": "审一下这张图能过吗？",
})
rev["decision"] = dec

# 组装痕迹（不入发布件，另存登记件）
registration = {
    "review_id": dec["review_id"],
    "review_base": meta.get("layer_preflight", {}).get("base"),
    "content_id": "AD-20261005-003",
    "content_version": dec["content_version"],
    "content_type": "社媒图片",
    "channel": "社媒",
    "product_line": "洗瓶机/喂养",
    "version": "v1.0",
    "submitted_text_sha256": "475775341216c76e40ac5fe39266b1a8339c04f4ff025b0470e9318239839405",
    "submitted_text_verbatim": MATERIAL,
    "decision": "BLOCK",
    "issue_count": len(risk_items),
    "decision_provenance": dec["decision_provenance"],
    "findings": risk_items,
    "identity_evidence": {
        "submitted_ocr_german": "mOmCOZY\nBereit Für Die Nacht,\nSupermama?\nManche Superkräfte\nPassen Auf Den\nNachttisch\n\"Was Sind Deine Mama-Hacks Für Ruhigere Nächte?\"",
        "kb_l1_ocr_cache_sha256": S12["file_sha256"],
        "kb_l1_ocr_cache": "kb/l1/media/_cache/a3c7828f2f66554dfa574e112d66026473023265f771df1d63410de11423ff8a.json",
        "match": "德语 7 行逐字相同（送审侧 OCR 把 ä/ü 读成 a/u、逗号读成全角，属 OCR 归一化差异）",
        "extra_tokens_in_submission": ["5615 ROOT", "刘华丽"],
        "extra_tokens_note": ("这两串在库内同一图片的 OCR 缓存里**没有**；上一单（RT-20261005-IMG-03）"
                              "判定为审阅侧 DLP 水印、不是烧进成图的内部标识。本单**未独立观测画面**，"
                              "故按「未复核项」处理，不计入问题数量。"),
        "residual_uncertainty": ("图片文件本体未到本机 ⇒ 无法对送审件复算 sha256 与 a3c7828f… 逐字节比对；"
                                 "同一性由「德语 OCR 逐字相同 + 同位项目/活动 + 库内 5 条记录引用同一图片实体」确立，"
                                 "不是字节级证明。"),
    },
    "screened_out": {
        "p0_hits": 0,
        "rules_hits": 0,
        "candidates_considered": ["W-2.122（AAP 安全睡眠：不应让宝宝在成人床上睡整觉）",
                                  "W-2.36", "W-2.103", "W-2.380", "H05", "H09", "安全词"],
        "why_not": ("送审画面未到达 ⇒ 场景是否「同床睡眠」无从观测；H05/H09/安全词/W-2.x 均为英文措辞项，"
                    "与德语文案无逐字对应。未命中 ≠ 合规（库内统一口径）。"),
    },
}
registration["engine_envelope"] = {
    "engine_json": "_rt-img-20261005/rt-img-04-engine.json",
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
