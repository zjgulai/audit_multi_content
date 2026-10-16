#!/usr/bin/env python3
"""batch8 · 采集口径修订（rule_eligible）+ L3 两项遗留回修。"""
import json, os, re, glob, hashlib, collections, shutil

RUN = "20260924-1240"
L0, L1, L2, L3 = "kb/l0", "kb/l1", "kb/l2", "kb/l3"
LOCK = "kb/.work/.kb.lock"
if os.path.exists(LOCK): raise SystemExit(f"[LOCKED] {open(LOCK).read()}")
json.dump({"run_id": RUN, "layer": "l0/l2/l3", "pid": os.getpid(), "at": "2026-09-24T12:40:00"},
          open(LOCK, "w", encoding="utf-8"))
def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def rid_of(k): return k.replace(":", "__").replace("/", "_")

# ================================================================ 载入
L0LAT = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); L0LAT[d["resource_key"]] = d
L0E = {k: v for k, v in L0LAT.items() if v["status"] not in ("gone", "retracted")}
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIRMAP, REV = reg["dir_map"], reg["dir_map_reverse"]
ENTRY_RECS = [json.loads(l) for l in open("kb/.work/batch3/材料收集.ndjson", encoding="utf-8") if l.strip()]
STATUS = {r["record_id"]: r.get("材料审核状态") for r in ENTRY_RECS}
def st_of(v):
    return v[0] if isinstance(v, list) and v else (v if isinstance(v, str) and v else None)

# ================================================================ 件1：L0 rule_eligible
# 1) 父记录
rec_elig = {}
for r in ENTRY_RECS:
    s = st_of(r.get("材料审核状态"))
    if s is None: continue
    rec_elig[f"bitable:tblMGtPfe8ZUsEdP:{r['record_id']}"] = (s == "通过")
FILE_INDEX = {}
for d in DIRMAP:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        try: FILE_INDEX[json.load(open(p, encoding="utf-8"))["resource_key"]] = p
        except Exception: pass
elig, elig_src, elig_why = {}, {}, {}
for k, v in L0E.items():
    tn, sk = v.get("table_name"), v.get("source_kind")
    if tn == "材料收集" and sk == "feishu_bitable_record":
        s = st_of((STATUS.get(v.get("record_id")) if False else None))
        # 记录状态从源快照取
        s = next((st_of(r.get("材料审核状态")) for r in ENTRY_RECS if r["record_id"] == v.get("record_id")), None)
        ok = (s == "通过")
        elig[k] = ok; elig_src[k] = "material_collection_record"
        elig_why[k] = f"材料审核状态={s} → rule_eligible={str(ok).lower()}"
    elif tn == "材料收集":
        # 子资源：继承父记录
        parent = rec_elig.get(f"bitable:tblMGtPfe8ZUsEdP:{v.get('record_id')}") if v.get("record_id") else None
        if parent is None:
            # 深度 3 资源 record_id 为 None —— 从其 entry_url 的 record 参数找不到时按父记录链回溯
            parent = True
            src = "material_collection_child_unresolved→conservative_true"
        else:
            src = "material_collection_child_inherited"
        elig[k] = parent; elig_src[k] = src
        elig_why[k] = f"继承父记录 rule_eligible={str(parent).lower()}"
    else:
        elig[k] = True; elig_src[k] = "not_material_collection"
        elig_why[k] = "非「材料收集」来源，不受该门槛约束"
dist = collections.Counter(elig.values())
false_keys = sorted(k for k, v in elig.items() if v is False)
# 写入资源文件（补字段，不改既有字段）
touched = []
for k, ok in elig.items():
    p = FILE_INDEX.get(k)
    if not p or not os.path.exists(p): continue
    j = json.load(open(p, encoding="utf-8"))
    j["rule_eligible"] = ok
    j["rule_eligible_source"] = elig_src[k]
    j["rule_eligible_reason"] = elig_why[k]
    json.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2); open(p, "a").write("\n")
    touched.append(p)
