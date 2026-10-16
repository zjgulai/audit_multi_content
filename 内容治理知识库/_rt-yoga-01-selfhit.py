#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Owner 规矩① 独立复算：本素材 vs canonical 已定稿「反例 / 禁区」条款的自命中扫描。

判据（照 Owner 2026-10-05 现场口径）：
  · 对象 = kb/l4/canonical/ 五形态里 polarity == "反例" 或 semantics 以「禁区」开头的条目；
  · 比对面 = 本素材归一化文本 vs 条目的**逐字原文**（sample_body / text / 对应正文字段）；
  · 指标 = 最长共同片段（LCS，归一化后按字符）；
  · 归一化给出两套口径：cjk（保留中日韩+字母数字）与 ascii（只留 a-z0-9，供与上一单口径对比）。
输出：JSON，含每套口径的 top-N 与阈值计数。只读，不写库。
"""
import json, re, sys, unicodedata, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANON = ROOT / "kb" / "l4" / "canonical"
FORMS = ["wording_entry.jsonl", "wording_revision_pair.jsonl", "sample_case.jsonl",
         "scoped_clause.jsonl", "clause.jsonl"]
TEXT_FIELD_CANDIDATES = ["sample_body", "text", "raw_text", "body", "content",
                         "original", "before", "source_text", "statement"]


def norm_cjk(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return "".join(ch for ch in s if ch.isalnum())


def norm_ascii(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return "".join(ch for ch in s if ("a" <= ch <= "z") or ("0" <= ch <= "9"))


def lcs_len(a: str, b: str, b_ngrams_cache: dict) -> int:
    """最长共同子串长度：对 a 的每个长度做二分，判 a 的某 L-子串是否出现在 b 中。"""
    if not a or not b:
        return 0
    lo, hi = 0, min(len(a), len(b))
    blen = len(b)

    def has(L):
        if L in b_ngrams_cache:
            grams = b_ngrams_cache[L]
        else:
            grams = {b[i:i + L] for i in range(blen - L + 1)}
            b_ngrams_cache[L] = grams
        for i in range(len(a) - L + 1):
            if a[i:i + L] in grams:
                return True
        return False

    while lo < hi:
        mid = (lo + hi + 1) // 2
        if has(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


def field_text(rec: dict) -> str:
    for f in TEXT_FIELD_CANDIDATES:
        v = rec.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def main():
    material = (ROOT / "_rt-yoga-01-text.txt").read_text(encoding="utf-8")
    m_cjk, m_ascii = norm_cjk(material), norm_ascii(material)

    stats = {}
    hits = []
    scanned = 0
    for form in FORMS:
        p = CANON / form
        if not p.exists():
            stats[form] = {"file": "MISSING", "total": 0, "forbidden": 0}
            continue
        total = forb = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            total += 1
            pol = rec.get("polarity") or ""
            sem = rec.get("semantics") or ""
            if not (pol == "反例" or sem.startswith("禁区")):
                continue
            forb += 1
            scanned += 1
            txt = field_text(rec)
            if not txt:
                continue
            t_cjk, t_ascii = norm_cjk(txt), norm_ascii(txt)
            lc = lcs_len(t_cjk, m_cjk, {})
            la = lcs_len(t_ascii, m_ascii, {})
            hits.append({
                "form": form,
                "article_no": rec.get("article_no"),
                "polarity": pol,
                "semantics": sem,
                "material_type": rec.get("material_type"),
                "reason_category": rec.get("reason_category"),
                "channel": rec.get("channel"),
                "anchor": rec.get("anchor"),
                "source_sha256": rec.get("source_sha256"),
                "text_len": len(txt),
                "lcs_cjk": lc,
                "lcs_ascii": la,
                "anchor_note": "anchor 指向飞书源记录；本脚本只读 L4，不点飞书直链",
                "text_head": txt[:120].replace("\n", " "),
            })
        stats[form] = {"total": total, "forbidden": forb}

    def summarize(key):
        hs = sorted(hits, key=lambda h: -h[key])
        out = []
        for h in hs[:10]:
            out.append({k: h[k] for k in ("form", "article_no", "polarity", "semantics",
                                          "material_type", "reason_category", "anchor",
                                          "source_sha256", "text_len", key, "text_head")})
        return out

    res = {
        "schema": "rt-yoga-01-selfhit-check/1",
        "material_file": "_rt-yoga-01-text.txt",
        "material_len_chars": len(material),
        "material_norm_len_cjk": len(m_cjk),
        "material_norm_len_ascii": len(m_ascii),
        "method": "canonical 五形态逐条筛 polarity=反例 或 semantics 以「禁区」开头；"
                  "归一化后与本素材算最长共同子串（二分 + 子串集）",
        "canonical_form_counts": stats,
        "forbidden_clauses_scanned": scanned,
        "count_lcs_cjk_ge12": sum(1 for h in hits if h["lcs_cjk"] >= 12),
        "count_lcs_cjk_ge16": sum(1 for h in hits if h["lcs_cjk"] >= 16),
        "count_lcs_cjk_ge20": sum(1 for h in hits if h["lcs_cjk"] >= 20),
        "count_lcs_ascii_ge12": sum(1 for h in hits if h["lcs_ascii"] >= 12),
        "max_lcs_cjk": max([h["lcs_cjk"] for h in hits], default=0),
        "max_lcs_ascii": max([h["lcs_ascii"] for h in hits], default=0),
        "top10_by_lcs_cjk": summarize("lcs_cjk"),
        "top10_by_lcs_ascii": summarize("lcs_ascii"),
    }
    (ROOT / "_rt-yoga-01-selfhit.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in
                      ("forbidden_clauses_scanned", "count_lcs_cjk_ge12", "count_lcs_cjk_ge16",
                       "count_lcs_cjk_ge20", "max_lcs_cjk", "max_lcs_ascii")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
