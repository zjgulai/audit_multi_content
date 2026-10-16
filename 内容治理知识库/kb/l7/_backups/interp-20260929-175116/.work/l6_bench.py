#!/usr/bin/env python3
"""L6 性能实测：纯 Python 自实现倒排的查询耗时（含单元数），与 L5 关键词匹配的量级对照。
产出 kb/l6/benchmark.json。只读索引，不写索引文件。
"""
import importlib.util, json, os, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
L6 = "kb/l6"
spec = importlib.util.spec_from_file_location("l6_retriever", f"{L6}/retriever.py")
RT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RT)

QUERIES = [   # 10 中 + 10 英，含单词条与多条
    "宣称疗效的表述", "催奶增产", "医生推荐", "无痛吸奶", "静音承诺",
    "绝对安全", "模仿婴儿吸吮", "医院级", "FDA", "排名第一",
    "FDA approved claims", "best-selling", "more milk supply", "hospital grade pump",
    "pain-free pumping", "boosts milk supply", "clinically proven", "one size fits all",
    "doctor recommended", "whisper quiet",
]
L5_TEXT_1MB = {"bytes": 1035.8 * 1024, "lines": 3712, "elapsed_ms": 631.605,
               "source": "kb/l5/benchmark.json（L5 P0 匹配器：6 条 P0 规则 / 79 关键词 / 16 正则，逐行扫全文）"}

out = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "units": None, "bm25": {}, "vector": {}, "hybrid": {}}

t0 = time.perf_counter()
bm = RT.BM25()
out["bm25"]["load_ms"] = round((time.perf_counter() - t0) * 1000, 1)
out["units"] = len(bm.docs)
out["bm25"]["docs"] = len(bm.docs)
out["bm25"]["terms"] = {"zh": len(bm.post["zh"]), "en": len(bm.post["en"])}
out["bm25"]["avgdl"] = {"zh": bm.meta["avgdl_zh"], "en": bm.meta["avgdl_en"]}
out["bm25"]["implementation"] = RT.BM25.algorithm

# ---- 单查询耗时（BM25）
lat, scanned = [], []
for q in QUERIES:
    zh, en = RT.tokenize(q)
    terms = [(t, "zh") for t in zh] + [(t, "en") for t in en]
    n = sum(bm.post[lg].get(t, {}).get("df", 0) for t, lg in terms)
    for _ in range(5):
        t0 = time.perf_counter()
        bm.search(q)
        lat.append((time.perf_counter() - t0) * 1000)
    scanned.append({"query": q, "terms": len(terms), "postings_scanned": n})
s = sorted(lat)
out["bm25"]["query_latency_ms"] = {
    "queries": len(QUERIES), "runs_per_query": 5, "samples": len(s),
    "min": round(s[0], 3), "p50": round(statistics.median(s), 3),
    "p95": round(s[int(len(s) * 0.95) - 1], 3), "max": round(s[-1], 3),
    "mean": round(statistics.mean(s), 3),
}
out["bm25"]["throughput_qps"] = round(1000 / statistics.median(s), 1)
out["bm25"]["postings_scanned"] = {
    "mean": round(statistics.mean(x["postings_scanned"] for x in scanned), 1),
    "max": max(x["postings_scanned"] for x in scanned),
    "detail": sorted(scanned, key=lambda x: -x["postings_scanned"])[:5],
}
# ---- 单/多词条对照
single = [q for q in QUERIES if len(sum(RT.tokenize(q), [])) == 1]
multi = [q for q in QUERIES if len(sum(RT.tokenize(q), [])) >= 3]
def med(qs):
    xs = []
    for q in qs:
        for _ in range(5):
            t0 = time.perf_counter(); bm.search(q); xs.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(xs), 3) if xs else None
out["bm25"]["by_term_count"] = {"1_term_p50_ms": med(single), "3plus_terms_p50_ms": med(multi),
                                "n_single": len(single), "n_multi": len(multi)}

# ---- 向量与 hybrid
vec = RT.Vectors()
for name, mode in (("vector", "vector_only"), ("hybrid", "hybrid")):
    xs = []
    for q in QUERIES[:8]:
        for _ in range(3):
            t0 = time.perf_counter(); RT.search(q, top=5, mode=mode, bm25=bm, vec=vec)
            xs.append((time.perf_counter() - t0) * 1000)
    out[name] = {"queries": 8, "runs_per_query": 3, "p50_ms": round(statistics.median(xs), 3),
                 "max_ms": round(max(xs), 3), "min_ms": round(min(xs), 3)}
# 冷启动（模型加载，只付一次）
v2 = RT.Vectors()
t0 = time.perf_counter(); v2._load_model(); out["vector"]["cold_load_ms"] = round((time.perf_counter() - t0) * 1000, 1)

# ---- 与 L5 对照
p50 = out["bm25"]["query_latency_ms"]["p50"]
out["compare_with_l5"] = {
    "L5": L5_TEXT_1MB,
    "L5_per_KB_ms": round(L5_TEXT_1MB["elapsed_ms"] / (L5_TEXT_1MB["bytes"] / 1024), 3),
    "bm25_p50_ms": p50,
    "bm25_equivalent_text_KB": round(p50 / (L5_TEXT_1MB["elapsed_ms"] / (L5_TEXT_1MB["bytes"] / 1024)), 2),
    "verdict": (f"BM25 单查询中位 {p50} ms；L5 扫 1MB 是 {L5_TEXT_1MB['elapsed_ms']} ms"
                f"（约 {round(L5_TEXT_1MB['elapsed_ms'] / p50)} 倍）。自实现倒排不是瓶颈，"
                "本批不需要换实现或换库（jieba / rank_bm25 未安装，也未因此缺能力）。"),
}
json.dump(out, open(f"{L6}/benchmark.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"单元数 {out['units']}｜BM25 词表 zh {out['bm25']['terms']['zh']} / en {out['bm25']['terms']['en']}"
      f"｜索引加载 {out['bm25']['load_ms']} ms")
q = out["bm25"]["query_latency_ms"]
print(f"BM25 查询（{q['queries']} 条 × {q['runs_per_query']} 次）：p50 {q['p50']} ms｜p95 {q['p95']} ms｜"
      f"max {q['max']} ms｜吞吐 {out['bm25']['throughput_qps']} q/s")
print(f"  单词条 p50 {out['bm25']['by_term_count']['1_term_p50_ms']} ms｜"
      f"3+ 词条 p50 {out['bm25']['by_term_count']['3plus_terms_p50_ms']} ms｜"
      f"平均扫描倒排项 {out['bm25']['postings_scanned']['mean']}")
print(f"向量 p50 {out['vector']['p50_ms']} ms（冷启动加载模型 {out['vector']['cold_load_ms']} ms）｜"
      f"hybrid p50 {out['hybrid']['p50_ms']} ms")
print(f"对照 L5：{out['compare_with_l5']['verdict']}")