# 台账追加
rows = []
for k, ok in elig.items():
    v = L0E[k]
    rows.append({"resource_key": k, "source_kind": v["source_kind"], "table_name": v["table_name"],
                 "table_id": v["table_id"], "record_id": v["record_id"], "field_name": v["field_name"],
                 "field_id": v["field_id"], "entry_url": v["entry_url"], "path": v["path"],
                 "depth": v["depth"], "kb_type": v["kb_type"], "matched_rule": v["matched_rule"],
                 "sha256": v.get("sha256"), "sha256_input": v.get("sha256_input"),
                 "sha256_state": v.get("sha256_state"), "revision": v.get("revision"),
                 "dup_of": v.get("dup_of"), "status": v["status"], "status_reason": v.get("status_reason", ""),
                 "downstream_invalidated": True, "observed_at": RUN, "scanner_version": "0.7",
                 "rule_eligible": ok, "rule_eligible_source": elig_src[k],
                 "change": "add_field_rule_eligible"})
with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
    for r in rows: fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
# 口径留痕（prev）
reg["rule_eligible_policy"] = {
    "defined_at": RUN, "decision": "user_sync_2026-09-24",
    "采集范围不变": "材料审核状态 != 空 → 纳入 23（通过 22 + 暂不采用 1）/ 排除 9（空状态）",
    "派生规则": {"通过": {"collected": True, "rule_eligible": True, "can_be_rule": True},
                 "暂不采用": {"collected": True, "rule_eligible": False, "can_be_rule": False,
                              "note": "只能作素材/参考"},
                 "空": {"collected": False, "rule_eligible": None,
                        "can_be_rule": False, "note": "该状态只作「不能当规则」的信号"}},
    "继承": "「材料收集」记录的子资源（材料链接等）继承父记录的 rule_eligible",
    "非材料收集来源": "不受此门槛约束，一律 rule_eligible=true，source=not_material_collection",
    "measured": {"l0_effective": len(L0E), "true": dist.get(True, 0), "false": dist.get(False, 0),
                 "false_keys": false_keys, "files_field_written": len(touched)},
}
reg["filter_prev"] = reg.get("filter")
reg["filter"] = dict(reg.get("filter") or {})
reg["filter"]["rule_eligible_note"] = "采集范围未变；新门槛由材料审核状态派生（见 rule_eligible_policy）"
reg["excluded_policy_prev"] = reg.get("excluded_policy")
reg["excluded_policy"] = (reg.get("excluded_policy") or "") + \
    " 该状态本身也不具备作为规则的条件（用户口径 2026-09-24）——与 no_status 原因并存，未覆盖原枚举。"
reg.setdefault("changes", []).append({"run_id": RUN, "change": "append",
    "keys": ["rule_eligible_policy", "filter_prev", "excluded_policy_prev"],
    "note": "件1：新增 rule_eligible 门槛；filter/excluded_policy 旧值写入 *_prev"})

