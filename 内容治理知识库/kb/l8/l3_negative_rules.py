#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l3_negative_rules.py —— 负面样本 → 规则（N-1.x 段）的**唯一产出者**。

目标（Owner 2026-10-20）：飞书侧 @守衡 发任一图片，命中知识库里的负面样本规则，
指出问题、给出建议。

已批准的 5 个参数（逐条落地；改它们要 Owner 重新签字）
────────────────────────────────────────────────────
  ① 粒度 = **问题要点**（不是每条记录一条），图片级挂载；
  ② 无「建议」的记录 → 只出 **prohibit 型**规则（`action.kind=prohibit`）；
  ③ 无「原因分类」→ 进 **N-00 未分类**（不猜分类）；
  ④ 条款号段 = **N-1.x**（W-1/W-2 已被措辞规则占用、S-1 已被案例占用）；
  ⑤ scope = **渠道 × 品线**，取不到留空（不编）。

★ 2026-10-20 实测后对参数①的**落地细化**（不改变口径，只把"要点"读对）：
  630 个「问题要点」里只有 **30% 带规范信号**（不能/不要/应改/避免…），
  其余是 @ 提醒（「麻烦看看呀」）、需求描述（「尺寸 1200×1200」）、纯观察（「这个质感不对」）。
  若把每个要点原样变成规则，会把 **125 条 @ 提醒**做成规则。
  ⇒ 规则分两档，**同一 N-1 段、同一证据链**，只多一个 `rule_kind` 字段：
     · `point`         —— 要点级规则（带规范信号；这是**主力**）
     · `record_level`  —— 该记录一个规范要点都没有时的兜底（取记录首句问题陈述），
                          `confidence=low`，如实标注，**不冒充判定**
  记录连兜底都没有 ⇒ 进 `unresolved[]`（不硬造规则），并让覆盖闸门点名到图。

证据链
──────
每条规则带 `evidence_units[]`（L2 unit_id + anchor + source_sha256）与 `image_refs[]`
（file_token + anchor + 图片 sha256 + OCR 字数）⇒ 条款号 → 规则 → L2 单元 → L0 记录 → 飞书直链。

用法
────
  kb/kbpy l8/l3_negative_rules.py                 # 预演（默认，不写盘）
  kb/kbpy l8/l3_negative_rules.py --apply --run <RUN>
