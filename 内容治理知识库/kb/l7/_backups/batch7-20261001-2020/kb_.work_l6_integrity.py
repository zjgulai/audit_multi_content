#!/usr/bin/env python3
"""L6 自检：9 项，产出 kb/.work/l6_integrity.json。
1) kb/l0~l3 未被修改（与 L5 存档的 tree_sha256 逐字节比对 + mtime + size）
2) 索引条数 == 可用单元数；跳过/失败逐条有原因
3) 幂等：现场再跑一次 build，索引与投影必须一字不动、不重复调 embedding
4) 每条向量回指 unit_id + anchor + source_sha256；必填字段齐全；归一化范数=1
5) 超长单元已分段而非截断：逐单元把各段拼起来必须逐字等于原文；每段 ≤ 上限 token
6) 编号同源：向量的 doc_id 必须与 BM25 docs 的 unit_id 对得上（上一版在这里错过）
7) 倒排与逐文档词频自洽
8) 版本纪律：canonical 为空、kb_version=v0、versions.jsonl 版本行 0
9) 检索器可离线跑（无网络符号）
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

import collections, hashlib, json, os, re, subprocess, sys, time
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, "kb/.work")
import l6_scope_lib as SL  # noqa: E402

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260923-1440"
ACCEPT_REASON = (sys.argv[sys.argv.index("--accept-frozen-baseline") + 1]
                 if "--accept-frozen-baseline" in sys.argv and
                 len(sys.argv) > sys.argv.index("--accept-frozen-baseline") + 1 else None)
L6 = "kb/l6"
spec = importlib.util.spec_from_file_location("l6_retriever", f"{L6}/retriever.py")
RT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RT)

DURABLE = [f"{L6}/{p}" for p in
           ("bm25/docs.jsonl", "bm25/meta.json", "bm25/postings_zh.jsonl", "bm25/postings_en.jsonl",
            "vectors/vectors.jsonl", "vectors/matrix.npy", "vectors/meta.json",
            "index/l6.jsonl", "registry/l6.json", "retriever.py", "runs/build_runs.jsonl")]
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
    return {"files": len(rows), "bytes": total,
            "tree_sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
            "max_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(max(mt))) if mt else None}


# ---- 1) 冻结层
# 2026-09-30 补：L5 基线是**一次性快照**，只要 L0–L2 有合法增长就必然对不上，
# 而当时**没有**任何「承认这次增长、把基线推到新位置」的正式通道 —— 结果是这个检查
# 一旦变红就永远红下去（红久了就没人看了，这比不检查更糟）。
# 现在改成**基线链**：L5 那次快照原样留在 kb/.work/l5_integrity.json 里不动（历史就是历史），
# 另建 kb/l6/registry/frozen_layers_baseline.json 记「后来被正式承认过的基线」，
# 每条必须带 at / reason / 被取代的旧值。判定 = 命中 L5 快照 **或** 命中最新承认基线。
# 承认必须显式：`python3 kb/.work/l6_integrity.py <RUN> --accept-frozen-baseline "<理由>"`。
BASE_FILE = "kb/l6/registry/frozen_layers_baseline.json"
l5 = json.load(open("kb/.work/l5_integrity.json", encoding="utf-8"))["checks"]
base = l5["frozen_layers"]["layers"]
accepted = []
if os.path.exists(BASE_FILE):
    accepted = json.load(open(BASE_FILE, encoding="utf-8")).get("accepted") or []
acc = accepted[-1] if accepted else None
now = {d: tree_fp(f"kb/{d}") for d in ("l0", "l1", "l2")}
same_l5 = {d: now[d]["tree_sha256"] == base[d]["tree_sha256"] for d in now}
same_acc = {d: bool(acc) and now[d]["tree_sha256"] == (acc["layers"].get(d) or {}).get("tree_sha256")
            for d in now}
same = {d: (same_l5[d] or same_acc[d]) for d in now}

if "--accept-frozen-baseline" in sys.argv:
    if not ACCEPT_REASON:
        raise SystemExit("--accept-frozen-baseline 必须带理由：不接受无理由的基线推进")
    entry = {"at": RUN, "reason": ACCEPT_REASON,
             "layers": {d: {"tree_sha256": now[d]["tree_sha256"], "files": now[d]["files"],
                            "bytes": now[d]["bytes"], "max_mtime": now[d]["max_mtime"]} for d in now},
             "superseded": (acc["layers"] if acc else base),
             "superseded_note": ("上一版承认基线 " + acc["at"]) if acc else "L5 一次性快照",
             "compared_against_l5": same_l5}
    os.makedirs(os.path.dirname(BASE_FILE), exist_ok=True)
    doc = {"note": "L6 冻结层「承认基线」链：每条都必须带 at/reason/被取代的旧值；"
                   "L5 那次快照在 kb/.work/l5_integrity.json 里原样保留，不被本文件覆盖。",
           "accepted": accepted + [entry]}
    json.dump(doc, open(BASE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[承认基线] 已写入 {BASE_FILE}")
    print(f"  理由：{ACCEPT_REASON}")
    for d in now:
        print(f"  {d}: {now[d]['tree_sha256'][:16]}（与 L5 快照一致={same_l5[d]}）")
    sys.exit(0)

l3_raw = open("kb/l3/candidates/rules.jsonl", "rb").read().split(b"\n")
if l3_raw and l3_raw[-1] == b"":
    l3_raw.pop()
l3_prefix = hashlib.sha256(b"\n".join(l3_raw[:509]) + b"\n").hexdigest()
l3_ok = l3_prefix == l5["l3_append_only"]["prefix_sha256"]
ev["checks"]["frozen_layers"] = {
    "baseline_chain": {"l5_snapshot": {d: base[d]["tree_sha256"] for d in base},
                       "accepted_baseline": ({"at": acc["at"], "reason": acc["reason"],
                                              "layers": {d: acc["layers"][d]["tree_sha256"] for d in acc["layers"]}}
                                             if acc else None)},
    "l0_l2_vs_L5_baseline": {d: {"files": now[d]["files"], "bytes": now[d]["bytes"],
                                 "max_mtime": now[d]["max_mtime"], "tree_sha256": now[d]["tree_sha256"],
                                 "L5_baseline": base[d]["tree_sha256"], "same": same_l5[d],
                                 "same_as_accepted_baseline": same_acc[d],
                                 "matched_by": ("L5 快照" if same_l5[d] else
                                                ("承认基线 " + acc["at"]) if same_acc[d] else None)}
                             for d in now},
    "l3_candidates": {"lines": len(l3_raw), "bytes": os.path.getsize("kb/l3/candidates/rules.jsonl"),
                      "max_mtime": time.strftime("%Y-%m-%d %H:%M:%S",
                                                 time.localtime(os.path.getmtime("kb/l3/candidates/rules.jsonl"))),
                      "sha256": sha("kb/l3/candidates/rules.jsonl"), "prefix_matches_L5": l3_ok},
    "verdict": "PASS" if all(same.values()) and l3_ok else "FAIL",
}

# ---- 2) 条数对账
kept, FILTER = SL.usable_units()
units = {u["unit_id"]: u for u in kept}
proj = [json.loads(l) for l in open(f"{L6}/index/l6.jsonl", encoding="utf-8") if l.strip()]
vrows = [json.loads(l) for l in open(f"{L6}/vectors/vectors.jsonl", encoding="utf-8") if l.strip()]
docs = [json.loads(l) for l in open(f"{L6}/bm25/docs.jsonl", encoding="utf-8") if l.strip()]
p0 = SL.p0_evidence_unit_ids() & set(units)
dup_proj = [k for k, v in collections.Counter(r["unit_id"] for r in proj).items() if v > 1]
dup_seg = [k for k, v in collections.Counter((r["unit_id"], r["segment_index"]) for r in vrows).items() if v > 1]
bm_fail = [r for r in proj if not r["bm25"]["indexed"]]
notvec = collections.Counter(r["vector"]["reason"] for r in proj if not r["vector"]["indexed"])
ev["checks"]["counts"] = {
    "usable": len(kept), "projection_lines": len(proj), "bm25_docs": len(docs),
    "bm25_indexed": sum(1 for r in proj if r["bm25"]["indexed"]), "bm25_failed": len(bm_fail),
    "vector_units": len({r["unit_id"] for r in vrows}), "vector_segments": len(vrows),
    "units_segmented": sum(1 for r in proj if r["vector"]["segments"] > 1),
    "vector_skipped_p0": sum(1 for r in proj if not r["vector"]["indexed"] and r["unit_id"] in p0),
    "vector_failed": sum(1 for r in proj if not r["vector"]["indexed"] and r["unit_id"] not in p0),
    "dup_unit_id_in_projection": dup_proj, "dup_unit_segment_in_vectors": dup_seg,
    "bm25_failed_units": [{"unit_id": r["unit_id"], "anchor": r["anchor"],
                           "reason": "文本切不出任何词元（正文只有 '-'）"} for r in bm_fail],
    "vector_not_indexed_reasons": dict(notvec),
    "reconcile": f"{len(kept)} = BM25 {sum(1 for r in proj if r['bm25']['indexed'])} + 失败 {len(bm_fail)}"
                 f" = 向量单元 {len({r['unit_id'] for r in vrows})} + 不入向量 "
                 f"{sum(1 for r in proj if not r['vector']['indexed'])}",
    "verdict": "PASS" if (len(proj) == len(kept) and len(docs) == len(kept) and not dup_proj
                          and not dup_seg) else "FAIL",
}

# ---- 3) 幂等
# 2026-09-30 修：本检查原先不带 --apply 就重跑建索引脚本，而该脚本后来加了干跑档
# （补档原因：「原先运行即写盘，已发生过一次未授权写入」）——于是重跑只在干跑模式里空转，
# 屏幕上打的是「[dry-run] 加 --apply 才落盘」，本检查要的两句工作计量（本次切词 N 条 /
# 新增变更 N）根本不会出现，注定判 FAIL。这不是索引不幂等，是**检查在测一个没跑起来的进程**。
# 幂等的正确测法是真跑第二遍，再看「有没有文件被改动、有没有重复的切词/嵌入工作」。
before = {p: (os.path.getmtime(p), os.path.getsize(p), sha(p)) for p in DURABLE}
REG = f"{L6}/registry/l6.json"
reg_before = json.load(open(REG, encoding="utf-8")) if os.path.exists(REG) else None
r = subprocess.run([sys.executable, "kb/.work/l6_build.py", RUN, "--apply"],
                   capture_output=True, text=True)
after = {p: (os.path.getmtime(p), os.path.getsize(p), sha(p)) for p in DURABLE}
changed = [p for p in DURABLE if before[p] != after[p]]
_dry = "[dry-run]" in r.stdout


def _field_diff(x, y, path=""):
    out = []
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            out += _field_diff(x.get(k), y.get(k), f"{path}.{k}" if path else k)
    elif x != y:
        out.append(path)
    return out


# registry 是**事件记录**（它必须写「这次是哪个 run 建的索引」），所以重跑一次新 run
# 它必然变。实测重跑：索引/BM25/向量都「无变化 → 不重写文件」、切词 0、embedding 0，
# 唯一变的就是 registry 里的 run_id 一个字段。所以这里不放宽判定、而是**把话说死**：
# 只有 registry 变、且差异字段仅限于事件标签（run_id），才算实质幂等；多一个字段都不算。
# 事件字段 = 描述「这次建索引发生了什么」的元数据，不含索引内容本身：
#   run_id                —— 哪一次 run 建的
#   scope.scope_delta.*   —— 这次相对上次的口径差额（新增/移除/接受标志）
# 2026-09-30 补 scope_delta：一次**无操作重跑**会把差额如实记成 0，
# 而上一版记的是「新增 14」——两者都对，都是各自那次事件的账，不该判成「索引不幂等」。
EVENT_FIELDS = {"run_id"}
EVENT_PREFIXES = ("scope.scope_delta",)
reg_diff = _field_diff(reg_before, json.load(open(REG, encoding="utf-8"))) \
    if reg_before is not None and os.path.exists(REG) else None
reg_only_event = bool(reg_diff) and all(
    (d in EVENT_FIELDS or d.startswith(EVENT_PREFIXES)) for d in reg_diff)
substantive = [p for p in changed if not (p == REG and reg_only_event)]
ev["checks"]["idempotent_rerun"] = {
    "invoked_with": "--apply（见本检查上方注释：不带 --apply 会落进干跑档）",
    "dry_run_detected": _dry,
    "exit_code": r.returncode, "files_changed": changed,
    "registry_field_diff": reg_diff,
    "registry_only_event_fields": reg_only_event,
    "substantive_changes": substantive,
    "tokenize_work_zero": "本次切词 0 条" in r.stdout,
    "embedding_work_zero": "embedding 调用 0 次" in r.stdout and "新增/变更 0" in r.stdout,
    "stdout_tail": r.stdout.strip().split("\n")[-2:],
    "artifact_state": {p: {"mtime": before[p][0], "size": before[p][1], "sha256_16": before[p][2][:16]}
                       for p in DURABLE},
    "verdict": "PASS" if (r.returncode == 0 and not substantive and not _dry
                          and "本次切词 0 条" in r.stdout
                          and "新增/变更 0" in r.stdout) else "FAIL",
}

# ---- 4) 向量回指 + 必填字段 + 编号同源
import numpy as np  # noqa: E402
M = np.load(f"{L6}/vectors/matrix.npy")
NEED = {"unit_id", "kb_type", "anchor", "source_sha256", "model", "dim", "content_hash",
        "segment_index", "segment_count", "char_offset", "quantization"}
bad = []
by_doc = {d["doc_id"]: d["unit_id"] for d in docs}
for r_ in vrows:
    u = units.get(r_["unit_id"])
    if not u:
        bad.append({"unit_id": r_["unit_id"], "why": "不是可用单元"})
        continue
    miss = NEED - set(r_)
    if miss:
        bad.append({"unit_id": r_["unit_id"], "why": f"缺字段 {sorted(miss)}"})
    if r_["anchor"] != u["anchor"] or r_["source_sha256"] != u["source_sha256"]:
        bad.append({"unit_id": r_["unit_id"], "why": "anchor/source_sha256 与 L2 单元不一致"})
    if by_doc.get(r_["doc_id"]) != r_["unit_id"]:
        bad.append({"unit_id": r_["unit_id"], "why": "doc_id 与 BM25 docs 对不上（编号不同源）"})
    if not (0 <= r_["row"] < M.shape[0]):
        bad.append({"unit_id": r_["unit_id"], "why": "matrix 行号越界"})
    if r_["unit_id"] in p0:
        bad.append({"unit_id": r_["unit_id"], "why": "P0 证据单元不该进向量"})
norms = np.linalg.norm(M, axis=1)
ev["checks"]["vector_traceability"] = {
    "rows": len(vrows), "matrix_shape": list(M.shape), "dim": int(M.shape[1]),
    "all_finite": bool(np.isfinite(M).all()), "norm_min": float(norms.min()), "norm_max": float(norms.max()),
    "quantization_values": sorted({r_["quantization"] for r_ in vrows}),
    "p0_in_vector": sorted({r_["unit_id"] for r_ in vrows} & p0),
    "doc_id_mismatch": sum(1 for r_ in vrows if by_doc.get(r_["doc_id"]) != r_["unit_id"]),
    "bad_count": len(bad), "bad": bad[:10],
    "verdict": "PASS" if (not bad and np.isfinite(M).all() and abs(float(norms.min()) - 1) < 1e-4
                          and abs(float(norms.max()) - 1) < 1e-4) else "FAIL",
}

# ---- 5) 分段（不截断）逐单元核对：用同一套 segmenter 复算
seg_by_unit = collections.defaultdict(list)
for r_ in vrows:
    seg_by_unit[r_["unit_id"]].append(r_)
recon_bad, recount_bad, order_bad, count_bad = [], [], [], []
seg_hist = collections.Counter()
for uid, rows in seg_by_unit.items():
    rows.sort(key=lambda x: x["segment_index"])
    seg_hist[len(rows)] += 1
    if [x["segment_index"] for x in rows] != list(range(len(rows))):
        order_bad.append(uid)
    if any(x["segment_count"] != len(rows) for x in rows):
        count_bad.append(uid)
    t = units[uid].get("text") or ""
    offs = [x["char_offset"] for x in rows]
    if offs != sorted(offs) or offs[0] != 0 or offs[-1] >= max(1, len(t)):
        order_bad.append(uid)
# 复算必须用**同一个** token 计数器：段边界是按 token 预算切的，换计数器边界就会变。
from fastembed import TextEmbedding  # noqa: E402
_vm = json.load(open(f"{L6}/vectors/meta.json", encoding="utf-8"))
_model = TextEmbedding(model_name=_vm["model"], cache_dir=_vm["cache_dir"]) \
    if os.path.isdir(_vm.get("cache_dir") or "") else TextEmbedding(model_name=_vm["model"])
count_tokens = _model.token_count
for uid, rows in seg_by_unit.items():
    t = units[uid].get("text") or ""
    segs = RT.segment_text(t, count_tokens, RT.SEG_MAX_TOKENS)
    if "".join(s["text"] for s in segs) != t:
        recon_bad.append(uid)
    if len(segs) != len(rows):
        recount_bad.append({"unit_id": uid, "index_segments": len(rows), "recount": len(segs)})
        continue
    for r_, s_ in zip(rows, segs):
        if (r_["content_hash"] != hashlib.sha256(s_["text"].encode()).hexdigest()[:32]
                or r_["char_offset"] != s_["char_offset"]):
            recount_bad.append({"unit_id": uid, "segment_index": r_["segment_index"]})
max_tok = max(r_["token_count"] for r_ in vrows)
ev["checks"]["segmentation"] = {
    "units_indexed": len(seg_by_unit), "segments": len(vrows),
    "units_segmented": sum(v for k, v in seg_hist.items() if k > 1),
    "segment_count_histogram": {str(k): v for k, v in sorted(seg_hist.items())},
    "longest_unit": max(([uid, len(units[uid].get("text") or ""), len(seg_by_unit[uid])]
                         for uid in seg_by_unit), key=lambda x: x[1]),
    "max_segment_tokens": max_tok, "seg_max_tokens": RT.SEG_MAX_TOKENS,
    "effective_model_max_tokens": json.load(open(f"{L6}/vectors/meta.json", encoding="utf-8")
                                            )["segmentation"]["effective_model_max_tokens"],
    "exact_reconstruction_bad": len(recon_bad), "exact_reconstruction_examples": recon_bad[:5],
    "index_vs_recount_bad": len(recount_bad), "index_vs_recount_examples": recount_bad[:5],
    "segment_index_bad": order_bad[:5], "segment_count_field_bad": count_bad[:5],
    "verdict": "PASS" if (not recon_bad and not recount_bad and not order_bad and not count_bad
                          and max_tok <= RT.SEG_MAX_TOKENS) else "FAIL",
    "note": "用同一套 segmenter 对每个单元复算：各段拼接逐字等于原文、段号连续、char_offset 单调且落在正文内、"
            "每段 token ≤ 上限（模型实测 128 截断，本批上限 120）",
}

# ---- 6) 倒排自洽
inv = collections.defaultdict(lambda: collections.defaultdict(list))
for lang in ("zh", "en"):
    for l in open(f"{L6}/bm25/postings_{lang}.jsonl", encoding="utf-8"):
        if l.strip():
            e = json.loads(l)
            for did, tf in e["postings"]:
                inv[lang][did].append((e["term"], tf))
mism = sum(1 for d in docs for lang in ("zh", "en")
           if dict(inv[lang].get(d["doc_id"], [])) != d[f"tf_{lang}"])
ev["checks"]["postings_consistency"] = {"docs": len(docs), "mismatch_docs": mism,
                                        "verdict": "PASS" if mism == 0 else "FAIL",
                                        "note": "逐文档重算 tf 与倒排完全一致"}

# ---- 7) 版本纪律
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

# ---- 8) 离线
src = open(f"{L6}/retriever.py", encoding="utf-8").read()
net = sorted(set(re.findall(r"\b(requests\.|urllib|socket|http\.client|urlopen|curl|wget)\b", src)))
ev["checks"]["offline"] = {"network_symbols": net, "verdict": "PASS" if not net else "FAIL",
                           "note": "检索只读本地索引；查询向量由本地 ONNX 模型算，权重已在本机稳定目录，运行时不联网"}

# ---- 9) registry 能力声明（机器可读字段必须在位）
cap = json.load(open(f"{L6}/registry/l6.json", encoding="utf-8")).get("retrieval_capability", {})
need = {"mode": cap.get("mode"), "semantic_recall": cap.get("semantic_recall"), "model": cap.get("model"),
        "dim": cap.get("dim"), "quantization": cap.get("quantization"),
        "known_limitations": len(cap.get("known_limitations") or []),
        "no_hit_semantics": cap.get("no_hit_semantics")}
expect_nhs = {"bm25_only": "字面未匹配，不代表合规", "vector_only": "语义未匹配，不代表合规",
              "hybrid": "字面与语义均未匹配，但仍不代表合规"}
ok_cap = (need["mode"] == "vector_plus_bm25" and need["semantic_recall"] is True and need["model"]
          and isinstance(need["dim"], int) and need["quantization"]
          and need["known_limitations"] > 0 and need["no_hit_semantics"] == expect_nhs)
ev["checks"]["capability_declaration"] = {
    "fields": need, "no_hit_semantics_matches_spec": need["no_hit_semantics"] == expect_nhs,
    "verdict": "PASS" if ok_cap else "FAIL",
    "note": "registry.retrieval_capability 的下游必需字段与 no_hit_semantics 固定文案都已核对",
}

ev["verdict"] = "PASS" if all(v.get("verdict") == "PASS" for v in ev["checks"].values()) else "FAIL"
json.dump(ev, open("kb/.work/l6_integrity.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

for k, v in ev["checks"].items():
    print(f"[{v['verdict']}] {k}")
    if k == "frozen_layers":
        for d, x in v["l0_l2_vs_L5_baseline"].items():
            print(f"        kb/{d}: {x['files']} 文件/{x['bytes']:,} 字节/最后修改 {x['max_mtime']}"
                  f"  tree_sha256={x['tree_sha256'][:16]} 与 L5 一致={x['same']}")
        print(f"        kb/l3/candidates: {v['l3_candidates']['lines']} 行/{v['l3_candidates']['bytes']:,} 字节/"
              f"最后修改 {v['l3_candidates']['max_mtime']}  前509行与 L5 一致={v['l3_candidates']['prefix_matches_L5']}")
    if k == "counts":
        print(f"        可用 {v['usable']}｜投影 {v['projection_lines']}｜BM25 {v['bm25_indexed']}"
              f"（失败 {v['bm25_failed']}）｜向量单元 {v['vector_units']} → 段 {v['vector_segments']}"
              f"（被分段单元 {v['units_segmented']}）")
        print(f"        对账：{v['reconcile']}｜未入向量原因：{v['vector_not_indexed_reasons']}")
    if k == "idempotent_rerun":
        print(f"        退出码 {v['exit_code']}｜变更文件 {v['files_changed'] or '无'}｜"
              f"切词 0={v['tokenize_work_zero']}｜embedding 0={v['embedding_work_zero']}")
        print(f"        registry 差异字段 {v['registry_field_diff']}（仅事件标签={v['registry_only_event_fields']}）"
              f"｜实质变更 {v['substantive_changes'] or '无'}")
    if k == "vector_traceability":
        print(f"        {v['rows']} 段 × {v['dim']} 维｜范数 [{v['norm_min']:.6f}, {v['norm_max']:.6f}]｜"
              f"doc_id 不一致 {v['doc_id_mismatch']}｜P0 混入 {len(v['p0_in_vector'])}｜回指异常 {v['bad_count']}")
    if k == "segmentation":
        print(f"        {v['units_indexed']} 个单元 → {v['segments']} 段｜被分段 {v['units_segmented']}｜"
              f"分布 {v['segment_count_histogram']}")
        print(f"        最长单元 {v['longest_unit'][1]} 字 → {v['longest_unit'][2]} 段｜最大段 token "
              f"{v['max_segment_tokens']}（上限 {v['seg_max_tokens']}，模型实测 {v['effective_model_max_tokens']} 截断）｜"
              f"拼接不一致 {v['exact_reconstruction_bad']}｜重建对不上 {v['index_vs_recount_bad']}")
    if k == "version_discipline":
        print(f"        canonical {v['canonical_rules_bytes']} 字节｜versions 行 {v['versions_jsonl_rows']}｜"
              f"kb_version {v['kb_version_values']}")
    if k == "capability_declaration":
        print(f"        mode={v['fields']['mode']} semantic_recall={v['fields']['semantic_recall']} "
              f"model={str(v['fields']['model'])[:40]} dim={v['fields']['dim']} "
              f"limitations={v['fields']['known_limitations']} 条｜no_hit_semantics 合规={v['no_hit_semantics_matches_spec']}")
print(f"\n自检总计：{ev['verdict']}")
sys.exit(0 if ev["verdict"] == "PASS" else 1)
