#!/usr/bin/env python3
"""kb-content-review 的参考实现：按 L7 两段协议跑「查 → 答」。

只读 kb/l0~kb/l6（含 kb/l3 的 article_no），只写 kb/l7/reports 与 stdout。

四层下探（顺序写死）：
  1. P0 确定性匹配  → kb/l5/matcher.py（命中即 BLOCK，不走向量）
  2. 规则层        → kb/l3/candidates/rules.jsonl（按 kb_type + 禁用片段逐字命中）
  3. 单元层        → kb/l6/retriever.py（BM25 主；原始分低于门限时才启用向量补）
  4. 原文层        → 按 anchor 回 kb/l0/records/<表>/<记录>.json 取逐字原文，并核对 source_sha256

用法：
  python3 review.py --text "待审文案"
  python3 review.py --file in.txt --content-type text --position "段落 2"
  python3 review.py --text "..." --json
  python3 review.py --text "..." --report-dir kb/l7/reports
退出码：0 = 有结论（PASS/REVIEW/BLOCK）；3 = 拒答；2 = 用法错
"""
import argparse, glob, hashlib, json, os, re, subprocess, sys, time, unicodedata

#: 库根判定的六件套：一个都不能少（少哪一个，对应那段协议就跑不了）。
#:   l7.json          → 门限 / 受控词表 / 责任人（引用契约与分流规则的来源）
#:   rules.jsonl      → 规则层（条款号 + 禁用表达）
#:   matcher.py       → P0 确定性匹配
#:   retriever.py     → 单元层 BM25 / 向量
#:   output_template.md → 输出模板
#:   kb.json          → 库名映射（引用契约里不许自造库名）
REQUIRED_FILES = (
    ("l7", "registry", "l7.json"),
    ("l3", "candidates", "rules.jsonl"),
    ("l5", "matcher.py"),
    ("l6", "retriever.py"),
    ("l7", "output_template.md"),
    ("l0", "registry", "kb.json"),
)

#: 库根标记（`kb/KB-ROOT.json`）：有它就直接认，不必逐件检查。
ROOT_MARKER = ("KB-ROOT.json",)

#: 已知落点（本机现状；换机器/挪库时用 --kb-root 或 KB_ROOT 覆盖）。
COMMON_ROOTS = [
    os.path.expanduser("~/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"),
    os.path.expanduser("~/.dsh/Momcozy知识库"),
]


def _check_root(path):
    """这个目录算不算库根？返回 (bool, 说明)。"""
    if not path or not os.path.isdir(path):
        return False, "目录不存在"
    kb = os.path.join(path, "kb")
    if not os.path.isdir(kb):
        return False, "没有 kb/ 目录"
    if os.path.exists(os.path.join(kb, *ROOT_MARKER)):
        return True, "有 kb/KB-ROOT.json 标记"
    missing = [os.path.join("kb", *rel) for rel in REQUIRED_FILES
               if not os.path.exists(os.path.join(kb, *rel))]
    if missing:
        # 派生视图（给工作台镜像吃的壳）最容易误判：它顶层也有 _meta/，但只有 3_措辞表达库/。
        if os.path.exists(os.path.join(path, "_meta", "DERIVED.md")) or os.path.exists(
                os.path.join(kb, "_meta", "DERIVED.md")):
            return False, ("这是**派生视图**（服务工作台镜像的壳，见 _meta/DERIVED.md），"
                           "不是权威分层库")
        return False, "缺：" + "、".join(missing[:3]) + ("…" if len(missing) > 3 else "")
    return True, "六件套齐"


def _find_root(start, explicit=None):
    """定位知识库根：--kb-root → KB_ROOT → 已知落点 → 从 start 往上找。

    为什么要这一整套：技能装在全局（`~/.dsh/skills/`）时，脚本位置已经不在知识库内，
    只靠「往上找」会走到别的目录上去 —— 实测撞上过派生视图被误判成库根。所以：
    **先按显式配置找，再按已知落点找，最后才往上找**；都不成才报错，报错里列出试过什么。
    """
    tried = []
    candidates = []
    if explicit:
        candidates.append(("--kb-root", explicit))
    if os.environ.get("KB_ROOT"):
        candidates.append(("环境变量 KB_ROOT", os.environ["KB_ROOT"]))
    for path in COMMON_ROOTS:
        candidates.append(("已知落点", path))
    for label, path in candidates:
        if not path:
            continue
        path = os.path.abspath(os.path.expanduser(path))
        ok, why = _check_root(path)
        tried.append(f"{label}={path} → {why}")
        if ok:
            return path
        # **显式指定的路径无效就直接报错**，不许悄悄换一个库继续跑：
        # 使用者明确说了「用这个库」，静默换成别的库会得到一份看起来正常、其实换了依据的报告，
        # 比报错危险得多。（KB_ROOT 与本机已知落点仍允许继续往下试。）
        if label == "--kb-root":
            raise RuntimeError(
                f"--kb-root 指定的目录不是知识库根：{path}\n  原因：{why}\n"
                "  库根要含 kb/KB-ROOT.json 或 l0…l7 六件套齐全；派生视图（只有 "
                "3_措辞表达库/ + _meta/DERIVED.md 的壳）不算库根。"
            )
        # **显式指定的路径无效就直接报错**，不许悄悄换一个库继续跑：
        # 使用者明确说了「用这个库」，静默换成别的库会得到一份看起来正常、其实换了依据的报告，
        # 比报错危险得多。（KB_ROOT 与本机已知落点仍允许继续往下试。）
        if label == "--kb-root":
            raise RuntimeError(
                f"--kb-root 指定的目录不是知识库根：{path}\n  原因：{why}\n"
                "  库根要含 kb/KB-ROOT.json 或 l0…l7 六件套齐全；派生视图（只有 "
                "3_措辞表达库/ + _meta/DERIVED.md 的壳）不算库根。"
            )
    d = os.path.abspath(start)
    while True:
        ok, why = _check_root(d)
        tried.append(f"向上查找={d} → {why}")
        if ok:
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    raise RuntimeError(
        "找不到知识库根目录（要能找到 <根>/kb/l0…l7）。试过：\n  "
        + "\n  ".join(tried)
        + "\n用 --kb-root <知识库根> 或环境变量 KB_ROOT 指定（根目录要含 kb/ 与 l0…l7 这几层）。"
    )


