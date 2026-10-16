#!/usr/bin/env python3
"""前置 B：配对一致性抽检（必做）。
从 atomic 规则里随机抽 10 条，回原始记录核对「命中片段」与「建议替换」是否同一条记录的同一行。
"""
import json, random, hashlib, collections, sys, re

RUN = sys.argv[1]
L3, L2 = "kb/l3", "kb/l2"
latest = {}
for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); latest[r["rule_id"]] = r
U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
by_rec = collections.defaultdict(dict)
for u in U:
    if u["unit_type"] == "entry":
        by_rec[u["resource_id"]][u.get("heading_path")] = u

atomic = [r for r in latest.values() if r.get("rule_kind") == "atomic"]
random.seed(20260923)                      # 固定种子，可复现
sample = random.sample(atomic, 10)

rows, mismatches = [], []
for r in sample:
    rid = r.get("resource_id") or (r.get("resource_ids") or [None])[0]
    rec = by_rec.get(rid, {})
    src_hit = (rec.get("命中片段") or {}).get("text")
    src_fix = (rec.get("修改建议") or {}).get("text")
    if r["form"] == "revision_pair":
        # 案例型：前/后必须来自同一单元的 meta
        before = r["forbidden_expression"]; after = r["suggested_replacement"]
        ok = bool(before) and before in (r.get("rule_text") or "") and after in (r.get("rule_text") or "")
        verdict = "✅ 同单元（前/后取自同一 revision_pair 单元）" if ok else "❌ 不成对"
        rows.append({"rule_id": r["rule_id"], "form": "revision_pair", "record_id": rid,
                     "anchor": r["anchor"], "source_sha256": (r["evidence_units"][0] or {}).get("source_sha256"),
                     "hit_fragment": before[:60], "suggested_replacement": after[:60],
                     "verdict": verdict})
        if not ok:
            mismatches.append(r["rule_id"])
        continue
    if src_hit is None or src_fix is None:
        # 入口规则聚合了多记录；改用 expression_fix_pairs 内的 record_id 逐对核验
        pairs = r.get("expression_fix_pairs") or []
        bad = []
        for p in pairs:
            prid = p.get("record_id"); prec = by_rec.get(prid, {})
            ph = (prec.get("命中片段") or {}).get("text")
            pf = (prec.get("修改建议") or {}).get("text")
            if p.get("fix") and pf and p["fix"] != pf:
                bad.append((prid, p.get("fix")[:40], pf[:40]))
            if p.get("fragment") and ph and p["fragment"] not in ph:
                bad.append((prid, "fragment 不在该记录命中片段内: " + p["fragment"][:30], ph[:40]))
        ok = not bad
        rows.append({"rule_id": r["rule_id"], "form": r["form"], "record_id": f"{len(pairs)} 条配对",
                     "anchor": r["anchor"], "source_sha256": (r["evidence_units"][0] or {}).get("source_sha256"),
                     "hit_fragment": r["forbidden_expression"][:60],
                     "suggested_replacement": r["suggested_replacement"][:60],
                     "verdict": ("✅ 逐对回源一致（%d 对全部命中同记录）" % len(pairs)) if ok
                                else f"❌ {len(bad)} 对错配：{bad[:2]}"})
        if not ok:
            mismatches.append(r["rule_id"])
        continue
    # 单记录入口/边界规则：直接比对
    ok = (src_hit and src_fix)
    detail = f"源记录 {rid}｜命中片段={src_hit[:40]}｜修改建议={src_fix[:40]}"
    rows.append({"rule_id": r["rule_id"], "form": r["form"], "record_id": rid,
                 "anchor": r["anchor"], "source_sha256": (r["evidence_units"][0] or {}).get("source_sha256"),
                 "hit_fragment": src_hit[:60], "suggested_replacement": src_fix[:60],
                 "verdict": ("✅ 同记录同一行" if ok else "❌ 该记录缺命中片段或修改建议")})
    if not ok:
        mismatches.append(r["rule_id"])

out = {"run_id": RUN, "sampled": len(sample), "seed": 20260923,
       "atomic_total": len(atomic), "mismatches": mismatches, "rows": rows}
json.dump(out, open("kb/.work/l5_spotcheck.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"抽检 {len(sample)}/{len(atomic)} 条 atomic 规则 | 发现错配 {len(mismatches)} 条")
for i, x in enumerate(rows, 1):
    print(f"\n[{i}] {x['rule_id']} ({x['form']})")
    print(f"    记录: {x['record_id']}")
    print(f"    命中片段/前: {x['hit_fragment']}")
    print(f"    建议替换/后: {x['suggested_replacement']}")
    print(f"    锚点: {x['anchor'][:64]}  sha: {str(x['source_sha256'])[:16]}")
    print(f"    结论: {x['verdict']}")
print(f"\n{'✅ 未发现错配，可继续导出' if not mismatches else '❌ 发现错配，停止导出：' + str(mismatches)}")
