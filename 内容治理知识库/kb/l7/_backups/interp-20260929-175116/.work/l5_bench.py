#!/usr/bin/env python3
"""L5 性能验收：P0 匹配耗时（PRD §12 要求 < 1 秒）。

- 语料取自 L2 真实广告文案（kb/l2 只读，anchor 前缀 #广告文案明细/ 的 Headline / Primary Text 等）
- 不访问网络；只加载 kb/l5/p0_patterns.jsonl 后本地正则匹配
- 产出 kb/l5/benchmark.json
"""
import json, os, statistics, sys, time, platform, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L2 = os.path.join(ROOT, "kb/l2/units.jsonl")
MATCHER = os.path.join(ROOT, "kb/l5/matcher.py")
OUT = os.path.join(ROOT, "kb/l5/benchmark.json")

spec = importlib.util.spec_from_file_location("l5_matcher", MATCHER)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

COPY_FIELDS = ("Headline", "Primary Text", "Description", "Long Headline", "标题", "正文")
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
        "under_1s": max(times) < threshold_ms,
    }
    bench["cases"].append(rec)
    print(f"{key:22s} {rec['chars_human']:>10s} / {n_lines:>7d} 行  "
          f"min={rec['elapsed_ms']['min']:8.3f} ms  median={rec['elapsed_ms']['median']:8.3f} ms  "
          f"max={rec['elapsed_ms']['max']:8.3f} ms  命中规则={','.join(rec['hit_rules'])}  "
          f"{'✅<1s' if rec['under_1s'] else '❌超时'}")

batch_case = [c for c in bench["cases"] if c["case"] == "batch_ad_copy"][0]
bench["compile_ms"] = round(statistics.median(ct), 3)
bench["compile_note"] = "冷启动：读 kb/l5/p0_patterns.jsonl 并编译全部正则一次；常驻服务只付一次"
bench["per_copy_avg_ms"] = round(batch_case["elapsed_ms"]["median"] / len(lines), 4)
bench["artifact_sha256"] = {f: __import__("hashlib").sha256(open(os.path.join(ROOT, f), "rb").read()).hexdigest()
                            for f in ("kb/l5/p0_patterns.jsonl", "kb/l5/matcher.py")}
bench["verdict"] = "PASS" if all(c["under_1s"] for c in bench["cases"]) else "FAIL"
bench["verdict_note"] = ("全部规模均在 1 秒内" if bench["verdict"] == "PASS"
                         else "存在超过 1 秒的规模")
json.dump(bench, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"冷启动（读模式表 + 编译正则）：{bench['compile_ms']} ms（一次性）")
print(f"\n单条文案摊薄耗时：{bench['per_copy_avg_ms']} ms/条（{batch_case['elapsed_ms']['median']} ms ÷ {len(lines)} 条）")
print(f"验收：{bench['verdict']} → {OUT}")
sys.exit(0 if bench["verdict"] == "PASS" else 1)