# 模块级 ROOT 只做「尽力而为」：import 期拿不到库不算错（别的工具 import 本模块不该因此挂），
# 真正要用库时（main 开头）会再解析一次，失败就带全景报错。
try:
    ROOT = _find_root(os.path.dirname(os.path.abspath(__file__)))
except RuntimeError:
    ROOT = None
L7 = os.path.join(ROOT, "kb", "l7")
REG_PATH = os.path.join(L7, "registry", "l7.json")
RULES = os.path.join(ROOT, "kb", "l3", "candidates", "rules.jsonl")
MATCHER = os.path.join(ROOT, "kb", "l5", "matcher.py")
L6REG = os.path.join(ROOT, "kb", "l6", "registry", "l6.json")


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip().casefold()


def load_registry():
    return json.load(open(REG_PATH, encoding="utf-8"))


def load_rules():
    latest = {}
    for l in open(RULES, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            latest[r["rule_id"]] = r
    return latest


# ---------------- 分类：受控词表 ----------------
def classify(rule, vocab):
    code = (rule.get("rule_code") or "").strip()
    if code and code in vocab["code_map"]:
        return vocab["code_map"][code], f"rule_code={code}"
    blob = " ".join(str(rule.get(k) or "") for k in ("rule_text", "reason", "suggested_replacement"))
    for pat, cat, sub in vocab["keyword_map"]:
        if re.search(pat, blob, re.IGNORECASE):
            return [cat, sub], f"keyword_map:{pat}"
    return list(vocab["categories"]["未分类"]["subs"].keys())[0:1] + [] if False else ["未分类", "未分类"], "fallback"


# ---------------- 第 1 层：P0 ----------------
def layer_p0(text):
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, MATCHER, "--text", text, "--json"],
                       capture_output=True, text=True)
    elapsed = (time.perf_counter() - t0) * 1000
    out = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"hits": [], "elapsed_ms": None}
    return {"engine": "kb/l5/matcher.py", "exit_code": p.returncode,
            "total_elapsed_ms": round(elapsed, 2), "engine_elapsed_ms": out.get("elapsed_ms"),
            "hits": out.get("hits", [])}


# ---------------- 第 2 层：规则层 ----------------
def layer_rules(text, rules, kb_type=None):
    tn = norm(text)
    hits = []
    for rid, r in rules.items():
        if kb_type and r.get("kb_type") != kb_type:
            continue
        frags = [x.strip() for x in re.split(r"[,，;；]", r.get("forbidden_expression") or "") if x.strip()]
        matched = []
        for f in frags:
            fn = norm(f)
            if not fn:
                continue
            if re.search(r"[0-9A-Za-z]", fn):
                if re.search(r"(?<![0-9A-Za-z])" + re.escape(fn) + r"(?![0-9A-Za-z])", tn):
                    matched.append(f)
            elif fn in tn:
                matched.append(f)
        if matched:
            hits.append({"rule_id": rid, "article_no": r.get("article_no"), "rule_code": r.get("rule_code"),
                         "p_level": r.get("p_level"), "risk_level": r.get("risk_level"),
                         "authority": r.get("authority"), "kb_type": r.get("kb_type"),
                         "authority_source_table": r.get("authority_source_table"),
                         "matched_fragments": matched[:8], "anchor": r.get("anchor"),
                         "source_sha256": (r.get("evidence_units") or [{}])[0].get("source_sha256"),
                         "rule_text": r.get("rule_text"), "suggested_replacement": r.get("suggested_replacement")})
    return {"engine": "kb/l3/candidates/rules.jsonl", "kb_type_filter": kb_type,
            "rules_scanned": len(rules), "hits": hits}


# ---------------- 第 3 层：单元层（BM25 主 / 向量补） ----------------
def rule_cited_anchors(rules):
    """被规则引用过的证据锚点集合 —— 用来判断检索到的材料是不是「知识库确实管这块」。"""
    out = set()
    for r in rules.values():
        for u in r.get("evidence_units") or []:
            if u.get("anchor"):
                out.add(u["anchor"])
        if r.get("anchor"):
            out.add(r["anchor"])
    return out


