#!/usr/bin/env python3
"""L5 性能验收：P0 匹配耗时（PRD §12「P0 层响应 ≤ 1 秒」）。

- 语料取自 L2 真实广告文案（kb/l2 只读，anchor 前缀 #广告文案明细/ 的 Headline / Primary Text 等）
- 不访问网络；只加载 kb/l5/p0_patterns.jsonl 后本地正则匹配
- 产出 kb/l5/benchmark.json

## ★ 判据分级（Owner 2026-10-12 同意；**只放松余量用例，不放松真实形态**）

PRD §12 原文「≤ 1 秒（关键词/正则匹配）」**未限定输入规模**，而本 bench 的四个用例里
`large_doc_1mb` 是**余量用例**（1 MB ≈ 37 万字符 ≈ 一本书），不是任何真实送审的形态
（真实送审 = 单条文案 / 一张图 OCR / 视频字幕）。

    真实送审形态（single_primary_text / single_with_hit / batch_ad_copy）
        ⇒ **硬门槛 < 1000 ms 一个字没松**
    余量用例（large_doc_1mb）
        ⇒ 改判 **每模式中位耗时 ≤ 120 ms**

**为什么**：实测每模式耗时四次测量恒定 **102.9–105.3 ms**，而模式表从 7 条扩到 11 条
（补 H01/H03/H08/M03）⇒ 总耗时**线性于模式数**，是功能增强不是算法劣化。
不分级的话这条会一直红着，**真的劣化来了也看不出来**（狼来了）。
每模式 120 ms 的余量意味着：模式数涨到 15 条（11/2 行要补的 4 类红线）时 1 MB 仍 ≈ 1.8 s，
而**同一条余量用例每模式超过 120 ms 才说明 matcher 真的变慢了**。

判据自证见 `--selftest`（含反向对照：真实形态超 1 s 必须 FAIL、余量用例超 120 ms/模式必须 FAIL）。
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

import json, os, statistics, sys, time, platform, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L2 = os.path.join(ROOT, "kb/l2/units.jsonl")
MATCHER = os.path.join(ROOT, "kb/l5/matcher.py")
OUT = os.path.join(ROOT, "kb/l5/benchmark.json")

spec = importlib.util.spec_from_file_location("l5_matcher", MATCHER)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

#: 真实送审形态 ⇒ PRD §12 硬门槛（**不许放松**）
REAL_CASES = ("single_primary_text", "single_with_hit", "batch_ad_copy")
#: 余量用例 ⇒ 按「每模式耗时」判（Owner 2026-10-12 同意）
MARGIN_CASES = ("large_doc_1mb",)
HARD_LIMIT_MS = 1000.0
PER_PATTERN_LIMIT_MS = 120.0
CRITERION = {
    "hard_limit_ms": HARD_LIMIT_MS,
    "per_pattern_limit_ms": PER_PATTERN_LIMIT_MS,
    "real_cases": list(REAL_CASES),
    "margin_cases": list(MARGIN_CASES),
    "ruling": "Owner 2026-10-12：真实送审形态保持 <1s 硬门槛；1MB 余量用例改判每模式 ≤120 ms",
}
COPY_FIELDS = ("Headline", "Primary Text", "Description", "Long Headline", "标题", "正文")


def judge_case(case, pattern_count):
    """单个用例的判定（**纯函数**，`--selftest` 直接喂合成用例验它）。"""
    case = dict(case)
    med = case["elapsed_ms"]["median"]
    case["per_pattern_ms"] = round(med / max(1, pattern_count), 3)
    if case["case"] in REAL_CASES:
        case["criterion"] = "hard_under_1s"
        case["limit_ms"] = HARD_LIMIT_MS
        case["pass"] = med < HARD_LIMIT_MS          # 与旧口径一致：**不分级**
        case["under_1s"] = case["pass"]
    elif case["case"] in MARGIN_CASES:
        case["criterion"] = "per_pattern_le_%dms" % int(PER_PATTERN_LIMIT_MS)
        case["limit_ms"] = PER_PATTERN_LIMIT_MS
        case["pass"] = case["per_pattern_ms"] <= PER_PATTERN_LIMIT_MS
        case["under_1s"] = med < HARD_LIMIT_MS      # 保留原字段，只作读数
    else:                                            # 未知用例 ⇒ 一律按硬门槛（保守）
        case["criterion"] = "hard_under_1s(unknown_case)"
        case["limit_ms"] = HARD_LIMIT_MS
        case["pass"] = med < HARD_LIMIT_MS
        case["under_1s"] = case["pass"]
    return case


def judge_all(cases, pattern_count):
    """⇒ (verdict, note)。**真实形态一条不放松**；余量用例按每模式判。"""
    judged = [judge_case(c, pattern_count) for c in cases]
    bad = [c["case"] for c in judged if not c["pass"]]
    real_bad = [c for c in judged if not c["pass"] and c["case"] in REAL_CASES]
    if not bad:
        return judged, "PASS", (
            "真实送审形态三档均 < %.0f ms；余量用例 %s 每模式 ≤ %.0f ms（分级口径，Owner 2026-10-12）"
            % (HARD_LIMIT_MS, "/".join(MARGIN_CASES), PER_PATTERN_LIMIT_MS))
    if real_bad:
        return judged, "FAIL", (
            "**真实送审形态**超硬门槛 %s ⇒ 这是**真的劣化**（分级口径**不覆盖**它）" % [c["case"] for c in real_bad])
    return judged, "FAIL", (
        "余量用例每模式耗时超 %.0f ms ⇒ **matcher 确实变慢了**（%s）"
        % (PER_PATTERN_LIMIT_MS, [c["case"] for c in judged if not c["pass"]]))


def selftest():
    """判据自证（**不跑真测量**，全合成用例）。"""
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    def mk(name, med):
        return {"case": name, "elapsed_ms": {"min": med, "median": med, "max": med}}

    P = 11
    # ① 真实形态正好 999 ms ⇒ pass；1000 ms ⇒ FAIL（边界是**严格小于**）
    _j, v, _n = judge_all([mk("single_with_hit", 999.0)], P)
    ck("① 真实形态 999 ms ⇒ PASS", v == "PASS", v)
    _j, v, _n = judge_all([mk("single_with_hit", 1000.0)], P)
    ck("② 真实形态正好 1000 ms ⇒ FAIL（严格 <1s，一个字没松）", v == "FAIL", v)
    # ③ 余量用例：11 模式 1229 ms ⇒ 每模式 111.7 ms ⇒ pass
    _j, v, _n = judge_all([mk("large_doc_1mb", 1229.122)], P)
    ck("③ 余量用例 1229 ms / 11 模式 = 111.7 ms ⇒ PASS（这正是本次裁定要放的那一格）", v == "PASS", v)
    # ④ 余量用例超每模式门槛 ⇒ FAIL
    _j4, v, _n = judge_all([mk("large_doc_1mb", 1500.0)], P)
    ck("④ 余量用例 1500 ms / 11 = 136.4 ms ⇒ **精确 FAIL**（判据不是恒绿）", v == "FAIL", v)
    # ⑤ 边界：正好 120.0 ms/模式 ⇒ pass
    _j, v, _n = judge_all([mk("large_doc_1mb", 120.0 * P)], P)
    ck("⑤ 边界：正好 120.000 ms/模式 ⇒ PASS", v == "PASS", v)
    _j, v, _n = judge_all([mk("large_doc_1mb", 120.0 * P + 0.5)], P)
    ck("⑤b 边界：120.05 ms/模式 ⇒ FAIL", v == "FAIL", v)
    # ⑥ ★ 最关键的反向对照：**真实形态不许被分级口径救活**
    _j, v, note = judge_all([mk("large_doc_1mb", 1229.0), mk("batch_ad_copy", 1200.0)], P)
    ck("⑥ 反向对照：**真实形态超 1 s ⇒ 整体 FAIL**（分级不覆盖真实形态）",
       v == "FAIL" and "真的劣化" in note, note[:40])
    # ⑦ 变异测试：把余量门槛放宽到 200 ms ⇒ ④ 精确变假
    global PER_PATTERN_LIMIT_MS, CRITERION
    keep = PER_PATTERN_LIMIT_MS
    PER_PATTERN_LIMIT_MS = 200.0
    _j, v, _n = judge_all([mk("large_doc_1mb", 1500.0)], P)
    ck("⑦ 变异测试：余量门槛放宽到 200 ms ⇒ ④ 精确变假", v == "PASS", v)
    PER_PATTERN_LIMIT_MS = keep
    # ⑧ 未知用例 ⇒ 按硬门槛（保守，不许悄悄放过）
    _j, v, _n = judge_all([mk("some_new_case", 5000.0)], P)
    ck("⑧ 未知用例 5000 ms ⇒ FAIL（按硬门槛兜底，不许静默放过）", v == "FAIL", v)
    # ⑨ 判完的用例带 criterion / limit_ms / per_pattern_ms（读数可核）
    j, _v, _n = judge_all([mk("large_doc_1mb", 1229.0)], P)
    ck("⑨ 判定带 criterion/limit_ms/per_pattern_ms",
       all(k in j[0] for k in ("criterion", "limit_ms", "per_pattern_ms")), str(j[0].get("criterion")))
    print("l5_bench --selftest（判据分级 · Owner 2026-10-12）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + ex) if ex else ""))
    bad = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad, len(res), "" if not bad else "  ← 有失败"))
    return 1 if bad else 0


if "--selftest" in sys.argv:
    sys.exit(selftest())
lines = []
for ln in open(L2, encoding="utf-8"):
    u = json.loads(ln)
    if (u.get("anchor") or "").startswith("#广告文案明细/"):
        fn = (u.get("meta") or {}).get("field_name")
        if fn in COPY_FIELDS and (u.get("text") or "").strip():
            lines.append(u["text"].strip())
assert lines, "没取到广告文案语料"

single = lines[0]
batch = "\n".join(lines)
# 命中路径样例：取语料里命中规则最多的一条文案（真实源侧文案，不是构造文本）
_rules_for_pick = m.compile_patterns()
single_hit = max(lines, key=lambda x: sum(h["matched_count"] for h in m.match(x, _rules_for_pick)))
reps = max(1, -(-1_000_000 // max(1, len(batch))))
large = "\n".join(lines * reps)

# 冷启动成本：读模式表 + 编译正则（进程启动时一次性，不计入单次匹配）
ct = []
for _ in range(3):
    t0 = time.perf_counter()
    m.compile_patterns()
    ct.append((time.perf_counter() - t0) * 1000)
rules = m.compile_patterns()
TEXTS = [
    ("single_primary_text", "单条广告文案（源侧第一条 Primary Text）", single, 5),
    ("single_with_hit", "单条广告文案（语料里命中最多的一条）", single_hit, 5),
    ("batch_ad_copy", "一批广告文案（全部 Headline/Primary Text 共 %d 条）" % len(lines), batch, 3),
    ("large_doc_1mb", "大文档（上述文案重复至 ≈1MB）", large, 3),
]
bench = {
    "requirement": "《内容审查 Agent PRD》§12：P0 匹配耗时 < 1 秒",
    "exporter_version": json.load(open(os.path.join(ROOT, "kb/l5/registry/l5.json"),
                                      encoding="utf-8"))["exporter_version"],
    "pattern_count": len(rules),
    "corpus": {"source": "kb/l2/units.jsonl（anchor 前缀 #广告文案明细/，字段 %s）"
                         % "/".join(COPY_FIELDS),
               "lines_available": len(lines)},
    "network": "无（matcher 只读本地 p0_patterns.jsonl，无任何网络调用）",
    "env": {"python": platform.python_version(), "platform": platform.platform()},
    "cases": [],
}
threshold_ms = 1000.0
for key, label, text, rounds in TEXTS:
    m.match(text, rules)  # 预热
    times = []
    hits = None
    for _ in range(rounds):
        t0 = time.perf_counter()
        hits = m.match(text, rules)
        times.append((time.perf_counter() - t0) * 1000)
    n_lines = len(text.split("\n"))
    rec = {
        "case": key, "label": label,
        "chars": len(text), "chars_human": f"{len(text)/1024:.1f} KB" if len(text) >= 1024 else f"{len(text)} 字符",
        "lines": n_lines, "rounds": rounds,
        "elapsed_ms": {"min": round(min(times), 3),
                       "median": round(statistics.median(times), 3),
                       "max": round(max(times), 3)},
        "hit_rules": sorted({h["rule_code"] for h in hits}),
        "hit_count": sum(h["matched_count"] for h in hits),
        "under_1s": max(times) < threshold_ms,   # 保留原字段（老读者）；判定以 judge_case 为准
    }
    # ★ 先判再打印：否则控制台会把每一档都打成 ❌（读的是还没算出来的 pass 字段），
    #   而总结说 PASS —— 那种"账面不一致"正是本库反复在治的病。
    rec = judge_case(rec, len(rules))
    bench["cases"].append(rec)
    print(f"{key:22s} {rec['chars_human']:>10s} / {n_lines:>7d} 行  "
          f"min={rec['elapsed_ms']['min']:8.3f} ms  median={rec['elapsed_ms']['median']:8.3f} ms  "
          f"max={rec['elapsed_ms']['max']:8.3f} ms  命中规则={','.join(rec['hit_rules'])}  "
          f"{'✅' if rec.get('pass') else '❌'}（{rec.get('criterion')}）")

batch_case = [c for c in bench["cases"] if c["case"] == "batch_ad_copy"][0]
bench["compile_ms"] = round(statistics.median(ct), 3)
bench["compile_note"] = "冷启动：读 kb/l5/p0_patterns.jsonl 并编译全部正则一次；常驻服务只付一次"
bench["per_copy_avg_ms"] = round(batch_case["elapsed_ms"]["median"] / len(lines), 4)
bench["artifact_sha256"] = {f: __import__("hashlib").sha256(open(os.path.join(ROOT, f), "rb").read()).hexdigest()
                            for f in ("kb/l5/p0_patterns.jsonl", "kb/l5/matcher.py")}
bench["cases"], bench["verdict"], bench["verdict_note"] = judge_all(bench["cases"], len(rules))
bench["criterion"] = CRITERION
json.dump(bench, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"冷启动（读模式表 + 编译正则）：{bench['compile_ms']} ms（一次性）")
print(f"\n单条文案摊薄耗时：{bench['per_copy_avg_ms']} ms/条（{batch_case['elapsed_ms']['median']} ms ÷ {len(lines)} 条）")
print(f"验收：{bench['verdict']} → {OUT}")
sys.exit(0 if bench["verdict"] == "PASS" else 1)
