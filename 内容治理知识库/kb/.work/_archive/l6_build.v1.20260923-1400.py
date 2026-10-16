#!/usr/bin/env python3
"""L6 建索引（向量 + BM25，分语言）。
- kb/l0~l3 全程只读；产物只写 kb/l6/
- 幂等：BM25 主键 (unit_id, content_hash, tokenizer_version)；向量主键 (unit_id, content_hash, model, dim)
  三者没变 → unchanged，不重新切词、不重新调 embedding；全量无变化时不重写索引文件
- embedding 失败退避重试（最多 3 次），仍失败登记原因，不静默跳过
"""
import hashlib, json, os, sys, time, collections, importlib.util

sys.path.insert(0, "kb/.work")
import l6_scope_lib as SL

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260923-1400"
L6 = "kb/l6"
B_DIR, V_DIR = f"{L6}/bm25", f"{L6}/vectors"
for d in (B_DIR, V_DIR, f"{L6}/index", f"{L6}/registry", f"{L6}/runs"):
    os.makedirs(d, exist_ok=True)

# 复用 kb/l6/retriever.py 里的切法（build 与 query 必须同一份口径）
spec = importlib.util.spec_from_file_location("l6_retriever", f"{L6}/retriever.py")
RT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RT)

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
BATCH = 64
MAX_RETRY = 3
t_start = time.time()

# ---------------- 范围 ----------------
units = SL.load_units()
kept, FILTER = SL.usable_units(units)
assert len(kept) == 1899, f"可用单元数 {len(kept)} != 1899，范围口径对不上，停"
p0_ids = SL.p0_evidence_unit_ids()
p0_in_scope = p0_ids & {u["unit_id"] for u in kept}
print(f"可用单元 {len(kept)}｜P0 证据单元（不入向量）{len(p0_in_scope)}")


def write_if_changed(path, text):
    """内容一样就不碰文件（连 mtime 都不变）→ 重跑可做到零写入。"""
    if os.path.exists(path):
        with open(path, "rb") as fh:
            if fh.read() == text.encode("utf-8"):
                return False
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True


def chash(t):
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()[:32]


def excerpt(t, n=160):
    import re as _re
    return _re.sub(r"\s+", " ", t or "").strip()[:n]


def table_of(anchor):
    a = anchor or ""
    return a[1:].split("/")[0] if a.startswith("#") else a.split("/")[0]


def langtag(t):
    zh = any(RT.is_cjk(c) for c in t)
    en = any(c.isascii() and c.isalpha() for c in t)
    return "中英混排" if zh and en else ("中文" if zh else ("英文/拉丁" if en else "无字母"))