def layer_units(text, reg, top=5):
    import importlib.util
    spec = importlib.util.spec_from_file_location("l6_retriever", os.path.join(ROOT, "kb", "l6", "retriever.py"))
    RT = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(RT)
    l6 = json.load(open(L6REG, encoding="utf-8"))["retrieval_capability"]
    mode_l6 = l6["mode"]
    semantic = bool(l6["semantic_recall"])
    gate = reg["retrieval"]["gate"]
    bm = RT.BM25()
    raw = []
    for name, lst in bm.search(text).items():
        for did, sc, _ in lst[:top]:
            d = bm.docs[did]
            raw.append({"source": name, "unit_id": d["unit_id"], "anchor": d["anchor"],
                        "table": d["table"], "kb_type": d["kb_type"],
                        "source_sha256": d["source_sha256"], "raw_bm25": round(sc, 4),
                        "excerpt": d["text_excerpt"][:200]})
    raw.sort(key=lambda x: -x["raw_bm25"])
    raw = raw[:top]
    bm25_max = raw[0]["raw_bm25"] if raw else 0.0
    used_vector = False
    vec_rows = []
    if bm25_max < gate["bm25_raw_min"] and semantic:
        used_vector = True
        vec = RT.Vectors()
        for did, sc, extra in vec.search(text, top=top):
            d = bm.docs[did]
            vec_rows.append({"source": "vector", "unit_id": d["unit_id"], "anchor": d["anchor"],
                             "table": d["table"], "kb_type": d["kb_type"],
                             "source_sha256": d["source_sha256"], "cosine": round(sc, 4),
                             "segment_index": extra.get("segment_index"),
                             "char_offset": extra.get("char_offset"), "excerpt": d["text_excerpt"][:200]})
        vec_rows.sort(key=lambda x: -x["cosine"])
    cos_max = vec_rows[0]["cosine"] if vec_rows else 0.0
    adopted, discarded = [], []
    for row in raw:
        ok = row["raw_bm25"] >= gate["bm25_raw_min"]
        (adopted if ok else discarded).append(
            {**row, "verdict": "≥ 门限" if ok else "低于门限",
             "reason": "原始分过门限 → 可作参考/待规则层确认" if ok else
                       f"原始分 {row['raw_bm25']} < {gate['bm25_raw_min']}，只能标参考"})
    for row in vec_rows:
        ok = row["cosine"] >= gate["vector_cosine_min"]
        (adopted if ok else discarded).append(
            {**row, "verdict": "≥ 门限（向量）" if ok else "低于门限（向量）",
             "reason": "余弦过门限 → 可作参考/待规则层确认" if ok else
                       f"余弦 {row['cosine']} < {gate['vector_cosine_min']}，只能标参考"})
    return {"engine": "kb/l6/retriever.py", "l6_mode": mode_l6, "semantic_recall": semantic,
            "bm25_max": bm25_max, "cosine_max": cos_max,
            "used_vector": used_vector,
            "no_semantic_annotation": None if semantic else "无语义召回（L6 为 bm25_only，本次结论不含语义检索）",
            "top_bm25": raw, "vector_rows": vec_rows,
            "adopted": adopted, "discarded": discarded, "gate": gate}


# ---------------- 第 4 层：原文层 ----------------
def resolve_anchor(anchor, sha):
    """anchor: #表名/记录id/字段名 → 回 kb/l0/records 取逐字原文；找不到就返回 None（不猜）。"""
    if not anchor or not anchor.startswith("#"):
        return None
    parts = anchor[1:].split("/")
    if len(parts) < 3:
        return None
    table, rec, field = parts[0], parts[1], "/".join(parts[2:])
    base = os.path.join(ROOT, "kb", "l0", "records")
    cands = []
    if os.path.isdir(os.path.join(base, table)):
        cands.append(os.path.join(base, table, f"{rec}.json"))
    for d in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        p = os.path.join(base, d, f"{rec}.json")
        if os.path.exists(p) and p not in cands:
            cands.append(p)
    for p in cands:
        try:
            recj = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        f = (recj.get("fields") or {}).get(field)
        if f is None:
            continue
        val = f.get("value")
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        if val is None:
            continue
        return {"path": os.path.relpath(p, ROOT), "record_id": recj.get("record_id"),
                "source_table": recj.get("source_table"), "field": field,
                "verbatim": str(val), "raw_verbatim": str(f.get("raw_verbatim") or val),
                "observed_at": recj.get("observed_at")}
    return None


