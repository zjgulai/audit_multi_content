#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RT-20261005-IMG-07 —— 把「引擎拒答封套」+「按 Owner 2026-10-05 规则① 登记的 findings」
组装成 feishu_publish.py 认的形状。

不藏的三件事（照实写在最前）：
  1. 引擎 with_kb_evidence.py 本单**实际输出 = NEEDS_INPUT（拒答 / 退出码 3）**：
     P0 0 命中、509 条规则 0 命中、L6 BM25 Top10 里**没有** S-1.2 的单元
     （f8e2ee3741a6d1b8c307；本单现跑复核：该 unit 不在 kb/l6/bm25 的 4261 个 doc 里）
     ⇒ 引擎对「已定稿反例 / 禁区」没有消费者，按 no_hit fail-closed 拒答。
     本 BLOCK **不是引擎产出的**，是判定主体『图片安全审查』按 Owner 规则① 登记得出。
  2. 本单相对前几单（IMG-02/03/04/05/06）的**新增事实**：库内同一图片文件实体
     （sha256 a3c7828f…，123,988 字节）**就在本机**（kb/l1/media 下 4 份同 sha 副本）。
     本单据此**真的看了原图**（read_image：原图 1080x1350 + 床头柜区域放大图），
     画面观察第一次进得来。送审件**字节**仍未到本机 —— 这点没有变，同一性仍由
     「OCR 逐字相同 + 文件实体唯一」确立。
  3. 前序单（IMG-04/05）曾称「库内 sample_case 自带 not_proves / forbidden（不许据本条直接判 BLOCK）」。
     本单现核：权威 L4（kb/l4/canonical/sample_case.jsonl）的 S-1.2 / S-1.175 **没有**这两个字段；
     那段文字只在**派生视图生成器**（kb/.work/gen-host-library-l4.py:242-249 及其备份）里，
     且当前 live view（kb/view）只有 3_措辞表达库、**不含案例** ⇒ 不是活冲突，只登记更正。
     权威 L4 的定性是：polarity=反例 · semantics=禁区：不能这么做 + 为什么 · status=stable ·
     evidence_strength=禁区可复现：有完整样本本体 + 原因分析。

