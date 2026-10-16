#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RT-20261005-IMG-08 —— 判定主体『图片安全审查』按 Owner 2026-10-05 规则①
把「自命中已定稿反例/禁区 S-1.2」登记成 findings，供引擎 decide() 出三态。

三条不许藏的边界（写在最前）：
 1. 引擎 live 路径本单实际输出 = **拒答**（coverage.covered=false；P0 0 命中；509 条规则 0 命中；
    L6 BM25 Top5 全是内部样本的 [image_ocr] 单元，Top1 就是本素材自己的 OCR 单元）。
    ⇒ 本 findings **不是 live 检索产出**，是判定主体登记；引擎只负责据此出三态。
 2. 送审件的**字节**没有到本机 —— 同一性由三件事确立（德语行对应 + 图片实体 sha + S-1.2 样本正文），
    **不能**对送审件复算 sha。
 3. L4 S-1.2 的 `advice` 字段首句是「建议倒着放…」，与它自己的后半句、与 `reason_analysis` 相矛盾
    （疑为采集时把「奶瓶不建议倒着放」的「不」丢了）⇒ 该字段**不得直接外发**，本单不引用它。

本脚本只做「现读现核 + 登记」；不改引擎、不改发布件、不写 kb/。
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SESSION = sys.argv[1] if len(sys.argv) > 1 else "unknown-session"

TEXT = (HERE / "text.txt").read_text(encoding="utf-8").rstrip("\n")
LIVE = HERE / "findings.json"
OUT = HERE / "findings-registered.json"

IMG_SHA = "a3c7828f2f66554dfa574e112d66026473023265f771df1d63410de11423ff8a"
IMG_BYTES = 123988

