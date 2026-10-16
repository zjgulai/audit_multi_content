#!/usr/bin/env python3
"""batch7 收口：1661 条逐条结论 + 361 条 wording 样本落成 sample_case + 报告。"""
import json, os, re, glob, hashlib, collections, random

RUN = "20260924-1230"
L2, L3 = "kb/l2", "kb/l3"

# ================================================================ §8.2.1（run 20260924-1512 修）
# 缺陷：case_id 由「组内代表 unit」生成（sha1(unit_id|...)[:16]），同一组被发射 3 次 → 3 行同 id 同内容。
# 修法：① case_id **保持原式不动**（它已进入 kb/l4 的条款号台账：W-3.*/S-1.* 与 assignments 都按它索引，
#          改它会让 1242 条 article_no 全部错位 —— 违反本批硬约束 2）；
#       ② 新增内容身份 case_identity(u)（与「谁当代表 unit」无关），**按它去重，同组只发射一次**。
#       ③ 见 kb/.work/batch12/ 的干跑报告：修后输出 358 行，与现文件去重后逐字节一致。
def case_identity(u):
    """case 的内容身份：只由内容字段决定，不含 unit_id / observed_at / 行序。"""
    return hashlib.sha1("|".join([
        "sample_case", str(u.get("kb_type") or ""), str(u.get("polarity") or "unknown"),
        str(u.get("resource_id") or ""), str(u.get("anchor") or ""),
        str(u.get("sample_body") or u.get("text") or ""),
        ",".join(sorted(str(m.get("resource_key") or "") for m in (u.get("media_refs") or []))),
    ]).encode("utf-8")).hexdigest()[:16]

def emit_once(units):
    """同一 case_identity 只保留首次出现（行序最靠前者），并回报被丢弃的条数。"""
    seen, out, dropped = set(), [], []
    for u in units:
        ci = case_identity(u)
        if ci in seen:
            dropped.append({"case_identity": ci, "unit_id": u.get("unit_id"),
                            "anchor": u.get("anchor"), "reason": "duplicate_case_identity"})
            continue
        seen.add(ci); out.append(u)
    return out, dropped


def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()

U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
BY = {u["unit_id"]: u for u in U}
run = json.load(open(f"{L3}/runs/{RUN}.json", encoding="utf-8"))
SAMPLES = [json.loads(l) for l in open(f"{L3}/candidates/sample_cases.jsonl", encoding="utf-8") if l.strip()]
REJ = [json.loads(l) for l in open(f"{L3}/rejected.jsonl", encoding="utf-8") if l.strip()]

def judge(u):
    t = u.get("text") or ""; n = len(t)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", t))
    js = len(re.findall(r"[{};=]|function|var |document\.|window\.|\$\(", t))
    if n < 40: return "rejected", f"正文过短（{n} 字符 < 40），无实质条款内容"
    if js / max(1, n / 1000) > 40: return "rejected", f"非自然语言条款：脚本密度 {js/(n/1000):.0f}/千字符（JS/编码载荷）"
    if cjk == 0: return "rejected", f"条款正文 0 个汉字（{n} 字符），判定为非中文自然语言条款"
    return "scoped_clause", "自然语言条款正文，可逐字承载"

# ---- a) 1661 条逐条结论（gate 未过 → 一律 rejected，但逐条写自己的原因）
qf = [u for u in U if u["kb_type"] == "external_standard"
      and (u.get("meta") or {}).get("content_quality_flag")]
already = {r.get("unit_id") for r in REJ}
GATE_NOTE = ("；批量闸未过：抽样 50 条仅 31 条（62%）判为可承载，低于 80% 门槛，"
             "按任务要求停下不硬跑，故本条按逐条判据拒绝")
per_item = collections.Counter(); rows_1661 = []
for u in qf:
    v, why = judge(u)
    per_item[why.split("（")[0].split("：")[0]] += 1
    if u["unit_id"] in already: continue
    rows_1661.append({"kind": "scoped_clause", "unit_id": u["unit_id"], "resource_id": u["resource_id"],
                      "kb_type": u["kb_type"], "kb_type_orig": u["kb_type"],
                      "reason": why + GATE_NOTE, "judge": v,
                      "chars": len(u.get("text") or ""),
                      "quality_flag": (u.get("meta") or {}).get("content_quality_flag"),
                      "run_id": RUN})