本脚本不改引擎、不改发布件；只做「封套字段保真 + 登记字段补齐」，所有断言现读现核。
"""
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

ENGINE = HERE / "rt-img-07-engine.json"
OUT = HERE / "rt-img-07-decision.json"
TEXT = HERE / "rt-img-07-text.txt"
IMG_SHA = "a3c7828f2f66554dfa574e112d66026473023265f771df1d63410de11423ff8a"
IMG_BYTES = 123988

MATERIAL = TEXT.read_text(encoding="utf-8")
MATCH_SPAN = "mOmCOZY\nBereit Für Die Nacht,\nSupermama?\nManche Superkräfte\nPassen Auf Den\nNachttisch\n\"Was Sind Deine Mama-Hacks Für Ruhigere Nächte?\""

# ── ① 现读 L4 定稿（权威），逐条断言 ──────────────────────────────────────
def load_case(art):
    for line in (ROOT / "kb/l4/canonical/sample_case.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("article_no") == art:
            return d
    raise SystemExit(f"FATAL: {art} not in kb/l4/canonical/sample_case.jsonl")

S12, S1175 = load_case("S-1.2"), load_case("S-1.175")

assert S12["polarity"] == "反例", S12["polarity"]
assert S12["semantics"].startswith("禁区"), S12["semantics"]
assert S12["reason_category"] == "原则性错误", S12["reason_category"]
assert S12["status"] == "stable" and S12["material_type"] == "图片"
assert S12["valid_until"] == "2027-03-28"          # 今天 2026-10-05 ⇒ 未过期
assert S12["unit_id"] == "f8e2ee3741a6d1b8c307"
assert S1175["polarity"] == "反例" and S1175["semantics"].startswith("禁区")
# 送审德语内容**逐字**在两条案例正文里
for s in ("Bereit Für Die Nacht,", "Supermama?", "Manche Superkräfte",
          "Was Sind Deine Mama-Hacks Für Ruhigere Nächte?"):
    assert s in S12["sample_body"], ("S-1.2 missing", s)
    assert s in S1175["sample_body"], ("S-1.175 missing", s)
# 更正 IMG-04/05 的不实陈述：权威 L4 **没有** not_proves / forbidden
assert "not_proves" not in S12 and "forbidden" not in S12
assert "not_proves" not in S1175 and "forbidden" not in S1175
# 同一图片文件实体
img_shas = {m["source_sha256"] for m in S12["media_refs"]}
assert img_shas == {IMG_SHA}, img_shas
assert {m["source_sha256"] for m in S1175["media_refs"]} == {IMG_SHA}

# ── ② 现核：图片文件实体**在本机**（4 份同 sha 副本，逐份复算 + 比字节数）──
copies = []
for p in sorted((ROOT / "kb/l1/media").rglob("*.png")):
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    if h == IMG_SHA:
        b = p.stat().st_size
        assert b == IMG_BYTES, (str(p), b)
        copies.append((str(p.relative_to(ROOT)), b))
assert len(copies) >= 1, "FATAL: 图片文件实体不在本机"
VIEWED = copies[0][0]

# ── ③ 现核：S-1.2 的 L2 单元**不在** L6 BM25 索引里（引擎为什么看不见它）──
bm25_docs = ROOT / "kb/l6/bm25/docs.jsonl"
in_bm25 = None
if bm25_docs.exists():
    ids = set()
    for line in bm25_docs.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                ids.add(json.loads(line).get("unit_id"))
            except Exception:
                pass
    in_bm25 = S12["unit_id"] in ids
    total_docs = len(ids)
else:
    total_docs = None
assert in_bm25 is False, f"S-1.2 unit unexpectedly in bm25 index: {in_bm25}"

# ── ④ 收引擎封套（保真，不改 evidence_meta）──────────────────────────────
rev = json.loads(ENGINE.read_text(encoding="utf-8"))
eng, meta = rev["decision"], rev["evidence_meta"]
assert eng["state"] == "NEEDS_INPUT", eng["state"]
assert meta["layer_preflight"]["mode"] == "enforced" and meta["layer_preflight"]["ok"]
assert meta["decision_owner"]["skill"] == "图片安全审查"

DECISION_NOTE = (
    "【本结论的来路，必须一起读】引擎 with_kb_evidence.py 本单实际输出 = NEEDS_INPUT"
    "（拒答 · 退出码 3）：P0 0 命中、509 条规则 0 命中、L6 召回 Top10 未召回 S-1.2 的单元"
    f"（{S12['unit_id']}，本单现跑复核：该 unit 不在 kb/l6/bm25 的 {total_docs} 个 doc 里）。"
    "⇒ 引擎对「已定稿反例/禁区」没有消费者，按 no_hit fail-closed 拒答。"
    "本 BLOCK **不是引擎产出的**，而是判定主体『图片安全审查』按 Owner 2026-10-05 规则①"
    "（自命中已定稿反例/禁区 = 本素材本身有定论，必须登记 findings 并出三态，不许降级/拒答）登记得出。"
    "引擎侧缺口记作 GAP-SELFHIT-1（**未登记进 kb/l7/registry**，前几单也未登记）。"
)

NEW_FACT_NOTE = (
    "【本单新增事实：画面本体这次真的看到了】前几单（IMG-02/03/06）报告写「画面本体未到本机、画面未判」。"
    f"本单现核：库内同一图片文件实体 sha256 {IMG_SHA[:8]}…（{IMG_BYTES:,} 字节）**就在本机** —— "
    f"kb/l1/media 下有 {len(copies)} 份同 sha 副本（逐份复算一致，本单读的是 {VIEWED}）。"
    "本单用 read_image 看了原图（1080x1350）与床头柜区域放大图；画面观察见风险项 2。"
    "**但送审件的字节仍未到本机** —— 同一性仍由「OCR 逐字相同 + 该文件实体被 5 条 L0 记录引用」确立，"
    "不能对送审件复算 sha。这条边界没有变，不许读成「送审件已逐字节比对」。"
)

BOUNDARY_NOTE = (
    "【更正前几单的一处不实陈述】IMG-04/05 曾称「库内 sample_case 自带 not_proves / forbidden"
    "（案例只作参照、不许据本条直接判 BLOCK）」。本单现核：权威 L4（kb/l4/canonical/sample_case.jsonl）"
    "的 S-1.2 / S-1.175 **没有** not_proves / forbidden 字段（全文 grep 0 命中）；那段文字只在"
    "**派生视图生成器**（kb/.work/gen-host-library-l4.py:242-249 及其备份）里，是宿主库视图给案例"
    "统一盖的「参照」章，且当前 live view（kb/view）只有 3_措辞表达库、**不含案例** ⇒ 不是活冲突。"
    "**权威 L4 对该两条的定性是**：polarity=反例 · semantics=禁区：不能这么做 + 为什么 · status=stable · "
    "evidence_strength=禁区可复现：有完整样本本体 + 原因分析；rule_eligible 单元可在 L2 解析。"
)

risk_items = [
    {
        "risk_type": "原则性错误（自命中已定稿反例/禁区 S-1.2，近重复 S-1.175）",
        "priority_tier": "BLOCK",
        "action": "按已定稿反例定论处置：改正画面中奶瓶的摆放（不得倒置/横倒放置），改后重新提交",
        "original_text": MATCH_SPAN,
        "rule_code": "S-1.2",
        "evidence": {
            "library": "内部正负样本库（kb_type=internal_sample）",
            "article_no": "S-1.2",
            "anchor": S12["anchor"],
            "source_sha256": S12["source_sha256"],
            "excerpt": S12["reason_analysis"],
            "trace": {
                "form": S12["form"], "polarity": S12["polarity"], "semantics": S12["semantics"],
                "reason_category": S12["reason_category"], "status": S12["status"],
                "owner": S12["owner"], "valid_until": S12["valid_until"],
                "effective_from": S12["effective_from"], "material_type": S12["material_type"],
                "channel": S12["channel"], "evidence_strength": S12["evidence_strength"],
                "l4_anchor": S12["anchor"], "l2_unit_id": S12["unit_id"],
                "l2_media_anchor": S12["media_refs"][0]["anchor"],
                "l1_source_sha256": S12["source_sha256"],
                "l1_image_file_sha256": IMG_SHA,
                "l1_image_file_bytes": IMG_BYTES,
                "l1_image_local_copies": [c[0] for c in copies],
                "l1_file": "kb/l1/2_内部正负样本库/bitable__tbld8qE92YaY38Yz__recvw2vgYXHKgM.json",
                "l2_file": f"kb/l2/units.jsonl（unit_id={S12['unit_id']}）",
                "l0_entry_url": "https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc?table=tbld8qE92YaY38Yz&record=recvw2vgYXHKgM",
                "l0_record_id": "recvw2vgYXHKgM",
                "l0_verbatim_field": "具体原因/分析",
                "sha_note": ("与 L0 记录值比对一致（**不是重算**）：sha 输入是 record_fields 字段 blob，"
                             "本地 L0 件不含该 blob；要真核对只能点 L0 直链。"),
            },
            "near_duplicate": {
                "article_no": "S-1.175", "material_type": S1175["material_type"],
                "anchor": S1175["anchor"], "unit_id": S1175["unit_id"],
                "source_sha256": S1175["source_sha256"],
                "entry_url": "https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc?table=tbld8qE92YaY38Yz&record=recvw2wE9MmvI2",
                "reason_analysis": S1175["reason_analysis"],
            },
        },
        "suggestion": ("按已定稿反例处置 —— 定论逐字：「奶瓶不建议倒着放，对于宝宝和妈妈来说，奶瓶的卫生"
                       "重要至极……随意倒着放这个行为不符合用户习惯」。改正画面中奶瓶的摆放后重新提交。"
                       "⚠️ L0「建议」字段文本与「具体原因/分析」逐字相同、首句却是否定句（原文「建议倒着放…」），"
                       "疑为采集时字段复制错误 ⇒ 该字段**不得直接外发**，需业务先确认口径。"),
    },
    {
        "risk_type": "画面观察（本次首次可判 · 知识库无对应条款）",
        "priority_tier": "REVIEW",
        "action": "人工确认画面场景是否可接受（夜间卧室 + 婴儿在成人床上）；如需逐字节核送审件，请补送图片文件本体",
        "original_text": MATCH_SPAN,
        "rule_code": None,
        "evidence": {
            "library": "（无条款号：本项不是规则命中，是画面观察 + 证据边界）",
            "article_no": None, "anchor": None, "source_sha256": None,
            "excerpt": (
                f"本单已看原图（kb/l1/media 同 sha 副本，{IMG_BYTES:,} 字节，1080x1350）。画面逐项观察："
                "① 夜景卧室插画：窗外月牙 + 暖色床头灯；妈妈盘腿坐在**成人床**上，宝宝俯卧/侧卧在她腿上；"
                "② 妈妈 T 恤印超人「S」标志（对应设计要求的「带超人标志」）；"
                "③ 床头柜自左至右：蓝色圆柱设备（momcozy 标）、薄荷绿保温瓶（momcozy 标 + 「37」）、"
                "**一只白色奶瓶状物件横放**（非直立）、平板/手机；"
                "④ 宝宝面部不可见（不构成可识别的儿童出镜）；⑤ 未见换脸/合成痕迹（插画风格）。"
                "【边界，必须一起读】库内**没有**针对「图片里的婴儿睡眠场景」的可判条款："
                "引擎规则层 0 命中、P0 0 命中；库内最接近的定稿是**措辞类**条款 W-2.122 / W-2.103"
                "（AAP 安全睡眠：不应让宝宝在成人床上睡整觉），但它们是**文字表述**条款，"
                "**不构成本图的可判依据**。⇒ 按库口径「查不到就说查不到」：本项不作为 BLOCK 依据，"
                "登记为人工复核项。送审件**字节**仍未到本机，无法对送审件复算 sha256。"
            ),
        },
        "suggestion": ("① 人工看画面确认场景可接受性；② 如需把同一性钉到字节级，补送图片文件本体/URL；"
                       "③ 该画面场景若要自动化判定，需先由 kb-pipeline 把「婴儿睡眠场景」类规则补进 L3/L5"
                       "（本库现无）。"),
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
        f"同一图片文件实体（sha256 {IMG_SHA[:8]}…，{IMG_BYTES:,} 字节）、同一活动"
        "（欧洲社媒德国 8.14 Jeder Schritt der Stillreise）、德语 OCR 与样本正文逐字相同；"
        "该条款定论 = 原则性错误「奶瓶不建议倒着放」。⇒ 不能发。"
        + DECISION_NOTE + NEW_FACT_NOTE + BOUNDARY_NOTE
    ),
    "risk_items": risk_items,
    # 发布件从**这个键**取表列「问题分类汇总」（feishu_publish.py:496）——
    # 不给它，那一列会写空（本单第一版就踩了：行已建、汇总列空）。按 risk_items 现算，不手抄。
    "issue_summary_by_category": {it["risk_type"]: 1 for it in risk_items},
})
rev["decision"] = dec
rev["source"] = "kb-evidence-findings-cache/1 + 判定主体登记（Owner 2026-10-05 规则①）"
rev["registered_by"] = "图片安全审查（会话 session-96cf115a）"
rev["base"] = "RT-20261005-IMG-07"

OUT.write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")

print("✅ decision built:", OUT)
print("   state =", dec["state"], "| issue_count =", dec["issue_count"])
print("   S-1.2 anchor =", S12["anchor"], "| unit =", S12["unit_id"])
print("   image copies on disk =", len(copies), "| bytes =", IMG_BYTES)
print("   S-1.2 unit in L6 bm25 index =", in_bm25, f"(index docs = {total_docs})")
print("   layer_preflight =", meta["layer_preflight"]["mode"], "red_total=", meta["layer_preflight"]["red_total"])
