#!/usr/bin/env python3
"""Owner 硬规矩① · 自命中独立复算（RT-20261005-YOGA-03）。

口径（写死，可复算）：
  1) 扫 kb/l4/canonical 的**五个形态文件**（wording_entry / wording_revision_pair /
     sample_case / scoped_clause / clause），逐条取 polarity / semantics
     （字段可能在不同键名上，故做键名回退）。
  2) 筛「已定稿的反例/禁区」：polarity == '反例' 或 semantics 以「禁区」开头。
  3) 把这些条目的**全部字符串值**拼成候选文本，与本素材做**归一化后最长公共子串**（LCS）。
     归一化 = 小写 + 只留字母/数字/汉字（去空白与标点）。
  4) 按阈值 n ∈ {8,12,16,20,30} 报命中条数与最长片段。
输出 JSON + 人读摘要。
"""
import json, re, sys, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANON = ROOT / "kb/l4/canonical"
FORMS = ["wording_entry", "wording_revision_pair", "sample_case", "scoped_clause", "clause"]
MAT = (ROOT / "_rt-yoga-03-text.txt").read_text(encoding="utf-8")

def norm(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s.lower())

def get(d, *names):
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return None

def strings_of(obj, out, depth=0):
    if depth > 6:
        return
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("cite_check", "media_refs", "attachment_refs", "trace", "extra"):
                continue
            strings_of(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            strings_of(v, out, depth + 1)

MATN = norm(MAT)
idx = collections.defaultdict(list)
for i in range(len(MATN) - 7):
    idx[MATN[i:i+8]].append(i)

def lcs_vs(matn, candn):
    """返回 cand 中出现在 mat 里的最长公共子串（>=8），用 8-gram 索引加速。"""
    best = ""
    best_at = None
    n = len(candn)
    i = 0
    while i < n - 7:
        starts = idx.get(candn[i:i+8])
        if not starts:
            i += 1
            continue
        L = 8
        while i + L < n:
            sub = candn[i:i+L+1]
            if any(matn[s:s+L+1] == sub for s in starts[:200]):
                L += 1
            else:
                break
        if L > len(best):
            best = candn[i:i+L]
            best_at = i
        i += max(1, L - 7)
    return best, best_at

hits = []
all_sel = 0
for form in FORMS:
    p = CANON / (form + ".jsonl")
    if not p.exists():
        continue
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        pol = get(d, "polarity")
        sem = get(d, "semantics")
        if not (pol == "反例" or (isinstance(sem, str) and sem.startswith("禁区"))):
            continue
        all_sel += 1
        strs = []
        strings_of(d, strs)
        cand = norm("\n".join(strs))
        if len(cand) < 8:
            continue
        best, at = lcs_vs(MATN, cand)
        if best:
            hits.append({
                "form": form,
                "article_no": get(d, "article_no", "id"),
                "polarity": pol,
                "semantics": (sem or "")[:120],
                "anchor": get(d, "anchor"),
                "source_sha256": get(d, "source_sha256"),
                "lcs_len": len(best),
                "lcs": best[:120],
            })

hits.sort(key=lambda x: -x["lcs_len"])
buckets = {}
for n in (8, 12, 16, 20, 30):
    sub = [h for h in hits if h["lcs_len"] >= n]
    buckets[n] = sub

print("selected 反例/禁区 entries:", all_sel, "| with files scanned:",
      sum(1 for f in FORMS if (CANON / (f + ".jsonl")).exists()))
print("material sha256/bytes:", __import__("hashlib").sha256(MAT.encode()).hexdigest(), len(MAT.encode()))
for n in (8, 12, 16, 20, 30):
    print("--- n>=%d: %d entries" % (n, len(buckets[n])))
    for h in buckets[n][:12]:
        print("    %s %s lcs=%d %r  anchor=%s sha=%s" % (
            h["form"], h["article_no"], h["lcs_len"], h["lcs"][:60], h["anchor"],
            (h["source_sha256"] or "")[:16]))

out = {"material_sha256": __import__("hashlib").sha256(MAT.encode()).hexdigest(),
       "selected_total": all_sel,
       "thresholds": {str(n): len(v) for n, v in buckets.items()},
       "top_hits": hits[:40]}
(pathlib.Path(__file__).resolve().parent / "selfhit.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote selfhit.json")
