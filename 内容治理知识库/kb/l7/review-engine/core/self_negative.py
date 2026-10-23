#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""self_negative.py —— 本素材**就是**库里某条负面样本规则的取证图 ⇒ 必须认出来。

## 为什么要有这一层（2026-10-20 真单，Owner 原话：「发 339 中的图片，却没有命中知识库」）

图片单的**三条身份判据**（图字节 sha256 / 图内文字逐字包含 / 行重合）都会因为
**传输形态**失效：同一张海报，飞书聊天图与多维表附件原件的字节不同、两套 OCR 也读得不同。
实测那一单：送审正文带 `sha256=2e3055b1…`，库内同一套海报是 `b9328ba2…`；行重合只有 0.50。

**但单元层照样把它召回了**（实测 BM25 原始分 308）。而命中的 L2 单元自带 `source_sha256`
—— 那个 sha 与规则 `image_refs[].sha256` 是**同一把尺子**（两边都是图字节，不是文字）。

⇒ 本条判据**不依赖送审侧把 sha 传对，也不依赖 OCR 读得一样**：
    问的是「我检索到的那件库内材料，是不是某条负面样本规则的取证图？」

## 判据（只认两条**确定性**的，不比相似度）

  ① 命中单元的 `source_sha256` == 规则某张取证图的 `sha256`；
  ② 命中单元的 `anchor` == 规则的取证锚点（`anchor` / `l2_anchor`）。

命中一律 **REVIEW** 级 —— 与 `layer_negative_rules` 同口径（历史审核意见，不是判定依据，
也不据此 BLOCK）。之所以要单独一层而不是塞进 matcher：matcher 的 `require_visual`
要求「画面线索对上」或「同图指纹」，而这件素材**恰恰过不了那两条**（传输差异）——
它是「我认得这张图」这一事实本身，不该被相似度闸门拦掉。

## 反 fail-open（这才是本层存在的理由）

上一版的形状：负面样本规则层 0 命中 ⇒ 覆盖判据被一个安全词（实测 `wearable`）撑起来
⇒ `covered_by=safe_vocabulary` ⇒ 无 findings ⇒ **PASS**。
而那张图在库里是**负面样本**（规则 N-1.39 / N-1.88 / N-1.97）。
「未命中 ≠ 合规」是库规硬口径 ⇒ 这种组合**不许**落 PASS。

用法：
    python3 kb/l7/review-engine/core/self_negative.py --selftest
    python3 kb/l7/review-engine/core/self_negative.py --units-json <trace.units.top_bm25 的 json>