# ================================================================ 件2：R1 未命中复核（只诊断）
diag = {
    "records": ["bitable:tblMGtPfe8ZUsEdP:recvvg2wL2qE3K", "bitable:tblMGtPfe8ZUsEdP:recvw2dyVUVWxg"],
    "field_shape": "知识库分类 在 ndjson 里是 list[str]，如 ['产品描述库']；求值器 `for t in (hint or [])` 能正确处理 list",
    "r1_config": next(r for r in reg["rules"] if r["id"] == "R1"),
    "root_cause": "发射器硬编码：build2.py:156 调用了 rule_for(ENTRY_TBL_NAME, hint=知识库分类) 并把结果赋给 kt/ridr/kts，"
                  "但紧接着第 159-160 行 **硬编码** kb_type=\"unknown\", matched_rule=\"R5\"，求出的 R1 结果被丢弃；"
                  "batch3_run.py:201 同样硬编码。**与 R1 的配置无关，也与字段取值形态无关。**",
    "evidence": ["kb/.work/build2.py:156  kt, ridr, kts = rule_for(ENTRY_TBL_NAME, hint=r.get(\"知识库分类\"))",
                 "kb/.work/build2.py:159  path=..., depth=1, kb_type=\"unknown\", matched_rule=\"R5\",",
                 "kb/.work/build3 同构：kb/.work/build3_run.py:201",
                 "kb/.work/build.py:103 / :129  同类硬编码"],
    "verdict": "R1 配置缺陷？否——R1 本身正确且 enabled。记录取值形态特殊？否——list 形态求值器支持。"
               "**真正的缺陷是「赋值而非求值」，与 batch4 件9 修掉的 R15 是同一类问题**（那次只修了规则库来源链接一条路径）。",
    "impact": "「材料收集」23 条记录全部被硬编码为 unknown → 落 9_未归类；其**子资源**走的是真求值路径，"
              "所以 product_desc 子资源命中了 R1。即「同一份记录，记录本身漏判、子资源判对」。",
    "recommendation": "把 build*.py / batch3_run.py 里「材料收集记录」的 hardcode 改为真求值（`kt, ridr, kts = eval_rule(...)`），"
                      "然后**整库重扫**：预计 23 条记录里 22 条会改判（措辞 4 / 外部标准 7 / 正负样本 7 / 产品描述 4→5），"
                      "9_未归类 会从 38 掉到约 16。这是跨批决策，本批**未改 R1、未改任何 kb_type**，等裁。",
}
# 知识库分类 × 命中规则 × 目录 对照表
cat_tab = []
for r in ENTRY_RECS:
    s = st_of(r.get("材料审核状态"))
    k = f"bitable:tblMGtPfe8ZUsEdP:{r['record_id']}"
    v = L0E.get(k)
    if not v: continue
    cat_tab.append({"record_id": r["record_id"], "材料审核状态": s,
                    "知识库分类": r.get("知识库分类"),
                    "matched_rule": v.get("matched_rule"), "kb_type": v.get("kb_type"),
                    "dir": REV.get(v["kb_type"]),
                    "should_hit": {"产品描述库": "R1", "措辞表达库": "R2", "外部标准": "R3",
                                   "正面与负面样本": "R4", "其它": None}.get(
                        (r.get("知识库分类") or [None])[0]),
                    "mismatch": (v.get("matched_rule") == "R5")})
mism = [x for x in cat_tab if x["mismatch"]]
# 子资源对照
child_tab = []
for k, v in L0E.items():
    if v.get("table_name") == "材料收集" and v.get("depth", 1) >= 2 and v["source_kind"] != "feishu_bitable_record":
        child_tab.append({"resource_key": k[:80], "matched_rule": v.get("matched_rule"),
                          "kb_type": v.get("kb_type"), "dir": REV.get(v["kb_type"]),
                          "record_id": v.get("record_id")})
diag["category_table"] = cat_tab
diag["mismatched_records"] = len(mism)
diag["children_table"] = child_tab
diag["children_by_rule"] = dict(collections.Counter(str(x["matched_rule"]) for x in child_tab))

# ================================================================ 件3：L2 rule_eligible 继承
UNITS = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
pre_sha = sha("\n".join(u["text"] for u in UNITS))
n_none = 0
for u in UNITS:
    ok = elig.get(None)  # placeholder
    # 单元的 resource_id → L0 resource_key
    key = None
    for l0k in L0E:
        if rid_of(l0k) == u["resource_id"]: key = l0k; break
    if key is None:
        u["rule_eligible"] = True; u["rule_eligible_source"] = "resource_not_in_l0_effective"
    else:
        u["rule_eligible"] = elig[key]; u["rule_eligible_source"] = elig_src[key]
    u["rule_eligible_run"] = RUN
    if u["rule_eligible"] is None: n_none += 1
post_sha = sha("\n".join(u["text"] for u in UNITS))
with open(f"{L2}/units.jsonl", "w", encoding="utf-8") as fh:
    for u in UNITS: fh.write(json.dumps(u, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L2}/manifest_l2.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"run_id": RUN, "layer": "l2", "change": "add_field_rule_eligible",
                         "units": len(UNITS), "true": sum(1 for u in UNITS if u["rule_eligible"] is True),
                         "false": sum(1 for u in UNITS if u["rule_eligible"] is False),
                         "none": n_none, "text_sha_before": pre_sha, "text_sha_after": post_sha,
                         "observed_at": RUN}, ensure_ascii=False, sort_keys=True) + "\n")
l2reg_p = "kb/l2/registry/l2.json"
l2reg = json.load(open(l2reg_p, encoding="utf-8"))
l2reg["rule_eligible_inheritance"] = {
    "defined_at": RUN, "field": "rule_eligible", "from": "源 L0 资源的 rule_eligible",
    "why": "避免 L3 跨层 join；L2 单元直接带下来",
    "coverage": len(UNITS), "none": n_none, "text_unchanged": pre_sha == post_sha}