# ---------------- BM25：增量 ----------------
old_docs = {}
if os.path.exists(f"{B_DIR}/docs.jsonl"):
    for l in open(f"{B_DIR}/docs.jsonl", encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            old_docs[r["unit_id"]] = r

bm_status = {}
docs, tok_work = [], 0
for i, u in enumerate(kept):
    uid, txt = u["unit_id"], u.get("text") or ""
    ch = chash(txt)
    prev = old_docs.get(uid)
    same = bool(prev and prev["content_hash"] == ch
                and prev["tokenizer_version"] == RT.TOKENIZER_VERSION)
    if same:
        rec = dict(prev)
        rec["doc_id"] = i
        bm_status[uid] = "unchanged"
    else:
        zh, en = RT.tokenize(txt)
        tf_zh, tf_en = collections.Counter(zh), collections.Counter(en)
        rec = {
            "doc_id": i, "unit_id": uid, "kb_type": u["kb_type"], "anchor": u["anchor"],
            "source_sha256": u["source_sha256"], "content_hash": ch,
            "tokenizer_version": RT.TOKENIZER_VERSION, "table": table_of(u["anchor"]),
            "heading_path": u.get("heading_path"), "lang": langtag(txt),
            "char_len": len(txt), "text_excerpt": excerpt(txt),
            "dl_zh": len(zh), "dl_en": len(en),
            "tf_zh": dict(tf_zh), "tf_en": dict(tf_en),
        }
        bm_status[uid] = "changed" if prev else "new"
        if not zh and not en:
            bm_status[uid] = "failed"
            rec["fail_reason"] = "文本切不出任何词元（无汉字字母数字，仅标点/空白/符号）"
        tok_work += 1
    docs.append(rec)

# 倒排：由 docs 的 tf 表推导（不依赖旧 postings，避免增量拼接出错）
post = {"zh": collections.defaultdict(list), "en": collections.defaultdict(list)}
dl_sum = {"zh": 0, "en": 0}
N = {"zh": 0, "en": 0}
for d in docs:
    for lang in ("zh", "en"):
        tf = d[f"tf_{lang}"]
        if tf:
            N[lang] += 1
            dl_sum[lang] += d[f"dl_{lang}"]
            for term, c in tf.items():
                post[lang][term].append([d["doc_id"], c])
meta = {
    "tokenizer_version": RT.TOKENIZER_VERSION, "k1": RT.K1, "b": RT.B,
    "docs_total": len(docs), "N_zh": N["zh"], "N_en": N["en"],
    "avgdl_zh": round(dl_sum["zh"] / N["zh"], 3) if N["zh"] else 0,
    "avgdl_en": round(dl_sum["en"] / N["en"], 3) if N["en"] else 0,
    "terms_zh": len(post["zh"]), "terms_en": len(post["en"]),
    "postings_zh": sum(len(v) for v in post["zh"].values()),
    "postings_en": sum(len(v) for v in post["en"].values()),
    "built_at": time.strftime("%Y-%m-%d %H:%M:%S"), "run_id": RUN,
    "lang_policy": "中文 bigram / 英文小写+分词+轻词干；两套词表与倒排分语言存放，不混",
}

bm_touched = [u for u, s in bm_status.items() if s in ("new", "changed")]
bm_files_changed = bool(bm_touched) or not os.path.exists(f"{B_DIR}/meta.json")
if bm_files_changed:
    with open(f"{B_DIR}/docs.jsonl", "w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")
    for lang in ("zh", "en"):
        with open(f"{B_DIR}/postings_{lang}.jsonl", "w", encoding="utf-8") as fh:
            for term in sorted(post[lang]):
                pl = sorted(post[lang][term])
                fh.write(json.dumps({"term": term, "df": len(pl), "postings": pl},
                                    ensure_ascii=False, sort_keys=True) + "\n")
    json.dump(meta, open(f"{B_DIR}/meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bm_write = "重写"
else:
    bm_write = "索引无变化 → 不重写文件"
print(f"BM25：{meta['docs_total']} 文档｜术语 zh {meta['terms_zh']} / en {meta['terms_en']}｜"
      f"词条（含重复）zh {meta['postings_zh']} / en {meta['postings_en']}｜"
      f"平均长度 zh {meta['avgdl_zh']} / en {meta['avgdl_en']}｜本次切词 {tok_work} 条｜{bm_write}")

# ---------------- 向量：增量 ----------------
old_vec, old_dim = {}, None
if os.path.exists(f"{V_DIR}/vectors.jsonl"):
    import numpy as np
    old_dim = json.load(open(f"{V_DIR}/meta.json", encoding="utf-8"))["dim"]
    M_old = np.load(f"{V_DIR}/matrix.npy")
    for l in open(f"{V_DIR}/vectors.jsonl", encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            old_vec[r["unit_id"]] = (r, M_old[r["row"]])

todo, keep_rows, vec_status, vec_meta_rows = [], [], {}, []
for u in kept:
    uid, txt = u["unit_id"], u.get("text") or ""
    if uid in p0_in_scope:
        vec_status[uid] = ("skipped_p0", "P0 规则的证据单元：P0 走 kb/l5/matcher.py 确定性匹配，不入向量")
        continue
    if not txt.strip():
        vec_status[uid] = ("failed", "文本为空，无内容可嵌入")
        continue
    ch = chash(txt)
    prev = old_vec.get(uid)
    if prev and prev[0]["content_hash"] == ch and prev[0]["model"] == MODEL \
            and prev[0]["dim"] == old_dim and prev[0]["dim"] > 0:
        keep_rows.append((prev[0], prev[1]))
        vec_status[uid] = ("unchanged", "")
    else:
        todo.append((u, ch))
        vec_status[uid] = ("new" if not prev else "changed", "")

embed_calls = retries = 0
new_rows, failures = [], []
if todo:
    from fastembed import TextEmbedding
    import numpy as np
    model = TextEmbedding(model_name=MODEL)
    dim = None
    for s in range(0, len(todo), BATCH):
        chunk = todo[s:s + BATCH]
        texts = [u.get("text") or "" for u, _ in chunk]
        vecs, err = None, None
        for attempt in range(1, MAX_RETRY + 1):
            try:
                embed_calls += 1
                vecs = [np.asarray(v, dtype="float32") for v in model.embed(texts)]
                break
            except Exception as e:                       # noqa: BLE001 退避重试
                err = f"{type(e).__name__}: {e}"
                if attempt < MAX_RETRY:
                    retries += 1
                    time.sleep(2 ** attempt)
        if vecs is None:
            for u, _ in chunk:
                vec_status[u["unit_id"]] = ("failed", f"embedding 连续失败 {MAX_RETRY} 次：{err}")
                failures.append({"unit_id": u["unit_id"], "reason": err})
            continue
        for (u, ch), v in zip(chunk, vecs):
            n = float(np.linalg.norm(v))
            if n == 0:
                vec_status[u["unit_id"]] = ("failed", "模型返回零向量，不写入（拒绝伪造）")
                failures.append({"unit_id": u["unit_id"], "reason": "zero_vector"})
                continue
            new_rows.append(({
                "unit_id": u["unit_id"], "kb_type": u["kb_type"], "anchor": u["anchor"],
                "source_sha256": u["source_sha256"], "model": MODEL, "dim": int(v.shape[0]),
                "content_hash": ch, "table": table_of(u["anchor"]), "lang": langtag(u.get("text") or ""),
                "char_len": len(u.get("text") or ""),
            }, (v / n).astype("float32")))

all_rows = keep_rows + new_rows
vec_files_changed = bool(new_rows) or not os.path.exists(f"{V_DIR}/meta.json")
if all_rows and vec_files_changed:
    import numpy as np
    dims = {r["dim"] for r, _ in all_rows}
    assert len(dims) == 1, f"维度不一致 {dims}"
    dim = dims.pop()
    with open(f"{V_DIR}/vectors.jsonl", "w", encoding="utf-8") as fh:
        for i, (row, _) in enumerate(all_rows):
            fh.write(json.dumps(dict(row, row=i), ensure_ascii=False, sort_keys=True) + "\n")
    M = np.vstack([v for _, v in all_rows]).astype("float32")
    np.save(f"{V_DIR}/matrix.npy", M)
    json.dump({"model": MODEL, "dim": int(dim), "count": len(all_rows),
               "normalize": "l2（存的就是归一化后的向量，点积即余弦）",
               "provider": "fastembed(ONNX) + onnxruntime，本地 CPU，无外联调用",
               "max_seq": "模型自带上限 512 token，超长文本被模型截断（未额外切块）",
               "built_at": time.strftime("%Y-%m-%d %H:%M:%S"), "run_id": RUN},
              open(f"{V_DIR}/meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    vec_write = "重写"
else:
    vec_write = "向量无变化 → 不重写文件" if all_rows else "无向量可写"
print(f"向量：条数 {len(all_rows)}｜新增/变更 {len(new_rows)}｜复用 {len(keep_rows)}｜"
      f"embedding 调用 {embed_calls} 次、重试 {retries} 次｜失败 {len(failures)}｜{vec_write}")

# ---------------- 投影 + registry ----------------
VDIM = json.load(open(f"{V_DIR}/meta.json", encoding="utf-8"))["dim"] if os.path.exists(f"{V_DIR}/meta.json") else None
bm_indexed = {d["unit_id"] for d in docs if d["dl_zh"] or d["dl_en"]}
vec_indexed = {r["unit_id"] for r, _ in all_rows}
idx = []
for u in kept:
    uid = u["unit_id"]
    b_ok, v_ok = uid in bm_indexed, uid in vec_indexed
    vs, vreason = vec_status.get(uid, ("unknown", "未处理"))
    idx.append({
        "unit_id": uid, "kb_type": u["kb_type"], "anchor": u["anchor"],
        "source_sha256": u["source_sha256"], "content_hash": chash(u.get("text") or ""),
        "model": MODEL if v_ok else None, "dim": VDIM if v_ok else None,
        "status": "indexed" if (b_ok and v_ok) else ("partial" if (b_ok or v_ok) else "failed"),
        "bm25": {"indexed": b_ok, "terms_zh": len(next((d["tf_zh"] for d in docs if d["unit_id"] == uid), {})),
                 "terms_en": len(next((d["tf_en"] for d in docs if d["unit_id"] == uid), {}))},
        "vector": {"indexed": v_ok, "reason": None if v_ok else (vreason or "未入向量")},
    })
proj_txt = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in idx)
proj_written = write_if_changed(f"{L6}/index/l6.jsonl", proj_txt)

probe = json.load(open("kb/.work/l6_probe.json", encoding="utf-8")) if os.path.exists("kb/.work/l6_probe.json") else {}
probe0 = json.load(open("kb/.work/l6_probe_initial.json", encoding="utf-8")) if os.path.exists("kb/.work/l6_probe_initial.json") else None
reg = {
    "kb_version": "v0", "run_id": RUN, "mode": "vector_plus_bm25",
    "mode_note": "首选模式：本地 ONNX 多语 embedding 模型可用（无外联接口），向量 + BM25 都建",
    "scope": {"usable_units": len(kept), "source": "kb/l2/units.jsonl 经 L3 口径过滤",
              "filter_distribution": {f"{k[0]}|{k[1]}": v for k, v in FILTER.items()},
              "scope_file": "kb/l6/SCOPE.txt" if os.path.exists(f"{L6}/SCOPE.txt") else None},
    "tokenizer": {
        "version": RT.TOKENIZER_VERSION, "rrf_k": RT.RRF_K, "bm25": {"k1": RT.K1, "b": RT.B},
        "zh": "按字符类别切出连续汉字段 → 直接 bigram（不依赖分词库）；单字段退化为 unigram",
        "en": "小写化 → 按标点/空白分词 → 轻词干（复数/时态/副词后缀保守剥离）",
        "mixed": "按字符类别分段，各段用各自的切法；词表与倒排分语言存放，不混",
        "why": "中文 bigram 对英文会明显劣化；素材里英文占比高，混一套切法会拉低英文侧召回",
    },
    "embedding": {
        "model": MODEL, "dim": VDIM,
        "provider": "fastembed 0.7.4 + onnxruntime 1.19.2（本地 CPU）",
        "normalized": "l2", "batch": BATCH, "max_retry": MAX_RETRY,
        "p0_excluded_units": len(p0_in_scope),
        "p0_policy": "走 kb/l5/matcher.py 的确定性匹配，因此不重复建向量",
    },
    "fusion": {"method": "RRF", "k": RT.RRF_K,
               "how": "先在 bm25_zh / bm25_en 两个语言子索引之间按名次融合，再与 vector 名次融合",
               "why": "RRF 只用名次不用原始分，规避 BM25 分与余弦分量纲不同",
               "rerank": "本轮不做 rerank 模型"},
    "idempotency": {
        "bm25_key": ["unit_id", "content_hash", "tokenizer_version"],
        "vector_key": ["unit_id", "content_hash", "model", "dim"],
        "content_hash": "sha256(unit.text)[:32]",
        "unchanged": "键全同 → 复用已有 tf 表与已有向量，不重新切词、不重新调 embedding；全量无变化时不重写索引文件",
    },
    "embedding_probe": probe,
    "embedding_probe_initial": probe0,
    "mode_history": [
        {"step": "首轮探测（13:56）", "result": "bm25_only",
         "why": "当时 curl 只给 3 秒超时，huggingface/pypi 全判为不可达；本机也确实没有现成的 embedding 依赖与模型文件"},
        {"step": "复测网络（13:58）", "result": "可达", "why": "huggingface.co / pypi.org 均返回 200，首轮是超时太短导致的误判"},
        {"step": "装 ONNX 路线依赖（13:59）", "result": "fastembed 0.7.4 装好",
         "why": "onnxruntime 1.19.2 本机已有，fastembed 走 ONNX 不需要 torch（省 2GB）"},
        {"step": "决定走首选模式", "result": "vector_plus_bm25",
         "why": "拿到真实向量（多语模型、384 维），两套索引都建；未使用随机数/哈希/零向量充数"},
    ],
    "counts": {
        "usable": len(kept),
        "bm25_indexed": len(bm_indexed), "bm25_failed": len(kept) - len(bm_indexed),
        "vector_indexed": len(vec_indexed), "vector_skipped_p0": len(p0_in_scope),
        "vector_failed": len(kept) - len(vec_indexed) - len(p0_in_scope),
        "note": "全部为持久口径（索引里到底有没有这条），与「本次运行做了什么」无关；后者写在 runs/ 里",
    },
    "bm25_scale": {k: meta[k] for k in ("docs_total", "N_zh", "N_en", "avgdl_zh", "avgdl_en",
                                        "terms_zh", "terms_en", "postings_zh", "postings_en")},
}
reg_txt = json.dumps(reg, ensure_ascii=False, indent=1) + "\n"
reg_written = write_if_changed(f"{L6}/registry/l6.json", reg_txt)

did_work = bool(new_rows) or tok_work > 0 or bm_files_changed or vec_files_changed
if did_work:
    with open(f"{L6}/runs/build_runs.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "run_id": RUN, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "usable": len(kept), "bm25_tokenized": tok_work, "bm25_docs": len(docs),
            "vectors_new_or_changed": len(new_rows), "vectors_reused": len(keep_rows),
            "embedding_calls": embed_calls, "embedding_retries": retries,
            "embedding_failures": len(failures), "elapsed_s": round(time.time() - t_start, 1),
            "wrote_bm25": bm_files_changed, "wrote_vectors": vec_files_changed,
        }, ensure_ascii=False, sort_keys=True) + "\n")

json.dump({"run_id": RUN, "bm_status": bm_status, "vec_status": {k: v[0] for k, v in vec_status.items()},
           "vec_reasons": {k: v[1] for k, v in vec_status.items() if v[1]},
           "bm25_meta": meta, "embed_calls": embed_calls, "retries": retries, "failures": failures,
           "bm_files_changed": bm_files_changed, "vec_files_changed": vec_files_changed,
           "elapsed_s": round(time.time() - t_start, 1)},
          open("kb/.work/l6_build.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"索引投影 {len(idx)} 行（{'重写' if proj_written else '未变不写'}）｜"
      f"registry（{'重写' if reg_written else '未变不写'}）｜总耗时 {time.time()-t_start:.1f}s")
