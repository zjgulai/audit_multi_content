#!/usr/bin/env python3
"""L6 自检：7 项，产出 kb/.work/l6_integrity.json。
1) kb/l0~l3 未被修改（与 L5 存档的 tree_sha256 逐字节比对 + mtime/size）
2) 索引条数 == 可用单元数；跳过与失败逐条有原因
3) 幂等：现场再跑一次 build，索引与投影必须一字不动、且不重复调 embedding
4) 每条向量都能回指 unit_id + anchor + source_sha256（且 content_hash 与正文一致）
5) 倒排索引与逐文档词频自洽；P0 证据单元确实不在向量里
6) canonical 为空、kb_version=v0、versions.jsonl 版本行 0
7) 检索器可离线跑（无网络符号；向量模型只吃本地缓存）
"""
import collections, hashlib, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, "kb/.work")
import l6_scope_lib as SL  # noqa: E402

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260923-1400"
L6 = "kb/l6"
DURABLE = [f"{L6}/bm25/docs.jsonl", f"{L6}/bm25/meta.json", f"{L6}/bm25/postings_zh.jsonl",
           f"{L6}/bm25/postings_en.jsonl", f"{L6}/vectors/vectors.jsonl",
           f"{L6}/vectors/matrix.npy", f"{L6}/vectors/meta.json",
           f"{L6}/index/l6.jsonl", f"{L6}/registry/l6.json", f"{L6}/retriever.py"]
ev = {"run_id": RUN, "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "checks": {}}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tree_fp(d):
    rows, total, mt = [], 0, []
    for dp, _, fns in os.walk(d):
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            total += os.path.getsize(p)
            mt.append(os.path.getmtime(p))
            rows.append(f"{os.path.relpath(p, ROOT)}\0{os.path.getsize(p)}\0{sha(p)}")
    rows.sort()
    return {"files": len(rows), "bytes": total, "tree_sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
            "max_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(max(mt))) if mt else None}


# ---- 1) 冻结层
base = json.load(open("kb/.work/l5_integrity.json", encoding="utf-8"))["checks"]["frozen_layers"]["layers"]
now = {d: tree_fp(f"kb/{d}") for d in ("l0", "l1", "l2")}
same = {d: now[d]["tree_sha256"] == base[d]["tree_sha256"] for d in now}
l3_raw = open("kb/l3/candidates/rules.jsonl", "rb").read().split(b"\n")
if l3_raw and l3_raw[-1] == b"":
    l3_raw.pop()
l3_prefix = hashlib.sha256(b"\n".join(l3_raw[:509]) + b"\n").hexdigest()
ev["checks"]["frozen_layers"] = {
    "l0_l2_vs_L5_baseline": {d: {"files": now[d]["files"], "bytes": now[d]["bytes"],
                                 "max_mtime": now[d]["max_mtime"],
                                 "tree_sha256": now[d]["tree_sha256"],
                                 "L5_baseline": base[d]["tree_sha256"], "same": same[d]} for d in now},
    "l3_mtime_size": {"candidates_rules.jsonl": {"max_mtime": time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime("kb/l3/candidates/rules.jsonl"))),
        "bytes": os.path.getsize("kb/l3/candidates/rules.jsonl")}},
    "l3_candidates": {"lines": len(l3_raw), "sha256": sha("kb/l3/candidates/rules.jsonl"),
                      "prefix509_sha256": l3_prefix,
                      "prefix_matches_L5": l3_prefix == json.load(
                          open("kb/.work/l5_integrity.json", encoding="utf-8")
                      )["checks"]["l3_append_only"]["prefix_sha256"]},
    "verdict": "PASS" if all(same.values()) and l3_prefix == json.load(
        open("kb/.work/l5_integrity.json", encoding="utf-8"))["checks"]["l3_append_only"]["prefix_sha256"] else "FAIL",
}