"""
from __future__ import annotations

import json
import os
import sys

# 规则语料（唯一真源；`layer_negative_rules` 读的是同一个文件）
RULES_REL = os.path.join("kb", "l3", "candidates", "negative_rules.jsonl")


def _find_root(start=None):
    """从本文件往上找工作区根（含 `kb/l3/candidates/negative_rules.jsonl` 的那一层）。"""
    d = start or os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.exists(os.path.join(d, RULES_REL)):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return os.getcwd()


def load_rules(path=None):
    p = path or os.path.join(_find_root(), RULES_REL)
    out = []
    if not os.path.exists(p):
        return out
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:                       # noqa: BLE001 — 坏行不许拖死评审
                    continue
    return out


def build_index(rules):
    """图字节 sha256 / 取证锚点 → [(规则, image_ref)]。

    两条都要：sha 抗传输形态差异（图字节同一把尺子），锚点抗「L1 没算 sha」的老数据。
    """
    by_sha, by_anchor = {}, {}
    for r in rules or []:
        for im in (r.get("image_refs") or []):
            sha = (im.get("sha256") or "").strip().lower()
            if sha:
                by_sha.setdefault(sha, []).append((r, im))
            for key in (im.get("anchor"), im.get("l2_anchor")):
                if key:
                    by_anchor.setdefault(key, []).append((r, im))
    return by_sha, by_anchor


def _hit(rule, im, unit_row, matched_by):
    """把一条「同图」命中包成**与 `layer_negative_rules` 同形状**的 hit。

    形状必须对得上 `review.py` 里那个 findings 循环（它读 evidence/action/rule_code/…）——
    否则要么 KeyError 崩链，要么少字段让报告那一格空掉。宁可多给，不可少给。
    """
    act = rule.get("action") or {}
    anchor = unit_row.get("anchor") or im.get("anchor")
    sha = unit_row.get("source_sha256") or im.get("sha256")
    return {
        "article_no": rule.get("article_no"),
        "rule_id": rule.get("rule_id"),
        "rule_code": rule.get("rule_code"),
        "rule_code_label": rule.get("rule_code_label"),
        "rule_kind": rule.get("rule_kind"),
        "confidence": rule.get("confidence"),
        "rule_text": rule.get("rule_text") or "",
        "action": act,
        # 相似度那一侧**没有分数可报**：这不是相似命中，是身份命中 ⇒ 照实写 1.0 / 0.0 / 0.0
        "score": 1.0, "visual_score": 0.0, "text_score": 0.0,
        "why": "同图（%s）" % matched_by,
        "reasons": ["本素材检索命中的库内单元与规则取证图同图：%s" % matched_by],
        "image_refs": [x.get("file_token") for x in (rule.get("image_refs") or [])][:5],
        "evidence": [{"anchor": anchor, "source_sha256": sha,
                      "record_id": (unit_row.get("record_id") or im.get("record_id"))}],
        # ★ 本层独有的标记：下游据此在报告里写清「这张图在库里是负面样本」
        "library_negative_sample": True,
        "matched_by": matched_by,
        "record_id": im.get("record_id") or unit_row.get("record_id"),
        "unit_raw_bm25": unit_row.get("raw_bm25"),
        "unit_anchor": anchor,
    }


def self_negative_hits(unit_rows, rules=None, top=3):
    """单元层命中里，凡是「库里负面样本规则的取证图」⇒ 逐条报出来（按条款号去重）。

    @param unit_rows `trace["units"]["top_bm25"]`：每行至少有 anchor / source_sha256 / raw_bm25
    @returns hit 列表（与 layer_negative_rules 同形状，另带 library_negative_sample=True）
    """
    rows = [r for r in (unit_rows or []) if isinstance(r, dict)]
    if not rows:
        return []
    rules = rules if rules is not None else load_rules()
    by_sha, by_anchor = build_index(rules)
    out, seen = [], set()
    for row in rows:
        sha = (row.get("source_sha256") or "").strip().lower()
        anchor = row.get("anchor") or ""
        cand = []
        if sha and sha in by_sha:
            cand = [(r, im, "图字节 sha256 相同") for r, im in by_sha[sha]]
        elif anchor and anchor in by_anchor:
            cand = [(r, im, "取证锚点相同") for r, im in by_anchor[anchor]]
        for rule, im, matched_by in cand:
            key = rule.get("rule_id") or rule.get("article_no")
            if key in seen:
                continue
            seen.add(key)
            out.append(_hit(rule, im, row, matched_by))
            if len(out) >= top:
                return out
    return out


# ────────────────────── 收窄：「这条规则讲的是不是这张图」 ──────────────────────
#
# 为什么必须有这一层（2026-10-20 Owner 实测：「我发了图片，回复的问题是其他图片的」）
# ---------------------------------------------------------------------------
# 病灶在**数据形状**上，不在匹配算法里：规则的取证图是**整条记录的全部图**，
# 而规则的正文可能只讲其中一张。实测同一记录（`recvw7XIUgACVh`，5 张图）的四条规则：
#     N-1.337「图1: 不同族裔的妈妈们…」  N-1.340「图2: 妈妈抱着宝宝站在镜子前…」
#     N-1.342「图3：妈妈照料宝宝…」       N-1.344「图4: 分屏图片」
# 四条规则的 `image_refs` **全都是那 5 张**（唯一 sha 4 个）⇒ 用户发的是**图4**，
# 却被印上「图1/图2/图3」三条的意见 —— 这就是「回复的问题是其他图片的」。
#
# 另外一类噪声：跨记录聚合出来的规则（`record_ids` 多条、取证图几十张），
# 实测 N-1.370「麻烦看看呀」覆盖 **14 条记录 / 43 张图**、N-1.134 覆盖 4 条记录 / 14 张图 ——
# 这种规则对**任何**一张图都可能命中，它根本不是「这张图的意见」。
#
# 本层的判据（两条，都是确定性的）：
#   ① **跨记录聚合**（`record_ids` > 1）⇒ 图片级命中一律不认（它是一条记录级/跨记录意见）；
#   ② 规则正文写了「图N」⇒ N 必须等于**本素材对上的那张取证图的 seq**；
#      对上的那张由「提交图自己的 sha」优先、检索单元的 sha 兜底来定位。
#   ③ 没有「图N」且只有一条记录 ⇒ 保留，但**按记录级意见**表述（调用方不许说成「这张图命中」）。


import re as _re2

MAX_REFS_UNIQUE = 12          # 单记录内取证图唯一 sha 的上限（超过 ⇒ 视为"套装/批量"意见，不是单图）
FIG_RE = _re2.compile(r"图\s*(\d+)")


def image_shas_in(text):
    """素材正文里的图片指纹（`sha256=<64 hex>`）—— 与 `negative_rule_match` 同口径。"""
    return {m.group(1).lower() for m in _re2.finditer(r"sha256\s*[=:]\s*([0-9a-fA-F]{64})", str(text or ""))}


def _ref_seqs(rule, shas):
    """规则里 sha 命中 `shas` 的那些取证图 → 它们的 seq（取不到就是 None）。"""
    out = []
    for im in (rule.get("image_refs") or []):
        if (im.get("sha256") or "").lower() in shas:
            out.append(im.get("seq"))
    return out


def narrow_negative_hits(hits, rules=None, submitted_shas=(), unit_shas=(), max_unique=MAX_REFS_UNIQUE):
    """把「讲的是别的图 / 跨记录聚合」的命中剔掉。

    @returns (kept, dropped)；`dropped` 里每条带 `why` —— **不静默丢**（trace 与报告都要看得见）。

    ★★ 2026-10-20 第三轮（Owner：「我在飞书侧发图片，就是无法命中这些规则」）：
      上一版把「跨记录聚合」直接判成「不是这张图的意见」，可那是个**规则级属性**，
      而手上早有**图级事实** —— 匹配层已经把「对上的那张取证图」写进 `matched_image`
      （record_id + sha256）；`match_rank>=2` 更是「图内文字逐字对上」的同图指纹。

      实测：Owner 17:11 那单（库内那张 AAP「Sharing your bed」），5 条命中 score=1.00、
      `matched_image.record_id=recvw7XIUgXEvk`（就在规则的两条记录里），却被
      「跨 2 条记录聚合 ⇒ 不是这张图的意见」整批剔掉 ⇒ findings=0 ⇒ 报告写"没有问题"。
      同一批 339 张库内图里，**122 张（37%）**的命中就是这样被清空的。

      修法（**只放开「图级对上了」这一种**，不放宽任何别的）：
        · 先把「对上的那张图」定下来：提交图 sha → 检索单元 sha → `matched_image.sha256`
          三级取到 seq；再叠 `match_rank>=2` 与 `library_negative_sample` 两道同图证据；
        · **跨记录聚合** 与 **取证图过多**（>max_unique）两条，只在「**没对上任何一张取证图**」时才丢
          —— 那才是"这条意见根本不指向这张图"的真形状；
        · 「规则正文讲图N」这条判据**一个字不动**，而且现在用上了 matched_image 的 sha
          （飞书 IM 压缩过的图，提交 sha 对不上，靠它才定位得到 seq）。
      反向对照见自证 ⑿（没锚定的跨记录规则必须仍丢）与 ⒂/⒃。
    """
    rules = rules if rules is not None else load_rules()
    idx = {(r.get("rule_id") or r.get("article_no")): r for r in rules}
    sub = {s.lower() for s in (submitted_shas or ())}
    uni = {s.lower() for s in (unit_shas or ())}
    kept, dropped = [], []
    for h in hits or []:
        r = idx.get(h.get("rule_id")) or idx.get(h.get("article_no")) or {}
        if not r:
            dropped.append({"article_no": h.get("article_no"), "why": "规则查不到（不许凭空留）"})
            continue
        recs = set(r.get("record_ids") or [])
        refs = r.get("image_refs") or []
        uniq = {(im.get("sha256") or "").lower() for im in refs if im.get("sha256")}
        # ── 图级锚定：本单到底对上了这条规则的**哪一张**取证图 ──────────────────
        _mi = h.get("matched_image") or {}
        _mi_sha = (_mi.get("sha256") or "").lower()
        _anchor_shas = set(sub) | set(uni)
        if _mi_sha and _mi_sha in uniq:
            _anchor_shas.add(_mi_sha)
        seqs = [s for s in _ref_seqs(r, _anchor_shas) if s is not None]
        anchored = (bool(seqs)
                    or int(h.get("match_rank") or 0) >= 2
                    or bool(h.get("library_negative_sample")))
        why = None
        if len(recs) > 1 and not anchored:
            why = ("跨 %d 条记录聚合的规则（%d 张取证图），且本单没对上它的任何一张取证图"
                   " ⇒ 不是这张图的意见" % (len(recs), len(uniq)))
        elif len(uniq) > max_unique and not anchored:
            why = ("取证图覆盖 %d 张（>%d，属套装/批量意见），且本单没对上任何一张"
                   " ⇒ 定位不到本图" % (len(uniq), max_unique))
        else:
            m = FIG_RE.search(r.get("rule_text") or "")
            if m:
                want = int(m.group(1))
                if not seqs:
                    why = ("规则正文讲「图%d」，但提交图、检索单元与命中图都对不上这条规则的取证图"
                           " ⇒ 无法确认是这张图" % want)
                elif want not in seqs:
                    why = "规则正文讲「图%d」，本素材对上的取证图是 seq=%s ⇒ 是**别的图**" % (want, sorted(set(seqs)))
            else:
                # 记录级意见（无图序号）：保留，但把证据锚点改到**对上的那张图**上
                pass
        if why:
            dropped.append({"article_no": h.get("article_no"), "rule_id": h.get("rule_id"), "why": why})
            continue
        hit = dict(h)
        if seqs:
            for im in (r.get("image_refs") or []):
                if im.get("seq") in seqs:
                    hit["evidence"] = [{"anchor": im.get("anchor") or im.get("l2_anchor"),
                                        "source_sha256": im.get("sha256"),
                                        "record_id": im.get("record_id")}]
                    hit["matched_figure_seq"] = im.get("seq")
                    break
        # ★ 2026-10-20（串图修复 ②，第二个轴）：**改名避免与「图片归属角色」撞车** ——
        #   这里说的是「规则正文讲的是不是这张图」（figure / record），
        #   而 `attribution` 这个键现在归**图片角色**用（subject / record_level / shared_reference）。
        #   两个轴都要成立才允许当成「这张图的依据」：讲的是这张图 ∧ 这张图是那条记录的**被审对象**。
        hit["figure_attribution"] = ("figure" if FIG_RE.search(r.get("rule_text") or "") else "record")
        # ★ 2026-10-20 第三轮：把「有没有对上某张取证图」这个**图级事实**留进 trace ——
        #   下游（评审链的归属门、报告、审计）据此决定能不能引用，不必各自再猜一遍。
        hit["figure_anchored"] = bool(anchored)
        hit["figure_matched_seq"] = sorted(set(s for s in seqs if s is not None))
        kept.append(hit)
    return kept, dropped



# ────────────────────────────── 自证（含反向对照） ──────────────────────────────
def merge_image_identity_hits(existing_hits, identity_hits):
    """Merge image identity results, preferring them over same-rule semantic hits.

    The article number alone is not a safe dedupe key: identity results carry the
    precise matched image, attribution and evidence anchor. Only replace a hit
    when both rule and record match; otherwise retain both to prevent cross-record
    image attribution.
    """
    merged = [dict(h) for h in (existing_hits or [])]
    added = replaced = 0
    for identity in identity_hits or []:
        ident = dict(identity)
        key = (str(ident.get("article_no") or ""), str(ident.get("record_id") or ""))
        index = next((i for i, old in enumerate(merged)
                      if key[0] and key[1]
                      and (str(old.get("article_no") or ""), str(old.get("record_id") or "")) == key), None)
        if index is None:
            merged.append(ident)
            added += 1
            continue
        prior = merged[index]
        ident["semantic_match"] = {k: prior.get(k) for k in ("matched_by", "score", "attribution")
                                   if prior.get(k) is not None}
        merged[index] = {**prior, **ident}
        replaced += 1
    return merged, {"added": added, "replaced": replaced}


def _selftest():
    """八例：三条正例 ＋ 四条反例 ＋ 一条形状断言。

    **反向对照是判据的一部分**：把 sha 判据拆掉，⑵⑶ 必须变红；把锚点判据拆掉，⑵ 必须变红。
    """
    rules = [
        {"article_no": "N-9.1", "rule_id": "r1", "rule_code": "R-PNT", "rule_code_label": "要点",
         "rule_kind": "point", "rule_text": "海报里婴幼儿被抱着贴近成人胸前，属高风险姿势",
         "action": {"kind": "prohibit", "replacement": None},
         "image_refs": [{"file_token": "tokA", "record_id": "recA", "sha256": "a" * 64,
                         "anchor": "#素材/recA/图片素材/#img.1",
                         "l2_anchor": "#素材/recA/图片素材/#img.1"}]},
        {"article_no": "N-9.2", "rule_id": "r2", "rule_code": "R-PNT", "rule_code_label": "要点",
         "rule_kind": "point", "rule_text": "版头单词拼错",
         "action": {"kind": "prohibit", "replacement": None},
         "image_refs": [{"file_token": "tokB", "record_id": "recB", "sha256": "b" * 64,
                         "anchor": "#素材/recB/图片素材/#img.1"}]},
    ]
    cases = []

    # ⑴ 正例：单元 sha 与规则取证图 sha 相同 ⇒ 命中该规则
    h = self_negative_hits([{"anchor": "#素材/recC/图片素材/#img.1", "source_sha256": "a" * 64,
                             "raw_bm25": 308.5}], rules=rules)
    cases.append(("sha 相同 ⇒ 命中 N-9.1", bool(h) and h[0]["article_no"] == "N-9.1", h[:1]))

    # ⑵ 正例：锚点相同（sha 缺失的老数据）⇒ 也能命中
    h = self_negative_hits([{"anchor": "#素材/recB/图片素材/#img.1", "raw_bm25": 42.0}], rules=rules)
    cases.append(("锚点相同 ⇒ 命中 N-9.2", bool(h) and h[0]["article_no"] == "N-9.2", h[:1]))

    # ⑶ 反例：sha 不相干 ⇒ 一条都不许给（否则任意素材都会被判成负面样本）
    h = self_negative_hits([{"anchor": "#素材/recZ/图片素材/#img.1", "source_sha256": "c" * 64,
                             "raw_bm25": 300.0}], rules=rules)
    cases.append(("sha 不相干 ⇒ 不命中", h == [], h[:1]))

    # ⑷ 反例：空输入 ⇒ 空结果（不许抛、不许编）
    cases.append(("空单元 ⇒ 空", self_negative_hits([], rules=rules) == [], []))

    # ⑸ 去重：同一条规则的**多张**取证件都命中时，只报一条
    h = self_negative_hits([
        {"anchor": "#素材/recA/图片素材/#img.1", "source_sha256": "a" * 64},
        {"anchor": "#素材/recA/图片素材/#img.2", "source_sha256": "a" * 64},
    ], rules=rules)
    cases.append(("同规则多图 ⇒ 只报一条", len(h) == 1, h))

    # ⑹ 形状：必须是 REVIEW 口径（能与 review.py 的 findings 循环对上），且标了本层标记
    h = self_negative_hits([{"anchor": "#素材/recA/图片素材/#img.1", "source_sha256": "a" * 64,
                             "raw_bm25": 308.5}], rules=rules)
    need = ("article_no", "rule_id", "rule_code", "rule_text", "action", "evidence",
            "library_negative_sample", "matched_by")
    ok_shape = bool(h) and all(k in h[0] for k in need) and h[0]["library_negative_sample"] is True
    cases.append(("hit 形状齐（含 library_negative_sample）", ok_shape, h[:1]))

    # ⑺ 证据锚点必须回指**本素材命中的那个单元**（溯源要能落回 L2/L0）
    ok_anchor = bool(h) and (h[0]["evidence"][0]["anchor"] == "#素材/recA/图片素材/#img.1")
    cases.append(("evidence 锚点 = 命中单元锚点", ok_anchor, h[:1]))

    # ⑻ top 生效：一次最多报 top 条
    h = self_negative_hits([
        {"anchor": "#素材/recA/图片素材/#img.1", "source_sha256": "a" * 64},
        {"anchor": "#素材/recB/图片素材/#img.1", "source_sha256": "b" * 64},
    ], rules=rules, top=1)
    cases.append(("top=1 ⇒ 只报 1 条", len(h) == 1, h))

    # ── ⑼–⒁ 收窄层（「这条规则讲的是不是这张图」）───────────────────────────────
    #   夹具照抄真数据的形状：同一条记录 5 张图、规则正文写「图N」；
    #   另一条是跨 2 记录聚合的噪声规则。
    R = [
        {"article_no": "N-9.4", "rule_id": "r-fig4", "rule_text": "图4: 分屏图片",
         "record_ids": ["recA"],
         "image_refs": [{"file_token": "t1", "record_id": "recA", "seq": 1, "sha256": "1" * 64,
                         "anchor": "#素材/recA/图片素材/#img.1"},
                        {"file_token": "t2", "record_id": "recA", "seq": 2, "sha256": "2" * 64,
                         "anchor": "#素材/recA/图片素材/#img.2"},
                        {"file_token": "t4", "record_id": "recA", "seq": 4, "sha256": "4" * 64,
                         "anchor": "#素材/recA/图片素材/#img.4"}]},
        {"article_no": "N-9.1", "rule_id": "r-fig1", "rule_text": "图1: 不同族裔的妈妈们…",
         "record_ids": ["recA"],
         "image_refs": [{"file_token": "t1", "record_id": "recA", "seq": 1, "sha256": "1" * 64,
                         "anchor": "#素材/recA/图片素材/#img.1"},
                        {"file_token": "t4", "record_id": "recA", "seq": 4, "sha256": "4" * 64,
                         "anchor": "#素材/recA/图片素材/#img.4"}]},
        {"article_no": "N-9.0", "rule_id": "r-plain", "rule_text": "记录级意见：替换包装图",
         "record_ids": ["recA"],
         "image_refs": [{"file_token": "t4", "record_id": "recA", "seq": 4, "sha256": "4" * 64,
                         "anchor": "#素材/recA/图片素材/#img.4"}]},
        {"article_no": "N-9.9", "rule_id": "r-noise", "rule_text": "麻烦看看呀",
         "record_ids": ["recA", "recB", "recC"],
         "image_refs": [{"file_token": "x%d" % i, "record_id": "recX", "seq": 1,
                         "sha256": "%064x" % (100 + i), "anchor": "#素材/recX/图片素材/#img.1"}
                        for i in range(5)]},
    ]
    hits = [{"article_no": "N-9.4", "rule_id": "r-fig4"}, {"article_no": "N-9.1", "rule_id": "r-fig1"},
            {"article_no": "N-9.0", "rule_id": "r-plain"}, {"article_no": "N-9.9", "rule_id": "r-noise"}]
    kept, dropped = narrow_negative_hits(hits, rules=R, unit_shas={"4" * 64})
    names = [h["article_no"] for h in kept]
    dn = {d["article_no"]: d["why"] for d in dropped}

    # ⑼ 正例：讲「图4」、对上的就是 seq=4 ⇒ 保留（这张图的意见）
    cases.append(("图序号相符（图4 vs seq4）⇒ 保留", "N-9.4" in names, names))
    # ⑽ 反例：讲「图1」、实际对上 seq=4 ⇒ 必须丢（这就是 Owner 报的「别的图的问题」）
    cases.append(("图序号不符（图1 vs seq4）⇒ 丢弃", "N-9.1" in dn, dn))
    # ⑾ 正例：无图序号的记录级意见 ⇒ 保留（但表述为记录级）
    cases.append(("无图序号 ⇒ 保留且标 record",
                  "N-9.0" in names and [h.get("figure_attribution") for h in kept if h["article_no"] == "N-9.0"] == ["record"], kept))
    # ⑿ 反例：跨记录聚合的噪声规则 ⇒ 必须丢
    cases.append(("跨 3 条记录聚合 ⇒ 丢弃", "N-9.9" in dn, dn))
    # ⒀ 证据锚点改到**对上的那张图**（不是规则的第一张）
    ev = next((h.get("evidence") for h in kept if h["article_no"] == "N-9.4"), None)
    cases.append(("evidence 锚点 = 对上的那张（seq4）",
                  bool(ev) and ev[0].get("anchor") == "#素材/recA/图片素材/#img.4", ev))
    # ⒁ 对不上任何取证图 ⇒ 丢（不许硬认）
    kept2, dropped2 = narrow_negative_hits([{"article_no": "N-9.1", "rule_id": "r-fig1"}],
                                           rules=R, unit_shas={"9" * 64}, submitted_shas=set())
    cases.append(("对不上取证图 ⇒ 丢弃（不硬认）", not kept2 and bool(dropped2), dropped2))

    # ── ⒂–⒄ 第三轮：**跨记录规则但图级对上了**（2026-10-20 Owner「发图片命中不了」）──
    #   夹具照抄真数据：一条规则覆盖 recA(seq2)+recB(seq1)，正文没有「图N」；
    #   一条同样跨记录但正文写「图1」。两条都必须**先看图级锚定**再判。
    R2 = [
        {"article_no": "N-9.5", "rule_id": "r-cross", "rule_text": "建议：同房不同床，宝宝睡独立婴儿床",
         "record_ids": ["recA", "recB"],
         "image_refs": [{"file_token": "t1", "record_id": "recA", "seq": 2, "sha256": "5" * 64,
                         "anchor": "#素材/recA/图片素材/#img.2"},
                        {"file_token": "t2", "record_id": "recB", "seq": 1, "sha256": "6" * 64,
                         "anchor": "#素材/recB/图片素材/#img.1"}]},
        {"article_no": "N-9.6", "rule_id": "r-cross-fig", "rule_text": "图1: 不同族裔的妈妈们",
         "record_ids": ["recA", "recB"],
         "image_refs": [{"file_token": "t1", "record_id": "recA", "seq": 2, "sha256": "5" * 64,
                         "anchor": "#素材/recA/图片素材/#img.2"},
                        {"file_token": "t2", "record_id": "recB", "seq": 1, "sha256": "6" * 64,
                         "anchor": "#素材/recB/图片素材/#img.1"}]},
    ]
    kept3, dropped3 = narrow_negative_hits(
        [{"article_no": "N-9.5", "rule_id": "r-cross", "match_rank": 2,
          "matched_image": {"record_id": "recA", "seq": 2, "sha256": "5" * 64,
                            "anchor": "#素材/recA/图片素材/#img.2"}}],
        rules=R2, unit_shas=set(), submitted_shas=set())
    cases.append(("⒂ 跨记录规则但**图级对上**（matched_image 命中取证图）⇒ 保留",
                  bool(kept3) and kept3[0].get("figure_anchored") is True
                  and kept3[0].get("figure_matched_seq") == [2], (kept3, dropped3)))

    kept4, dropped4 = narrow_negative_hits(
        [{"article_no": "N-9.5", "rule_id": "r-cross"}],
        rules=R2, unit_shas=set(), submitted_shas=set())
    cases.append(("⒃ 反向对照：**去掉图级锚定**的同一条规则 ⇒ 仍丢（不许把口径放成恒真）",
                  (not kept4) and bool(dropped4) and "没对上" in dropped4[0]["why"], dropped4))

    kept5, dropped5 = narrow_negative_hits(
        [{"article_no": "N-9.6", "rule_id": "r-cross-fig", "match_rank": 2,
          "matched_image": {"record_id": "recA", "seq": 2, "sha256": "5" * 64}}],
        rules=R2, unit_shas=set(), submitted_shas=set())
    cases.append(("⒄ 图N 判据在锚定之后**仍生效**（讲图1 / 对上 seq2 ⇒ 丢）",
                  (not kept5) and any("别的图" in d["why"] for d in dropped5), dropped5))

    semantic = [{"article_no": "N-1.317", "record_id": "recA", "matched_by": "semantic",
                 "score": 0.82, "attribution": "record"}]
    exact = [{"article_no": "N-1.317", "record_id": "recA", "matched_by": "phash",
              "match_rank": 4, "attribution": "subject", "matched_image": {"seq": 1}}]
    merged, counts = merge_image_identity_hits(semantic, exact)
    cases.append(("身份命中覆盖同规则同记录的弱语义归属，且留审计字段",
                  len(merged) == 1 and merged[0].get("attribution") == "subject"
                  and merged[0].get("match_rank") == 4
                  and merged[0].get("semantic_match", {}).get("matched_by") == "semantic"
                  and counts == {"added": 0, "replaced": 1}, (merged, counts)))
    other_record = [{"article_no": "N-1.317", "record_id": "recB", "matched_by": "phash",
                     "attribution": "subject"}]
    merged2, counts2 = merge_image_identity_hits(semantic, other_record)
    cases.append(("同规则跨记录保留两条，不串图",
                  len(merged2) == 2 and counts2 == {"added": 1, "replaced": 0}
                  and merged2[0].get("record_id") == "recA"
                  and merged2[1].get("record_id") == "recB", (merged2, counts2)))

    bad = [c for c in cases if not c[1]]
    for name, ok, _ in cases:
        print(("  ✅ " if ok else "  ❌ ") + name)
    print("selftest %s（%d/%d）" % ("PASS" if not bad else "FAIL", len(cases) - len(bad), len(cases)))
    return 0 if not bad else 3


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return _selftest()
    if "--units-json" in argv:
        p = argv[argv.index("--units-json") + 1]
        rows = json.load(open(p, encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("top_bm25") or rows.get("units") or []
        hits = self_negative_hits(rows)
        print(json.dumps({"hits": hits, "n": len(hits)}, ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
