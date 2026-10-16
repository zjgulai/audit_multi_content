#!/usr/bin/env python3
# 自命中核查（规矩①）：本素材 vs 库内已定稿「反例/禁区」条款的规范化字符 n-gram 重叠。
# 判据：polarity=='反例' 或 semantics 以「禁区」开头。
import json, glob, os, re, unicodedata, pathlib
from collections import Counter

root = pathlib.Path(__file__).resolve().parent
text = (root / "yoga-text.txt").read_text(encoding="utf-8")

def norm(s):
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    return s

N = norm(text)
TEXT_FIELDS = ["reason_analysis", "sample_body", "advice", "semantics", "reason_category",
               "sample_body_clean", "正文", "text"]

rows = []
for f in glob.glob("kb/l4/canonical/*.jsonl"):
    if os.path.basename(f) == "rules.jsonl":
        continue
    for ln in open(f, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("polarity") == "反例" or str(r.get("semantics", "")).startswith("禁区"):
            rows.append(r)

print("反例/禁区条款数:", len(rows), file=os.sys.stderr)

def clause_text(r):
    parts = []
    for k in TEXT_FIELDS:
        v = r.get(k)
        if isinstance(v, str):
            parts.append(v)
    return "\n".join(parts)

def ngrams(s, n):
    return set(s[i:i+n] for i in range(len(s)-n+1))

text_ng = {n: ngrams(N, n) for n in (8, 12, 16, 20, 24)}

out = []
for r in rows:
    c = norm(clause_text(r))
    rec = {"article_no": r.get("article_no"), "form": r.get("form"),
           "polarity": r.get("polarity"), "semantics": r.get("semantics"),
           "material_type": r.get("material_type"), "valid_until": r.get("valid_until")}
    for n in (8, 12, 16, 20, 24):
        cg = ngrams(c, n)
        inter = text_ng[n] & cg
        rec["shared_%d" % n] = len(inter)
        if n in (16, 20) and inter:
            rec["sample_%d" % n] = sorted(inter)[:5]
    out.append(rec)

out.sort(key=lambda r: (-r["shared_16"], -r["shared_20"], -r["shared_12"]))
print(json.dumps({"matched_16": sum(1 for r in out if r["shared_16"] > 0),
                  "matched_12": sum(1 for r in out if r["shared_12"] > 0),
                  "top": out[:15]}, ensure_ascii=False, indent=1))

# 反向覆盖：素材里的中文长片段是否出现在任一 反例/禁区 条款里
allc = "\n".join(norm(clause_text(r)) for r in rows)
han = re.findall(r"[\u4e00-\u9fff]{18,}", N)
hits = [h for h in han if h in allc]
print("素材中 >=18 连续中文字片段:", len(han), "｜出现在反例/禁区条款里的:", len(hits), file=os.sys.stderr)
if hits:
    print("HITS:", hits[:20], file=os.sys.stderr)