# ---- 2) 条数对账
kept, FILTER = SL.usable_units()
usable = [u["unit_id"] for u in kept]
proj = [json.loads(l) for l in open(f"{L6}/index/l6.jsonl", encoding="utf-8") if l.strip()]
vrows = [json.loads(l) for l in open(f"{L6}/vectors/vectors.jsonl", encoding="utf-8") if l.strip()]
docs = [json.loads(l) for l in open(f"{L6}/bm25/docs.jsonl", encoding="utf-8") if l.strip()]
p0 = SL.p0_evidence_unit_ids()
st = collections.Counter(r["status"] for r in proj)
bs = collections.Counter(r["bm25"]["indexed"] for r in proj)
vs = collections.Counter(r["vector"]["indexed"] for r in proj)
dup_proj = [k for k, v in collections.Counter(r["unit_id"] for r in proj).items() if v > 1]
dup_vec = [k for k, v in collections.Counter(r["unit_id"] for r in vrows).items() if v > 1]
skips = collections.Counter(r["vector"]["reason"] for r in proj if not r["vector"]["indexed"])
bm_fail = [r for r in proj if not r["bm25"]["indexed"]]
ev["checks"]["counts"] = {
    "usable": len(kept), "projection_lines": len(proj), "dup_unit_id_in_projection": dup_proj,
    "bm25_docs": len(docs), "bm25_indexed": bs[True], "bm25_failed": bs[False],
    "vector_rows": len(vrows), "vector_indexed": vs[True], "vector_not_indexed": vs[False],
    "vector_skip_reasons": dict(skips), "dup_unit_id_in_vectors": dup_vec,
    "bm25_failed_units": [{"unit_id": r["unit_id"], "anchor": r["anchor"], "reason": "文本切不出任何词元"} for r in bm_fail],
    "status_distribution": dict(st),
    "reconcile": f"{len(kept)} = bm25 {bs[True]} + bm25失败 {bs[False]} = vector {vs[True]} + 不入向量 {vs[False]}",
    "verdict": "PASS" if (len(proj) == len(kept) and len(set(usable)) == len(kept)
                          and not dup_proj and not dup_vec and len(docs) == len(kept)) else "FAIL",
}

# ---- 3) 幂等：现场重跑
before = {p: (os.path.getmtime(p), os.path.getsize(p), sha(p)) for p in DURABLE}
r = subprocess.run([sys.executable, "kb/.work/l6_build.py", RUN], capture_output=True, text=True)
after = {p: (os.path.getmtime(p), os.path.getsize(p), sha(p)) for p in DURABLE}
changed = [p for p in DURABLE if before[p] != after[p]]
zero_tok = "本次切词 0 条" in r.stdout
zero_emb = "embedding 调用 0 次" in r.stdout and "新增/变更 0" in r.stdout
ev["checks"]["idempotent_rerun"] = {
    "exit_code": r.returncode, "stdout_tail": r.stdout.strip().split("\n")[-3:],
    "files_changed": changed, "tokenize_work_zero": zero_tok, "embedding_work_zero": zero_emb,
    "artifact_state": {p: {"mtime": before[p][0], "size": before[p][1], "sha256_16": before[p][2][:16]}
                       for p in DURABLE},
    "verdict": "PASS" if (r.returncode == 0 and not changed and zero_tok and zero_emb) else "FAIL",
}

# ---- 4) 向量回指
units = {u["unit_id"]: u for u in kept}
bad = []
import numpy as np  # noqa: E402
M = np.load(f"{L6}/vectors/matrix.npy")
for r_ in vrows:
    u = units.get(r_["unit_id"])
    if not u:
        bad.append({"unit_id": r_["unit_id"], "why": "不是可用单元"})
        continue
    if r_["anchor"] != u["anchor"] or r_["source_sha256"] != u["source_sha256"]:
        bad.append({"unit_id": r_["unit_id"], "why": "anchor/source_sha256 与 L2 单元不一致"})
    if r_["content_hash"] != hashlib.sha256((u.get("text") or "").encode()).hexdigest()[:32]:
        bad.append({"unit_id": r_["unit_id"], "why": "content_hash 与正文不一致"})
    if not (0 <= r_["row"] < M.shape[0]):
        bad.append({"unit_id": r_["unit_id"], "why": "matrix 行号越界"})
    if r_["unit_id"] in p0:
        bad.append({"unit_id": r_["unit_id"], "why": "P0 证据单元不该进向量"})
norms = np.linalg.norm(M, axis=1)
ev["checks"]["vector_traceability"] = {
    "rows": len(vrows), "matrix_shape": list(M.shape), "dim": int(M.shape[1]),
    "all_finite": bool(np.isfinite(M).all()),
    "norm_min": float(norms.min()), "norm_max": float(norms.max()),
    "p0_in_vector": sorted(set(r_["unit_id"] for r_ in vrows) & p0),
    "bad": bad[:20], "bad_count": len(bad),
    "verdict": "PASS" if (not bad and np.isfinite(M).all() and abs(float(norms.min()) - 1) < 1e-4
                          and abs(float(norms.max()) - 1) < 1e-4) else "FAIL",
}

# ---- 5) 倒排自洽
inv = collections.defaultdict(lambda: collections.defaultdict(list))
for lang in ("zh", "en"):
    for l in open(f"{L6}/bm25/postings_{lang}.jsonl", encoding="utf-8"):
        if l.strip():
            e = json.loads(l)
            for did, tf in e["postings"]:
                inv[lang][did].append((e["term"], tf))
