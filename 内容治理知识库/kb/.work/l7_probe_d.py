#!/usr/bin/env python3
"""L7 自验 D：规避型（字面不同、语义相近）查询 × 三模式对比。
- bm25_only：L6 倒排原始分
- vector_only：L6 向量余弦
- 加权融合：min-max 归一后的加权和（自己算，不改 kb/l6）
只读 kb/l6 索引，不写 kb/l6。
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
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

import importlib.util, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
spec = importlib.util.spec_from_file_location("l6r", "kb/l6/retriever.py")
RT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RT)

QUERIES = [
    "最佳、第一名这种说法有问题吗",
    "说能帮妈妈通乳算不算踩线",
    "能不能说产品是医院同款",
    "医生都说推荐这个牌子，可以这么写吗",
    "讲吸奶完全不疼会不会有问题",
]

bm, vec = RT.BM25(), RT.Vectors()
out = []
for q in QUERIES:
    # bm25_only
    lists = bm.search(q)
    bm_rows = []
    for name, lst in lists.items():
        for did, sc, _ in lst[:10]:
            d = bm.docs[did]
            bm_rows.append({"unit_id": d["unit_id"], "anchor": d["anchor"], "table": d["table"],
                            "raw_bm25": round(sc, 4), "excerpt": d["text_excerpt"][:160],
                            "kb_type": d["kb_type"], "source_sha256": d["source_sha256"]})
    bm_rows.sort(key=lambda x: -x["raw_bm25"])
    # 同一单元只留最高
    seen, bm_top = set(), []
    for r in bm_rows:
        if r["unit_id"] in seen:
            continue
        seen.add(r["unit_id"])
        bm_top.append(r)
    bm_top = bm_top[:3]
    # vector_only
    v_rows = []
    for did, sc, extra in vec.search(q, top=3):
        d = bm.docs[did]
        v_rows.append({"unit_id": d["unit_id"], "anchor": d["anchor"], "table": d["table"],
                       "cosine": round(sc, 4), "excerpt": d["text_excerpt"][:160],
                       "kb_type": d["kb_type"], "source_sha256": d["source_sha256"],
                       "segment_index": extra.get("segment_index")})
    # 加权融合（min-max 归一）
    pool, meta = {}, {}
    for r in bm_rows:                      # 所有 BM25 命中（含未进 Top3 的）都进池
        pool[r["unit_id"]] = {"bm": r["raw_bm25"], "vec": 0.0}
        meta[r["unit_id"]] = r
    for r in v_rows:
        pool.setdefault(r["unit_id"], {"bm": 0.0, "vec": 0.0})["vec"] = r["cosine"]
        meta.setdefault(r["unit_id"], r)
    for lst in lists.values():
        for did, sc, _ in lst:
            d = bm.docs[did]
            u = d["unit_id"]
            if u not in pool:
                pool[u] = {"bm": 0.0, "vec": 0.0}
                meta[u] = {"unit_id": u, "anchor": d["anchor"], "table": d["table"],
                           "excerpt": d["text_excerpt"][:160]}
            pool[u]["bm"] = max(pool[u]["bm"], sc)
    def fuse(w_bm, w_vec):
        bms = [v["bm"] for v in pool.values()] or [0]
        mn, mx = min(bms), max(bms)
        rows = []
        for uid, v in pool.items():
            nb = (v["bm"] - mn) / (mx - mn) if mx > mn else 0.0
            score = w_bm * nb + w_vec * v["vec"]
            src = meta[uid]
            rows.append({"unit_id": uid, "score": round(score, 4), "bm25": round(v["bm"], 3),
                         "cosine": round(v["vec"], 4), "anchor": src["anchor"], "table": src["table"],
                         "excerpt": src["excerpt"]})
        rows.sort(key=lambda x: (-x["score"], x["unit_id"]))
        return rows[:3]
    out.append({"query": q,
                "bm25_only": bm_top,
                "vector_only": v_rows,
                "fuse_0.7_0.3": fuse(0.7, 0.3),
                "fuse_0.5_0.5": fuse(0.5, 0.5)})
json.dump(out, open("kb/.work/l7_probe_d.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for r in out:
    print("=" * 90)
    print("查询:", r["query"])
    for mode in ("bm25_only", "vector_only", "fuse_0.7_0.3"):
        print(f"  --- {mode}")
        for i, x in enumerate(r[mode], 1):
            sc = x.get("score", x.get("raw_bm25", x.get("cosine")))
            print(f"    #{i} {sc:>8}  {x['anchor'][:52]}")
            print(f"         {x['excerpt'][:100]}")
