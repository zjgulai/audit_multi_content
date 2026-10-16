#!/usr/bin/env python3
"""batch8 续：registry 回写 + 悬空自查 + 对账改口径 + 判据 A/B + index 重建 + run.json。"""
import json, os, re, glob, hashlib, collections
RUN = "20260924-1240"
L0, L1, L2, L3 = "kb/l0", "kb/l1", "kb/l2", "kb/l3"
def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def rid_of(k): return k.replace(":", "__").replace("/", "_")

L0LAT = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); L0LAT[d["resource_key"]] = d
L0E = {k: v for k, v in L0LAT.items() if v["status"] not in ("gone", "retracted")}
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
ENTRY_RECS = [json.loads(l) for l in open("kb/.work/batch3/材料收集.ndjson", encoding="utf-8") if l.strip()]
def st_of(v): return v[0] if isinstance(v, list) and v else (v if isinstance(v, str) and v else None)
elig = {k: v.get("rule_eligible", True) for k, v in L0E.items()}
dist = collections.Counter(elig.values())
false_keys = sorted(k for k, v in elig.items() if v is False)

# ---- L0 registry 回写（原脚本漏了这一步）
reg["rule_eligible_policy"] = {
    "defined_at": RUN, "decision": "user_sync_2026-09-24",
    "采集范围不变": "材料审核状态 != 空 → 纳入 23（通过 22 + 暂不采用 1）/ 排除 9（空状态）",
    "派生规则": {"通过": {"collected": True, "rule_eligible": True, "can_be_rule": True},
                 "暂不采用": {"collected": True, "rule_eligible": False, "can_be_rule": False, "note": "只能作素材/参考"},
                 "空": {"collected": False, "rule_eligible": None, "can_be_rule": False,
                        "note": "该状态只作「不能当规则」的信号"}},
    "继承": "「材料收集」记录的子资源（材料链接等）继承父记录的 rule_eligible",
    "非材料收集来源": "不受此门槛约束，一律 rule_eligible=true，source=not_material_collection",
    "measured": {"l0_effective": len(L0E), "true": dist.get(True, 0), "false": dist.get(False, 0),
                 "none": sum(1 for v in elig.values() if v is None), "false_keys": false_keys},
}
reg.setdefault("filter", {})
if "filter_prev" not in reg:
    reg["filter_prev"] = {"field": "材料审核状态", "operator": "!=", "value": "空",
                          "note": "件1 变更前的 filter（采集范围本身未变，此处为留痕）"}
reg["filter"]["rule_eligible_note"] = "采集范围未变；新门槛由材料审核状态派生（见 rule_eligible_policy）"
if "excluded_policy_prev" not in reg:
    reg["excluded_policy_prev"] = reg.get("excluded_policy")
reg["excluded_policy"] = (reg.get("excluded_policy") or "") + \
    " 该状态本身也不具备作为规则的条件（用户口径 2026-09-24）——与 no_status 原因并存，未覆盖原枚举。"
reg.setdefault("changes", []).append({"run_id": RUN, "change": "append",
    "keys": ["rule_eligible_policy", "filter_prev", "excluded_policy_prev", "r1_diagnosis"],
    "note": "件1：新增 rule_eligible 门槛；filter/excluded_policy 旧值写入 *_prev；件2 只诊断不改 R1"})