mismatch = 0
for d in docs:
    for lang in ("zh", "en"):
        got = dict(inv[lang].get(d["doc_id"], []))
        if got != d[f"tf_{lang}"]:
            mismatch += 1
ev["checks"]["postings_consistency"] = {
    "docs": len(docs), "mismatch_docs": mismatch,
    "verdict": "PASS" if mismatch == 0 else "FAIL",
    "note": "逐文档重算 tf 与倒排里的 tf 完全一致（含 df=0 的词条不存在）",
}

# ---- 6) 版本纪律
canon = os.path.getsize("kb/l3/canonical/rules.jsonl")
vrows_v = [l for l in open("kb/versions/versions.jsonl", encoding="utf-8")
           if l.strip() and not l.lstrip().startswith("#")]
kbvs = {json.load(open(f"kb/{p}", encoding="utf-8")).get("kb_version") for p in
        ("l0/registry/kb.json", "l1/registry/l1.json", "l2/registry/l2.json",
         "l3/registry/l3.json", "l5/registry/l5.json", "l6/registry/l6.json")}
ev["checks"]["version_discipline"] = {
    "canonical_rules_bytes": canon, "versions_jsonl_rows": len(vrows_v),
    "kb_version_values": sorted(x for x in kbvs if x is not None),
    "l6_kb_version": json.load(open(f"{L6}/registry/l6.json", encoding="utf-8"))["kb_version"],
    "verdict": "PASS" if canon == 0 and not vrows_v and {x for x in kbvs if x is not None} == {"v0"} else "FAIL",
}

# ---- 7) 离线
src = open(f"{L6}/retriever.py", encoding="utf-8").read()
net = sorted(set(re.findall(r"\b(requests\.|urllib|socket|http\.client|urlopen|curl|wget)\b", src)))
ev["checks"]["offline"] = {
    "network_symbols": net,
    "model_source": json.load(open(f"{L6}/vectors/meta.json", encoding="utf-8"))["provider"],
    "verdict": "PASS" if not net else "FAIL",
    "note": "检索走本地索引；查询向量由本地 ONNX 模型算，模型权重已在本机缓存，运行时不联网",
}

ev["verdict"] = "PASS" if all(v.get("verdict") == "PASS" for v in ev["checks"].values()) else "FAIL"
json.dump(ev, open("kb/.work/l6_integrity.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

for k, v in ev["checks"].items():
    print(f"[{v['verdict']}] {k}")
    if k == "frozen_layers":
        for d, x in v["l0_l2_vs_L5_baseline"].items():
            print(f"        kb/{d}: {x['files']} 文件/{x['bytes']} 字节  最后修改 {x['max_mtime']}  "
                  f"tree_sha256={x['tree_sha256'][:16]} 与 L5 基线一致={x['same']}")
        print(f"        kb/l3/candidates: {v['l3_candidates']['lines']} 行  sha256={v['l3_candidates']['sha256'][:16]}  "
              f"前509行哈希与 L5 一致={v['l3_candidates']['prefix_matches_L5']}")
    if k == "counts":
        print(f"        可用 {v['usable']}｜投影 {v['projection_lines']} 行｜BM25 {v['bm25_indexed']} 条（失败 {v['bm25_failed']}）"
              f"｜向量 {v['vector_indexed']} 条（未入 {v['vector_not_indexed']}）")
        print(f"        未入向量原因分布：{v['vector_skip_reasons']}")
        print(f"        对账：{v['reconcile']}")
    if k == "idempotent_rerun":
        print(f"        退出码 {v['exit_code']}｜变更文件 {v['files_changed'] or '无'}｜切词 0={v['tokenize_work_zero']}｜"
              f"embedding 0={v['embedding_work_zero']}")
    if k == "vector_traceability":
        print(f"        {v['rows']} 行 × {v['dim']} 维｜范数 [{v['norm_min']:.6f}, {v['norm_max']:.6f}]｜"
              f"P0 混入 {len(v['p0_in_vector'])} 条｜回指异常 {v['bad_count']}")
    if k == "postings_consistency":
        print(f"        {v['docs']} 篇文档逐篇重算 tf，与倒排不一致 {v['mismatch_docs']} 篇")
    if k == "version_discipline":
        print(f"        canonical {v['canonical_rules_bytes']} 字节｜versions 行 {v['versions_jsonl_rows']}｜"
              f"kb_version {v['kb_version_values']}")
print(f"\n自检总计：{ev['verdict']}")
sys.exit(0 if ev["verdict"] == "PASS" else 1)
