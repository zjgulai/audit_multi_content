#!/usr/bin/env python3
"""L5 自检证据：只读校验，产出 kb/.work/l5_integrity.json。

覆盖 7 项：
 1) l0 / l1 / l2 未被改动（内容指纹 + mtime 上界）
 2) l3 只追加（前 509 行前缀哈希不变）
 3) 每条 pattern 都能回指 rule_id + anchor + source_sha256
 4) 每条 pattern 的词都出自规则本身（literal ⊆ 命中片段；synonym ⊆ rule_text/建议替换）→ 无凭空加词
 5) version discipline（canonical 仍 0 字节、kb_version 仍 v0、versions.jsonl 仍 0 条版本行）
 6) matcher 离线（只读本地文件，无网络依赖）
 7) **P0 规则配置字段**（2026-10-15 加）：每条 P0 模式必须带非空 `content_type` 与 `rule_version`
    （PRD §6.5「适用内容类型」「生效版本」；口径见 `kb/.work/l5_export.py` 顶部两段注释）。
    反向对照：`python3 kb/.work/mutate_rule_config.py`（4 条变异，差分必须**精确**为 {p0_rule_config}，
    且还原后 sha256 逐字节一致）。
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

import hashlib, json, os, re, subprocess, sys, unicodedata
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
L3_V01_LINES = 509
L3_PREFIX_SHA = "780d2a432db775e7"


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip().casefold()


#: ── 增量指纹（2026-10-12 加）────────────────────────────────────────────────
#   为什么：`tree_fp` 原先对**每个文件无条件 sha256**。实测 kb/l0+l1+l2 合计
#   **4432 MB / 10485 文件 ⇒ 5.88s**（tree_fp(l0) 2.87 / (l1) 2.61 / (l2) 0.40），
#   而这是**每单评审都付**的固定开销（L5 闸门 8.6s 的主体）。
#   而 `frozen_layers` 的 **verdict 只用 max_mtime**（`max_mtime < l5_first`），
#   `tree_sha256` 只是**记录**下来的（消费方：`workflow_check` 拿它比 L5 基线）。
#   ⇒ 改法：先比 `size` + `mtime_ns`；两者全同 ⇒ **复用缓存里的 sha256，不读文件**。
#     拼出的 rows 与全量版**逐字节相同** ⇒ `tree_sha256` **不变**（有 --selftest 钉着）。
#   ★ 漏检面（**不藏**）：`size` 与 `mtime_ns` 都相同、内容却变过的文件会被漏掉。
#     兜底：`KB_TREE_FP_FULL=1` 强制全量（日更应带此变量跑一次，作权威基线）。
DIGEST_CACHE = "kb/.work/frozen-digest-cache.json"
_FP_NEW = {}
_FP_STATS = {"reuse": 0, "recompute": 0}


#: 缓存最长寿命（小时）—— 超期则**自动退回全量**重锚定一次。
#   为什么需要它：快路径信 `size`+`mtime_ns`，挡不住「同尺寸＋同 mtime 的内容改动」。
#   ★ 与其去改日更那条 launchd 作业（那是对**工作流**的改动），不如让缓存**自己**老化 ——
#     效果相同（每天至少一次全量真算），但**对工作流零改动**。
#     24h 与日更（每天 03:30）同节奏，不会更疏。
CACHE_MAX_AGE_H = float(os.environ.get("KB_TREE_FP_CACHE_MAX_H") or 24)


def _fingerprint_cache():
    """读缓存。任一条不满足 ⇒ 返回 {} ⇒ **退化为全量**（fail-closed，不静默）：
      · 显式要求全量（`KB_TREE_FP_FULL=1`）
      · 缓存读不到 / 坏掉
      · **缓存超龄**（`full_at` 距今 > `CACHE_MAX_AGE_H`）—— 见上
    """
    if os.environ.get("KB_TREE_FP_FULL"):
        return {}
    try:
        with open(DIGEST_CACHE, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return {}
    fa = d.get("full_at")
    if fa:
        try:
            age_h = (datetime.now() - datetime.strptime(fa, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600.0
            if age_h > CACHE_MAX_AGE_H:
                return {}                                # 超龄 ⇒ 全量重锚定
        except Exception:                                # noqa: BLE001
            return {}                                    # 时间戳读不出 ⇒ 保守走全量
    return (d.get("files") or {})


def tree_fp(d, cache=None):
    """返回形状与旧版**逐字相同**（4 个键）—— 缓存与统计走模块级变量，
    **不进返回值**，免得污染 `l5_integrity.json` 与 `workflow_check` 的既有读数形状。
    """
    rows, total, mtimes = [], 0, []
    for dp, _, fns in os.walk(d):
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, ROOT)
            st = os.stat(p)
            sz = st.st_size
            total += sz
            mtimes.append(st.st_mtime)
            old = (cache or {}).get(rel)
            if (old and old.get("size") == sz
                    and old.get("mtime_ns") == st.st_mtime_ns
                    and old.get("sha256")):
                dig = old["sha256"]                       # 快路径：stat 全同 ⇒ 不读文件
                _FP_STATS["reuse"] += 1
            else:
                dig = sha_file(p)                         # 慢路径：真算
                _FP_STATS["recompute"] += 1
            _FP_NEW[rel] = {"size": sz, "mtime_ns": st.st_mtime_ns, "sha256": dig}
            rows.append(f"{rel}\0{sz}\0{dig}")
    rows.sort()
    h = hashlib.sha256("\n".join(rows).encode()).hexdigest()
    return {"files": len(rows), "bytes": total,
            "tree_sha256": h,
            "max_mtime": datetime.fromtimestamp(max(mtimes)).strftime("%Y-%m-%d %H:%M:%S") if mtimes else None}


ev = {"checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "checks": {}}

# ---- 1) l0/l1/l2 只读
_FP_CACHE = _fingerprint_cache()
frozen = {d: tree_fp(f"kb/{d}", cache=_FP_CACHE) for d in ("l0", "l1", "l2")}
try:                                     # 回写缓存（原子替换）；失败不影响判定
    _tmp = DIGEST_CACHE + ".swtmp"
    with open(_tmp, "w", encoding="utf-8") as _fh:
        _now_s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _was_full = (bool(os.environ.get("KB_TREE_FP_FULL"))
                     or not _FP_CACHE)          # 缓存为空 ⇒ 本次实际就是全量
        _prev_full_at = None
        try:
            with open(DIGEST_CACHE, encoding="utf-8") as _pf:
                _prev_full_at = json.load(_pf).get("full_at")
        except Exception:                       # noqa: BLE001
            pass
        json.dump({"at": _now_s,
                   # `full_at` = **上一次真正全量**的时刻（超龄判定就是比它）
                   "full_at": _now_s if _was_full else _prev_full_at,
                   "full": _was_full,
                   "files": _FP_NEW}, _fh, ensure_ascii=False)
    os.replace(_tmp, DIGEST_CACHE)
except Exception as _e:                  # noqa: BLE001
    print("        ! 指纹缓存回写失败（不影响本次判定）：%s" % _e)
l5_files = []
for dp, _, fns in os.walk("kb/l5"):
    for fn in fns:
        l5_files.append(os.path.join(dp, fn))
l5_first = min(os.path.getmtime(p) for p in l5_files)
ev["checks"]["frozen_layers"] = {
    "layers": frozen,
    "l5_first_write": datetime.fromtimestamp(l5_first).strftime("%Y-%m-%d %H:%M:%S"),
    "verdict": "PASS" if all(datetime.strptime(v["max_mtime"], "%Y-%m-%d %H:%M:%S").timestamp() < l5_first
                             for v in frozen.values()) else "FAIL",
    "note": "l0/l1/l2 全部文件最后修改时间早于 l5 首次写入；且记录内容指纹，供后续阶段比对漂移",
}

# ---- 2) l3 只追加
raw = open("kb/l3/candidates/rules.jsonl", "rb").read().split(b"\n")
if raw and raw[-1] == b"":
    raw.pop()
prefix = b"\n".join(raw[:L3_V01_LINES]) + b"\n"
pre_sha_full = hashlib.sha256(prefix).hexdigest()
pre_sha = pre_sha_full[:16]
# 前置 A 在追加前记录过同一口径的哈希（未追加时整文件 = 这 509 行）
try:
    PREP_BASELINE = json.load(open("kb/.work/l5_prep.json", encoding="utf-8"))["before_sha256"]
except Exception:
    PREP_BASELINE = None
base_rows = [json.loads(l) for l in raw[:L3_V01_LINES]]
new_rows = [json.loads(l) for l in raw[L3_V01_LINES:]]
base_ids = {r["rule_id"] for r in base_rows}
new_ids = {r["rule_id"] for r in new_rows}
structural = {
    "baseline_distiller_version": sorted({str(r.get("distiller_version")) for r in base_rows}),
    "appended_distiller_version": sorted({str(r.get("distiller_version")) for r in new_rows}),
    "baseline_ids_unique": len(base_ids) == len(base_rows),
    "appended_covers_baseline": new_ids == base_ids,
    "baseline_has_expression_fix_pairs": sum(1 for r in base_rows if r.get("expression_fix_pairs")),
    "baseline_has_rule_kind": sum(1 for r in base_rows if "rule_kind" in r),
    "rule_code_filled_in_append": sum(1 for a, b in zip(base_rows, new_rows)
                                      if not a.get("rule_code") and b.get("rule_code")),
    "l3_rule_code_not_unique": {"H07": sum(1 for r in new_rows if r.get("rule_code") == "H07"),
                                "why": "品线内容边界规则库复用同一套规则码（authority=inferred，未进导出）"},
}
ev["checks"]["l3_append_only"] = {
    "lines": len(raw), "baseline_lines": L3_V01_LINES,
    "prefix_sha256_16": pre_sha,
    "prefix_recipe": "前 509 行以 \\n 连接 + 末尾换行，取 sha256",
    "prefix_sha256": pre_sha_full,
    "prep_baseline_sha256": PREP_BASELINE,
    "byte_identical_to_pre_append": pre_sha_full == PREP_BASELINE,
    "stale_note_value": L3_PREFIX_SHA,
    "stale_note_reproduced": pre_sha == L3_PREFIX_SHA,
    "stale_note_explain": "阶段早期笔记里的 780d2a432db775e7 用 8 种候选拼接口径都复算不出来，判为口径未记录的旧值；"
                          "改用前置 A 写入的 before_sha256 作为基线，本次复算逐字节一致",
    "by_version": {str(json.loads(l).get("distiller_version")): 1 for l in raw} and
                  {v: sum(1 for l in raw if str(json.loads(l).get("distiller_version")) == v)
                   for v in {str(json.loads(l).get("distiller_version")) for l in raw}},
    "structural": structural,
    "verdict": "PASS" if (pre_sha_full == PREP_BASELINE
                          and structural["baseline_ids_unique"] and structural["appended_covers_baseline"]
                          and structural["baseline_has_rule_kind"] == 0
                          and sorted(structural["baseline_distiller_version"]) == ["None"]
                          and sorted(structural["appended_distiller_version"]) == ["l3-0.2"]) else "FAIL",
}
cand = {}
for ln in raw:
    r = json.loads(ln)
    cand[r["rule_id"]] = r
ev["checks"]["l3_append_only"]["rules_latest_view"] = len(cand)

# ★ 2026-10-13：pattern 回指要查**两个**候选件。
#   为什么：外部标准规则住 `candidates/external_standard.jsonl`（`rules.jsonl` 是措辞库的件，
#   塞进去会让 `l7_gate` 的 C2「现行规则库名（1）」判不出唯一库名 —— 实测红过）。
#   ⚠️ **不改上面的 `raw` / `cand`** —— 它们同时供 `l3_append_only` 的冻结基线比对
#   （`baseline_has_rule_kind==0` / `baseline_distiller_version==["None"]` 都是按**措辞件**的
#   历史形状判的），混进来会把这个基线判据弄脏。所以另建一个只给回指用的视图。
cand_all = dict(cand)
_p_ext = "kb/l3/candidates/external_standard.jsonl"
if os.path.exists(_p_ext):
    for _ln in open(_p_ext, encoding="utf-8"):
        if _ln.strip():
            _r = json.loads(_ln)
            cand_all[_r["rule_id"]] = _r
ev["pattern_traceability_src"] = {
    "wording": len(cand), "external_standard": len(cand_all) - len(cand),
    "note": "回指查两个候选件；l3_append_only 的基线仍只看措辞件"}
# ⚠️ 放在 `ev` 顶层、**不放 `ev["checks"]`** —— 打印循环 `for k,v in ev["checks"].items()`
#    要求每一项都有 `verdict`，塞进去会 `KeyError: 'verdict'`（实测崩过一次）。
cand = cand_all          # ← 只影响下面的 pattern 回指段

# ---- 3) + 4) pattern 回指与词源
pats = [json.loads(l) for l in open("kb/l5/p0_patterns.jsonl", encoding="utf-8") if l.strip()]
trace_bad, word_bad, rows = [], [], []
for p in pats:
    r = cand.get(p["rule_id"])
    eu = (r or {}).get("evidence_units") or [{}]
    hit = {"pattern_id": p["pattern_id"], "rule_code": p.get("rule_code")}
    if not r:
        trace_bad.append({**hit, "why": "rule_id 在 l3 候选里不存在"})
        continue
    if p["anchor"] != eu[0].get("anchor") or p["source_sha256"] != eu[0].get("source_sha256"):
        trace_bad.append({**hit, "why": "anchor/source_sha256 与规则 evidence_units[0] 不一致"})
    for u in p["evidence_units"]:
        if not (u.get("unit_id") and u.get("anchor") and u.get("source_sha256")):
            trace_bad.append({**hit, "why": "证据三元组缺项"})
            break
    pool_source = norm(r["forbidden_expression"])
    # ★ 2026-10-21：`reason` 也算规则自己的文本（H09 的边界表述住在 `reason` 里）
    pool_rule = norm((r.get("rule_text") or "") + " " + (r.get("suggested_replacement") or "")
                     + " " + (r.get("reason") or ""))
    pool = pool_source + " " + pool_rule
    terms = {m["term"]: m for m in p.get("match_terms") or []}
    for w in p["patterns"]:
        m = terms.get(w)
        if not m:
            word_bad.append({**hit, "word": w, "kind": "no_basis", "why": "进了匹配表但没有词级溯源记录"})
            continue
        b = m.get("basis") or ""
        if b == "verbatim_source" and norm(w) not in pool_source:
            word_bad.append({**hit, "word": w, "kind": b, "why": "自称逐字来自命中片段，实际不在"})
        elif b == "verbatim_rule_text" and norm(w) not in pool_rule:
            word_bad.append({**hit, "word": w, "kind": b, "why": "自称逐字来自规则文本，实际不在"})
        elif b.startswith("equivalent_of:"):
            anc = norm(b.split(":", 1)[1])
            if not anc or anc == norm(w) or anc not in pool:
                word_bad.append({**hit, "word": w, "kind": b,
                                 "why": "等价锚点词不是该规则自己写过的词"})
        elif not b.startswith("verbatim_"):
            word_bad.append({**hit, "word": w, "kind": b or "empty", "why": "basis 非法"})
    rows.append({**hit, "keywords": len(p["patterns"]), "regex": len(p["regex_patterns"]),
                 "whitelist": len(p["whitelist"]), "shared_sha256": p["source_sha256"][:12]})
ev["checks"]["pattern_traceability"] = {
    "patterns": len(pats), "bad": trace_bad,
    "verdict": "PASS" if not trace_bad else "FAIL", "detail": rows,
}
basis_cnt = {}
for p in pats:
    for m in p.get("match_terms") or []:
        basis_cnt[m["basis"].split(":")[0]] = basis_cnt.get(m["basis"].split(":")[0], 0) + 1
ev["checks"]["no_fabricated_words"] = {
    "checked": sum(len(p["patterns"]) for p in pats),
    "basis_distribution": basis_cnt,
    "dropped_ungrounded": sum(len((p.get("variant_sources") or {}).get("dropped_ungrounded") or [])
                              for p in pats),
    "bad": word_bad, "verdict": "PASS" if not word_bad else "FAIL",
    "rule": "匹配表里每个词都必须带 basis，且 basis 要对得上规则原文："
            "verbatim_source（逐字在命中片段里）/ verbatim_rule_text（逐字在 rule_text 或建议替换里）/ "
            "equivalent_of:<锚点词>（锚点词必须是该规则自己写过的词）。对不上即判为凭空加词。",
}

# ---- 5) 版本纪律
canon = os.path.getsize("kb/l4/canonical/rules.jsonl")  # 2026-09-23 由 kb/l3/canonical/ 迁至此处，见 kb/l3/CANONICAL_MOVED.md
vrows = [l for l in open("kb/versions/versions.jsonl", encoding="utf-8")
         if l.strip() and not l.lstrip().startswith("#")]
kbvs, kbv_missing = set(), []
for d in ("l0/registry/kb.json", "l1/registry/l1.json", "l2/registry/l2.json",
          "l3/registry/l3.json", "l5/registry/l5.json"):
    v = json.load(open(f"kb/{d}", encoding="utf-8")).get("kb_version")
    if v is None:
        kbv_missing.append(d)
    kbvs.add(v)
ev["checks"]["version_discipline"] = {
    "canonical_rules_bytes": canon,
    "versions_jsonl_rows": len(vrows),
    "kb_version_values": sorted(x for x in kbvs if x is not None),
    "registries_missing_kb_version": kbv_missing,
    "verdict": "PASS" if canon == 0 and not vrows and {x for x in kbvs if x is not None} == {"v0"} else "FAIL",
}

# ---- 6) 离线
src = open("kb/l5/matcher.py", encoding="utf-8").read()
net = re.findall(r"\b(requests|urllib|socket|http\.client|urlopen|lark|curl|wget)\b", src)
ev["checks"]["offline"] = {"network_symbols_found": sorted(set(net)),
                           "verdict": "PASS" if not net else "FAIL"}

# ---- 7) P0 规则配置字段（PRD §6.5「适用内容类型」「生效版本」）------------------
# ★★ 2026-10-15 加。Owner 当日两条口径落在 `l5_export.py` ⇒ `p0_patterns.jsonl` 每条 P0 模式
#   多两列：`content_type=["全部"]`（原话「内容类型写全部」）、`rule_version="1.0"`
#   （原话「生效版本就是从1.0开始，修改之后再更新迭代版本就好」）。
#
# 为什么必须钉住（**不是预防性设计**）：这两列由 `l5_export.py` 生成，
#   而它每次 `--apply` 都**覆盖写**整张模式表 —— 今后任何一次改 `VARIANTS` / 改导出逻辑，
#   都可能把这两列**静默丢掉**，而本文件原有的 6 项判据**一条都不查它们** ⇒ 丢了照样全绿。
#   这与本库栽过的「判据恒绿、看着像守着」是同一族（见 AGENTS.md 那条）。
#
# 「空」的判据与 `l5_integrity` 别处同口径：`None` / `""` / `[]` / `{}` 都算空。
_missing_ct = [(p.get("rule_code") or p.get("rule_id")) for p in pats
               if not (p.get("content_type") or [])]
_missing_rv = [(p.get("rule_code") or p.get("rule_id")) for p in pats
               if not str(p.get("rule_version") or "").strip()]
_ct_vals = sorted({json.dumps(p.get("content_type"), ensure_ascii=False) for p in pats})
_rv_vals = sorted({str(p.get("rule_version")) for p in pats})
ev["checks"]["p0_rule_config"] = {
    "patterns": len(pats),
    "missing_content_type": sorted(x for x in _missing_ct if x),
    "missing_rule_version": sorted(x for x in _missing_rv if x),
    "content_type_values": _ct_vals,
    "rule_version_values": _rv_vals,
    # ★ 判据：表非空 ＋ 两列**一条都不缺**。空表也算 FAIL（`not pats`）—— 表被清空同样是事故。
    "verdict": "PASS" if (pats and not _missing_ct and not _missing_rv) else "FAIL",
}

ev["verdict"] = "PASS" if all(v.get("verdict") == "PASS" for v in ev["checks"].values()) else "FAIL"
json.dump(ev, open("kb/.work/l5_integrity.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

for k, v in ev["checks"].items():
    print(f"[{v['verdict']}] {k}")
    if k == "frozen_layers":
        for d, x in v["layers"].items():
            print(f"        kb/{d}: {x['files']} 文件 / {x['bytes']} 字节 / tree_sha256={x['tree_sha256'][:16]} / 最后修改 {x['max_mtime']}")
        print(f"        l5 首次写入 {v['l5_first_write']}")
    if k == "l3_append_only":
        print(f"        行数 {v['lines']}，版本分布 {v['by_version']}")
        print(f"        前 {v['baseline_lines']} 行前缀哈希 {v['prefix_sha256_16']}（{v['prefix_recipe']}）")
        print(f"        旧笔记值 {v['stale_note_value']} 可复现={v['stale_note_reproduced']}；{v['stale_note_explain'][:60]}…")
        for kk, vv in v["structural"].items():
            print(f"        {kk}: {vv}")
    if k == "pattern_traceability":
        print(f"        {v['patterns']} 条 pattern 全部回指 rule_id/anchor/source_sha256，异常 {len(v['bad'])}")
    if k == "no_fabricated_words":
        print(f"        校验 {v['checked']} 个词，basis 分布 {v['basis_distribution']}，越界 {len(v['bad'])}，"
              f"剔除凭空词 {v['dropped_ungrounded']}")
        for b in v["bad"][:10]:
            print("        !", b)
    if k == "p0_rule_config":
        print(f"        模式 {v['patterns']} 条 / content_type 取值 {v['content_type_values']} / rule_version 取值 {v['rule_version_values']}")
        if v["missing_content_type"]:
            print(f"        ! 缺 content_type：{v['missing_content_type'][:10]}")
        if v["missing_rule_version"]:
            print(f"        ! 缺 rule_version：{v['missing_rule_version'][:10]}")
    if k == "version_discipline":
        print(f"        canonical {v['canonical_rules_bytes']} 字节 / versions 行 {v['versions_jsonl_rows']} / kb_version {v['kb_version_values']}")
        if v["registries_missing_kb_version"]:
            print(f"        ! 缺 kb_version 字段的 registry：{v['registries_missing_kb_version']}（冻结层，只报不改）")
print(f"\n自检总计：{ev['verdict']}")
sys.exit(0 if ev["verdict"] == "PASS" else 1)
