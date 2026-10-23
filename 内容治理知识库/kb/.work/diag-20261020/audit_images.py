#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片路径普查（只读）—— 量化「库内图片类负面样本能不能被命中」这一类问题。

产出六块：
  A. 图片规模与 OCR 状态
  B. L2「图内文字」单元 → L4 条款的引用率
  C. 反面案例的判定类型（画面类 / 文字类）
  D. ★ 题材闸门自检：拿**每条案例自己那条记录的图内文字**当素材，闸门能过吗
  E. 语言分布（英文 / 中文 / 混排）—— 决定文字路径是否可能
  F. 同图多记录

用法：python3 kb/.work/diag-20261020/audit_images.py
  ⚠️ 只读；不写任何库文件。
"""
import glob
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
KEEP = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")


def jload(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def jlines(p):
    out = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_case_theme():
    p = os.path.join(ROOT, "kb/l7/review-engine/core/case_theme.py")
    spec = importlib.util.spec_from_file_location("case_theme_audit", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def lang_of(s):
    """按字面判断：中文 / 英文 / 混排。"""
    s = str(s or "")
    c, e = len(CJK.findall(s)), len(LATIN_WORD.findall(s))
    if c and e:
        return "中英混排"
    if c:
        return "中文"
    if e:
        return "英文"
    return "无字"


def main():
    print("=" * 78)
    print("图片路径普查（只读） ", os.path.basename(ROOT))
    print("=" * 78)

    # ── A. 图片规模与 OCR 状态 ────────────────────────────────────────────
    media_dirs = [d for d in glob.glob(os.path.join(ROOT, "kb/l1/media/*")) if os.path.isdir(d)]
    img_status = Counter()
    img_total = 0
    img_empty_ocr = 0
    recs_with_media = 0
    for d in media_dirs:
        p = os.path.join(d, "ocr.json")
        if not os.path.exists(p):
            continue
        recs_with_media += 1
        try:
            doc = jload(p)
        except Exception:
            img_status["ocr.json坏"] += 1
            continue
        for im in (doc.get("images") or []):
            img_total += 1
            st = str(im.get("status") or "未标")
            img_status[st] += 1
    print("\n=== A. 图片规模与 OCR 状态 ===")
    print(f"  L1 media 记录目录：{recs_with_media}（目录 {len(media_dirs)}）｜图片条目：{img_total}")
    print(f"  状态分布：{dict(img_status)}")

    # ── B. L2 图内文字单元 → L4 引用率 ────────────────────────────────────
    units = jlines(os.path.join(ROOT, "kb/l2/units.jsonl"))
    ocr_units = [u for u in units if "[image_ocr]" in str(u.get("text") or "")]
    l4_anchors = set()
    l4_files = ["sample_case", "scoped_clause", "wording_entry", "wording_revision_pair"]
    for f in l4_files:
        for d in jlines(os.path.join(ROOT, f"kb/l4/canonical/{f}.jsonl")):
            if d.get("anchor"):
                l4_anchors.add(d["anchor"])
    ocr_anchor_set = {u["anchor"] for u in ocr_units}
    print("\n=== B. L2「图内文字」单元 → L4 条款 ===")
    print(f"  L2 单元总数 {len(units)}｜含 [image_ocr] 的 {len(ocr_units)}（独立 anchor {len(ocr_anchor_set)}）")
    print(f"  L4 条款 anchor 池 {len(l4_anchors)}")
    print(f"  ★ 被 L4 条款直接引用的图内文字单元：{len(ocr_anchor_set & l4_anchors)}")

    # resource_id -> OCR 文本
    ocr_by_res = defaultdict(str)
    for u in units:
        if "[image_ocr]" not in str(u.get("text") or ""):
            continue
        rid = u.get("resource_id") or ""
        ocr_by_res[rid] += "\n" + str(u.get("text") or "")
        # 同时按 anchor 里的记录 id 建一份（resource_id 写法可能不同）
        m = re.search(r"#素材/([^/]+)/", str(u.get("anchor") or ""))
        if m:
            ocr_by_res["rec:" + m.group(1)] += "\n" + str(u.get("text") or "")

    # ── C/D. 反面案例：判定类型 + 题材闸门自检 ────────────────────────────
    cases = jlines(os.path.join(ROOT, "kb/l4/canonical/sample_case.jsonl"))
    rev = [c for c in cases if c.get("polarity") == "反例"]

    VISUAL = ("画面", "场景", "构图", "视觉", "照片", "图片", "排版", "字体", "字号", "颜色", "色调",
              "人物", "模特", "出镜", "背景", "元素", "logo", "Logo", "LOGO", "构图", "实拍")
    TEXTUAL = ("文案", "表述", "字样", "拼写", "大写", "小写", "措辞", "用语", "说法", "标题", "错别字")

    ct = load_case_theme()
    rows = []
    for c in rev:
        rid = str(c.get("resource_id") or "")
        rec = ""
        m = re.search(r"(rec[a-zA-Z0-9]+)", rid)
        if m:
            rec = m.group(1)
        ocr = (ocr_by_res.get(rid) or ocr_by_res.get("rec:" + rec) or "").strip()
        judged = str(c.get("reason_analysis") or "") + " " + str(c.get("sample_body") or "")
        v = sum(1 for k in VISUAL if k in judged)
        t = sum(1 for k in TEXTUAL if k in judged)
        kind = "画面类" if v > t else ("文字类" if t > v else "未定")
        ok, why = (None, "无图内文字")
        if ocr:
            ok, why = ct.case_thematic_ok(c, ocr)
        rows.append({"no": c.get("article_no"), "kind": kind, "has_ocr": bool(ocr),
                     "gate_ok": ok, "why": why, "ocr_lang": lang_of(ocr)})

    has_ocr = [r for r in rows if r["has_ocr"]]
    gate_pass = [r for r in has_ocr if r["gate_ok"] is True]
    print("\n=== C. 反面案例判定类型 ===")
    print(f"  反例 {len(rev)} 条｜有关联图内文字的 {len(has_ocr)} 条｜无图/无字 {len(rows)-len(has_ocr)} 条")
    print(f"  判定类型：{dict(Counter(r['kind'] for r in rows))}")
    print(f"  其中「有图内文字」那批的判定类型：{dict(Counter(r['kind'] for r in has_ocr))}")

    print("\n=== D. ★ 题材闸门自检（素材 = 该案例自己那条记录的图内文字）===")
    print(f"  能过闸门的：{len(gate_pass)} / {len(has_ocr)}"
          f"  ⇒ 通过率 {len(gate_pass)/max(1,len(has_ocr)):.1%}")
    print(f"  被挡下的理由分布：{dict(Counter(r['why'] for r in has_ocr if not r['gate_ok']))}")
    print(f"  图内文字语言分布：{dict(Counter(r['ocr_lang'] for r in has_ocr))}")

    # ── E. 按语言看闸门通过率 ────────────────────────────────────────────
    print("\n=== E. 闸门通过率 × 素材语言 ===")
    by_lang = defaultdict(lambda: [0, 0])
    for r in has_ocr:
        by_lang[r["ocr_lang"]][1] += 1
        if r["gate_ok"]:
            by_lang[r["ocr_lang"]][0] += 1
    for lang, (ok, tot) in sorted(by_lang.items(), key=lambda x: -x[1][1]):
        print(f"  {lang:<8} 通过 {ok}/{tot}  ({ok/tot:.0%})")

    # ── F. 同图多记录 ────────────────────────────────────────────────────
    sha_recs = defaultdict(set)
    for d in media_dirs:
        p = os.path.join(d, "ocr.json")
        if not os.path.exists(p):
            continue
        try:
            doc = jload(p)
        except Exception:
            continue
        rid = doc.get("record_id") or os.path.basename(d)
        for im in (doc.get("images") or []):
            if im.get("sha256"):
                sha_recs[im["sha256"]].add(rid)
    dup = {k: v for k, v in sha_recs.items() if len(v) > 1}
    print("\n=== F. 同一张图出现在多条记录 ===")
    print(f"  不同图 sha {len(sha_recs)}｜跨 ≥2 条记录的 {len(dup)}｜"
          f"涉及记录 {len(set().union(*dup.values())) if dup else 0}")
    top = sorted(dup.items(), key=lambda x: -len(x[1]))[:5]
    for sha, recs in top:
        print(f"  {sha[:12]}…  {len(recs)} 条：{sorted(recs)[:6]}")

    # ── 收口：这批案例里，被判「画面类」且闸门过不了的 ──────────────────
    worst = [r for r in has_ocr if r["kind"] == "画面类" and not r["gate_ok"]]
    print("\n=== 结论 ===")
    print(f"  画面类判定 + 有图内文字 + 闸门过不了：{len(worst)} 条")
    print(f"  样例：{[(r['no'], r['ocr_lang']) for r in worst[:8]]}")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_images.out.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows,
                   "A": {"recs_with_media": recs_with_media, "images": img_total,
                         "status": dict(img_status)},
                   "B": {"l2_units": len(units), "ocr_units": len(ocr_units),
                         "ocr_anchors": len(ocr_anchor_set),
                         "cited_by_l4": len(ocr_anchor_set & l4_anchors)},
                   "D": {"gate_pass": len(gate_pass), "denom": len(has_ocr)},
                   "F": {"distinct_sha": len(sha_recs), "dup_sha": len(dup)}},
                  fh, ensure_ascii=False, indent=1)
    print(f"\n明细已落：{out}")


if __name__ == "__main__":
    sys.exit(main())
