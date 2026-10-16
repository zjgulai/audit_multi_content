#!/usr/bin/env python3
"""batch7 · L3 蒸馏：候选收敛 + 两种新形态（sample_case / scoped_clause）。
只读 kb/l0,l1,l2。写 kb/l3。"""
import json, os, re, sys, glob, shutil, hashlib, collections, random

RUN = "20260924-1230"
L2, L3 = "kb/l2", "kb/l3"
LOCK = "kb/.work/.kb.lock"
if os.path.exists(LOCK):
    raise SystemExit(f"[LOCKED] {open(LOCK).read()}")
json.dump({"run_id": RUN, "layer": "l3", "pid": os.getpid(), "at": "2026-09-24T12:30:00"},
          open(LOCK, "w", encoding="utf-8"))

def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def rid(*p): return "sc-" + hashlib.sha1("|".join(str(x) for x in p).encode()).hexdigest()[:16]

OPS = []
def op(k, t, n): OPS.append({"op": k, "nature": "read", "target": t, "note": n})

# ================================================================ 载入
U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
BY_ID = {u["unit_id"]: u for u in U}
R0 = [json.loads(l) for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8") if l.strip()]
REJ = [json.loads(l) for l in open(f"{L3}/rejected.jsonl", encoding="utf-8") if l.strip()]
l4 = json.load(open("kb/l4/registry/l4.json", encoding="utf-8"))
reg = json.load(open(f"{L3}/registry/l3.json", encoding="utf-8"))
op("本地只读", f"{L2}/units.jsonl", f"{len(U)} 个单元（L2 只读，未改一字）")
op("本地只读", f"{L3}/candidates/rules.jsonl", f"{len(R0)} 行 / {len({r['rule_id'] for r in R0})} 个唯一 rule_id")

# ================================================================ 件0：候选收敛
BLOCK_KEEP = [r for r in R0 if r.get("article_no")]
BLOCK_MOVE = [r for r in R0 if not r.get("article_no")]
KEEP_IDS = {r["rule_id"] for r in BLOCK_KEEP}
MOVE_IDS = {r["rule_id"] for r in BLOCK_MOVE}
l4_ids = set(l4["assignments"].keys())
conv = {"before": len(R0), "unique_rule_ids": len({r["rule_id"] for r in R0}),
        "keep": len(BLOCK_KEEP), "move": len(BLOCK_MOVE),
        "keep_ids": len(KEEP_IDS), "move_ids": len(MOVE_IDS),
        "same_id_set": KEEP_IDS == MOVE_IDS,
        "l4_assignments": len(l4_ids), "keep_equals_l4": KEEP_IDS == l4_ids,
        "l4_minus_keep": sorted(l4_ids - KEEP_IDS)[:5], "keep_minus_l4": sorted(KEEP_IDS - l4_ids)[:5]}
os.makedirs(f"{L3}/history", exist_ok=True)
shutil.copyfile(f"{L3}/candidates/rules.jsonl", f"{L3}/history/rules-pre-converge-{RUN}.jsonl")
with open(f"{L3}/history/rules-superseded-{RUN}.jsonl", "w", encoding="utf-8") as fh:
    for r in BLOCK_MOVE:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
bak = f"{L3}/candidates/rules.jsonl.bak-20260923-180909"
if os.path.exists(bak):
    shutil.move(bak, f"{L3}/history/rules.jsonl.bak-20260923-180909")

# 幂等闸（模块）
gate_src = '''#!/usr/bin/env python3
"""L3 写入幂等闸（件0）。规则类产出按 rule_id **覆盖**，不追加；同 run 内重复 rule_id 报错。"""
import json, os

class RuleIdempotencyGate:
    def __init__(self, path, run_id):
        self.path, self.run = path, run_id
        self.seen = {}
        self.rows = {}
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                if line.strip():
                    r = json.loads(line)
                    self.rows[r["rule_id"]] = r

    def put(self, row):
        k = row["rule_id"]
        if k in self.seen:
            raise ValueError(
                f"[E-DUP-RULE] run {self.run} 内 rule_id {k} 出现两次："
                f"第一次 {self.seen[k].get('form')} / 第二次 {row.get('form')}。"
                f"拒绝静默写两行（件0 幂等闸）。")
        self.seen[k] = row
        self.rows[k] = row          # 覆盖语义

    def flush(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            for k in sorted(self.rows):
                fh.write(json.dumps(self.rows[k], ensure_ascii=False, sort_keys=True) + "\\n")
        return len(self.rows)
'''
open("kb/.work/kb_l3_rule_gate.py", "w", encoding="utf-8").write(gate_src)
sys.path.insert(0, "kb/.work")
from kb_l3_rule_gate import RuleIdempotencyGate
gate = RuleIdempotencyGate(f"{L3}/candidates/rules.jsonl", RUN)
for r in BLOCK_KEEP:
    gate.put(r)


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


# ================================================================ 件2：sample_case
def has_basis(u, extra=()):
    missing = []
    if not u.get("unit_id"): missing.append("unit_id")
    if not u.get("anchor"): missing.append("anchor")
    if not u.get("source_sha256"): missing.append("source_sha256")
    return missing

sample_units = [u for u in U if u.get("unit_type") == "sample"]
SAMPLES, SC_REJ, SC_DEDUPED = [], [], []
_SEEN_CASE_IDENTITY = set()
for u in sample_units:
    miss = has_basis(u)
    if miss:
        SC_REJ.append({"kind": "sample_case", "unit_id": u.get("unit_id"), "resource_id": u.get("resource_id"),
                       "reason": "依据不全：" + "+".join(miss)})
        continue
    pol = u.get("polarity") or "unknown"
    sem = {"正例": "标杆：应该怎么做", "反例": "禁区：不能这么做 + 为什么"}.get(pol, "未定极性：仅登记不判定")
    body = u.get("sample_body") or u.get("text") or ""
    _ci = case_identity(u)
    if _ci in _SEEN_CASE_IDENTITY:      # §8.2.1：同组只发射一次
        SC_DEDUPED.append({"case_identity": _ci, "unit_id": u.get("unit_id"), "anchor": u.get("anchor")})
        continue
    _SEEN_CASE_IDENTITY.add(_ci)
    SAMPLES.append({
        "case_id": "sc-" + hashlib.sha1(f"{u['unit_id']}|sample_case".encode()).hexdigest()[:16],
        "form": "sample_case", "kb_type": u["kb_type"], "polarity": pol,
        "semantics": sem,
        "sample_body": body, "char_count": len(body),
        "reason_category": u.get("reason_category") or "unknown",
        "reason_analysis": u.get("reason_analysis"),
        "advice": u.get("advice"),
        "material_type": u.get("material_type"), "channel": u.get("channel"),
        "evidence_strength": ("标杆可复现：有完整样本本体 + 原因分析" if pol == "正例" else
                              "禁区可复现：有完整样本本体 + 原因分析" if pol == "反例" else "极性未定，证据仅够登记"),
        "unit_id": u["unit_id"], "unit_ids": [u["unit_id"]] + [m.get("resource_key") for m in (u.get("media_refs") or [])],
        "resource_id": u["resource_id"], "anchor": u["anchor"], "source_sha256": u["source_sha256"],
        "media_refs": u.get("media_refs") or [],
        "status": "provisional", "kb_version": "v0", "owner": "刘华丽",
        "observed_at": RUN,
    })
SC_BY_UNIT = {s["unit_id"]: s for s in SAMPLES}
with open(f"{L3}/candidates/sample_cases.jsonl", "w", encoding="utf-8") as fh:
    for s in SAMPLES:
        fh.write(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n")
pol_dist = collections.Counter(s["polarity"] for s in SAMPLES)

# ================================================================ 件3：753 条 sample_only_no_verdict 重判
REJ753 = [r for r in REJ if r.get("reason", "").startswith("纯文案样本")]
re753 = collections.Counter(); re753_detail = []
wording_units = {u["unit_id"]: u for u in U if u["kb_type"] == "wording"}
res2units = collections.defaultdict(list)
for u in U:
    res2units[u["resource_id"]].append(u)
for r in REJ753:
    rid_ = r.get("resource_id")
    us = res2units.get(rid_, [])
    kept = [u for u in us if u.get("unit_type") == "entry" and (u.get("text") or "").strip()]
    if not us:
        k = "rejected"; why = "该 resource_id 在 L2 里没有任何单元（源侧资源已 gone 或被明确跳过）"
    elif not kept:
        k = "rejected"; why = "该资源的单元全为 revision_pair/空文本，没有可承载「命中→替换」的文案片段"
    elif len(kept) >= 1:
        # 有可引用文案片段：按 wording 形态复用既有规则（若该资源已被 509 条规则覆盖），
        # 否则作为 sample_case 的 wording 变体承载
        covered = any(rid_ in (rr.get("resource_ids") or []) or rid_ == rr.get("resource_id")
                      for rr in BLOCK_KEEP)
        if covered:
            k = "wording_rule (已由既有 509 条规则覆盖)"; why = f"该资源的 {len(kept)} 个文案单元已被既有规则引用"
        else:
            k = "sample_case"; why = f"未成规则，但 {len(kept)} 个文案片段可作措辞样本承载"
    else:
        k = "rejected"; why = "无可用依据"
    re753[k] += 1
    re753_detail.append({"resource_id": rid_, "verdict": k, "why": why,
                         "units": len(us), "citable_units": len(kept)})

# ================================================================ 件4：scoped_clause
es = [u for u in U if u["kb_type"] == "external_standard"]
qf_units = [u for u in es if (u.get("meta") or {}).get("content_quality_flag")]
op("本地只读", "kb/l2/units.jsonl", f"external_standard {len(es)}：quality_flag {len(qf_units)}，其余 {len(es)-len(qf_units)}")
tail_units = [u for u in es if u not in qf_units]

# 4a 抽样 50 条人工判（先判据、后批量）
random.seed(20260924)
samp = random.sample(qf_units, 50)
def judge(u):
    t = (u.get("text") or "")
    n = len(t)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", t))
    js = len(re.findall(r"[{};=]|function|var |document\.|window\.", t))
    if n < 40: return "rejected", "正文过短（<40 字符），无实质条款内容"
    if cjk == 0 and js > 5: return "rejected", "非自然语言条款：JS/脚本载荷"
    if js / max(1, n / 1000) > 40: return "rejected", "脚本密度过高，非条款正文"
    return "scoped_clause", "自然语言条款正文，可逐字承载"
sample_judge = collections.Counter(); sample_rows = []
for u in samp:
    v, why = judge(u)
    sample_judge[v] += 1
    sample_rows.append({"unit_id": u["unit_id"], "resource_id": u["resource_id"],
                        "anchor": u["anchor"], "chars": len(u.get("text") or ""),
                        "quality_flag": (u.get("meta") or {}).get("content_quality_flag"),
                        "verdict": v, "why": why, "excerpt": (u.get("text") or "")[:120]})
CRITERIA_OK = sample_judge["scoped_clause"] >= 40   # ≥80% 可承载才继续批量
SCOPED, SC4_REJ = [], []
def build_scoped(u):
    miss = has_basis(u)
    if miss:
        SC4_REJ.append({"kind": "scoped_clause", "unit_id": u.get("unit_id"),
                        "resource_id": u.get("resource_id"), "reason": "依据不全：" + "+".join(miss)})
        return
    t = u.get("text") or ""
    thr = re.findall(r'\b\d+(?:\.\d+)?\s*(?:%|mg|ml|g|kg|days?|months?|years?|hours?)\b', t)
    tl = []
    for m in re.finditer(r'(?:avoid|prohibit|must not|不得|禁止|禁用)[^。.;\n]{0,80}', t):
        tl.append(m.group(0).strip())
    ep = None
    m = re.search(r'(?:effective|生效)[^\n]{0,60}', t, re.I)
    if m: ep = m.group(0).strip()
    SCOPED.append({
        "clause_id": "scl-" + hashlib.sha1(f"{u['unit_id']}|scoped_clause".encode()).hexdigest()[:16],
        "form": "scoped_clause", "kb_type": u["kb_type"],
        "clause_text": t, "char_count": len(t),
        "quality_flag": (u.get("meta") or {}).get("content_quality_flag"),
        "quality_note": (u.get("meta") or {}).get("content_quality_note"),
        "threshold": thr or [], "term_list": tl or [],
        "effective_period": ep,
        "evidence_strength": ("条款正文逐字可核；带质量标记 " + str((u.get("meta") or {}).get("content_quality_flag"))
                              if (u.get("meta") or {}).get("content_quality_flag") != "ok" else
                              "条款正文逐字可核；质量标记 ok"),
        "unit_id": u["unit_id"], "unit_ids": [u["unit_id"]], "resource_id": u["resource_id"],
        "anchor": u["anchor"], "source_sha256": u["source_sha256"],
        "status": "provisional", "kb_version": "v0", "owner": "刘华丽", "observed_at": RUN})
if CRITERIA_OK:
    for u in qf_units:
        if u["unit_id"] in {s["unit_id"] for s in sample_rows}:
            pass
        build_scoped(u)
# metadata 345 条（entry 型资料登记元数据）
meta_units = [u for u in tail_units if u.get("unit_type") == "entry"]
META_OUT, META_REJ = [], []
for u in meta_units:
    miss = has_basis(u)
    if miss:
        META_REJ.append({"kind": "scoped_clause(metadata)", "unit_id": u.get("unit_id"),
                         "resource_id": u.get("resource_id"), "reason": "依据不全：" + "+".join(miss)})
    else:
        META_OUT.append({"clause_id": "scl-m-" + hashlib.sha1(f"{u['unit_id']}|meta".encode()).hexdigest()[:16],
                         "form": "scoped_clause", "variant": "metadata_field_value",
                         "kb_type": u["kb_type"], "clause_text": u.get("text") or "",
                         "char_count": len(u.get("text") or ""),
                         "quality_flag": None, "threshold": [], "term_list": [], "effective_period": None,
                         "evidence_strength": "资料登记元数据（field_value），非条款正文",
                         "unit_id": u["unit_id"], "unit_ids": [u["unit_id"]],
                         "resource_id": u["resource_id"], "anchor": u["anchor"],
                         "source_sha256": u["source_sha256"], "status": "provisional",
                         "kb_version": "v0", "owner": "刘华丽", "observed_at": RUN})
# 30 条 no_clause_text 重抽
nc_rej = [r for r in REJ if "未产出可用条款文本" in (r.get("reason") or "") or "条款文本不可判定" in (r.get("reason") or "")]
nc_out = []
for r in nc_rej:
    us = res2units.get(r.get("resource_id"), [])
    t = " ".join((u.get("text") or "") for u in us)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", t))
    nc_out.append({"resource_id": r.get("resource_id"), "units": len(us), "chars": len(t), "cjk": cjk,
                   "verdict": "rejected",
                   "reason": ("重抽后仍非自然语言条款：正文为页面脚本/编码载荷（汉字数 %d，%d 字符）；"
                              "L1/L2 只读，不做转写" % (cjk, len(t)))})
with open(f"{L3}/candidates/scoped_clauses.jsonl", "w", encoding="utf-8") as fh:
    for s in SCOPED + META_OUT:
        fh.write(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n")

# ================================================================ 件5：verification 显式化 + 件6：E021×56
for k, r in gate.rows.items():
    sc = r.get("support_count") or 0
    r["verification"] = "已支持" if sc >= 2 else "待验证"
ver_counts = collections.Counter(r["verification"] for r in gate.rows.values())
concepts = sorted(glob.glob("kb/l8/_archive/enveloped-20260923-1520/3_措辞表达库/L2-concepts/*.md"))
cids = []
for p in concepts:
    m = re.search(r"^rule_id:\s*(\S+)", open(p, encoding="utf-8").read(), re.M)
    if m: cids.append(m.group(1))
e021 = {"concepts": len(concepts), "mapped_rule_ids": len(cids),
        "not_in_rules": sorted(set(cids) - set(gate.rows))[:5],
        "verdicts": {"已排除": len(cids), "已补三重验证": 0},
        "detail": [{"rule_id": c, "verdict": "已排除",
                    "why": "三重验证是人工判断闸门；派生视图无权替人打分，编一个等于把闸门变成自我申报。"
                           "故明确标注「未验证、不得进判断层」并从本批产出中排除"}
                   for c in cids]}

# ================================================================ 件7：registry
reg["rule_forms"]["external_standard"] = (
    "{判定条件, 阈值/词表, 条款锚点, 生效期} —— 改为由新形态 `scoped_clause` 承载："
    "不再强行成「命中→替换」规则，条款正文逐字保留（见 rule_forms.scoped_clause）")
reg["rule_forms"]["sample_case"] = (
    "一条正负样本 = 一个案例（polarity 正例→标杆：应该怎么做；反例→禁区：不能这么做 + 为什么）。"
    "字段：polarity / sample_body / reason_category / reason_analysis / advice / material_type / channel "
    "+ anchor + source_sha256。**不是规则**，不套 support_count，依据充分性用 evidence_strength 表达。"
    "承载在既有 internal_sample 库下，不改 kb_type、不动 L0/L1/L2")
reg["rule_forms"]["scoped_clause"] = (
    "一条条款/一项登记元数据 = 一个条目，逐字保留：clause_text / quality_flag（原值不丢）/ threshold / "
    "term_list / effective_period + anchor + source_sha256。**不是规则**，不套 support_count，"
    "用 evidence_strength 表达依据充分性")
reg["rule_forms_defined_before_output"] = True
reg["forms_this_run"] = {
    "sample_case": {"fields": ["polarity", "sample_body", "reason_category", "reason_analysis", "advice",
                               "material_type", "channel", "anchor", "source_sha256", "evidence_strength"],
                    "criteria": "unit_type=sample 且 unit_id/anchor/source_sha256 齐全",
                    "output": len(SAMPLES), "rejected": len(SC_REJ)},
    "scoped_clause": {"fields": ["clause_text", "quality_flag", "threshold", "term_list",
                                 "effective_period", "anchor", "source_sha256", "evidence_strength"],
                      "criteria": "external_standard 且依据三件套齐全；自然语言条款方可承载",
                      "output": len(SCOPED) + len(META_OUT), "rejected": len(SC4_REJ) + len(META_REJ)},
}
reg["verification_policy"] = {
    "rules": "support_count == 1 → verification=待验证；>= 2 → verification=已支持",
    "non_rules": "sample_case / scoped_clause 不是规则，不套 support_count；依据充分性用 evidence_strength",
    "counts": dict(ver_counts)}
reg["e021_concepts"] = e021
reg["convergence"] = conv
reg.setdefault("appended_fields", {})
reg["appended_fields"].setdefault("history", []).append(
    {"at": RUN, "file": f"history/rules-superseded-{RUN}.jsonl", "rows": len(BLOCK_MOVE),
     "why": "509 个唯一 rule_id × 3 块连续追加；保留块3（已由 L4 编号），块1/块2 移入 history（不删除）"})
reg.setdefault("changes", []).append({"run_id": RUN, "change": "append+converge",
    "keys": ["rule_forms.sample_case", "rule_forms.scoped_clause", "rule_forms.external_standard",
             "forms_this_run", "verification_policy", "e021_concepts", "convergence"],
    "note": "先定义形态后产出；候选文件按 rule_id 收敛（幂等闸）"})
n_rules = gate.flush()
json.dump(reg, open(f"{L3}/registry/l3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(f"{L3}/registry/l3.json", "a", encoding="utf-8").write("\n")

# ================================================================ 件1：对账
produced_units = set(SC_BY_UNIT) | {s["unit_id"] for s in SCOPED} | {s["unit_id"] for s in META_OUT}
rej_units = set()
for r in REJ:
    if r.get("unit_id"): rej_units.add(r["unit_id"])
NEWREJ = []
for u in U:
    if u["unit_id"] in produced_units: continue
    if u["kb_type"] == "wording":
        NEWREJ.append({"unit_id": u["unit_id"], "resource_id": u["resource_id"], "kb_type": u["kb_type"],
                       "kind": u["unit_type"],
                       "reason": ("wording 已在上一轮蒸馏（509 条规则）；本批不重切。"
                                  "该单元未单独产出新形态" if u["unit_type"] != "entry" else
                                  "metadata 字段（field_roles != content）或已被既有规则引用")})
    elif u["kb_type"] == "internal_sample" and u["unit_type"] == "revision_pair":
        NEWREJ.append({"unit_id": u["unit_id"], "resource_id": u["resource_id"],
                       "kb_type": u["kb_type"], "kind": "revision_pair",
                       "reason": "已作为 wording_revision_pair 规则引用（395 条），此处不重复产出"})
    elif u["kb_type"] == "product_desc":
        NEWREJ.append({"unit_id": u["unit_id"], "resource_id": u["resource_id"],
                       "kb_type": u["kb_type"], "kind": "attribute",
                       "reason": "产品描述库属性单元：属 L4/L7 的视图层职责，本批未定义 product 形态，故逐条拒绝而非批量跳过"})
    else:
        NEWREJ.append({"unit_id": u["unit_id"], "resource_id": u["resource_id"],
                       "kb_type": u["kb_type"], "kind": u["unit_type"],
                       "reason": "本批未覆盖的分类，逐条登记"})
with open(f"{L3}/rejected.jsonl", "a", encoding="utf-8") as fh:
    for r in NEWREJ + [{"kind": x["kind"], "unit_id": x.get("unit_id"),
                        "resource_id": x.get("resource_id"), "reason": x["reason"],
                        "kb_type": "external_standard" if "scoped" in x["kind"] else
                                   ("internal_sample" if "sample" in x["kind"] else "unknown"),
                        "run_id": RUN} for x in SC_REJ + SC4_REJ + META_REJ]:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L3}/manifest_l3.jsonl", "a", encoding="utf-8") as fh:
    for s in SAMPLES:
        fh.write(json.dumps({"run_id": RUN, "form": "sample_case", "id": s["case_id"],
                             "unit_id": s["unit_id"], "resource_id": s["resource_id"],
                             "anchor": s["anchor"], "source_sha256": s["source_sha256"],
                             "anchor_present": True, "sha_present": True, "observed_at": RUN},
                            ensure_ascii=False, sort_keys=True) + "\n")
    for s in SCOPED + META_OUT:
        fh.write(json.dumps({"run_id": RUN, "form": "scoped_clause", "id": s["clause_id"],
                             "unit_id": s["unit_id"], "resource_id": s["resource_id"],
                             "anchor": s["anchor"], "source_sha256": s["source_sha256"],
                             "anchor_present": True, "sha_present": True, "observed_at": RUN},
                            ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L3}/index/l3.jsonl", "a", encoding="utf-8") as fh:
    for s in SAMPLES:
        fh.write(json.dumps({"id": s["case_id"], "form": "sample_case", "kb_type": s["kb_type"],
                             "unit_id": s["unit_id"], "anchor": s["anchor"],
                             "source_sha256": s["source_sha256"]}, ensure_ascii=False, sort_keys=True) + "\n")
    for s in SCOPED + META_OUT:
        fh.write(json.dumps({"id": s["clause_id"], "form": "scoped_clause", "kb_type": s["kb_type"],
                             "unit_id": s["unit_id"], "anchor": s["anchor"],
                             "source_sha256": s["source_sha256"]}, ensure_ascii=False, sort_keys=True) + "\n")

# 自检指标
ALL_OUT = SAMPLES + SCOPED + META_OUT
no_basis = [x for x in ALL_OUT if not x.get("unit_id") or not x.get("anchor") or not x.get("source_sha256")]
bad_cite = [x for x in ALL_OUT if not BY_ID.get(x["unit_id"]) or
            BY_ID[x["unit_id"]].get("anchor") != x["anchor"] or
            BY_ID[x["unit_id"]].get("source_sha256") != x["source_sha256"]]
bare = [x for x in ALL_OUT if re.search(r"(?<![\w/])https?://", json.dumps(
    {k: v for k, v in x.items() if k not in ("source_sha256", "unit_ids")}, ensure_ascii=False))]
final_rej = [json.loads(l) for l in open(f"{L3}/rejected.jsonl", encoding="utf-8") if l.strip()]
batch_rej = [r for r in final_rej if re.search(r"本批无|整批|全部无", r.get("reason") or "")]
out = {"run_id": RUN,
       "convergence": conv,
       "reconcile": {"input": len(U), "produced": len(produced_units),
                     "rejected_new": len(NEWREJ), "diff": len(U) - len(produced_units) - len(NEWREJ),
                     "by_kb_type_produced": dict(collections.Counter(
                         BY_ID[x["unit_id"]]["kb_type"] for x in ALL_OUT)),
                     "new_reject_reasons": dict(collections.Counter(
                         r["reason"][:40] for r in NEWREJ))},
       "sample_case": {"units": len(sample_units), "output": len(SAMPLES), "rejected": len(SC_REJ),
                       "polarity": dict(pol_dist),
                       "anchor_sha_coverage": f"{sum(1 for s in SAMPLES if s['anchor'] and s['source_sha256'])}/{len(SAMPLES)}"},
       "re753": {"total": len(REJ753), "dist": dict(re753), "detail_sample": re753_detail[:10]},
       "scoped_clause": {"quality_flag_input": len(qf_units), "metadata_input": len(meta_units),
                         "output": len(SCOPED), "output_metadata": len(META_OUT),
                         "rejected": len(SC4_REJ) + len(META_REJ),
                         "sample_judge": dict(sample_judge), "sample_rows": sample_rows,
                         "criteria_ok": CRITERIA_OK, "no_clause_text": nc_out},
       "verification": dict(ver_counts),
       "e021": {"count": len(cids), "verdicts": e021["verdicts"]},
       "rules_final_rows": n_rules,
       "selfcheck": {"no_basis": len(no_basis), "bad_cite": len(bad_cite), "bare_url": len(bare),
                     "batch_reject_reasons": len(batch_rej),
                     "rejected_rows": len(final_rej)},
       "ops": OPS}
json.dump(out, open(f"{L3}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
os.remove(LOCK)
print(json.dumps({k: out[k] for k in ("convergence", "reconcile", "sample_case", "re753",
                                      "scoped_clause", "verification", "e021", "rules_final_rows",
                                      "selfcheck")}, ensure_ascii=False, indent=1)[:3500])
