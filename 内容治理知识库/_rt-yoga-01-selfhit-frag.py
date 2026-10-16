#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补：把 _rt-yoga-01-selfhit.py 的 LCS **片段本体**打出来（判「是不是噪声」必须看片段，不能只看长度）。"""
import json, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANON = ROOT / "kb" / "l4" / "canonical"
FORMS = ["sample_case.jsonl"]
TEXT_FIELD_CANDIDATES = ["sample_body", "text", "raw_text", "body", "content",
                         "original", "before", "source_text", "statement"]


def norm_cjk(s):
    s = unicodedata.normalize("NFKC", s).casefold()
    return "".join(ch for ch in s if ch.isalnum())


def lcs_fragment(a, b):
    """返回 (长度, 片段)：经典 DP 太慢，用「按长度二分 + 定位」两步。"""
    lo, hi = 0, min(len(a), len(b))
    best = ""
    while lo <= hi:
        L = (lo + hi) // 2
        found = None
        grams = {b[i:i + L]: i for i in range(max(0, len(b) - L + 1))}
        for i in range(max(0, len(a) - L + 1)):
            if a[i:i + L] in grams:
                found = a[i:i + L]
                break
        if found is not None:
            best = found
            lo = L + 1
        else:
            hi = L - 1
    return len(best), best


def field_text(rec):
    for f in TEXT_FIELD_CANDIDATES:
        v = rec.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return ""


material = (ROOT / "_rt-yoga-01-text.txt").read_text(encoding="utf-8")
m = norm_cjk(material)
out = []
for line in (CANON / "sample_case.jsonl").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    rec = json.loads(line)
    if not ((rec.get("polarity") == "反例") or (rec.get("semantics") or "").startswith("禁区")):
        continue
    txt = field_text(rec)
    if not txt:
        continue
    n = norm_cjk(txt)
    L, frag = lcs_fragment(n, m)
    if L >= 10:
        out.append({"article_no": rec.get("article_no"), "lcs": L, "fragment": frag,
                    "anchor": rec.get("anchor"), "source_sha256": rec.get("source_sha256")})
out.sort(key=lambda x: -x["lcs"])
res = {"schema": "rt-yoga-01-selfhit-fragments/1", "threshold": 10, "count": len(out), "hits": out}
(ROOT / "_rt-yoga-01-selfhit-fragments.json").write_text(
    json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
for h in out:
    print("%-8s LCS=%-3d %s" % (h["article_no"], h["lcs"], h["fragment"]))