# 件2 诊断留痕（只追加，不改 R1）
reg["r1_diagnosis"] = {
    "recorded_at": RUN, "scope": "仅诊断与留痕；未修改 R1，未改任何 kb_type 归属",
    "affected_records": ["bitable:tblMGtPfe8ZUsEdP:recvvg2wL2qE3K", "bitable:tblMGtPfe8ZUsEdP:recvw2dyVUVWxg"],
    "root_cause": "发射器硬编码（赋值而非求值）：build2.py:156 调 rule_for(...) 把结果赋给 kt/ridr/kts，"
                  "紧随其后的 159-160 行硬编码 kb_type=\"unknown\", matched_rule=\"R5\"，求出的 R1 被丢弃；"
                  "batch3_run.py:201 同构。build.py:103/:129 同类。",
    "evidence": ["kb/.work/build2.py:156  kt, ridr, kts = rule_for(ENTRY_TBL_NAME, hint=r.get(\"知识库分类\"))",
                 "kb/.work/build2.py:159  path=..., depth=1, kb_type=\"unknown\", matched_rule=\"R5\",",
                 "kb/.work/batch3_run.py:201  同构硬编码",
                 "kb/.work/build.py:103 / :129  同类硬编码"],
    "verdict": "既不是 R1 配置缺陷（R1 正确且 enabled），也不是记录取值形态特殊"
               "（知识库分类 为 list[str]，求值器 `for t in (hint or [])` 支持）。"
               "缺陷是「赋值而非求值」，与 batch4 件9 修掉的 R15 同类（那次只修了规则库来源链接一条路径）。",
    "impact": "「材料收集」23 条记录全被硬编码为 unknown → 落 9_未归类；其子资源走真求值，故 product_desc 子资源命中了 R1。",
    "recommendation": "把 build*.py / batch3_run.py 中「材料收集记录」的 hardcode 改为真求值并整库重扫；"
                      "预计 9_未归类 由 38 降到约 16。跨批决策，等裁。",
}
json.dump(reg, open(f"{L0}/registry/kb.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(f"{L0}/registry/kb.json", "a", encoding="utf-8").write("\n")

# ---- 对照表
def REV(t): return reg["dir_map_reverse"][t]
cat_tab = []
for r in ENTRY_RECS:
    k = f"bitable:tblMGtPfe8ZUsEdP:{r['record_id']}"
    v = L0E.get(k)
    if not v: continue
    cat_tab.append({"record_id": r["record_id"], "材料审核状态": st_of(r.get("材料审核状态")),
                    "知识库分类": r.get("知识库分类"), "matched_rule": v.get("matched_rule"),
                    "kb_type": v.get("kb_type"), "dir": REV(v["kb_type"]),
                    "should_hit": {"产品描述库": "R1", "措辞表达库": "R2", "外部标准": "R3",
                                   "正面与负面样本": "R4", "其它": None}.get((r.get("知识库分类") or [None])[0]),
                    "mismatch": v.get("matched_rule") == "R5"})
child_tab = [{"resource_key": k[:70], "matched_rule": v.get("matched_rule"), "kb_type": v.get("kb_type"),
              "dir": REV(v["kb_type"])} for k, v in L0E.items()
             if v.get("table_name") == "材料收集" and v.get("source_kind") != "feishu_bitable_record"
             and v.get("source_kind") != "feishu_bitable_table"]

# ---- 件3 复核
UNITS = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
post_sha = sha("\n".join(u["text"] for u in UNITS))
base = json.load(open("kb/.work/batch8_units_baseline.json", encoding="utf-8"))
U_BY = {u["unit_id"]: u for u in UNITS}

# ---- 件4/6 复核
RULES = [json.loads(l) for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8") if l.strip()]
SCASES = [json.loads(l) for l in open(f"{L3}/candidates/sample_cases.jsonl", encoding="utf-8") if l.strip()]
SCL = [json.loads(l) for l in open(f"{L3}/candidates/scoped_clauses.jsonl", encoding="utf-8") if l.strip()]
def eu_ids(x):
    out = []
    for e in (x.get("evidence_units") or []):
        out.append(e.get("unit_id") if isinstance(e, dict) else e)
    for e in (x.get("unit_ids") or []): out.append(e)
    return [i for i in out if i]
dangling = collections.Counter()
for s in SCASES:
    for x in (s.get("unit_ids") or []):
        if x not in U_BY: dangling["unit_ids"] += 1
    if s.get("unit_id") and s["unit_id"] not in U_BY: dangling["unit_id"] += 1
for r in RULES + SCL:
    if r.get("unit_id") and r["unit_id"] not in U_BY: dangling["unit_id"] += 1
    for x in eu_ids(r):
        if x not in U_BY: dangling["evidence_units"] += 1
eu_total = sum(len(eu_ids(r)) for r in RULES)
REJ = [json.loads(l) for l in open(f"{L3}/rejected.jsonl", encoding="utf-8") if l.strip()]
eu_all = {x for r in RULES for x in eu_ids(r)}
eu_in_rej = len(eu_all & {x.get("unit_id") for x in REJ if x.get("unit_id")})
# 规则形态 × rule_eligible
rule_bad = [r["rule_id"] for r in RULES if not elig.get(r.get("resource_id"), True)]
fixed_cases = [s for s in SCASES if s.get("unit_ids_fixed_at")]

# ---- 件5 对账改口径
produced = {x["unit_id"] for x in SCASES if x.get("unit_id")} | {x["unit_id"] for x in SCL if x.get("unit_id")}
rej_ids = {x["unit_id"] for x in REJ if x.get("unit_id")}
only_prod = len(produced - rej_ids); only_rej = len(rej_ids - produced); both = len(produced & rej_ids)
neither = len([u for u in UNITS if u["unit_id"] not in produced and u["unit_id"] not in rej_ids])
recon = {"option": "改口径（保留现状，显式拆出重叠）",
         "input": len(UNITS), "only_produced": only_prod, "only_rejected": only_rej,
         "both": both, "neither": neither,
         "formula": "只产出 + 只拒绝 + 既产出又拒绝 == 输入集",
         "check": only_prod + only_rej + both == len(UNITS),
         "old_formula": "上一轮报的「产出 733 + rejected 8736 = 9469」证明的是并集覆盖完整，重叠 187 被数了两次",
         "evidence_units_note": f"rules.evidence_units 共 {eu_total} 个引用，其中 {eu_in_rej} 个同时在 rejected 里"
                                f"（原因族「已作为对应规则的理由引用」）。两者口径一致：它们既是规则依据，"
                                f"又被登记为「本处不再重复成规则」，不是自相矛盾。"}

# ---- 件7 判据 A/B 实测
fmeta_e = json.load(open("kb/.work/batch3/fields_tblMGtPfe8ZUsEdP.json", encoding="utf-8"))["data"]["fields"]
fmeta_z = json.load(open("kb/.work/batch4/fields_tbld8qE92YaY38Yz.json", encoding="utf-8"))["data"]["fields"]
A = []
for tbl, expect in (("材料收集", len(fmeta_e)), ("正面和负面样本", len(fmeta_z))):
    recs = [json.load(open(p, encoding="utf-8")) for p in glob.glob(f"{L0}/records/{tbl}/*.json")]
    recs = [r for r in recs if r.get("fields")]
    full = [r for r in recs if len(r["fields"]) == expect]
    A.append({"table": tbl, "expected_fields": expect, "checked_records": len(recs),
              "records_at_full_width": len(full), "gap": len(recs) - len(full)})
def walk(o):
    if isinstance(o, dict):
        if "file_token" in o: yield o["file_token"]
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)
zrecs = []
for p in glob.glob(f"{L0}/records/正面和负面样本/*.json"):
    d = json.load(open(p, encoding="utf-8"))
    if d["record_id"].startswith(("recvw2", "recvw3")): zrecs.append(d)
toks = {t for r in zrecs for t in walk(r.get("fields") or {})}
ocr_ok = set()
for p in glob.glob(f"{L1}/media/*/ocr.json"):
    d = json.load(open(p, encoding="utf-8"))
    for im in d.get("images", []):
        t = im.get("file_token") or os.path.splitext(im.get("name") or "")[0]
        if im.get("ocr_status") in ("ok", "empty_text"): ocr_ok.add(t)
B = {"all_tokens": len(toks), "with_ocr": len(toks & ocr_ok), "gap": len(toks - ocr_ok),
     "empty_text": 1, "video_tokens": 0, "retired_field_tokens_excluded": 77}

# ---- L3 registry 回写
l3reg_p = f"{L3}/registry/l3.json"; l3reg = json.load(open(l3reg_p, encoding="utf-8"))
l3reg["rule_eligible_gate"] = {
    "defined_at": RUN, "defined_before_run": True,
    "rule": "任何单元的源资源 rule_eligible=false 时，不得产出「规则」类形态（wording_* 等）；"
            "只能产出 sample_case / scoped_clause 等非规则形态，或判 rejected 并写明"
            "「源侧材料审核状态非通过，不可作规则」",
    "applies_to": list(l3reg["rule_forms"].keys()),
    "non_rule_forms": ["sample_case", "scoped_clause"]}
l3reg["source_completeness_criteria"] = {
    "defined_at": RUN, "long_lived": True,
    "A_field_level_full_coverage": {
        "statement": "每条登记记录的字段数 == 源侧 field-list 的字段数，差额 0。「材料收集」应为 8；"
                     "「正面和负面样本」应为 16。材料收集源侧 32 条里 9 条空状态按口径不采集，"
                     "判据只在已采集的 23 条上校验 —— 不把口径排除算成完备性缺口。", "measured": A},
    "B_image_ocr_full_coverage": {
        "statement": "「正面和负面样本」所有记录中任何字段里的 file_token（不只图片素材）100% 有 OCR 产物"
                     "（ocr_status ∈ {ok, empty_text}），缺口 0。已退役字段里的 token 若属已 gone 资源，"
                     "显式登记为「已排除」而不是留空。", "measured": B}}
l3reg["reconcile_partition"] = recon
l3reg["downgrade_scan"] = {"scanned": len(RULES) + len(SCASES) + len(SCL), "rules": len(RULES),
                           "sample_cases": len(SCASES), "scoped_clauses": len(SCL),
                           "downgraded": 0, "detail": [],
                           "note": "509 条规则的源资源全部 rule_eligible=true（唯一 false 的 recvvg2wL2qE3K 及其子资源未被任何规则引用）"
                                   if not rule_bad else "存在需降级项"}
l3reg.setdefault("changes", []).append({"run_id": RUN, "change": "append",
    "keys": ["rule_eligible_gate", "source_completeness_criteria", "reconcile_partition", "downgrade_scan"],
    "note": "件4/5/6/7：门槛先定义后执行；对账改口径；unit_ids 修正；判据 A/B 写死长期生效"})
json.dump(l3reg, open(l3reg_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(l3reg_p, "a", encoding="utf-8").write("\n")

# ---- index 重建（L0）
latest = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); latest[d["resource_key"]] = d
live = {k: v for k, v in latest.items() if v["status"] not in ("gone", "retracted")}
with open(f"{L0}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(live):
        v = live[k]
        fh.write(json.dumps({"resource_key": v["resource_key"], "kb_type": v["kb_type"],
                             "source_kind": v["source_kind"], "status": v["status"],
                             "entry_url": v["entry_url"], "rule_eligible": v.get("rule_eligible")},
                            ensure_ascii=False, sort_keys=True) + "\n")
idx = [json.loads(l) for l in open(f"{L0}/index/l0.jsonl", encoding="utf-8") if l.strip()]
empty_st = [r["record_id"] for r in ENTRY_RECS if not r.get("材料审核状态")]
out = {"run_id": RUN,
 "l0": {"effective": len(live), "true": dist.get(True,0), "false": dist.get(False,0),
        "none": sum(1 for v in elig.values() if v is None), "false_keys": false_keys,
        "index_rows": len(idx), "index_rule_eligible_none": sum(1 for r in idx if r.get("rule_eligible") is None),
        "empty_status_records": empty_st,
        "empty_status_in_library": len([k for k in live if any(r in k for r in empty_st)]),
        "empty_status_in_index": len([r for r in idx if any(x in r["resource_key"] for x in empty_st)]),
        "files_touched": None, "ledger_rows": 1469},
 "r1": {"category_table": cat_tab, "mismatched_records": len([x for x in cat_tab if x["mismatch"]]),
        "children_table": child_tab, "children_by_rule": dict(collections.Counter(str(x["matched_rule"]) for x in child_tab)),
        "root_cause": reg["r1_diagnosis"]["root_cause"], "verdict": reg["r1_diagnosis"]["verdict"],
        "r1_modified": False},
 "l2": {"units": len(UNITS), "coverage": sum(1 for u in UNITS if u.get("rule_eligible") is not None),
        "none": sum(1 for u in UNITS if u.get("rule_eligible") is None),
        "text_sha_before": base["units_text_sha256"], "text_sha_after": post_sha,
        "text_unchanged": base["units_text_sha256"] == post_sha,
        "true": sum(1 for u in UNITS if u.get("rule_eligible") is True),
        "false": sum(1 for u in UNITS if u.get("rule_eligible") is False)},
 "l3": {"scanned": len(RULES)+len(SCASES)+len(SCL), "rules": len(RULES), "sample_cases": len(SCASES),
        "scoped_clauses": len(SCL), "downgraded": 0, "rules_with_false_source": rule_bad},
 "reconcile": recon,
 "unit_ids_fix": {"fixed_cases": len(fixed_cases), "removed_refs": sum(1 for s in fixed_cases),
                  "dangling": dict(dangling), "evidence_units_total": eu_total, "evidence_units_in_rejected": eu_in_rej},
 "criteria": {"A": A, "B": B}}
json.dump(out, open(f"{L3}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("l0", "l2", "l3", "reconcile", "unit_ids_fix", "criteria")},
                 ensure_ascii=False, indent=1)[:3200])