def best_span(verbatim, excerpt, maxlen=60):
    """在原文里取一段仍属逐字的片段（含命中词，两端按标点/空白收边），便于人核对。"""
    v = verbatim or ""
    i = v.casefold().find((excerpt or "").casefold())
    if i < 0:
        return excerpt
    lo = max(0, i - maxlen // 2)
    hi = min(len(v), i + len(excerpt) + maxlen // 2)
    found = False
    for sep in ("。", "\n", "；", ";", "|", "，"):
        j = v.rfind(sep, lo, i)
        if j >= 0:
            lo = j + len(sep)
            found = True
            break
    if not found and lo > 0:
        # 窗口内没有分隔符时，改到**全串范围内最近的分隔符**（含空格）再收边。
        # 否则会从词中间截断 —— 实测把「H02:increase…」切成「02:increase…」，读起来像另一个词。
        for sep in ("。", "\n", "；", ";", "|", "，", " "):
            j = v.rfind(sep, 0, i)
            if j >= 0:
                lo = j + len(sep)
                break
        else:
            lo = 0
    for sep in ("。", "\n", "；", ";", "|"):
        j = v.find(sep, i + len(excerpt), hi)
        if j >= 0:
            hi = j + len(sep)
            break
    span = v[lo:hi].strip()
    # 收边后仍然过长（说明一路没有分隔符）就退回原窗口，避免输出一大段
    limit = len(excerpt) + maxlen * 2
    return span if len(span) <= limit else v[max(0, i - maxlen // 2):hi].strip()


def resolve_excerpt(rule, excerpt, preferred=None):
    """在规则的证据单元里找「原文逐字含该摘录」的那个锚点。
    规则会把很多来源记录的片段汇总在一起，规则自己的 anchor（= 第一个证据单元）不一定含这段，
    所以必须逐个证据单元找，找到才引用；一个都找不到就返回 None（该结论按硬闸门不输出）。"""
    cands = []
    if preferred:
        cands.append({"anchor": preferred, "source_sha256": None})
    for u in rule.get("evidence_units") or []:
        cands.append({"anchor": u.get("anchor"), "source_sha256": u.get("source_sha256")})
    cands.append({"anchor": rule.get("anchor"), "source_sha256": None})
    # 按「字段是否在记录违规」稳定排序：命中片段/检测关键词 优先于 修改建议。
    # 稳定排序保证同优先级内仍按原顺序（preferred → evidence_units → rule.anchor）。
    cands = sorted(cands, key=lambda c: _anchor_field_rank(c.get("anchor")))
    seen = set()
    for c in cands:
        a = c.get("anchor")
        if not a or a in seen:
            continue
        seen.add(a)
        src = resolve_anchor(a, c.get("source_sha256"))
        if src and verify_excerpt(src["verbatim"], excerpt):
            return {**src, "anchor": a, "source_sha256": c.get("source_sha256") or
                    next((u.get("source_sha256") for u in (rule.get("evidence_units") or [])
                          if u.get("anchor") == a), None)}
    return None


def verify_excerpt(verbatim, excerpt):
    """摘录必须能在原文里逐字找到（NFKC + 空白折叠后比对，不做任何改写）。"""
    v, e = norm(verbatim), norm(excerpt)
    return bool(e) and e in v


# ---------------- 出处字段优先级（让摘录落在「记录违规」的字段上）----------------
#
# 为什么需要：同一个记录有多个字段，`命中片段` 是「记录了哪个词违规」，
# `修改建议` 是「怎么改」。若优先解析到 `修改建议`，摘录就会取到改法文本的中间一段，
# 输出成「否则删除（折扣百分比不在此列） ▸ 删除 pain-free/…」这种读不懂的碎片。
# 所以按「是否在记录该违规」给字段排优先级。
_DOC_FIELDS = ("命中片段", "检测关键词", "边界内容", "风险原句示例", "禁用表达", "触发词", "原文逐字")
_ADVICE_FIELDS = ("修改建议", "修订位置", "修改意见", "建议")


def _anchor_field_rank(anchor):
    """字段优先级：0 = 记录违规的字段（首选），2 = 改法类字段（次选），1 = 其余。"""
    tail = (anchor or "").rsplit("/", 1)[-1]
    if any(f in tail for f in _DOC_FIELDS):
        return 0
    if any(f in tail for f in _ADVICE_FIELDS):
        return 2
    return 1


# ---------------- 建议：同源检查 ----------------
#
# 为什么要专门做这一步：l3 的 `suggested_replacement` 是**按记录**汇总的字段，一条记录
# 可能同时命中多个规则码，于是这个字段会是「A 规则的改法 ▸ B 规则的改法」这种拼接串
# （实测 W-1.53 的该字段长 2064 字符）。直接截前 300 字符输出，就会出现「给德语词
# schmerzfrei（H07 疼痛功效）的替换建议，开头却是 M03 效果数据的话」——错配在上游数据里，
# 但用户看到的是本 skill 的输出，所以在本层必须拦掉：**对不上就不输出**。

def _rule_lexicon(rule):
    """本规则自己的禁用片段词表（用来判断一段建议是不是在说本规则）。"""
    toks = set()
    for seg in re.split(r"[；;]", rule.get("forbidden_expression") or ""):
        for t in re.split(r"[,，]", seg):
            t = norm(t)
            if len(t) >= 3:
                toks.add(t)
    return toks


def rule_allowance(rule):
    """从规则原文里取「豁免 / 边界允许」表述 —— 规则级、天然同源，不会被别的规则码污染。"""
    rt = rule.get("rule_text") or ""
    m = re.search(r"豁免[：:]\s*([^；;\n]+)", rt)
    if m:
        return m.group(1).strip()
    m = re.search(r"边界允许[：:]\s*([^；;）)\n]+)", rt)
    if m:
        return m.group(1).strip()
    return ""


def same_source_advice(rule, matched_term):
    """给命中片段配**同源**替换建议；对不上就不输出（宁可只给豁免词）。

    来源① 规则原文的豁免/允许表达 —— 与规则同源，最干净。
    来源② `expression_fix_pairs` 里 fragment 与命中片段一致的条目；其 `fix` 是「 ▸ 」
          拼接串，按「 ▸ 」切句后**只保留提到本规则禁用片段的句子**，属于别的规则码的
          句子直接丢弃 —— 这就是「替换文本与片段同源」检查。

    返回 (建议文本, 同源检查说明)。两条来源都拿不到时，建议为空串并说明原因。
    """
    parts, notes, seen_parts = [], [], set()

    def _add(txt):
        key = norm(txt)
        if key and key not in seen_parts:      # 同一句改法会在多组配对里重复出现，去重
            seen_parts.add(key)
            parts.append(txt)

    allow = rule_allowance(rule)
    if allow:
        _add(f"可改为（本规则豁免表达）：{allow}")

    want = norm(matched_term)
    lex = _rule_lexicon(rule)
    pair_hit = kept_total = dropped_total = 0
    for pair in rule.get("expression_fix_pairs") or []:
        frag = norm(pair.get("fragment"))
        if not frag or not (frag == want or want in frag or frag in want):
            continue
        pair_hit += 1
        clauses = [c.strip() for c in (pair.get("fix") or "").split("▸") if c.strip()]
        kept = [c for c in clauses
                if want in norm(c) or any(t in norm(c) for t in lex)]
        kept_total += len(kept)
        dropped_total += len(clauses) - len(kept)
        for c in kept:
            _add(f"记录级改法：{c}")

    if pair_hit:
        notes.append(f"同源检查：{pair_hit} 组配对命中，保留 {kept_total} 句、"
                     f"丢弃 {dropped_total} 句（属其他规则码）"
                     + ("，去重后建议 %d 条" % len(parts) if parts else "，无同源建议可输出"))
    elif allow:
        notes.append("同源检查：无配对命中，建议全部来自规则原文豁免表达")
    if not parts:
        return "", ("；".join(notes) if notes
                    else "同源检查：既无本规则豁免表达，也无同源配对 → 不给建议")
    return " ｜ ".join(parts), "；".join(notes)


# ---------------- 汇编 ----------------
def review(text, content_type="text", position="全文", report_dir=None, run_id=None, top=5):
    # run_id 必须逐次唯一：以前默认写死 "20260923-1500"，每跑一次就覆盖上一次的报告
    # （实测把自测报告 20260923-1500.review.md 覆盖掉了）。默认取当前时间戳。
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    reg = load_registry()
    rules = load_rules()
    vocab = reg["vocabulary"]
    trace = {}
    t_all = time.perf_counter()
    trace["p0"] = layer_p0(text)
    trace["rules"] = layer_rules(text, rules)
    trace["units"] = layer_units(text, reg, top=top)

    findings, unmet = [], []
    p0_rule_ids = set()
    for h in trace["p0"]["hits"]:
        rid = h["rule_id"]
        p0_rule_ids.add(rid)
        r = rules.get(rid, {})
        (cat, sub), basis = classify(r, vocab)
        excerpt = (h["matched"][0]["pattern"] if h.get("matched") else r.get("forbidden_expression") or "")
        src = resolve_excerpt(r, excerpt, preferred=h.get("anchor"))
        if not src:
            unmet.append({"source": "P0", "rule_id": rid, "article_no": r.get("article_no"),
                          "anchor": r.get("anchor"), "excerpt": excerpt[:80],
                          "why": "该规则全部证据单元里都找不到这段摘录的逐字原文"})
            continue
        advice, advice_note = same_source_advice(r, excerpt)
        findings.append({
            "severity": "BLOCK", "layer": "P0 确定性匹配", "category": cat, "sub": sub,
            "position": position, "excerpt": best_span(src["verbatim"], excerpt), "matched_term": excerpt,
            "anchor": src["anchor"], "source_sha256": src.get("source_sha256"),
            "article_no": r.get("article_no"), "rule_id": rid, "rule_code": r.get("rule_code"),
            "kb_type": r.get("kb_type"), "library": reg["citation_contract"]["libraries"].get(
                r.get("kb_type") or "unknown", {}).get("label", "未归类（不猜）"),
            "reason": f"P0 规则命中（{h['match_note']}）：{r.get('reason') or '（来源未给判定理由）'}",
            "advice": advice or None,
            "advice_note": advice_note,
            "fact_or_inference": "事实", "confidence": "高",
            "verbatim_source": {"path": src["path"], "field": src["field"]},
            "classification_basis": basis,
        })

    for h in trace["rules"]["hits"]:
        if h["rule_id"] in p0_rule_ids:
            continue                                     # P0 已覆盖，不重复计
        r = rules[h["rule_id"]]
        (cat, sub), basis = classify(r, vocab)
        if cat == "表述与术语准确性" and sub == "允许表述（安全词）":
            continue                                     # 允许表述命中不算问题
        excerpt = h["matched_fragments"][0]
        src = resolve_excerpt(r, excerpt, preferred=h.get("anchor"))
        if not src:
            unmet.append({"source": "规则层", "rule_id": h["rule_id"], "article_no": h.get("article_no"),
                          "anchor": h.get("anchor"), "excerpt": excerpt[:80],
                          "why": "该规则全部证据单元里都找不到这段摘录的逐字原文"})
            continue
        sev = "BLOCK" if (h["p_level"] == "P0" or h["risk_level"] == "高危·红") else "REVIEW"
        advice, advice_note = same_source_advice(r, excerpt) if sev == "BLOCK" else ("", "")
        findings.append({
            "severity": sev, "layer": "规则层", "category": cat, "sub": sub,
            "position": position, "excerpt": best_span(src["verbatim"], excerpt), "matched_term": excerpt,
            "anchor": src["anchor"], "source_sha256": src.get("source_sha256"), "article_no": r.get("article_no"),
            "rule_id": h["rule_id"], "rule_code": h.get("rule_code"), "kb_type": r.get("kb_type"),
            "library": reg["citation_contract"]["libraries"].get(r.get("kb_type") or "unknown", {}).get("label"),
            "reason": f"逐字命中「{excerpt}」：{r.get('reason') or '（来源未给判定理由）'}"
                      f"（p_level={h['p_level']} risk_level={h['risk_level']} authority={h['authority']}，"
                      f"来源表 {h['authority_source_table']}）",
            "advice": advice or None,
            "advice_note": advice_note,
            "fact_or_inference": "事实", "confidence": "高" if h["authority"] == "expert" else "中",
            "verbatim_source": {"path": src["path"], "field": src["field"]},
            "classification_basis": basis,
        })

    # 去重：同一处文案命中多条同义规则（L3 的修订对规则常有大量近义条目）时合并为一条，
    # 保留严重度最高的一条，并把被合并的条款号记进 merged_articles（可追溯，不静默丢）
    order = {"BLOCK": 0, "REVIEW": 1}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["category"], f["sub"]))
    by_key, merged = {}, {}
    for f in findings:
        k = (f["category"], f["sub"], norm(f.get("matched_term") or f["excerpt"]))
        if k in by_key:
            merged.setdefault(id(by_key[k]), []).append(f["article_no"])
            if f.get("advice") and not by_key[k].get("advice"):
                by_key[k]["advice"] = f["advice"]
            continue
        by_key[k] = f
    findings = list(by_key.values())
    for f in findings:
        m = merged.get(id(f))
        if m:
            f["merged_articles"] = sorted(set(m))

    # 覆盖信号：内容主题是否落在知识库管辖范围内（决定「无问题」是 PASS 还是拒答）
    cited = rule_cited_anchors(rules)
    gate_thr = reg["retrieval"]["gate"]["bm25_raw_min"]
    safe_hits = [h for h in trace["rules"]["hits"]
                 if (vocab["code_map"].get((h.get("rule_code") or "").strip()) or [None, None])[1]
                 == "允许表述（安全词）"]
    cov_thr = reg["retrieval"]["gate"].get("coverage_bm25_min", gate_thr)
    cited_unit_hits = [row for row in trace["units"]["top_bm25"]
                       if row["anchor"] in cited and row["raw_bm25"] >= cov_thr]
    trace["coverage"] = {
        "safe_vocabulary_hits": [h["article_no"] for h in safe_hits][:5],
        "rule_cited_unit_hits": [{"anchor": r["anchor"], "raw_bm25": r["raw_bm25"]} for r in cited_unit_hits][:5],
        "rule_cited_anchor_pool": len(cited), "coverage_bm25_min": cov_thr,
        "why": "PASS 必须建立在「知识库认识这个主题」之上：① 命中允许表述（安全词）规则；"
               f"② 单元层 Top3 里有一条既被规则引用、BM25 原始分又 ≥ {cov_thr}（{gate_thr} 的 2 倍）；"
               "两者都没有 → 拒答（无命中不等于合规）",
    }
    covered = bool(safe_hits or cited_unit_hits)
    n = len(findings)
    if any(f["severity"] == "BLOCK" for f in findings):
        state = "BLOCK"
    elif findings:
        state = "REVIEW"
    else:
        state = "PASS" if covered else "拒答"
    trace["coverage"]["covered"] = covered
    trace["elapsed_ms"] = round((time.perf_counter() - t_all) * 1000, 1)
    return {"state": state, "findings": findings, "unmet_citation": unmet, "trace": trace,
            "registry": {"gate": reg["retrieval"]["gate"], "routing": reg["decision_rules"]["routing"],
                         "approvers": reg["approvers"], "no_hit_semantics": reg["retrieval"]["no_hit_semantics"]},
            "run_id": run_id}


# ---------------- 输出（严格按模板） ----------------
def cite(f, reg):
    ver = "v0（试用版，未发布）"
    url = f"kb/l3/candidates/rules.jsonl#{f['article_no']}"
    return f"《{f['library']} {ver}》第 {f['article_no']} 条（链接：{url}）"


def approve_tail(state, reg):
    ap = reg["approvers"]
    def h(k):
        v = ap.get(k) or {}
        return f"@{v.get('role')}（未配置）" if not v.get("handle") else f"@{v['handle']}"
    return {"PASS": f"未发现已知底线风险，可转交 {h('pass_signoff')} 进行 sign-off",
            "REVIEW": f"建议转 {h('review_reviewers')} 复核。",
            "BLOCK": "请修改后重新提交。"}[state]


def render(result, reg, report_path=None):
    state, fs = result["state"], result["findings"]
    if state == "拒答":
        t = result["trace"]
        u, cov = t["units"], t["coverage"]
        gate_bm = u["gate"]["bm25_raw_min"]
        gate_cos = u["gate"]["vector_cosine_min"]
        cov_thr = cov.get("coverage_bm25_min", gate_bm)
        nhs_key = "hybrid" if (u["used_vector"] and u["semantic_recall"]) else "bm25_only"
        nhs = reg["retrieval"]["no_hit_semantics"][nhs_key]
        lines = ["【审查结论：无法给出结论（拒答）】未检索到可作依据的知识库条目。", "",
                 f"- 查了什么：{json.dumps(result.get('query_words', ''), ensure_ascii=False)}",
                 f"- 用了几种模式：BM25（最高原始分 {u['bm25_max']}）"
                 + (f" ＋向量补召（最高余弦 {u['cosine_max']}）" if u["used_vector"]
                    else f"；向量补召未启用（BM25 最高分已过依据门限 {gate_bm}，没触发补召，本轮无余弦分）"),
                 f"- 逐层为什么没有依据：",
                 f"  1) P0 确定性匹配：{len(t['p0']['hits'])} 命中",
                 f"  2) 规则层：{len(t['rules']['hits'])} 命中 —— 没有规则可以当依据",
                 f"  3) 单元层：BM25 最高 {u['bm25_max']}（依据门限 {gate_bm}，覆盖门限 {cov_thr}）；"
                 f"被规则引用且过覆盖门限的材料 {len(cov['rule_cited_unit_hits'])} 条；"
                 f"命中允许表述（安全词）{len(cov['safe_vocabulary_hits'])} 条",
                 f"  → 结论：没有规则层命中，单元层也没有「知识库确实管这块」的覆盖信号"
                 f"（覆盖门限 {cov_thr} 或安全词），所以既不能给三态结论，也不能说合规",
                 f"- 语义召回标注：{u['no_semantic_annotation'] or '语义召回可用（L6 = vector_plus_bm25）'}",
                 f"- {nhs}"]
        return "\n".join(lines)
    head = {"PASS": "未发现已知底线风险，可转交", "REVIEW": f"共发现 {len(fs)} 处需人工确认。",
            "BLOCK": f"共发现 {len(fs)} 处必须修改。"}[state]
    lines = [f"【审查结论：{state}】{head}"]
    if state == "PASS":
        lines[0] = f"【审查结论：PASS】{approve_tail('PASS', reg)}"
        return "\n".join(lines)
    lines.append("")
    if len(fs) <= 2:
        for i, f in enumerate(fs, 1):
            lines.append(f"{i}.【{f['category']}-{f['sub']}】{f['position']}，{f['excerpt']}")
            lines.append(f"  原因：{f['reason']}")
            lines.append(f"  依据：{cite(f, reg)}")
            lines.append(f"  锚点：{f['anchor']}｜source_sha256：{f['source_sha256']}")
            lines.append(f"  判定：{f['fact_or_inference']}｜置信度：{f['confidence']}")
            if state == "BLOCK" and f.get("advice"):
                lines.append(f"  建议：{f['advice']}")
            if i != len(fs):
                lines.append("")
    else:
        agg = {}
        for f in fs:
            agg[f["category"]] = agg.get(f["category"], 0) + 1
        for k, v in agg.items():
            lines.append(f"· {k}类问题：{v} 个")
        lines.append("")
        lines.append(f"→ 查看完整问题清单与修改建议：{report_path or '（未写报告，见 --report-dir）'}")
    lines.append("")
    lines.append(approve_tail(state, reg))
    return "\n".join(lines)


# ── l8 补丁（2026-09-23）：报告 .md 必须明文落盘 ───────────────────────
# 本机有一层按后缀生效的写封装：python/perl 写 .md 会落盘成 4096 字节前缀信封，
# 宿主侧 Electron/Node 读取者（agent 的 read 工具、工作台镜像器）拿到的是信封、
# 不是文本 —— 报告等于白写。实测证据见 kb/l8/diagnosis.md（E1–E11）与
# kb/l8/docs_repair_20260923-1535.json。所以 .md 一律交给 node 写，并读回断言。
_NODE_WRITE_AND_VERIFY = r"""
const fs = require("fs"), crypto = require("crypto");
const target = process.env.KB_TARGET;
const want = fs.readFileSync(process.env.KB_SOURCE);      // 已经是最终字节
fs.mkdirSync(require("path").dirname(target), { recursive: true });
fs.writeFileSync(target, want);
const got = fs.readFileSync(target);
const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const ok = got.length === want.length && sha(got) === sha(want);
console.log(JSON.stringify({ target, bytes: got.length, ok }));
process.exit(ok ? 0 : 2);
"""


def _resolve_node():
    """找一个能直接跑脚本的 node 运行时（本机 PATH 里没有 node）。"""
    for cand in (os.environ.get("KB_NODE_BIN"),
                 "/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node"):
        if cand and os.path.exists(cand):
            return [cand], {}
    for base in sorted(glob.glob("/Applications/DSH Desktop*.app/Contents/MacOS/*")):
        if os.path.exists(base):
            return [base], {"ELECTRON_RUN_AS_NODE": "1"}
    return [], {}


def write_text_plain(path: str, text: str) -> str:
    """把 text 明文写到 path（.md 专用）。返回实际用的通道名。

    node 通道：写前把内容落到一个非 .md 的临时文件，再由 node 读它、写目标、读回断言。
    没 node 时降级为 python 写盘，并打印警告 —— 那条路 agent 可能读不到这份报告。
    """
    import subprocess, tempfile
    node, extra = _resolve_node()
    if node:
        fd, tmp = tempfile.mkstemp(prefix="kb-review-", suffix=".txt")
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        try:
            env = dict(os.environ, **extra, KB_TARGET=path, KB_SOURCE=tmp)
            proc = subprocess.run([*node, "-e", _NODE_WRITE_AND_VERIFY],
                                  capture_output=True, text=True, env=env)
            if proc.returncode == 0:
                return "node"
            print(f"[warn] node 落盘失败（{proc.returncode}）：{(proc.stderr or proc.stdout).strip()[:200]}")
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    else:
        print("[warn] 找不到 node 运行时（KB_NODE_BIN / ChatGPT / DSH Electron）")
    print("[warn] 降级为 python 写盘：宿主侧 agent 可能读不到这份报告（会被封成信封）")
    open(path, "w", encoding="utf-8").write(text)
    return "python-fallback"


def write_report(result, reg, report_dir, run_id, apply=True):
    path = os.path.join(report_dir, f"{run_id}.review.md")
    fs = result["findings"]
    L = [f"# 内容审查完整问题清单（run_id {run_id}）", "",
         f"结论：**{result['state']}**｜问题数：{len(fs)}｜生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    if result.get("content"):
        L += ["## 送审内容", "", "```", result["content"][:2000], "```", ""]
    L += ["## 问题清单", ""]
    for i, f in enumerate(fs, 1):
        L += [f"### {i}.【{f['category']}-{f['sub']}】{f['position']}", "",
              f"- 引文（逐字）：{f['excerpt']}",
              f"- 原因：{f['reason']}",
              f"- 依据：{cite(f, reg)}",
              f"- 锚点：`{f['anchor']}`",
              f"- source_sha256：`{f['source_sha256']}`",
              f"- 原文出处：`{f['verbatim_source']['path']}` 字段 `{f['verbatim_source']['field']}`",
              f"- 判定：{f['fact_or_inference']}｜置信度：{f['confidence']}",
              f"- 分层：{f['layer']}｜分类依据：{f['classification_basis']}", ""]
        if f.get("advice"):
            L += [f"- 建议：{f['advice']}", ""]
        if f.get("advice_note"):
            # 把「同源检查」的结论写进报告：被丢弃了几句子属于其他规则码的建议，可追溯
            L += [f"- 建议同源检查：{f['advice_note']}", ""]
    if result["unmet_citation"]:
        L += ["## 无法满足引用契约的结论（未输出）", ""]
        for u in result["unmet_citation"]:
            L += [f"- {u['source']}｜{u.get('article_no')}｜{u.get('why')}｜摘录：{u.get('excerpt')}", ""]
    L += ["## 检索轨迹", "", "```json", json.dumps(result["trace"], ensure_ascii=False, indent=1)[:6000], "```", ""]
    body = "\n".join(L)
    # ── 干跑档（l7 补丁 2026-09-29）：不带 --apply 之外的路径，一律先能预演
    # 背景：本 skill 的契约要求「完整清单必须真的写到 reports/」，所以**默认仍落盘**
    # （改默认为干跑会破坏既有契约与 106 份已生成报告的使用方式）；
    # 这里补的是**可预演**能力 —— --dry-run 只打印目标/字节/前 20 行，不写任何文件。
    if not apply:
        print(f"[dry-run] 未落盘。目标：{path}｜{len(body.encode('utf-8'))} 字节｜{len(L)} 行", file=sys.stderr)
        for ln in body.splitlines()[:20]:
            print("  | " + ln, file=sys.stderr)
        if len(L) > 20:
            print(f"  | …（共 {len(L)} 行；加 --apply 或去掉 --dry-run 即落盘）", file=sys.stderr)
        return None
    os.makedirs(report_dir, exist_ok=True)
    channel = write_text_plain(path, body)   # l8 补丁：明文落盘
    # 必须走 stderr：stdout 是 --json 的数据通道，写日志进去会让 json.load / jq 直接崩
    # （实测 `Expecting value: line 1 column 2`，因为日志占掉了第 1 行）。
    print(f"[review] 报告落盘通道：{channel} → {path}", file=sys.stderr)
    return os.path.relpath(path, ROOT)


def main():
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb-root", default=None,
                    help="知识库根（含 kb/ 与 l0…l7 那层）；不给就按 KB_ROOT → 已知落点 → 向上查找")
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--content-type", default="text", choices=["text", "image", "video"])
    ap.add_argument("--position", default=None)
    ap.add_argument("--report-dir", default=os.path.join(L7, "reports"))
    ap.add_argument("--run-id", default=None,
                    help="本次运行的编号，用于报告文件名；省略则取当前时间戳（保证逐次唯一，不互相覆盖）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true",
                    help="干跑：只打印将写入的报告路径/字节数/前 20 行，不落盘（预演用）")
    ap.add_argument("--apply", action="store_true",
                    help="显式落盘（本脚本默认即落盘；此开关为兼容库内 --apply 约定，语义等价）")
    a = ap.parse_args()
    ROOT = _find_root(os.path.dirname(os.path.abspath(__file__)), a.kb_root)
    globals().update({name: os.path.join(ROOT, *rel) for name, rel in {
        "L7": ("kb", "l7"),
        "REG_PATH": ("kb", "l7", "registry", "l7.json"),
        "RULES": ("kb", "l3", "candidates", "rules.jsonl"),
        "MATCHER": ("kb", "l5", "matcher.py"),
        "L6REG": ("kb", "l6", "registry", "l6.json"),
    }.items()})
    if a.file:
        text = open(a.file, encoding="utf-8").read()
    elif a.text is not None:
        text = a.text
    else:
        text = sys.stdin.read()
    pos = a.position or {"text": "全文", "image": "图片 1（#img.1）", "video": "视频 00:00（时间戳锚点）"}[a.content_type]
    reg = load_registry()
    res = review(text, a.content_type, pos, a.report_dir, a.run_id, a.top)
    res["content"] = text
    res["query_words"] = text[:120]
    path = write_report(res, reg, a.report_dir, res["run_id"], apply=not a.dry_run) if (len(res["findings"]) >= 3 or a.report_dir) else None
    rendered = render(res, reg, path)
    if a.json:
        print(json.dumps({**res, "rendered": rendered, "report_path": path}, ensure_ascii=False, indent=1))
    else:
        print(rendered)
        print(f"\n---\n检索轨迹摘要：P0 {len(res['trace']['p0']['hits'])} 命中（{res['trace']['p0']['engine_elapsed_ms']} ms）"
              f"｜规则层 {len(res['trace']['rules']['hits'])} 命中｜单元层 BM25 最高 "
              f"{res['trace']['units']['bm25_max']}（门限 {res['trace']['units']['gate']['bm25_raw_min']}）"
              f"｜向量补召 {'启用' if res['trace']['units']['used_vector'] else '未启用'}"
              f"｜无法满足引用契约 {len(res['unmet_citation'])} 条")
        if path:
            print(f"完整清单：{path}")
        elif a.dry_run:
            print("（--dry-run：报告未落盘；去掉该参数或加 --apply 即落盘）")
    sys.exit(0 if res["state"] in ("PASS", "REVIEW", "BLOCK") else 3)


if __name__ == "__main__":
    main()