"""
# ── 解释器守卫（与库内其它 l8 脚本同一口径）────────────────────────────────
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import collections
import difflib
import hashlib
import json
import os
import re
import sys
import time

APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
RUN = None
for _i, _a in enumerate(list(sys.argv)):
    if _a == "--run" and _i + 1 < len(sys.argv):
        RUN = sys.argv[_i + 1]
if RUN is None:
    # 兼容编排器：`kb_pipeline.py` 按 `args: ["RUN"]` 传**位置参数**（不是 --run）。
    _pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if _pos:
        RUN = _pos[0]
if RUN is None:
    RUN = time.strftime("%Y%m%d-%H%M")

TABLE_ID = "tbld8qE92YaY38Yz"
TABLE_NAME = "负面样本"
BASE = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
L0_REC = "kb/l0/records/负面样本"
L1_MEDIA = "kb/l1/2_内部正负样本库"
L2_UNITS = "kb/l2/units.jsonl"
OUT_RULES = "kb/l3/candidates/negative_rules.jsonl"
OUT_MAP = "kb/l3/candidates/negative_image_map.jsonl"
OUT_ITEM = "kb/l3/candidates/negative_item_map.jsonl"
OUT_REG = "kb/l3/registry/negative_rules.json"

CODE_BY_CATEGORY = {
    "品牌一致性": "N-01",
    "原则性错误": "N-02",
    "措辞表达": "N-03",
    "文化禁忌": "N-04",
    "合规红线": "N-05",
}
UNCLASSIFIED = "N-00"
CODE_LABEL = {
    "N-00": "未分类", "N-01": "品牌一致性", "N-02": "原则性错误",
    "N-03": "措辞表达", "N-04": "文化禁忌", "N-05": "合规红线",
}

# ★ 2026-10-21（Owner：「能跟飞书表中“原因分类”来对齐吗？归属于12类别」）：
#   实测 184 条负面样本记录里，**正文首行 `【原因分类】` 标签 184/184 全有**，而与 select 字段
#   133/133 一致（不一致 0）；字段为空的 51 条，正文标签全是 **【审核问题】** ——
#   是飞书 select **缺这个选项**，不是源侧没分类。本文件原来只读 select（下面 `cats`），
#   读到空就落 `N-00 未分类` ⇒ 96 条规则带着「未分类」这个名字流到报告里。
# ⇒ 修法：**select 空时回落到正文首行标签**；`rule_code` 一律不动
#   （rule_id 由 code+text 哈希、article_no 由 code 排序决定，动 code 会把历史编号全打乱）。
_KNOWN_TAGS = ("品牌一致性", "原则性错误", "措辞表达", "文化禁忌", "合规红线", "审核问题")
_REASON_TAG = re.compile(r"^\s*【([^】]{1,20})】")


def reason_tag(analysis):
    """「具体原因/分析」正文首行的 `【…】` 标签；认不出 ⇒ `None`（不猜）。"""
    m = _REASON_TAG.match(str(analysis or ""))
    t = (m.group(1) or "").strip() if m else ""
    return t if t in _KNOWN_TAGS else None


def label_of(code, tag):
    """规则行上的 `rule_code_label`：**真标签优先**，落不到才用码表，最后才是码本身。

    为什么 N-00 特殊：它的码表名是「未分类」，而实测这一码全部来自正文标签【审核问题】
    ⇒ 照码表印等于把「字段缺选项」说成「源侧没分类」。标签认不出时才保留「未分类」。
    """
    if tag:
        return tag
    return CODE_LABEL.get(code, code)
ARTICLE_PREFIX = "N-1"

#: **问题信号**（2026-10-20 收紧）：出现这些词的要点才算"可判定的问题"。
#  ★ 为什么比第一版窄：第一版把「建议/应该/必须/需要」也算信号，于是
#    「项目目标：配合 Costco 上架…」「头图建议：清晨通勤…」这类**需求描述**全成了规则。
#    实测 162 条里约四成是需求/设计说明 —— 那是 brief，不是判定。
NORMATIVE = re.compile(
    r"错|不对|不能|不要|不应|不许|禁止|避免|问题|风险|违规|不合规|不适|不适合|多余|遮挡|"
    r"裁到|重叠|不一致|不统一|缺失|没有支撑|色差|夸大|绝对化|误导|乱|偏差|错误|漏|写错|用错")
#: 需求/简报式开头 —— 是**要做什么**，不是**哪里错了**（不进规则，进 unresolved 说明）
BRIEF = re.compile(r"^(项目目标|项目背景|项目名|设计需求|项目需求|设计要求|需求|背景|参考|尺寸|数量|规格|"
                   r"头图建议|尾图建议|主题|排版|字体规范|色彩规范)")
#: 噪声：@ 提醒、致谢、客套 —— 实测 125 条，占要点 20%
NOISE = re.compile(r"@|麻烦看看|辛苦|姐姐|谢谢|看看这个|看看呀")
META_TAIL = re.compile(r"(价值评分|涉及消息数|参与审核)\s*[:：]")

CLUSTER_RATIO = 0.90      # 同码内近重复聚类阈值（difflib）


def clean(t):
    """去掉 @ 提醒、`【…】` 标签、多余空白与标点。"""
    s = str(t or "")
    s = re.sub(r"@[^\s，。；、,.;:]{1,16}", "", s)
    s = re.sub(r"【[^】]{0,16}】", "", s)
    s = META_TAIL.split(s)[0]
    s = re.sub(r"\s+", " ", s).strip(" ，。；、,.;:：")
    return s


def norm(s):
    """去重键归一：抹掉空白/标点，**不抹字**。"""
    return re.sub(r"[\s，。；：、,.;:!?！？（）()\[\]【】\"'“”‘’·…—\-]+", "", str(s or "")).lower()


def split_items(analysis):
    """把「具体原因/分析」拆成问题要点（保留原文，清洗交给 clean()）。"""
    t = str(analysis or "").strip()
    if not t:
        return []
    t = re.sub(r"^\s*【[^】]{1,20}】\s*(文案|图片|视频|其他)?\s*[:：]?\s*", "", t)
    m = re.search(r"【问题要点】", t)
    body = t[m.end():] if m else t
    items, cur = [], None
    for ln in (l.strip() for l in body.splitlines()):
        if not ln:
            continue
        mm = re.match(r"^(\d{1,2})\s*[\.、．)]\s*(.*)$", ln)
        if mm:
            if cur:
                items.append(cur)
            cur = mm.group(2).strip()
        elif cur is not None:
            cur += " " + ln
        else:
            cur = ln
    if cur:
        items.append(cur)
    out = []
    for it in items:
        it = re.sub(r"^\d{1,2}\s*[\.、．)]\s*", "", it).strip().strip("；; ")
        if it:
            out.append(it)
    return out


def core_statement(analysis):
    """记录首句问题陈述（`【问题要点】` 之前那一段），用作 record_level 兜底。"""
    t = str(analysis or "").strip()
    if not t:
        return ""
    t = re.sub(r"^\s*【[^】]{1,20}】\s*(文案|图片|视频|其他)?\s*[:：]?\s*", "", t)
    head = t.split("【问题要点】")[0]
    head = head.splitlines()[0] if head.strip() else ""
    return clean(head)


def split_advice(advice):
    t = str(advice or "").strip()
    if not t:
        return []
    parts = [clean(p) for p in re.split(r"[；;\n]+", t)]
    return [p for p in parts if len(p) >= 4]


def overlap_score(item, advice_seg):
    a, b = norm(item), norm(advice_seg)
    if not a or not b:
        return 0
    best, prev = 0, [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def load_l0_records():
    out = {}
    for fn in sorted(os.listdir(L0_REC)):
        if not fn.endswith(".json"):
            continue
        doc = json.load(open(os.path.join(L0_REC, fn), encoding="utf-8"))
        rid = doc.get("record_id")
        if rid:
            out[rid] = doc
    return out


def load_l2_media_units():
    """记录 → L2 媒体单元（**排除已退役**）。用于让每条规则**回指 L2**，而不只是 L1。

    为什么必须回指：Owner 口径「L3 跟 L2 同步」——规则的证据里要有 L2 单元，
    否则画面读数虽然进了 L2，规则却还挂在 L1 锚点上，链条在 L3 又断了。
    """
    retired = set()
    p = "kb/l2/retired_units.jsonl"
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                retired.add(json.loads(line)["unit_id"])
    out = collections.defaultdict(list)
    for line in open(L2_UNITS, encoding="utf-8"):
        if not line.strip():
            continue
        u = json.loads(line)
        rid = u.get("resource_id") or ""
        if rid.startswith("media_%s_" % TABLE_ID) and u.get("unit_id") not in retired:
            out[rid.split("media_%s_" % TABLE_ID, 1)[-1]].append(u)
    return out


def load_l2_units():
    out = {}
    for line in open(L2_UNITS, encoding="utf-8"):
        if not line.strip():
            continue
        u = json.loads(line)
        rid = u.get("resource_id") or ""
        if rid.startswith("bitable__%s__" % TABLE_ID):
            out[rid.split("__")[-1]] = u
    return out


def load_media():
    out = {}
    prefix = "media_%s_" % TABLE_ID
    for fn in os.listdir(L1_MEDIA):
        if not fn.startswith(prefix) or not fn.endswith(".json"):
            continue
        doc = json.load(open(os.path.join(L1_MEDIA, fn), encoding="utf-8"))
        rid = (doc.get("source") or {}).get("record_id") or fn[len(prefix):-5]
        reg = {}
        for m in (doc.get("media_refs") or []):
            tok = m.get("file_token")
            if not tok:
                continue
            seg = next((s for s in (doc.get("segments") or []) if s.get("anchor") == m.get("anchor")), None)
            vseg = next((s for s in (doc.get("segments") or [])
                         if s.get("anchor") == m.get("anchor") and s.get("kind") == "image_visual"), None)
            reg[tok] = {"seq": m.get("seq"), "sha256": m.get("sha256"), "bytes": m.get("bytes"),
                        "anchor": m.get("anchor"), "ocr_chars": len((seg or {}).get("text") or ""),
                        "ocr_text": ((seg or {}).get("text") or ""),
                        "visual": m.get("visual") or (vseg or {}).get("scene"),
                        "visual_text": m.get("visual_text") or (vseg or {}).get("text") or ""}
        out[rid] = reg
    return out


def val(doc, name):
    return ((doc.get("fields") or {}).get(name) or {}).get("value")


def image_refs_of(rid, doc, media, l2_media=None):
    mreg = media.get(rid) or {}
    out = []
    for a in (val(doc, "图片素材") or []):
        tok = a.get("file_token") if isinstance(a, dict) else None
        if not tok:
            continue
        m = mreg.get(tok) or {}
        _l2 = None
        for _u in ((l2_media or {}).get(rid) or []):
            if _u.get("anchor") == m.get("anchor"):
                _l2 = _u
                break
        if _l2 is None and len((l2_media or {}).get(rid) or []) == 1:
            _l2 = (l2_media or {})[rid][0]
        out.append({"file_token": tok, "record_id": rid, "seq": m.get("seq"),
                    "anchor": m.get("anchor") or ("#素材/%s/图片素材/#img.%s" % (rid, m.get("seq"))),
                    "sha256": m.get("sha256"), "ocr_chars": m.get("ocr_chars", 0),
                    "ocr_text": (m.get("ocr_text") or ""),
                    "l2_unit_id": (_l2 or {}).get("unit_id"),
                    "l2_anchor": (_l2 or {}).get("anchor"),
                    "l2_sha256": (_l2 or {}).get("source_sha256"),   # 不截断：同图指纹按**逐字重合**判，截断会让长图永远匹配不上
                    "visual": m.get("visual"), "visual_text": m.get("visual_text") or ""})
    return out


def cluser_merge(drafts):
    """同码内近重复聚类（difflib ≥ CLUSTER_RATIO），合并 support/证据/图片。

    为什么需要：实测 419 条初稿里有 **326 对** 相似度 >0.85 的重复（编号差异/标点差异）。
    聚类**只在同码内做**，跨码不合并（N-02「抱姿错误」与 N-03「措辞」不能并成一条）。
    """
    by_code = collections.defaultdict(list)
    for d in drafts:
        by_code[d["code"]].append(d)
    merged = []
    for code, ds in by_code.items():
        ds.sort(key=lambda d: (-len(d["record_ids"]), len(d["text"]), norm(d["text"])))
        reps = []
        for d in ds:
            key = norm(d["text"])
            hit = None
            for r in reps:
                if abs(len(r["_key"]) - len(key)) <= max(6, int(0.25 * len(key))) \
                        and difflib.SequenceMatcher(None, r["_key"], key).ratio() >= CLUSTER_RATIO:
                    hit = r
                    break
            if hit is None:
                d = dict(d)
                d["_key"] = key
                reps.append(d)
            else:
                hit.setdefault("tag", d.get("tag"))
                hit["record_ids"].update(d["record_ids"])
                hit["unit_ids"].update(d["unit_ids"])
                hit["images"].update(d["images"])
                hit["advices"].extend(d["advices"])
                hit["variants"].append(d["text"])
        merged.extend(reps)
    return merged


def build():
    recs = load_l0_records()
    units = load_l2_units()
    media = load_media()
    l2_media = load_l2_media_units()

    drafts = []
    unresolved = []
    stats = collections.Counter()
    per_record_rules = collections.Counter()

    for rid in sorted(recs):
        doc = recs[rid]
        cats = val(doc, "原因分类") or []
        code = CODE_BY_CATEGORY.get(cats[0], UNCLASSIFIED) if cats else UNCLASSIFIED
        analysis = val(doc, "具体原因/分析") or ""
        # ★ 2026-10-21：select 空 ⇒ 回落正文首行标签（见上方 `_KNOWN_TAGS` 那一段）。
        tag = reason_tag(analysis) or (cats[0] if (cats and cats[0] in _KNOWN_TAGS) else None)
        if not cats:
            stats["records_without_category"] += 1
            if tag:
                stats["records_category_from_body_tag"] += 1
        advice = split_advice(val(doc, "建议") or "")
        imgs = image_refs_of(rid, doc, media, l2_media)

        # ★ 2026-10-20（Owner 第 5 轮要求）：「具体原因/分析」里的**每一条**都要落成规则。
        #   不再按「有没有规范信号」筛：设计/视觉类意见、需求描述、客套话**一条不丢**，
        #   只按 kind 分级并在 `negative_item_map.jsonl` 里逐条留痕（原文 → 规则号）。
        raw_items = split_items(analysis)
        items = [clean(it) for it in raw_items]
        items = [x for x in items if x]
        stats["items_total"] += len(raw_items)
        core = core_statement(analysis)

        made = 0
        for it in items:
            if NOISE.search(it) or len(it) < 5:
                kind, conf = "non_substantive", "low"
            elif NORMATIVE.search(it):
                kind, conf = "point", "medium"
            elif BRIEF.match(it):
                kind, conf = "brief", "low"
            else:
                kind, conf = "observation", "low"
            drafts.append({"code": code, "tag": tag, "text": it, "kind": kind, "confidence": conf,
                           "record_ids": {rid}, "unit_ids": {units[rid]["unit_id"]} if rid in units else set(),
                           "images": {im["file_token"]: im for im in imgs}, "advices": [],
                           "variants": []})
            made += 1
        # 建议也**各自成规则**（Owner：「具体原因分析/建议都必须落成规则」）
        for seg in advice:
            drafts.append({"code": code, "tag": tag, "text": seg, "kind": "advice", "confidence": "low",
                           "record_ids": {rid}, "unit_ids": {units[rid]["unit_id"]} if rid in units else set(),
                           "images": {im["file_token"]: im for im in imgs}, "advices": [seg],
                           "variants": []})
            stats["advice_items"] += 1
        if not made:
            # 连一条要点都没有（字段是空的）：依次退到「建议原文」→「待人工」。
            if advice:
                drafts.append({"code": code, "tag": tag, "text": advice[0], "kind": "advice_only", "confidence": "low",
                               "record_ids": {rid}, "unit_ids": {units[rid]["unit_id"]} if rid in units else set(),
                               "images": {im["file_token"]: im for im in imgs}, "advices": [advice[0]],
                               "variants": []})
                made += 1
                stats["records_advice_only"] += 1
            else:
                drafts.append({"code": code, "tag": tag, "text": "该素材与库内负面样本记录相似，但源记录只有 @提醒、没有具体判定（需人工补）",
                               "kind": "needs_manual", "confidence": "low",
                               "record_ids": {rid}, "unit_ids": {units[rid]["unit_id"]} if rid in units else set(),
                               "images": {im["file_token"]: im for im in imgs}, "advices": [],
                               "variants": []})
                made += 1
                unresolved.append({"record_id": rid, "images": [im["file_token"] for im in imgs],
                                   "covered_by": "needs_manual",
                                   "reason": "该记录只有 @提醒/需求描述，没有任何可判定的要点",
                                   "analysis_head": clean(analysis)[:80]})
                stats["records_needs_manual"] += 1
        per_record_rules[rid] = made
        # 建议挂载（记录级建议 → 与该记录每条规则做重叠匹配）
        for d in drafts[-made:] if made else []:
            best, seg = 0, None
            for s in advice:
                if re.match(r"^(确认|是否|要不要|看看|麻烦)", s):
                    continue            # 这类"建议"是提问，不是改法（实测「确认一下要不要改成华氏度」→ 反义）
                sc = overlap_score(d["text"], s)
                if sc > best:
                    best, seg = sc, s
            # 判据收紧：重叠要够长（≥8 且 ≥ 要点长度的 35%），否则宁可不挂（→ prohibit）
            if seg and best >= 8 and best >= 0.35 * max(1, len(norm(d["text"]))):
                d["advices"].append(seg)

    merged = cluser_merge(drafts)
    _KIND_ORDER = {"point": 0, "observation": 1, "brief": 2, "advice": 3,
                   "record_level": 4, "advice_only": 5, "non_substantive": 6, "needs_manual": 7}
    merged.sort(key=lambda b: (b["code"], _KIND_ORDER.get(b["kind"], 9), -len(b["record_ids"]), norm(b["text"])))

    rules = []
    for i, b in enumerate(merged, start=1):
        adv = sorted({a for a in b["advices"] if a}, key=lambda s: (-len(s), s))
        ev = []
        for rid in sorted(b["record_ids"]):
            u = units.get(rid)
            if u:
                ev.append({"unit_id": u["unit_id"], "anchor": u.get("anchor"),
                           "source_sha256": u.get("source_sha256"), "record_id": rid})
        imgs = [b["images"][k] for k in sorted(b["images"])]
        for im in imgs:
            lu, la, ls = im.get("l2_unit_id"), im.get("l2_anchor"), im.get("l2_sha256")
            if lu and lu not in {e.get("unit_id") for e in ev}:
                ev.append({"unit_id": lu, "anchor": la, "source_sha256": ls,
                           "record_id": im.get("record_id"), "layer": "L2-media"})
        chans, prods = set(), set()
        for rid in b["record_ids"]:
            for c in (val(recs[rid], "渠道/市场") or []):
                if str(c).strip():
                    chans.add(str(c))
            p = val(recs[rid], "品线")
            for x in ([p] if isinstance(p, str) else (p or [])):
                if str(x).strip():
                    prods.add(str(x))
        vcues = collections.Counter()
        for im in imgs:
            vs = im.get("visual") or {}
            if vs.get("setting") and vs["setting"] not in ("未给", "看不清"):
                vcues["场景:" + str(vs["setting"])] += 1
            for p in (vs.get("people") or []):
                k = str(p.get("kind") or "").strip()
                if k and k != "分不清":
                    vcues["人物:" + k] += 1
            for p in (vs.get("products") or []):
                w = str(p.get("what") or "").strip()
                if w:
                    vcues["物件:" + w[:12]] += 1
            for c in (vs.get("risk_cues") or []):
                vcues["线索:" + str(c)[:20]] += 1
        rules.append({
            "rule_id": "nr-" + hashlib.sha1((b["code"] + "|" + norm(b["text"])).encode()).hexdigest()[:16],
            "article_no": "%s.%d" % (ARTICLE_PREFIX, i),
            "rule_code": b["code"],
            "rule_code_label": label_of(b["code"], b.get("tag")),
            "rule_kind": b["kind"],
            "confidence": b["confidence"],
            "form": "negative_sample_rule",
            "kb_type": "internal_sample",
            "kb_version": "v0",
            "source_table": TABLE_NAME,
            "source_table_id": TABLE_ID,
            "polarity": "反例",
            "rule_text": b["text"],
            "variants": b["variants"][:5],
            "action": {"kind": "replace" if adv else "prohibit",
                       "replacement": adv[0] if adv else None},
            "applicable_scope": {"channel": sorted(chans), "product_line": sorted(prods),
                                 "content_type": ["图片"]},
            "support_count": len(b["record_ids"]),
            "record_ids": sorted(b["record_ids"]),
            "evidence_units": ev,
            "image_refs": imgs,
            "image_count": len(imgs),
            "visual_cues": [k for k, _ in vcues.most_common(12)],
            "entry_url": "https://momcozy-in.feishu.cn/base/%s?table=%s&record=%s"
                         % (BASE, TABLE_ID, sorted(b["record_ids"])[0]),
            "observed_at": RUN,
            "status": "provisional",
            "owner": "刘华丽",
        })

    img_map = collections.defaultdict(lambda: {"rule_ids": [], "article_nos": []})
    for r in rules:
        for im in r["image_refs"]:
            e = img_map[im["file_token"]]
            if r["rule_id"] not in e["rule_ids"]:
                e["rule_ids"].append(r["rule_id"])
                e["article_nos"].append(r["article_no"])
    map_rows = []
    for tok in sorted(img_map):
        rid = next((im["record_id"] for r in rules for im in r["image_refs"] if im["file_token"] == tok), None)
        map_rows.append({"file_token": tok, "record_id": rid,
                         "rule_count": len(img_map[tok]["rule_ids"]),
                         "rule_ids": img_map[tok]["rule_ids"],
                         "article_nos": img_map[tok]["article_nos"]})

    src_images = {a.get("file_token") for doc in recs.values()
                  for a in (val(doc, "图片素材") or []) if isinstance(a, dict)}
    src_images.discard(None)
    covered = {m["file_token"] for m in map_rows}
    uncovered = sorted(src_images - covered)

    # ── 逐条溯源：每条「具体原因/分析」要点、每条「建议」→ 规则号 ──────────────
    #   为什么要有它：Owner 要求「这两栏必须**都**落成规则」——只报规则数证明不了这件事，
    #   要能逐条回指（原文 → 规则号），缺一条就点名。
    by_code = collections.defaultdict(list)
    for r in rules:
        by_code[r["rule_code"]].append(r)

    def best_rule(code, text):
        n = norm(text)
        best, br = None, 0.0
        for r in by_code.get(code, []):
            k = norm(r["rule_text"])
            if k == n:
                return r["rule_id"], 1.0
            if abs(len(k) - len(n)) <= max(8, int(0.35 * max(1, len(n)))):
                rr = difflib.SequenceMatcher(None, k, n).ratio()
                if rr > br:
                    br, best = rr, r["rule_id"]
        return best, br

    item_map = []
    for rid in sorted(recs):
        doc = recs[rid]
        cats = val(doc, "原因分类") or []
        code = CODE_BY_CATEGORY.get(cats[0], UNCLASSIFIED) if cats else UNCLASSIFIED
        for it in split_items(val(doc, "具体原因/分析") or ""):
            c = clean(it)
            if not c:
                continue
            rr, sc = best_rule(code, c)
            item_map.append({"record_id": rid, "field": "具体原因/分析", "text": c,
                             "rule_id": rr, "match": round(sc, 3)})
        for seg in split_advice(val(doc, "建议") or ""):
            rr, sc = best_rule(code, seg)
            item_map.append({"record_id": rid, "field": "建议", "text": seg,
                             "rule_id": rr, "match": round(sc, 3)})
    mapped = sum(1 for x in item_map if x["rule_id"])
    stat_item = {"items": len(item_map), "mapped": mapped,
                 "unmapped": [x for x in item_map if not x["rule_id"]][:20]}
    stat_item["by_field"] = {"%s|%s" % (k[0], "mapped" if k[1] else "unmapped"): v
                             for k, v in collections.Counter(
                                 (x["field"], bool(x["rule_id"])) for x in item_map).items()}

    summary = {
        "run": RUN,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "records_total": len(recs),
        "rules": len(rules),
        "rules_by_code": dict(sorted(collections.Counter(r["rule_code"] for r in rules).items())),
        "rules_by_label": dict(sorted(collections.Counter(r["rule_code_label"] for r in rules).items())),
        "rules_by_kind": dict(collections.Counter(r["rule_kind"] for r in rules)),
        "action_by_kind": dict(collections.Counter(r["action"]["kind"] for r in rules)),
        "source_images": len(src_images),
        "images_covered": len(covered),
        "images_uncovered": uncovered,
        "unresolved_records": unresolved,
        "stats": dict(stats),
        "item_map": stat_item,
        "params": {
            "granularity": "问题要点（带规范信号者为准；无要点则记录级兜底，均标 rule_kind）",
            "no_advice": "prohibit",
            "no_category": UNCLASSIFIED,
            "article_segment": ARTICLE_PREFIX + ".x",
            "scope": "渠道 × 品线，取不到留空",
        },
    }
    return rules, map_rows, item_map, summary


def main():
    rules, map_rows, item_map, summary = build()
    print("负面样本规则蒸馏 ｜ 记录 %d ｜ 规则 %d（要点 %d / 记录级 %d）｜ 图片覆盖 %d/%d"
          % (summary["records_total"], summary["rules"],
             summary["rules_by_kind"].get("point", 0),
             summary["rules_by_kind"].get("record_level", 0),
             summary["images_covered"], summary["source_images"]))
    print("  按码：", summary["rules_by_code"])
    print("  按标签：", summary.get("rules_by_label"))
    print("  动作：", summary["action_by_kind"])
    print("  源数据：", summary["stats"])
    if summary["unresolved_records"]:
        print("  ⚠️ 无可判定要点的记录：%d 条（图片 %d 张未覆盖）"
              % (len(summary["unresolved_records"]),
                 len(summary["images_uncovered"])))
        for x in summary["unresolved_records"][:5]:
            print("     %s ｜ %s" % (x["record_id"], x["analysis_head"][:50]))
    if not APPLY:
        print("\n[dry-run] 会写：%s / %s / %s（加 --apply 才落盘）"
              % (OUT_RULES, OUT_MAP, OUT_REG))
        return 0
    os.makedirs(os.path.dirname(OUT_RULES), exist_ok=True)
    with open(OUT_RULES, "w", encoding="utf-8") as fh:
        for r in rules:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with open(OUT_MAP, "w", encoding="utf-8") as fh:
        for m in map_rows:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")
    with open(OUT_ITEM, "w", encoding="utf-8") as fh:
        for m in item_map:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")
    prev = {}
    if os.path.exists(OUT_REG):
        try:
            prev = json.load(open(OUT_REG, encoding="utf-8"))
        except Exception:
            prev = {}
    summary["history"] = (prev.get("history") or [])[-9:] + [{
        "run": RUN, "at": summary["at"], "rules": summary["rules"],
        "images_covered": summary["images_covered"], "source_images": summary["source_images"]}]
    # 原子写：先落临时文件再换名 —— 半份 JSON 比没有更坏（本轮真踩过一次）
    _tmp = OUT_REG + ".tmp"
    with open(_tmp, "w", encoding="utf-8") as _fh:
        json.dump(summary, _fh, ensure_ascii=False, indent=1)
    os.replace(_tmp, OUT_REG)
    print("已写 %s（%d 条）/ %s（%d 张）/ %s" % (OUT_RULES, len(rules), OUT_MAP, len(map_rows), OUT_REG))
    return 0


if __name__ == "__main__":
    sys.exit(main())