# ── ① 现读 L4 定稿（权威）并逐条断言 ────────────────────────────────────────
def load_case(art):
    for line in (ROOT / "kb/l4/canonical/sample_case.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("article_no") == art:
            return json.loads(line)
    raise SystemExit("FATAL: %s 不在 kb/l4/canonical/sample_case.jsonl" % art)

S12 = load_case("S-1.2")
S1175 = load_case("S-1.175")
assert S12["polarity"] == "反例" and S12["semantics"].startswith("禁区"), S12["semantics"]
assert S12["reason_category"] == "原则性错误" and S12["status"] == "stable"
assert S12["material_type"] == "图片" and S12["channel"] == "社媒"
assert S12["valid_until"] == "2027-03-28", S12["valid_until"]          # 今天 2026-10-05 ⇒ 未过期
assert S12["unit_id"] == "f8e2ee3741a6d1b8c307"
assert S12["anchor"] == "#正面和负面样本/recvw2vgYXHKgM/原文反馈"
assert S12["source_sha256"] == "9f39a37061cf6d1e33af111127156a9a38e69d2cfd6de70e6c71f3e8685c5136"
assert {m["source_sha256"] for m in S12["media_refs"]} == {IMG_SHA}
assert S1175["polarity"] == "反例" and S1175["semantics"].startswith("禁区")
assert {m["source_sha256"] for m in S1175["media_refs"]} == {IMG_SHA}
# 权威 L4 **没有** not_proves / forbidden（更正 IMG-04/05 的不实陈述）
assert "not_proves" not in S12 and "forbidden" not in S12

# ── ② 现核：图片文件实体在本机（逐份复算 sha + 字节数）──────────────────────
copies = []
for p in sorted((ROOT / "kb/l1/media").rglob("*.png")):
    if hashlib.sha256(p.read_bytes()).hexdigest() == IMG_SHA:
        assert p.stat().st_size == IMG_BYTES, (str(p), p.stat().st_size)
        copies.append(str(p.relative_to(ROOT)))
assert copies, "FATAL: 图片文件实体不在本机"

# ── ③ 现核：送审 OCR 的德语行 ↔ S-1.2 样本正文里的德语行（去 OCR 噪声后逐行对应）──
ocr_lines = [l for l in TEXT.splitlines() if l.strip()]
# 本机 OCR 的**已知噪声**（逐条列出来，不做无记录的模糊匹配）
OCR_ALIASES = {"fuir": "fur", "krafte": "krafte"}   # 「Für」被 OCR 读成「Fuir」（多一个 i）
def norm(s):
    s = (s.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
          .replace("，", ",").replace("？", "?").replace("“", '"').replace("”", '"')
          .replace("’", "'").strip().lower())
    for a, b in OCR_ALIASES.items():
        s = s.replace(a, b)
    return s
body_norm = norm(S12["sample_body"])
german = [l for l in ocr_lines if any(w in l for w in ("Bereit", "Supermama", "Manche",
                                                       "Passen", "Nachttisch", "Mama-Hacks"))]
assert len(german) == 6, german
for l in german:
    if norm(l) not in body_norm:
        if l.strip().lower() == "nachttisch":      # 正文该词单独成行，OCR 合并进上一行
            assert "nachttisch" in body_norm
            continue
        raise SystemExit("FATAL: OCR 行不在样本正文里：%r" % l)
assert "jeder schritt der stillreise" in body_norm and "欧洲社媒德国" in S12["sample_body"]

# ── ④ 现核：S-1.2 的 L2 单元不在 L6 BM25 索引里（引擎为什么看不见它）────────
ids = set()
for line in (ROOT / "kb/l6/bm25/docs.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        ids.add(json.loads(line).get("unit_id"))
assert S12["unit_id"] not in ids, "S-1.2 unit 竟在 bm25 索引里"
assert S1175["unit_id"] not in ids
# ③ 的 L3 侧：509 条候选里**没有** S-1.2（它是 sample_case，规则文本在 L4 案例语义里）
l3 = [json.loads(l) for l in (ROOT / "kb/l3/candidates/rules.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
assert not [r for r in l3 if r.get("article_no") == "S-1.2"], "L3 里竟有 S-1.2"

# ── ⑤ 收 live 封套（保真），只增登记字段 ────────────────────────────────────
live = json.loads(LIVE.read_text(encoding="utf-8"))
assert live["schema"] == "kb-evidence-findings-cache/1"
sha = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()
assert live["text_sha256"] == sha, (live["text_sha256"], sha)
live_payload = live["payload"]
assert live_payload["state"] == "拒答", live_payload["state"]
assert (live_payload["trace"]["coverage"] or {}).get("covered") is False

REASON = (
    "① 同一性（送审件 = 库内已定稿反例 S-1.2 的样本本体）：送审 OCR 的 6 行德语与 S-1.2 "
    "样本正文里的德语行逐行对应（只差 OCR 噪声：ä/ü 脱落、全角标点；另有水印噪声 5615/ROOT/刘华丽）；"
    "S-1.2 的 media_refs 指向图片实体 sha256 %s…（%d 字节），该实体在本机 kb/l1/media 有 %d 份副本"
    "（逐份复算一致）。**送审件字节未到本机，不能对送审件复算 sha** —— 同一性由上述三件事确立。\n"
    "② 定论（L4 权威字段，逐字见 evidence.excerpt）：polarity=反例 · semantics=禁区：不能这么做 + 为什么 · "
    "reason_category=原则性错误 · status=stable · valid_until=2027-03-28（未过期）。"
    "画面里白色奶瓶状物件**横躺（非直立）**，即该案例的禁区行为。\n"
    "③ 近重复条款 S-1.175（同锚点体系、同图片实体、material_type=文字）不另计一条，避免双计。\n"
    "④ 引擎为什么没自己报：S-1.2 的 L2 单元 %s **不在** L6 BM25 索引的 %d 个 doc 里，"
    "且 509 条 L3 候选里没有 S-1.2 ⇒ 检索侧结构上看不见它（live：P0 0 命中、规则 0 命中、"
    "coverage.covered=false ⇒ 拒答）。本 BLOCK 据 Owner 2026-10-05 规则①由判定主体登记得出，"
    "缺口记作 GAP-SELFHIT-1（引擎缺「已定稿反例/禁区」消费者）。"
    % (IMG_SHA[:8], IMG_BYTES, len(copies), S12["unit_id"], len(ids))
)

ADVICE = ("改正画面中奶瓶的摆放（直立放置，不要让奶嘴朝下/瓶身横躺），改后以新版本重新提交。"
          "⚠️ 不引用 L4 的 advice 字段：该字段首句「建议倒着放…」与其自身后半句矛盾（疑为漏了「不」），"
          "不得直接外发，需业务先确认口径。")

finding_block = {
    "rule_id": "selfhit-S-1.2",
    "rule_code": "S-1.2",
    "library": "内部正负样本库（kb_type=internal_sample）",
    "article_no": "S-1.2",
    "layer": "L4 定稿 sample_case（反例/禁区）· case_id=%s" % S12["case_id"],
    "anchor": S12["anchor"],
    "source_sha256": S12["source_sha256"],
    "unit_id": S12["unit_id"],
    "excerpt": S12["reason_analysis"],          # 逐字，程序取出，非手抄
    "entry_url": "https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc"
                 "?table=tbld8qE92YaY38Yz&record=recvw2vgYXHKgM",
    "severity": "BLOCK",
    "category": "原则性错误",
    "sub": "自命中已定稿反例/禁区：奶瓶不得倒放/横躺（画面摆放）",
    "matched_term": "奶瓶不建议倒着放",
    "position": ("画面左下·床头柜区域（源图 1080x1350 坐标盒 215,820-445,960）：白色奶瓶状物件"
                 "横躺（非直立）、奶嘴朝左下；同区域另有蓝色圆柱设备与薄荷绿保温瓶（momcozy 标 +「37」）。"
                 "OCR 德语标题「Bereit Für Die Nacht, Supermama?」"),
    "reason": REASON,
    "advice": ADVICE,
    "fact_or_inference": "事实",
    "confidence": "高",
    "verbatim_verified": True,
}

OBS = (
    "本单实看原图（%s，源文件 sha256 %s…，%d 字节，1080x1350；read_image 归一化副本 sha256 "
    "286e0fb8ea634c77a0f441e8e64cf448341e0d72f6e2171ef3efda07a2881949，webp 63490 字节）。"
    "画面逐项观察：① 夜景卧室插画，窗外月牙 + 暖色床头灯；② 妈妈盘腿坐在**成人床**上，宝宝俯卧/侧卧在她腿上，"
    "**宝宝面部不可见**（只见后脑，不构成可识别的儿童出镜）；③ 妈妈 T 恤印超人「S」盾形标志；"
    "④ 床头柜自左至右：蓝色圆柱设备（momcozy 标）、薄荷绿保温瓶（momcozy 标 +「37」）、"
    "白色奶瓶状物件（横躺，见风险项 1）、白色平板（momcozy 标 + 按键）；⑤ 扁平插画风格，"
    "未见换脸/照片合成痕迹。\n"
    "【为什么只到 REVIEW】库内**没有**针对「图片里婴儿睡在成人床上（含软性床品）」的可判条款："
    "live 检索 P0 0 命中、509 条规则 0 命中 ⇒ 本项**不判**，交人裁（未命中 ≠ 合规）。"
    "第三方商标（超人「S」标志）的**权利归属**不属本 skill，如需核走 AI溯源与权利审查。"
    % (copies[0], IMG_SHA[:8], IMG_BYTES)
)

finding_obs = {
    "rule_id": "obs-adult-bed-infant",
    "rule_code": None,
    "library": "（无条款号：画面观察项，非规则命中）",
    "article_no": None,
    "layer": "画面观察（本次实看原图）",
    "anchor": None,
    "source_sha256": None,
    "unit_id": None,
    "excerpt": None,
    "entry_url": None,
    "severity": "REVIEW",
    "category": "画面安全观察",
    "sub": "婴儿俯卧于成人床（夜间）· 库内无可判条款",
    "matched_term": "",
    "position": "主画面：妈妈盘腿坐于成人床、宝宝俯卧其腿上；宝宝面部不可见",
    "reason": OBS,
    "advice": ("人工确认该场景与软性床品的可接受性；如需逐字节核送审件，请补送图片文件本体。"
               "另：证据覆盖只到「实看原图 + 区域放大」，**没有** provider 版本字段（本机 read_image 未回报），"
               "故本项不主张 provider 契约级完整。"),
    "fact_or_inference": "观察（非规则命中）",
    "confidence": "中",
    "verbatim_verified": False,
    "regions": [
        {"name": "full", "box": [0, 0, 1080, 1350], "sha256": IMG_SHA},
        {"name": "nightstand", "box": [60, 760, 520, 1160], "artifact": "nightstand-crop.png"},
        {"name": "bottle-zoom", "box": [215, 820, 445, 960], "artifact": "bottle-zoom.png"},
    ],
}

payload = dict(live_payload)                    # 保真：trace / run_id / query_words 原样带走
payload["findings"] = [finding_block, finding_obs]
payload["state"] = "BLOCK"
payload["registration"] = {
    "by": "图片安全审查（判定主体 · 装载目录名）",
    "session": SESSION,
    "basis": "Owner 2026-10-05 规则①：自命中已定稿反例/禁区 = 本素材本身有定论，必须登记 findings 并出三态，不许降级/拒答",
    "live_engine_state": live_payload["state"],
    "live_engine_run_id": live_payload.get("run_id"),
    "live_coverage_covered": False,
    "note": "findings 由判定主体登记（非 live 检索产出）；live 检索 0 命中、coverage.covered=false ⇒ 未命中 ≠ 合规",
}

OUT.write_text(json.dumps({
    "schema": "kb-evidence-findings-cache/1",
    "cached_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
    "text_sha256": sha,
    "source": "图片安全审查 · 判定主体登记（会话 %s）" % SESSION,
    "payload": payload,
}, ensure_ascii=False, indent=1), encoding="utf-8")

print("written:", OUT)
print("copies(%d):" % len(copies), copies)
print("text_sha256:", sha)
print("findings:", [(f["rule_id"], f["severity"]) for f in payload["findings"]])
print("excerpt[0] 逐字:", repr(finding_block["excerpt"][:60]))
