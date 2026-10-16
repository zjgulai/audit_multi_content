#!/usr/bin/env python3
"""Owner 硬规矩① · 自命中独立复算（RT-20261005-YOGA-02）。

口径（写死，可复算）：
  A 面 = canonical 五形态里 `polarity == '反例'` 或 `semantics` 以「禁区」开头的**已定稿**条目
         （`kb/l4/canonical/*.jsonl`；rules.jsonl 是 0 字节迁移留痕，不计）
  正文 = 该条的 `sample_body`（无则退 `reason_analysis` / `semantics`）
  B 面 = 本次送审素材冻结文本 `_rt-yoga-02-text.txt`
  两种归一：
    N1 字符级（激进）：小写 + 去掉所有非字母数字非 CJK → 抓「连写」型长片段
    N2 词级（保守）：小写 + 空白折叠为单空格 → 抓真实 n-gram
  对每个阈值 k 求最长公共子串（LCS，字符/词），逐条列出 条款号 + anchor + source_sha256 + 逐字片段。
"""
import json, re, sys, pathlib

root = pathlib.Path(__file__).resolve().parent.parent
MAT = (root / "_rt-yoga-02-text.txt").read_text(encoding="utf-8")

def n1(s):  # 字符级
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s.lower())
def n2(s):  # 词级
    return re.sub(r"\s+", " ", s.lower()).strip()

# ---- A 面 ----
cases = []
for line in open(root / "kb/l4/canonical/sample_case.jsonl", encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    if r.get("polarity") == "反例" or str(r.get("semantics") or "").startswith("禁区"):
        body = r.get("sample_body") or r.get("reason_analysis") or str(r.get("semantics") or "")
        cases.append({
            "article_no": r.get("article_no"), "case_id": r.get("case_id"),
            "polarity": r.get("polarity"), "semantics": r.get("semantics"),
            "anchor": r.get("anchor"), "source_sha256": r.get("source_sha256"),
            "material_type": r.get("material_type"), "channel": r.get("channel"),
            "status": r.get("status"), "valid_until": r.get("valid_until"),
            "body": body,
        })

def lcs_blocks(a, b, k):
    """返回 a 与 b 之间所有长度 >= k 的极大公共子串（去重）。"""
    out = set()
    if len(a) < k or len(b) < k:
        return out
    grams = {}
    for i in range(len(a) - k + 1):
        grams.setdefault(a[i:i+k], []).append(i)
    for j in range(len(b) - k + 1):
        g = b[j:j+k]
        if g in grams:
            for i in grams[g]:
                # 向左向右扩到极大
                s, t = i, j
                while s > 0 and t > 0 and a[s-1] == b[t-1]:
                    s -= 1; t -= 1
                e, f = i + k, j + k
                while e < len(a) and f < len(b) and a[e] == b[f]:
                    e += 1; f += 1
                out.add(a[s:e])
    return out

report = {"material_sha256": __import__("hashlib").sha256(
              (root / "_rt-yoga-02-text.txt").read_bytes()).hexdigest(),
          "clause_count": len(cases), "thresholds": {}}

for k in (8, 12, 16, 20):
    hits = []
    for c in cases:
        for mode, fn in (("N1-chars", n1), ("N2-words", n2)):
            blocks = lcs_blocks(fn(c["body"]), fn(MAT), k)
            for blk in blocks:
                hits.append({"article_no": c["article_no"], "case_id": c["case_id"],
                             "polarity": c["polarity"], "semantics": c["semantics"],
                             "anchor": c["anchor"], "source_sha256": c["source_sha256"],
                             "material_type": c["material_type"], "mode": mode,
                             "len": len(blk), "fragment": blk[:120]})
    hits.sort(key=lambda h: -h["len"])
    report["thresholds"][str(k)] = {"count": len(hits), "top": hits[:8]}

print(json.dumps(report, ensure_ascii=False, indent=2))
(root / "_rt-yoga-02-selfhit.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