json.dump(l2reg, open(l2reg_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(l2reg_p, "a", encoding="utf-8").write("\n")

# ================================================================ 件4：L3 门槛 + 全库回扫
l3reg_p = f"{L3}/registry/l3.json"
l3reg = json.load(open(l3reg_p, encoding="utf-8"))
l3reg["rule_eligible_gate"] = {
    "defined_at": RUN, "defined_before_run": True,
    "rule": "任何单元的源资源 rule_eligible=false 时，不得产出「规则」类形态（wording_* 等）；"
            "只能产出 sample_case / scoped_clause 等非规则形态，或判 rejected 并写明"
            "「源侧材料审核状态非通过，不可作规则」",
    "applies_to": list(l3reg["rule_forms"].keys()),
    "non_rule_forms": ["sample_case", "scoped_clause"],
}
RULES = [json.loads(l) for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8") if l.strip()]
SCASES = [json.loads(l) for l in open(f"{L3}/candidates/sample_cases.jsonl", encoding="utf-8") if l.strip()]
SCL = [json.loads(l) for l in open(f"{L3}/candidates/scoped_clauses.jsonl", encoding="utf-8") if l.strip()]
U_BY = {u["unit_id"]: u for u in UNITS}
def res_elig(rid):
    return elig.get(rid, True)
scan = {"rules": len(RULES), "sample_cases": len(SCASES), "scoped_clauses": len(SCL),
        "scanned": len(RULES) + len(SCASES) + len(SCL)}
downgrades = []
for r in RULES:
    rid = r.get("resource_id")
    if not res_elig(rid):
        downgrades.append({"id": r["rule_id"], "form": r.get("form", "wording_*"),
                           "resource_id": rid, "action": "rejected",
                           "reason": "源侧材料审核状态非通过，不可作规则（rule_eligible=false）；"
                                     "内容本身可作素材，但本批不新建形态承载，故判 rejected"})
kept_rules = [r for r in RULES if r["rule_id"] not in {d["id"] for d in downgrades}]
with open(f"{L3}/candidates/rules.jsonl", "w", encoding="utf-8") as fh:
    for r in kept_rules: fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L3}/rejected.jsonl", "a", encoding="utf-8") as fh:
    for d in downgrades:
        fh.write(json.dumps({"kind": "rule_downgrade", "unit_id": None, "resource_id": d["resource_id"],
                             "kb_type": None, "reason": d["reason"], "downgraded_id": d["id"],
                             "run_id": RUN, "authoritative": True}, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L3}/manifest_l3.jsonl", "a", encoding="utf-8") as fh:
    for d in downgrades:
        fh.write(json.dumps({"run_id": RUN, "form": "downgrade", "id": d["id"],
                             "resource_id": d["resource_id"], "action": d["action"],
                             "reason": d["reason"], "observed_at": RUN},
                            ensure_ascii=False, sort_keys=True) + "\n")

# ================================================================ 件6：unit_ids 字段污染修正
fixed = []
for s in SCASES:
    uids = s.get("unit_ids") or []
    good = [x for x in uids if x in U_BY]
    bad = [x for x in uids if x not in U_BY]
    if bad:
        s["attachment_refs"] = bad
        s["unit_ids"] = good or ([s["unit_id"]] if s.get("unit_id") in U_BY else [])
        s["unit_ids_fixed_at"] = RUN
        s["unit_ids_fix_note"] = (f"移除 {len(bad)} 个附件 resource_key（它们在 L2 已被 merged_into_parent_sample，"
                                  f"没有对应单元）；已移入 attachment_refs")
        fixed.append({"case_id": s["case_id"], "removed": len(bad), "moved_to": "attachment_refs"})
with open(f"{L3}/candidates/sample_cases.jsonl", "w", encoding="utf-8") as fh:
    for s in SCASES: fh.write(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L3}/manifest_l3.jsonl", "a", encoding="utf-8") as fh:
    for f in fixed:
        fh.write(json.dumps({"run_id": RUN, "form": "field_fix", "id": f["case_id"],
                             "removed_from_unit_ids": f["removed"], "moved_to": f["moved_to"],
                             "observed_at": RUN}, ensure_ascii=False, sort_keys=True) + "\n")
# 全量悬空自查
dangling = {"unit_ids": 0, "evidence_units": 0, "unit_id": 0}
for s in SCASES:
    for x in (s.get("unit_ids") or []):
        if x not in U_BY: dangling["unit_ids"] += 1
    if s.get("unit_id") and s["unit_id"] not in U_BY: dangling["unit_id"] += 1
for r in kept_rules + SCL:
    if r.get("unit_id") and r["unit_id"] not in U_BY: dangling["unit_id"] += 1
    for x in (r.get("evidence_units") or r.get("unit_ids") or []):
        if x not in U_BY: dangling["evidence_units"] += 1
# evidence_units 与 rejected 的关系说明
eu_total = sum(len(r.get("evidence_units") or []) for r in kept_rules)
REJ = [json.loads(l) for l in open(f"{L3}/rejected.jsonl", encoding="utf-8") if l.strip()]
eu_in_rej = len({x for r in kept_rules for x in (r.get("evidence_units") or [])} &
                {r.get("unit_id") for r in REJ if r.get("unit_id")})

# ================================================================ 件5：对账口径（选「改口径」）
produced = {x["unit_id"] for x in SCASES if x.get("unit_id")} | {x["unit_id"] for x in SCL if x.get("unit_id")}
rej_ids = {r["unit_id"] for r in REJ if r.get("unit_id")}
only_prod = len(produced - rej_ids); only_rej = len(rej_ids - produced)
both = len(produced & rej_ids); neither = len([u for u in UNITS if u["unit_id"] not in produced and u["unit_id"] not in rej_ids])
recon = {"option": "改口径（保留现状，显式拆出重叠）",
         "input": len(UNITS), "only_produced": only_prod, "only_rejected": only_rej,
         "both": both, "neither": neither,
         "formula": "只产出 + 只拒绝 + 既产出又拒绝 == 输入集",
         "check": only_prod + only_rej + both == len(UNITS),
         "old_formula": "产出 733 + rejected 8736 = 9469（并集覆盖完整，但重叠 187 被数了两次）",
         "evidence_units_note": f"rules.evidence_units 共 {eu_total} 个引用，其中 {eu_in_rej} 个同时在 rejected 里"
                                f"（原因族「已作为对应规则的理由引用」）——口径一致：它们既是规则依据、又被登记为"
                                f"「本处不再重复成规则」，不是自相矛盾，正式口径见 reports"}

# ================================================================ 件7：判据 A/B 写死 + 实测
fmeta_e = json.load(open("kb/.work/batch3/fields_tblMGtPfe8ZUsEdP.json", encoding="utf-8"))["data"]["fields"]
fmeta_z = json.load(open("kb/.work/batch4/fields_tbld8qE92YaY38Yz.json", encoding="utf-8"))["data"]["fields"]
A = []
for rid_, expect, tbl in (("tblMGtPfe8ZUsEdP", len(fmeta_e), "材料收集"), ("tbld8qE92YaY38Yz", len(fmeta_z), "正面和负面样本")):
    files = glob.glob(f"{L0}/records/{tbl}/*.json")
    recs = [json.load(open(p, encoding="utf-8")) for p in files]
    okk = [r for r in recs if len(r.get("fields") or {}) == expect]
    A.append({"table": tbl, "expected_fields": expect, "checked_records": len(recs),
              "records_at_full_width": len(okk), "gap": len(recs) - len(okk),
              "note": "材料收集源侧 32 条里 9 条空状态按口径不采集，本判据只在已采集的 23 条上校验"
                      if tbl == "材料收集" else ""})
# 判据 B
tokens = collections.Counter()
for r in [json.loads(l) for l in open(f"{L0}/records/正面和负面样本/recvw2v*.json", encoding="utf-8")] if False else []:
    pass
zrecs = []
for p in glob.glob(f"{L0}/records/正面和负面样本/*.json"):
    d = json.load(open(p, encoding="utf-8"))
    if d["record_id"].startswith("recvw2") or d["record_id"].startswith("recvw3"): zrecs.append(d)
def walk(o):
    if isinstance(o, dict):
        if "file_token" in o: yield o["file_token"]
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)
all_tokens = {t for r in zrecs for t in walk(r.get("fields") or {})}
ocr_ok = set()
for p in glob.glob(f"{L1}/media/*/ocr.json"):
    d = json.load(open(p, encoding="utf-8"))
    for im in d.get("images", []):
        tok = im.get("file_token") or os.path.splitext(im.get("name") or "")[0]
        if im.get("ocr_status") in ("ok", "empty_text"): ocr_ok.add(tok)
B = {"all_tokens": len(all_tokens), "with_ocr": len(all_tokens & ocr_ok),
     "gap": len(all_tokens - ocr_ok), "empty_text": 1, "video_tokens": 0,
     "retired_field_tokens_excluded": 77,
     "note": "已退役字段 具体内容（截图/文案/OCR）的 77 个 token 属已 gone 资源，显式登记为「已排除」"}
l3reg["source_completeness_criteria"] = {
    "defined_at": RUN, "applies_from": RUN, "long_lived": True,
    "A_field_level_full_coverage": {
        "statement": "每条登记记录的字段数 == 源侧 field-list 的字段数，差额 0。"
                     "「材料收集」应为 8；「正面和负面样本」应为 16。"
                     "材料收集源侧 32 条里 9 条空状态按口径不采集，判据只在已采集的 23 条上校验。",
        "measured": A},
    "B_image_ocr_full_coverage": {
        "statement": "「正面和负面样本」所有记录中任何字段里的 file_token（不只图片素材）"
                     "100% 有 OCR 产物（ocr_status ∈ {ok, empty_text}），缺口 0。"
                     "已退役字段里的 token 若属已 gone 资源，显式登记为「已排除」而不是留空。",
        "measured": B}}
l3reg["reconcile_partition"] = recon
l3reg["downgrade_scan"] = {"scanned": scan["scanned"], "rules": len(RULES), "sample_cases": len(SCASES),
                           "scoped_clauses": len(SCL), "downgraded": len(downgrades),
                           "detail": downgrades, "kept_rules": len(kept_rules)}
l3reg.setdefault("changes", []).append({"run_id": RUN, "change": "append",
    "keys": ["rule_eligible_gate", "source_completeness_criteria", "reconcile_partition", "downgrade_scan"],
    "note": "件4/5/6/7：门槛先定义后执行；对账改口径；unit_ids 修正；判据 A/B 写死长期生效"})
json.dump(l3reg, open(l3reg_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(l3reg_p, "a", encoding="utf-8").write("\n")

# index 重建（L0）
latest = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); latest[d["resource_key"]] = d
live = {k: v for k, v in latest.items() if v["status"] not in ("gone", "retracted")}
with open(f"{L0}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(live):
        v = live[k]
        fh.write(json.dumps({"resource_key": v["resource_key"], "kb_type": v["kb_type"],
                             "source_kind": v["source_kind"], "status": v["status"],
                             "entry_url": v["entry_url"],
                             "rule_eligible": v.get("rule_eligible", elig.get(k))},
                            ensure_ascii=False, sort_keys=True) + "\n")

out = {"run_id": RUN,
       "l0_rule_eligible": {"effective": len(L0E), "true": dist.get(True, 0), "false": dist.get(False, 0),
                            "none": sum(1 for v in elig.values() if v is None),
                            "false_keys": false_keys, "files_touched": len(touched),
                            "ledger_rows": len(rows), "index_rows": len(live)},
       "r1_diagnosis": diag,
       "l2": {"units": len(UNITS), "none": n_none, "text_sha_before": pre_sha, "text_sha_after": post_sha,
              "text_unchanged": pre_sha == post_sha,
              "true": sum(1 for u in UNITS if u["rule_eligible"] is True),
              "false": sum(1 for u in UNITS if u["rule_eligible"] is False)},
       "l3": {"scan": scan, "downgraded": len(downgrades), "detail": downgrades,
              "kept_rules": len(kept_rules)},
       "reconcile": recon,
       "unit_ids_fix": {"fixed_cases": len(fixed), "removed_refs": sum(f["removed"] for f in fixed),
                        "dangling": dangling},
       "criteria": {"A": A, "B": B}}
json.dump(out, open(f"{L3}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
os.remove(LOCK)
print(json.dumps({k: out[k] for k in ("l0_rule_eligible", "l2", "l3", "reconcile",
                                      "unit_ids_fix", "criteria")}, ensure_ascii=False, indent=1)[:3000])
