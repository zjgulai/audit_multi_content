#!/usr/bin/env python3
"""L6 检索器：BM25（自实现倒排，中文 bigram / 英文轻词干，分语言子索引）
              + 向量（多语言 ONNX 模型，按段落分段、不截断），RRF 融合。

三种模式：
    bm25_only    只用字面倒排
    vector_only  只用向量
    hybrid       两路融合（默认；向量索引不存在时自动降级为 bm25_only）
    auto         有向量就用 hybrid，没有就 bm25_only

用法：
    python3 kb/l6/retriever.py --query "宣称疗效的表述" --top 5
    python3 kb/l6/retriever.py --query "FDA approved claims" --top 5 --mode vector_only --json
    python3 kb/l6/retriever.py --query "医生推荐" --mode bm25_only --kb-type internal_sample
    python3 kb/l6/retriever.py --selftest     # 切法 / 分段 / RRF / 编号一致性 单元自测（不读盘写盘、不外联）

要点：
- 分语言切法：按字符类别把文本切成 zh / en 段，各用各的切法；词表与倒排分语言存放，不混。
  zh：连续汉字段直接切 bigram（不依赖分词库）；单字段退化为 unigram。
  en：小写化 → 按标点/空白分词 → 轻词干（只剥复数/时态/副词后缀，不做完整 Porter）。
- BM25 是自实现倒排（不使用 jieba / rank_bm25；依赖表里没有它们也不影响能力）。
- 向量：模型对超长文本会在 128 token 处静默截断（已实测），所以建索引时**按段落/句边界分段**，
  每段一条向量、共享同一 unit_id，并带 segment_index / segment_count / char_offset；
  检索按 unit_id 去重，取该单元下得分最高的段。
- 融合：RRF（k=60）。BM25 与向量两路统一用全局 doc_id（= 单元在可用集合里的序号）当键，
  两边编号同源，避免张冠李戴。本脚本只读 kb/l6/ 下的索引，不写盘、不外联。
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

import argparse, json, math, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
BM25_DIR = os.path.join(HERE, "bm25")
VEC_DIR = os.path.join(HERE, "vectors")
TOKENIZER_VERSION = "l6-tok-0.1"
SEGMENTER_VERSION = "l6-seg-0.1"
SEG_MAX_TOKENS = 120            # 模型实测在 128 token 截断，留余量
RRF_K = 60

# ── 依据优先：规则性字段的融合/打分权重（2026-09-30 加，附实测依据）────────────
# 实测问题：查 "hospital grade pump" 时，判定该用语违规的规则（M05 词表单元，69 字、
# tf_en={grade:3,hospital:1}）BM25 得分 10.198、**排第 52**，而 Top8 全是同时含
# hospital/grade/pump 三个词的散文（广告 Primary Text 与刚纳入的英文育儿书 4000 字块）。
# 机制不是索引坏了：规则是一张**关键词清单**，它没有 "pump" 这个词，
# 于是凡三个词全中的散文都赢它 —— 查询词里只要有一个泛词，短规则单元必输。
#
# 处置：给「规则性字段」的单元在 BM25 打分与 RRF 融合上各乘一个权重，把**依据**抬到**素材**前面。
# 权重只乘一次、只作用在字段角色上，不改倒排、不改分词、不改索引文件（纯读侧，可随时关）。
# 定 1.5 的依据（离线模拟 + 冻结判定集，w=1.0 → 1.5）：
#   · 14 条查询 Top3 相关合计 8 → 14，**无一条退化**
#   · 失败的 "hospital grade pump" 0 → 2（Top3 变成 命中片段 单元，直接点名 M05:hospital grade）
#   · 「无痛吸奶」0→1、「绝对安全承诺」0→2、「FDA approved claims」2→3
#   · B 组（库外问题，考拒答）三条模式**仍是全 0** —— 拒答行为不变
# 关掉：--no-field-weight 或 L6_NO_FIELD_WEIGHT=1（回退到 w=1.0 的老行为）。
FIELD_WEIGHT = 1.5
RULE_FIELDS = {"检测关键词", "边界内容", "豁免词", "正则表达式", "风险表达模式", "命中规则",
               "命中片段", "命中原因", "修改建议", "判定理由", "建议表达（合规话术）",
               "触发原因", "风险原句示例", "修订内容", "修订原因", "原文逐字"}
_FW_ON = not (("--no-field-weight" in sys.argv) or os.environ.get("L6_NO_FIELD_WEIGHT") == "1")


def field_name(d):
    """取单元的末级字段名：优先 heading_path 末段（'#表/记录/字段'），否则 meta.field_name。"""
    hp = (d or {}).get("heading_path") or ""
    if hp:
        return str(hp).rstrip("/").split("/")[-1]
    return str(((d or {}).get("field_name") or ""))


def field_weight(d):
    return FIELD_WEIGHT if (_FW_ON and field_name(d) in RULE_FIELDS) else 1.0
K1, B = 1.2, 0.75

# ---------------- 分语言切法 ----------------
CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
              (0x3040, 0x30FF), (0xAC00, 0xD7AF), (0x20000, 0x2FA1F))
WORD_RE = re.compile(r"[0-9A-Za-z\u00C0-\u024F]+")


def is_cjk(ch):
    o = ord(ch)
    return any(a <= o <= b for a, b in CJK_RANGES)


def light_stem(w):
    """英文轻词干：保守剥离常见后缀，避免过度归并。"""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("sses"):
        return w[:-2]
    if len(w) > 4 and w.endswith(("ches", "shes", "xes", "zes", "ses")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "as")):
        w = w[:-1]
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    if len(w) > 5 and w.endswith("ly"):
        w = w[:-2]
    return w


def tokenize(text):
    """→ (zh_tokens, en_tokens)。中英混排按字符类别分段，各用各的切法。"""
    t = unicodedata.normalize("NFKC", text or "").lower()
    zh, en = [], []
    i, n = 0, len(t)
    while i < n:
        ch = t[i]
        if is_cjk(ch):
            j = i
            while j < n and is_cjk(t[j]):
                j += 1
            run = t[i:j]
            if len(run) == 1:
                zh.append(run)                      # 单字段：退化为 unigram，否则 bigram 为空
            else:
                zh.extend(run[k:k + 2] for k in range(len(run) - 1))
            i = j
        elif WORD_RE.match(ch):
            j = i
            while j < n and (WORD_RE.match(t[j]) or t[j] in "'’"):
                j += 1
            for w in re.split(r"['’]", t[i:j]):
                w = w.strip()
                if len(w) >= 2:
                    en.append(w if w.isdigit() else light_stem(w))
            i = j
        else:
            i += 1
    return zh, en


# ---------------- 分段（建索引时用；不许截断） ----------------
SENT_END = "。！？!?；;"


def split_sentences(text):
    """切成「句/段」小块，**保证所有块顺序拼接后逐字等于原文**（一个字符都不丢）。
    换行与句末标点都留在前一块的末尾。返回 [(char_offset, chunk)]。"""
    text = text or ""
    chunks, i, n, start = [], 0, len(text), 0
    while i < n:
        ch = text[i]
        if ch == "\n":
            j = i
            while j < n and text[j] == "\n":
                j += 1
            chunks.append(text[start:j] if start < i else text[i:j])
            start = i = j
            continue
        if ch in SENT_END:
            j = i
            while j < n and text[j] in SENT_END:
                j += 1
            chunks.append(text[start:j])
            start = i = j
            continue
        if ch == "." and i + 1 < n and text[i + 1] in " \n\t":
            chunks.append(text[start:i + 1])
            start = i + 1
        i += 1
    if start < n:
        chunks.append(text[start:])
    out, off = [], 0
    for c in chunks:
        out.append((off, c))
        off += len(c)
    return out


def _hard_split(s, count_tokens, max_tokens):
    """单句就超限时按字符硬切：二分找最长的合法前缀，保证推进、不丢内容。"""
    parts = []
    while s:
        lo, hi, best = 1, len(s), 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if count_tokens(s[:mid]) <= max_tokens:
                best, lo = mid, mid + 1
            else:
                hi = mid - 1
        best = max(best, 1)
        parts.append(s[:best])
        s = s[best:]
    return parts


def segment_text(text, count_tokens, max_tokens=SEG_MAX_TOKENS):
    """按段落/句边界贪心打包成 ≤max_tokens 的段；单句超限则按 token 硬切。
    不截断：各段顺序拼接后逐字等于原文（integrity 里逐单元核对）。
    返回 [{"segment_index","char_offset","text","token_count","hard_split"}...]"""
    text = text or ""
    segs, cur, cur_off, cur_hard = [], "", 0, False
    for off, chunk in split_sentences(text):
        if not chunk.strip():                     # 纯空白块：并入当前段，不单独成段
            if not cur:
                cur, cur_off = chunk, off
            else:
                cur += chunk
            continue
        if count_tokens(chunk) <= max_tokens:
            pieces, hard = [chunk], False
        else:
            pieces = _hard_split(chunk, count_tokens, max_tokens)
            hard = len(pieces) > 1
        p_off = off
        for piece in pieces:
            if cur and count_tokens(cur + piece) > max_tokens:
                segs.append((cur_off, cur, cur_hard))
                cur, cur_off, cur_hard = piece, p_off, hard
            else:
                if not cur:
                    cur, cur_off = piece, p_off
                else:
                    cur += piece
                cur_hard = cur_hard or hard
            p_off += len(piece)
    if cur:
        segs.append((cur_off, cur, cur_hard))
    out = []
    for i, (off, seg, hard) in enumerate(segs):
        out.append({"segment_index": i, "char_offset": int(off), "text": seg,
                    "token_count": int(count_tokens(seg)), "hard_split": bool(hard)})
    return out


# ---------------- BM25（自实现倒排） ----------------
class BM25:
    algorithm = "自实现倒排（无 jieba / 无 rank_bm25）"

    def __init__(self, bm25_dir=BM25_DIR):
        self.meta = json.load(open(os.path.join(bm25_dir, "meta.json"), encoding="utf-8"))
        self.docs = [json.loads(l) for l in open(os.path.join(bm25_dir, "docs.jsonl"),
                                                 encoding="utf-8") if l.strip()]
        self.post = {}
        for lang in ("zh", "en"):
            p = os.path.join(bm25_dir, f"postings_{lang}.jsonl")
            self.post[lang] = {r["term"]: r for r in
                               (json.loads(l) for l in open(p, encoding="utf-8") if l.strip())}

    def search_lang(self, terms, lang, allow):
        post, docs = self.post[lang], self.docs
        N = self.meta[f"N_{lang}"]
        avgdl = self.meta[f"avgdl_{lang}"] or 1.0
        scores = {}
        for term in terms:
            e = post.get(term)
            if not e:
                continue
            df = e["df"]
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            for did, tf in e["postings"]:
                d = docs[did]
                if allow is not None and d["unit_id"] not in allow:
                    continue
                dl = d[f"dl_{lang}"] or 1.0
                s = idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / avgdl))
                scores[did] = scores.get(did, 0.0) + s * field_weight(d)
        return sorted(scores.items(), key=lambda x: (-x[1], x[0]))

    def search(self, query, allow=None, lang="auto"):
        zh_q, en_q = tokenize(query)
        out = {}
        if lang in ("auto", "zh") and zh_q:
            out["bm25_zh"] = [(d, s, {}) for d, s in self.search_lang(zh_q, "zh", allow)]
        if lang in ("auto", "en") and en_q:
            out["bm25_en"] = [(d, s, {}) for d, s in self.search_lang(en_q, "en", allow)]
        return out


# ---------------- 向量（按段存，按单元去重） ----------------
class Vectors:
    def __init__(self, vec_dir=VEC_DIR):
        import numpy as np
        self.meta = json.load(open(os.path.join(vec_dir, "meta.json"), encoding="utf-8"))
        self.rows = [json.loads(l) for l in open(os.path.join(vec_dir, "vectors.jsonl"),
                                                 encoding="utf-8") if l.strip()]
        self.M = np.load(os.path.join(vec_dir, "matrix.npy"))
        self.model = None

    def _load_model(self):
        from fastembed import TextEmbedding
        cache = self.meta.get("cache_dir")
        kw = {"cache_dir": cache} if cache and os.path.isdir(cache) else {}
        self.model = TextEmbedding(model_name=self.meta["model"], **kw)

    def search(self, query, top=50, allow=None):
        """返回 [(doc_id, 余弦分, {"segment_index","char_offset","segment_count"})]，
        同一 unit 只保留得分最高的段。"""
        import numpy as np
        if self.model is None:
            self._load_model()
        q = np.array(list(self.model.embed([query]))[0], dtype="float32")
        nq = float(np.linalg.norm(q))
        if not np.isfinite(nq) or nq == 0:
            return []                       # 模型给出零向量/非有限值：不猜，返回空
        q = q / nq
        # macOS Accelerate 的 BLAS 对这类尺寸会误报 divide-by-zero/overflow/invalid，
        # 实测输出全有限、与逐行点积最大差 5.6e-17，故局部屏蔽；真出现非有限值则退回逐行。
        with np.errstate(all="ignore"):
            s = self.M @ q
        if not np.isfinite(s).all():
            s = np.array([float(np.dot(row, q)) for row in self.M])
        out, seen = [], set()
        for i in np.argsort(-s):
            r = self.rows[int(i)]
            uid = r["unit_id"]
            if uid in seen:
                continue
            if allow is not None and uid not in allow:
                continue
            seen.add(uid)
            out.append((int(r["doc_id"]), float(s[i]),
                        {"segment_index": r["segment_index"], "char_offset": r["char_offset"],
                         "segment_count": r["segment_count"]}))
            if len(out) >= top:
                break
        return out


def rrf(lists, docs=None):
    """lists: {来源名: [(doc_id, 原始分, extra), ...]} → [(doc_id, RRF分, {来源: 名次}, extra)]

    融合侧同样乘 field_weight：只改 BM25 打分救不了「规则单元根本没进候选表」的情形，
    而两路都乘权重才能把依据稳定抬起来（见 RRF_K 上方那段实测）。
    docs 省略时（如自测里的合成数据）权重按 1.0 处理。
    """
    acc = {}
    for name, lst in lists.items():
        for rank, (did, _s, extra) in enumerate(lst, start=1):
            a = acc.setdefault(did, {"score": 0.0, "ranks": {}, "extra": {}})
            w = 1.0
            if docs is not None:
                try:
                    w = field_weight(docs[did])   # bm.docs 是**按 doc_id 下标的 list**，不是 dict
                except (KeyError, IndexError, TypeError):
                    w = 1.0
            a["score"] += w / (RRF_K + rank)
            a["ranks"][name] = rank
            if extra:
                a["extra"][name] = extra
    return sorted(((did, a["score"], a["ranks"], a["extra"]) for did, a in acc.items()),
                  key=lambda x: (-x[1], x[0]))


# ---------------- 对外检索入口 ----------------
def detect_mode(mode):
    if mode == "auto":
        return "hybrid" if os.path.exists(os.path.join(VEC_DIR, "matrix.npy")) else "bm25_only"
    return mode


def search(query, top=5, mode="auto", lang="auto", kb_type=None, bm25=None, vec=None):
    mode = detect_mode(mode)
    bm = bm25 if bm25 is not None else BM25()
    allow = None
    if kb_type:
        allow = {d["unit_id"] for d in bm.docs if d["kb_type"] == kb_type}
    lists = {}
    if mode in ("bm25_only", "hybrid"):
        lists.update(bm.search(query, allow=allow, lang=lang))
    if mode in ("vector_only", "hybrid"):
        if vec is None:
            vec = Vectors()
        lists["vector"] = vec.search(query, top=max(50, top * 10), allow=allow)
    fused = rrf(lists, docs=bm.docs)[:top]
    res = []
    for rank, (did, score, ranks, extra) in enumerate(fused, start=1):
        d = bm.docs[did]
        row = {
            "rank": rank, "score": round(score, 6), "sources": ranks, "match_mode": mode,
            "unit_id": d["unit_id"], "kb_type": d["kb_type"], "anchor": d["anchor"],
            "source_sha256": d["source_sha256"], "table": d["table"], "lang": d["lang"],
            "text_excerpt": d["text_excerpt"],
        }
        if "vector" in extra:
            row.update({"segment_index": extra["vector"]["segment_index"],
                        "segment_count": extra["vector"]["segment_count"],
                        "char_offset": extra["vector"]["char_offset"]})
        res.append(row)
    return {"query": query, "mode": mode, "lang": lang, "top": top,
            "lists_used": sorted(lists.keys()),
            "bm25_algorithm": BM25.algorithm, "results": res}


def selftest():
    """单元自测：切法 / 分段不丢内容 / RRF / 编号一致性。不写盘、不外联。"""
    ok = True
    print(f"tokenizer={TOKENIZER_VERSION} segmenter={SEGMENTER_VERSION} seg_max_tokens={SEG_MAX_TOKENS}")
    z, e = tokenize("这款吸奶器 more milk 100% safe，宣称疗效")
    print(f"  切法 zh={z}")
    print(f"       en={e}")
    ok &= ("吸奶" in z and "more" in e and "milk" in e and "safe" in e)

    # 分段：不截断 + 拼接回原文
    long_text = "".join(f"第{i}句：这是一段用于测试分段的中文句子。" for i in range(40))
    counter = lambda s: len(s)                       # 假计数器：1 字 1 token
    segs = segment_text(long_text, counter, max_tokens=60)
    joined = "".join(s["text"] for s in segs)
    print(f"  分段 {len(segs)} 段，最长 {max(len(s['text']) for s in segs)} 字，拼接后与原文一致={joined == long_text}")
    cases = ["第一段。\n\n第二段。\n第三段结束", "  \n开头有空行。结尾有换行\n",
             "no punctuation at all " * 30, "混排 mixed 内容。\nSecond line here. " * 20]
    recon = [("".join(x["text"] for x in segment_text(c, counter, max_tokens=60)) == c) for c in cases]
    print(f"  逐字拼接自测（4 种形态：多段/空行/无标点/中英混排）：{recon}")
    ok &= (len(segs) > 1 and joined == long_text and all(s["token_count"] <= 60 for s in segs)
           and [s["segment_index"] for s in segs] == list(range(len(segs)))
           and all(recon))
    segs2 = segment_text("啊" * 200, counter, max_tokens=60)
    print(f"  单句超限硬切 → {len(segs2)} 段，拼接一致={''.join(s['text'] for s in segs2) == '啊' * 200}")
    ok &= ("".join(s["text"] for s in segs2) == "啊" * 200 and len(segs2) == 4)

    f = rrf({"bm25_zh": [(1, 9.9, {}), (2, 8.8, {})],
             "vector": [(2, .9, {"segment_index": 0}), (1, .8, {})]})
    print(f"  RRF → {[(d, round(s, 5), r) for d, s, r, _ in f]}")
    ok &= (f[0][0] in (1, 2) and len(f) == 2 and abs(f[0][1] - (1 / 61 + 1 / 62)) < 1e-9)

    # 编号一致性：向量与 BM25 必须共用同一套 doc_id 空间
    if os.path.exists(os.path.join(VEC_DIR, "vectors.jsonl")) and os.path.exists(os.path.join(BM25_DIR, "docs.jsonl")):
        bm = BM25()
        v = Vectors()
        bydoc = {d["doc_id"]: d["unit_id"] for d in bm.docs}
        mism = [r["row"] for r in v.rows[:2000] if bydoc.get(r["doc_id"]) != r["unit_id"]]
        print(f"  编号一致性：抽查 {min(2000, len(v.rows))} 条向量，doc_id 对不上 BM25 的 {len(mism)} 条")
        ok &= not mism
    print("自测结论：" + ("✅ 通过" if ok else "❌ 不通过"))
    return 0 if ok else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--mode", default="auto",
                    choices=["auto", "bm25_only", "vector_only", "hybrid", "bm25", "vector"])
    ap.add_argument("--lang", default="auto", choices=["auto", "zh", "en"])
    ap.add_argument("--kb-type")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-field-weight", action="store_true",
                    help="关掉「依据优先」的规则性字段权重（回到 w=1.0 的老行为，用于 A/B 对照）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not a.query:
        ap.error("--query 必填（或用 --selftest）")
    mode = {"bm25": "bm25_only", "vector": "vector_only"}.get(a.mode, a.mode)
    out = search(a.query, top=a.top, mode=mode, lang=a.lang, kb_type=a.kb_type)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"查询：{a.query}\n模式：{out['mode']}｜用到：{','.join(out['lists_used'])}｜Top{out['top']}")
        print(f"BM25：{out['bm25_algorithm']}\n")
        for r in out["results"]:
            src = " ".join(f"{k}=#{v}" for k, v in r["sources"].items())
            seg = f"｜段 {r['segment_index']+1}/{r['segment_count']} @{r['char_offset']}" if "segment_index" in r else ""
            print(f"[{r['rank']}] {r['score']:.5f}  {r['unit_id']}  ({src}){seg}")
            print(f"    锚点：{r['anchor']}")
            print(f"    来源：{r['table']}  sha256={r['source_sha256'][:16]}  kb_type={r['kb_type']}  lang={r['lang']}")
            print(f"    正文：{r['text_excerpt'][:120]}")
    sys.exit(0)


if __name__ == "__main__":
    main()
