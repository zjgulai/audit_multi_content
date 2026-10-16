# 只读探针：复取 L6 BM25 原始分与完整 sha256（不写索引、不写库）
# 用法：sh kb/kbpy _probe/l6-top10-raw-20261004.py
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "kb", "l6"))
import retriever as R  # noqa: E402

QUERY = "婴幼儿睡眠安全"

bm = R.BM25()
raw = R.tokenize(QUERY)
print("tokenize ->", raw)

# docs.jsonl 顺序即 doc_id，按行号取
docs = bm.docs
print("docs_total ->", len(docs))
print("built_at ->", bm.meta.get("built_at"), "run ->", bm.meta.get("run_id"),
      "tokenizer ->", bm.meta.get("tokenizer_version"),
      "N_zh ->", bm.meta.get("N_zh"))

# 复取原始分：中文侧
terms_zh = raw[0] if isinstance(raw, tuple) else raw
scored = bm.search_lang(terms_zh, "zh", None)
print("zh cand count ->", len(scored))
rows = []
for rank, (did, score) in enumerate(scored[:15], 1):
    d = docs[did]
    rows.append({
        "rank": rank, "doc_id": did, "unit_id": d["unit_id"], "bm25_raw": round(float(score), 4),
        "kb_type": d["kb_type"], "anchor": d["anchor"], "source_sha256": d["source_sha256"],
        "table": d.get("table"), "char_len": d.get("char_len"),
        "heading_path": d.get("heading_path"),
        "excerpt": (d.get("text_excerpt") or "")[:70].replace("\n", " "),
    })
    print(rank, d["unit_id"], round(float(score), 4), d["kb_type"], d["anchor"],
          d["source_sha256"])
out = os.path.join(ROOT, "_probe", "l6-bm25-raw-20261004.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"query": QUERY, "mode": "bm25_only", "rows": rows}, fh,
              ensure_ascii=False, indent=2)
print("wrote", out)
