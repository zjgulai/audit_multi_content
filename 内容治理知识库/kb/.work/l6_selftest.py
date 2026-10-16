#!/usr/bin/env python3
"""L6 自验：A/B 两组查询 × 三种模式（bm25_only / vector_only / hybrid）× Top3。
- A 组：库里确定有对应内容（用库里现成的中英等价说法构造）
- B 组：库里没有对应内容（用来测拒答行为）
判断由人工逐条给（kb/.work/l6_judgments_ab.json），脚本只做汇总，不给"好看"的数字。
用法：
  python3 kb/.work/l6_selftest.py --show-pairs   # 打印所有需要判断的 (查询, 单元) 对（预演，不写盘）
  python3 kb/.work/l6_selftest.py                # ★预演：写 kb/l6/runs/<RUN>-selftest-dryrun.json
  python3 kb/.work/l6_selftest.py --apply        # 真档：汇总出 kb/l6/selftest.json

── 行为变更（批次5，2026-10-01）────────────────────────────────────────────
**本脚本此前「运行即写盘」**（无任何开关，`json.dump` 在计算段之后无条件执行）。
批次5 起照 `kb/.work/l4_report.py` 的样板补 `--apply` 干跑档：

  · 不带 `--apply` = **预演**：**不写** `kb/l6/selftest.json`、**不建** `kb/l6/_archive/`、
    **不归档**上一版；只写 `kb/l6/runs/<RUN>-selftest-dryrun.json`（`dry_run=true` / `applied=false`）。
  · 带 `--apply` = **真档**：归档上一版 → 写 `kb/l6/selftest.json`（`dry_run=false` / `applied=true`）。

**为什么改**（不是顺手重构）：本脚本于批次5 被补登进 `kb/l7/registry/layers.yaml` 的 L6 `engine`。
补登后若它仍是「运行即写盘」，等于在 engine 清单里塞进一个**不可预演的引擎** ——
契约 #3「预演默认，真档要显式 --apply」对它失效，而 engine 清单里的每个成员都该能被预演。

**归档机制不变**：真档仍先归档上一版到 `kb/l6/_archive/selftest.json.<上一版 run_id>`（:168-182 原有逻辑），
只是整段移进 `if APPLY`。

**闸门位次**：干跑闸门（argv 解析 + APPLY 判定）在**所有写之前**（最早的写在文件末尾），
也早于 `kb/l6/_archive` 的 `os.makedirs`。**如实声明一处不完全**：本脚本的计算段
（`RT.Vectors()` / `RT.BM25()` + 14 查询 × 3 模式检索）会读 `kb/l6/bm25/**`、`kb/l6/vectors/**`
并加载 fastembed 模型（读本地模型缓存）—— 那是**只读**，但严格讲模型加载不在本脚本可控范围内。
批次5 已实测：预演档跑完 `kb/l6/**` 全树 sha256 与跑前逐字节一致。

**命名避撞**：预演产物**不叫** `<RUN>-dryrun.json` —— 那个名字归 L6 的落章引擎
`kb/.work/l6_report.py`（它写顶层 `skill` 字段供 `skill_invocation_audit.py` 的 E2 消费）。
同名会互相覆盖、污染 E2/E3/E5 证据。故本脚本用 `<RUN>-selftest-dryrun.json`，
且**不带** `skill`/`skill_id`/`skills` 键 —— 本脚本**不落章**。
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

import importlib.util, json, os, statistics, sys, time

L6 = "kb/l6"

# ── 干跑闸门（批次5 补，2026-10-01）─────────────────────────────────────────
# 本段必须早于本脚本的**第一个副作用**（`kb/l6/_archive` 的 os.makedirs 与两处 'w' 写入，
# 均在文件末尾）。本段自身零写入 —— 只读 argv / 环境变量。
# 见文件头「行为变更」：此前运行即写盘；现在不带 --apply 一律不写 selftest.json。
_AV = list(sys.argv[1:])


def _take(flag):
    """摘取 `--flag v` / `--flag=v` 的值并从 _AV 里删掉（不影响其它开关）。"""
    for i, a in enumerate(_AV):
        if a == flag and i + 1 < len(_AV):
            v = _AV[i + 1]; del _AV[i:i + 2]; return v
        if a.startswith(flag + "="):
            v = a.split("=", 1)[1]; del _AV[i]; return v
    return None


RUN = _take("--run") or os.environ.get("L6_RUN") or "20260923-1440"
APPLY = "--apply" in _AV
if APPLY:
    _AV.remove("--apply")
SHOW = "--show-pairs" in _AV
# ──────────────────────────────────────────────────────────────────────────

spec = importlib.util.spec_from_file_location("l6_retriever", f"{L6}/retriever.py")
RT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RT)

QUERIES = [
    # A 组：库里确定有（中文）
    {"q": "催奶增产", "lang": "zh", "group": "A", "why": "库里有 H02 增产/奶量承诺的处置与命中片段"},
    {"q": "医生推荐背书", "lang": "zh", "group": "A", "why": "库里有检测关键词「医生推荐/医师推荐/专家推荐」与触发原因"},
    {"q": "无痛吸奶", "lang": "zh", "group": "A", "why": "库里有 H07 检测关键词「无痛吸奶」"},
    {"q": "绝对安全承诺", "lang": "zh", "group": "A", "why": "库里有「绝对安全/完全安全/零风险」类检测关键词"},
    # A 组：库里确定有（英文）
    {"q": "FDA approved claims", "lang": "en", "group": "A", "why": "库里有「FDA approved/certified」检测关键词与豁免词"},
    {"q": "hospital grade pump", "lang": "en", "group": "A", "why": "库里有 U03:hospital / M05:hospital-grade 命中片段"},
    {"q": "more milk supply", "lang": "en", "group": "A", "why": "库里有 H02:increasing milk supply 命中片段"},
    {"q": "best-selling", "lang": "en", "group": "A", "why": "库里有 M03:bestseller / Best-Selling 广告原文"},
    # B 组：库里没有（中文）——已核过词元重叠极低且无对应内容
    {"q": "汽车保养周期多久一次", "lang": "zh", "group": "B", "why": "语料里 汽车/保养/机油/轮胎 命中 0"},
    {"q": "基金定投和股票的区别", "lang": "zh", "group": "B", "why": "语料里 基金/定投/股票/理财 命中 0"},
    {"q": "钢琴考级曲目推荐", "lang": "zh", "group": "B", "why": "语料无钢琴考级内容（仅「推荐」这类通用词重叠）"},
    # B 组：库里没有（英文）
    {"q": "best hiking boots for winter", "lang": "en", "group": "B", "why": "语料里 hiking/boots 命中 0"},
    {"q": "python asyncio tutorial", "lang": "en", "group": "B", "why": "语料里 python/asyncio 命中 0"},
    {"q": "how to train for a marathon", "lang": "en", "group": "B", "why": "语料无马拉松训练内容（仅 how/to/for 这类功能词重叠）"},
]
MODES = ["bm25_only", "vector_only", "hybrid"]

JUDGES = json.load(open("kb/.work/l6_judgments_ab.json", encoding="utf-8")) if \
    os.path.exists("kb/.work/l6_judgments_ab.json") else {}

t0 = time.perf_counter()
bm, vec = RT.BM25(), RT.Vectors()
rows, pairs = [], {}
for item in QUERIES:
    per_mode = {}
    for m in MODES:
        out = RT.search(item["q"], top=3, mode=m, bm25=bm, vec=vec)
        per_mode[m] = out
        for r in out["results"]:
            k = f"{item['q']}||{r['unit_id']}"
            pairs.setdefault(k, {"query": item["q"], "group": item["group"], "lang": item["lang"],
                                 "unit_id": r["unit_id"], "anchor": r["anchor"], "table": r["table"],
                                 "kb_type": r["kb_type"],
                                 "excerpt": r["text_excerpt"][:200]})
    # 原始分（未经 RRF）：BM25 原始分 / 余弦分。RRF 分只反映名次，不能用来判「有没有命中」
    raw = {"bm25_max": None, "cosine_max": None}
    bm_lists = bm.search(item["q"])
    raw["bm25_max"] = round(max((s2 for _, lst in bm_lists.items() for _, s2, _ in lst), default=0.0), 4)
    vl = vec.search(item["q"], top=50)
    raw["cosine_max"] = round(max((sc for _, sc, _ in vl), default=0.0), 4)
    rec = {"query": item["q"], "lang": item["lang"], "group": item["group"], "why": item["why"],
           "raw_scores": raw,
           "note": JUDGES.get(item["q"], {}).get("note", ""), "modes": {}}
    for m in MODES:
        top = []
        for r in per_mode[m]["results"]:
            v = JUDGES.get(item["q"], {}).get("verdict", {}).get(r["unit_id"], "unknown")
            top.append({"rank": r["rank"], "unit_id": r["unit_id"], "anchor": r["anchor"],
                        "table": r["table"], "score": r["score"], "sources": r["sources"],
                        "segment_index": r.get("segment_index"),
                        "segment_count": r.get("segment_count"),
                        "char_offset": r.get("char_offset"),
                        "excerpt": r["text_excerpt"][:200], "relevance": v})
        rel = sum(1 for x in top if x["relevance"] == "相关")
        rec["modes"][m] = {"top3": top, "relevant_in_top3": rel,
                           "hit_at_3": (rel > 0) if any(x["relevance"] != "unknown" for x in top) else None,
                           "top1_score": top[0]["score"] if top else None,
                           "lists_used": per_mode[m]["lists_used"]}
    rows.append(rec)

judged = [r for r in rows if all(r["modes"][m]["hit_at_3"] is not None for m in MODES)]


def rate(sel, mode):
    sub = [r for r in sel if r["modes"][mode]["hit_at_3"] is not None]
    if not sub:
        return {"queries": 0, "hit": 0, "hit_rate_at3": None, "precision_at3": None}
    hit = sum(1 for r in sub if r["modes"][mode]["hit_at_3"])
    return {"queries": len(sub), "hit": hit, "hit_rate_at3": round(hit / len(sub), 3),
            "precision_at3": round(sum(r["modes"][mode]["relevant_in_top3"] for r in sub) / (3 * len(sub)), 3)}


summary = {}
for grp in ("A", "B"):
    for lg in ("zh", "en"):
        sel = [r for r in judged if r["group"] == grp and r["lang"] == lg]
        summary[f"{grp}_{lg}"] = {m: rate(sel, m) for m in MODES}
A_all = [r for r in judged if r["group"] == "A"]
B_all = [r for r in judged if r["group"] == "B"]
summary["A_all"] = {m: rate(A_all, m) for m in MODES}
summary["B_all"] = {m: rate(B_all, m) for m in MODES}

# B 组「是否仍拒答」：三种模式都不带阈值 → 一律返回 Top3；这里量化"看起来像命中"的程度
raw_cmp = {}
for grp in ("A", "B"):
    sub = [r for r in judged if r["group"] == grp]
    raw_cmp[grp] = {
        "bm25_max_median": round(statistics.median([r["raw_scores"]["bm25_max"] for r in sub]), 4) if sub else None,
        "cosine_max_median": round(statistics.median([r["raw_scores"]["cosine_max"] for r in sub]), 4) if sub else None,
        "bm25_max_values": {r["query"]: r["raw_scores"]["bm25_max"] for r in sub},
        "cosine_max_values": {r["query"]: r["raw_scores"]["cosine_max"] for r in sub},
    }

b_behavior = {}
for m in MODES:
    sub = [r for r in B_all if r["modes"][m]["top1_score"] is not None]
    sc = [r["modes"][m]["top1_score"] for r in sub]
    a_sc = [r["modes"][m]["top1_score"] for r in A_all if r["modes"][m]["top1_score"] is not None]
    b_behavior[m] = {
        "returns_results": bool(sub), "queries": len(sub),
        "top1_relevant": sum(1 for r in sub if r["modes"][m]["top3"][0]["relevance"] == "相关"),
        "any_relevant_in_top3": sum(1 for r in sub if r["modes"][m]["hit_at_3"]),
        "b_top1_score_median": round(statistics.median(sc), 6) if sc else None,
        "a_top1_score_median": round(statistics.median(a_sc), 6) if a_sc else None,
        "b_top1_score_max": round(max(sc), 6) if sc else None,
        "a_top1_score_min": round(min(a_sc), 6) if a_sc else None,
    }

out = {
    "run_id": RUN,
    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "modes": MODES,
    "how_to_read": "hit_at_3 = Top3 里至少一条与查询意图相关；precision_at3 = 相关条数/3。"
                   "A 组测检索能力，B 组测拒答行为。判断为人工逐条给出，缺判断记 unknown 不算命中。"
                   "三种模式都不带相关性阈值，一律返回 Top-N —— 因此 B 组是否拒答要按"
                   "返回结果是否相关来读，而不是按有没有返回结果来读。",
    "query_count": len(rows), "judged_count": len(judged),
    "summary": summary,
    "b_group_behavior": b_behavior,
    "raw_score_comparison": raw_cmp,
    "results": rows,
}
# 写盘前先归档上一版（2026-09-30 补）。
# 事故：本脚本 run 20260930-0150 直接覆盖了 2026-09-23 那版 selftest.json，
# 而上一版的旧指标当时只在本脚本的输出里，磁盘上没有副本 —— 违反了
# 「任何 w 模式目标，重建前先归档」这条在 L3 事故后立的规矩。
# 旧指标后来从 kb/l6/runs/20260923-1440.json 里捞回来了（那份报告完整存了 selftest 段），
# 但那是运气，不是机制。现在把归档做成机制：每跑一次留一版带 run_id 的历史。
# ★ 批次5（2026-10-01）：整段移进 `if APPLY` —— 预演档**不建归档目录、不复制归档、不写 selftest.json**。
_ARCH = f"{L6}/_archive"
_prev = f"{L6}/selftest.json"
out["dry_run"] = not APPLY
out["applied"] = bool(APPLY)

if APPLY:
    os.makedirs(_ARCH, exist_ok=True)
    if os.path.exists(_prev):
        _rid = json.load(open(_prev, encoding="utf-8")).get("run_id") or "unknown"
        _dst = f"{_ARCH}/selftest.json.{_rid}"
        if not os.path.exists(_dst):          # 不覆盖更早归档的同 run 副本
            import shutil as _sh
            _sh.copy2(_prev, _dst)
    json.dump(out, open(f"{L6}/selftest.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
else:
    # 预演档：只写带 run 的预演件。**不叫** `<RUN>-dryrun.json`（那个名字归 l6_report.py 的落章台账），
    # 且**不带** skill/skill_id/skills 键 —— 本脚本不是落章引擎（见文件头「命名避撞」）。
    _DRY = f"{L6}/runs/{RUN}-selftest-dryrun.json"
    if not os.path.isdir(f"{L6}/runs"):      # 目录已在则为**零副作用**（不调 makedirs）
        os.makedirs(f"{L6}/runs", exist_ok=True)
    json.dump({**out, "preview_of": _prev, "engine": "kb/.work/l6_selftest.py",
               "note": "预演档：kb/l6/selftest.json 未被写入、未归档；本件不是落章（无 skill 键）"},
              open(_DRY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if SHOW:
    print(f"需要判断的 (查询, 单元) 对：{len(pairs)} 条\n")
    for k in sorted(pairs, key=lambda x: (pairs[x]["group"], pairs[x]["query"], x)):
        p = pairs[k]
        print(f"[{p['group']}|{p['lang']}] {p['query']}  →  {p['unit_id']}")
        print(f"      {p['anchor']}  ({p['table']} / {p['kb_type']})")
        print(f"      {p['excerpt'][:150]}")
else:
    if APPLY:
        print(f"自验写入 {L6}/selftest.json｜已判断 {len(judged)}/{len(rows)} 条查询")
    else:
        print(f"[dry-run] 预演 → {L6}/runs/{RUN}-selftest-dryrun.json"
              f"（**未写** {L6}/selftest.json）｜已判断 {len(judged)}/{len(rows)} 条查询")
    for key in ("A_zh", "A_en", "A_all", "B_zh", "B_en", "B_all"):
        s = summary[key]
        print(f"  {key:6s} " + "｜".join(
            f"{m}: hit@3 {s[m]['hit_rate_at3']} p@3 {s[m]['precision_at3']}" for m in MODES))
    print("  原始分对照（A 组 vs B 组，中位）：")
    for grp in ("A", "B"):
        print(f"    {grp}: BM25 原始分 {raw_cmp[grp]['bm25_max_median']}｜余弦 {raw_cmp[grp]['cosine_max_median']}")
    print("  B 组行为：")
    for m in MODES:
        b = b_behavior[m]
        print(f"    {m}: 返回结果={b['returns_results']}｜Top1 相关 {b['top1_relevant']}/{b['queries']}｜"
              f"Top1 分数中位 B={b['b_top1_score_median']} vs A={b['a_top1_score_median']}")
print(f"总耗时 {time.perf_counter()-t0:.1f}s")