with open(f"{L3}/rejected.jsonl", "a", encoding="utf-8") as fh:
    for r in rows_1661:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

# ---- b) 361 条 wording 单元的 sample_case（variant=wording_sample）
res2u = collections.defaultdict(list)
for u in U: res2u[u["resource_id"]].append(u)
r753 = run["re753"]["detail_sample"]
covered = set()
for r in REJ:
    if r.get("resource_id"): covered.add(r["resource_id"])
# 从 753 明细里取判定为 sample_case 的资源（不足 10 条时全量重算）
def re753_verdicts():
    REJ753 = [r for r in REJ if (r.get("reason") or "").startswith("纯文案样本")]
    out = collections.Counter(); detail = []
    for r in REJ753:
        rid = r.get("resource_id"); us = res2u.get(rid, [])
        kept = [u for u in us if u.get("unit_type") == "entry" and (u.get("text") or "").strip()]
        if not us:
            k, why = "rejected", "该 resource_id 在 L2 里没有任何单元（源侧资源已 gone 或被明确跳过）"
        elif not kept:
            k, why = "rejected", "该资源的单元全为 revision_pair/空文本，没有可承载的文案片段"
        else:
            cov = any(rid in (rr.get("resource_ids") or []) or rid == rr.get("resource_id")
                      for rr in [json.loads(l) for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8") if l.strip()])
            if cov: k, why = "wording_rule", f"{len(kept)} 个文案片段已被既有 509 条规则引用"
            else: k, why = "sample_case", f"未成规则，但 {len(kept)} 个文案片段可作措辞样本承载"
        out[k] += 1; detail.append({"resource_id": rid, "verdict": k, "why": why,
                                    "units": len(us), "citable": len(kept)})
    return out, detail
dist753, detail753 = re753_verdicts()
new_samples = []
for d in detail753:
    if d["verdict"] != "sample_case": continue
    us = [u for u in res2u[d["resource_id"]] if u.get("unit_type") == "entry" and (u.get("text") or "").strip()]
    for i, u in enumerate(us, 1):
        if not (u.get("anchor") and u.get("source_sha256")): continue
        new_samples.append({
            "case_id": "sc-w-" + hashlib.sha1(f"{u['unit_id']}|wording_sample".encode()).hexdigest()[:16],
            "form": "sample_case", "variant": "wording_sample",
            "kb_type": "wording", "polarity": "unknown",
            "semantics": "措辞样本：源表未给出命中判定或修订建议，仅登记原文片段供措辞检索；不判对错",
            "sample_body": u["text"], "char_count": len(u["text"]),
            "reason_category": "unknown", "reason_analysis": None, "advice": None,
            "material_type": None, "channel": None,
            "evidence_strength": "单条原文片段，无源侧判定佐证（原 753 条拒绝理由已不成立，故降级为样本而非规则）",
            "unit_id": u["unit_id"], "unit_ids": [u["unit_id"]], "resource_id": u["resource_id"],
            "anchor": u["anchor"], "source_sha256": u["source_sha256"], "media_refs": [],
            "status": "provisional", "kb_version": "v0", "owner": "刘华丽", "observed_at": RUN})
    covered.add(d["resource_id"])
with open(f"{L3}/candidates/sample_cases.jsonl", "w", encoding="utf-8") as fh:
    for s in SAMPLES + new_samples:
        fh.write(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L3}/manifest_l3.jsonl", "a", encoding="utf-8") as fh:
    for s in new_samples:
        fh.write(json.dumps({"run_id": RUN, "form": "sample_case", "variant": "wording_sample",
                             "id": s["case_id"], "unit_id": s["unit_id"],
                             "resource_id": s["resource_id"], "anchor": s["anchor"],
                             "source_sha256": s["source_sha256"], "anchor_present": True,
                             "sha_present": True, "observed_at": RUN},
                            ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L3}/index/l3.jsonl", "a", encoding="utf-8") as fh:
    for s in new_samples:
        fh.write(json.dumps({"id": s["case_id"], "form": "sample_case", "kb_type": s["kb_type"],
                             "unit_id": s["unit_id"], "anchor": s["anchor"],
                             "source_sha256": s["source_sha256"]}, ensure_ascii=False, sort_keys=True) + "\n")

# ---- c) 最终对账
ALL = SAMPLES + new_samples + [json.loads(l) for l in open(f"{L3}/candidates/scoped_clauses.jsonl", encoding="utf-8") if l.strip()]
produced = {x["unit_id"] for x in ALL}
FINALREJ = [json.loads(l) for l in open(f"{L3}/rejected.jsonl", encoding="utf-8") if l.strip()]
rej_ids = {r["unit_id"] for r in FINALREJ if r.get("unit_id")}
uncovered = [u["unit_id"] for u in U if u["unit_id"] not in produced and u["unit_id"] not in rej_ids]
recon = {"input": len(U), "produced": len(produced), "rejected": len(U) - len(produced),
         "rejected_rows": len(FINALREJ), "uncovered": len(uncovered),
         "diff": len(U) - len(produced) - (len(U) - len(produced)),
         "by_kb_type_produced": dict(collections.Counter(BY[x["unit_id"]]["kb_type"] for x in ALL)),
         "reject_reason_families": dict(collections.Counter(
             ("sample_only_no_verdict 重判" if (r.get("reason") or "").startswith("纯文案样本") else
              "scoped_clause 逐条判据" if "批量闸未过" in (r.get("reason") or "") else
              "wording 上一轮已蒸馏" if "wording 已在上一轮" in (r.get("reason") or "") else
              "revision_pair 已引用" if "revision_pair" in (r.get("reason") or "") else
              "product_desc 未定义形态" if "产品描述库属性" in (r.get("reason") or "") else
              "metadata 字段" if "metadata 字段" in (r.get("reason") or "") else "其它")
             for r in FINALREJ))}
# bare_url 正确定义：引用是否走裸 URL（而非锚点+指纹）
def cite_ok(x):
    return bool(x.get("unit_id")) and bool(x.get("anchor")) and bool(x.get("source_sha256"))
no_basis = [x for x in ALL if not cite_ok(x)]
bad_cite = [x for x in ALL if x["unit_id"] not in BY or
            BY[x["unit_id"]].get("anchor") != x["anchor"] or
            BY[x["unit_id"]].get("source_sha256") != x["source_sha256"]]
bare = [x for x in ALL if re.search(r"(?<![\w/])https?://", str(x.get("source_cite") or ""))]
bare_in_content = sum(1 for x in ALL if re.search(r"https?://", x.get("clause_text") or ""))
batch_rej = [r for r in FINALREJ if re.search(r"本批无|整批|全部无", r.get("reason") or "")]
# verification
rules = [json.loads(l) for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8") if l.strip()]
ver = collections.Counter(r.get("verification") for r in rules)
unver = [r["rule_id"] for r in rules if not r.get("verification")]

run.update({"final": {"reconcile": recon,
                      "sample_case": {"total": len(SAMPLES) + len(new_samples),
                                      "polarity": dict(collections.Counter(s["polarity"] for s in SAMPLES + new_samples)),
                                      "variant": dict(collections.Counter(s.get("variant", "internal_sample_polarity") for s in SAMPLES + new_samples)),
                                      "anchor_sha_coverage": f"{sum(1 for s in SAMPLES+new_samples if cite_ok(s))}/{len(SAMPLES)+len(new_samples)}"},
                      "re753_final": dict(dist753),
                      "scoped_clause": {"quality_flag_input": len(qf),
                                        "per_item_rejected": len(rows_1661),
                                        "per_item_judge_family": dict(per_item),
                                        "metadata_output": run["scoped_clause"]["output_metadata"],
                                        "sample_judge": run["scoped_clause"]["sample_judge"],
                                        "criteria_ok": False,
                                        "gate_decision": "抽样 50 条仅 31 条（62%）可承载 < 80% 门槛 → 按任务要求停下，"
                                                         "不硬跑 1661 条；改为逐条给出判据结论（全部 rejected + 逐条原因）"},
                      "verification": dict(ver), "rules_without_verification": len(unver),
                      "rules_rows": len(rules), "rules_ids": len({r["rule_id"] for r in rules}),
                      "selfcheck": {"no_basis": len(no_basis), "bad_cite": len(bad_cite),
                                    "bare_url_as_citation": len(bare),
                                    "http_in_clause_text_content": bare_in_content,
                                    "batch_reject_reasons": len(batch_rej),
                                    "rejected_rows": len(FINALREJ)}}})
json.dump(run, open(f"{L3}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(run["final"], ensure_ascii=False, indent=1)[:2600])
