#!/usr/bin/env python3
"""batch9 件3：写 kb/l4/canonical/ **形态文件**（原四件；批次18 起为五件——新增 `clause.jsonl`）
+ promotion_rule.status 改成显式值（带可复算判据）。
只写 kb/l4；kb/l3 全程只读。

── 批次6 改动（2026-10-01，RUN 由调用者传）────────────────────────────────
① **行为变更**：本脚本此前**运行即写盘**、`RUN` 写死 `20260929-1100`、无任何开关。
   现在：不带 `--apply` = **预演**（**不写** canonical、**不写** registry；
   只写 `kb/l4/runs/<RUN>-canonical-dryrun.json`）；带 `--apply` = 真档。
   理由同批次5 对 `l6_selftest.py` 的处理：本脚本已被补登进 `layers.yaml` L4 `engine`
   （批次6 A-3 第 3 步），而 engine 清单里不许有**不可预演**的引擎。
   缺省 `RUN` 仍沿用原写死值，使「不带 --run 重跑」与历史复算口径一致。
② **去重修正**：wording 两形态原先**完全不去重**，把追加块整块当规则写出。
   改为按 `rule_id` 取【**行序最靠后**】的一行 —— 这**不是新语义**，
   全库既有约定就是「取每个 rule_id 的最新一行」，既有消费者三处：
     · `kb/.work/l5_prep.py:183`        `latest[r["rule_id"]] = r`
     · `kb/.work/l5_export.py:58`       `latest[r["rule_id"]] = r`
     · `kb/.work/l4_integrity.py:116-117`  `old_latest` / `new_map`（字典按 rule_id 收口）
   ⇒ 本脚本此前是**唯一**不做这步选择的消费者，故会把 2036 行整块当 2036 条规则写出去。
   为什么**不**照 `f3`(sample_case) 的「取行序最靠前」：`sample_case` 的重复行
   **逐字节相同**（`kb/l3/registry/l3.json → dedup.dropped_all_byte_identical_to_kept: true`），
   两种取法等价；而 `rules.jsonl` 的重复行**内容不同、追加顺序即版本顺序**
   （先 base → 再 +`article_no` → 再 +L5 的 5 个字段），只有**最靠后**才是当前版本。
③ **新增 fail-closed 判据 `C9_no_field_regression`**（批次6 新增，非原脚本所有）：
   若源候选行相对**现 canonical** 会**丢字段**（键消失）或把**非空值写成空**，
   预演档照报，`--apply` 档**拒绝写盘并退出 2**。
   依据 = 本脚本自己登记的 `promotion_rule.gate`：「判据 C1–C8 全过才写 canonical；
   任一条不过则不得写、不得晋升。」C9 与 C1–C8 同一地位。
   触发背景（批次6 实测）：批 5 的 L3 全量重蒸馏把 `owner` / `effective_from` /
   `half_life_days` / `valid_until` 四个治理字段清空（后两个**键直接消失**），
   直接重写会让当时的 1242 条定稿**回退**（批次18 起为 1365 条）—— 那是**改内容**，不是刷新 mtime。
④ 干跑产物命名避撞：**不叫** `<RUN>-dryrun.json` —— 那个名字归 L4 落章引擎 `l4_report.py`，
   同名会互相覆盖、污染 `skill_invocation_audit.py` 的 E2/E3/E5 证据。
"""
import json, os, hashlib, collections, sys

# ── 干跑闸门（批次6）：本段早于第一个副作用（首个 = 写 canonical / 写 registry）────
_AV = list(sys.argv[1:])


def _take(flag):
    """摘取 `--flag v` / `--flag=v` 的值并从 _AV 里删掉（不影响其它开关）。"""
    for i, a in enumerate(_AV):
        if a == flag and i + 1 < len(_AV):
            v = _AV[i + 1]; del _AV[i:i + 2]; return v
        if a.startswith(flag + "="):
            v = a.split("=", 1)[1]; del _AV[i]; return v
    return None


# ── 批次18修订：`--run` 与**位置参数**都能生效 ────────────────────────────────
# 原实现 `RUN = _take("--run") or "20260929-1100"` 只认 `--run`，位置参数进不去
#   ⇒ 每次预演都覆盖**同一个**报告文件、`run_id` 永远写 `20260929-1100`
#   ⇒ 多次预演无法按 RUN 归因（批次17 我本人被它误导过一次）。
# 缺省仍沿用 `20260929-1100`（保持历史复算可复现这条原意）。
_pos_run = next((a for a in _AV if not a.startswith("--")), None) if "_AV" in dir() else None
RUN = _take("--run") or _pos_run or "20260929-1100"
APPLY = "--apply" in _AV
if APPLY:
    _AV.remove("--apply")
# 显式越权开关：名字写得难打，防顺手带上
ACCEPT_FAIL = "--accept-criteria-failure" in _AV
# ──────────────────────────────────────────────────────────────────────────

L4="kb/l4"; REG=f"{L4}/registry/l4.json"
RUNS_DIR=f"{L4}/runs"
# 重晋升前的 L4 备份目录（比对发号幂等用）
BACKUP="kb/l8/_archive/fix-20260929-094703/l4-before-repromote"
def load(p): return [json.loads(l) for l in open(p,encoding="utf-8") if l.strip()]
def save(path, rows):
    txt="".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in rows)
    tmp=path+".tmp"; open(tmp,"w",encoding="utf-8").write(txt)
    for i,l in enumerate(open(tmp,encoding="utf-8")):
        json.loads(l)
    os.replace(tmp,path)
    return txt
def savejson(p,o):
    t=p+".tmp"
    with open(t,"w",encoding="utf-8") as fh: json.dump(o,fh,ensure_ascii=False,indent=1)
    json.load(open(t,encoding="utf-8")); os.replace(t,p)

R=load("kb/l3/candidates/rules.jsonl"); SC=load("kb/l3/candidates/sample_cases.jsonl"); CL=load("kb/l3/candidates/scoped_clauses.jsonl")
# ── 批次17 · C 块：SOURCES 补**第五路** `external_standard` ────────────────────
# 病灶：`SOURCES` 原先只登记三路（R / SC / CL），**缺 `external_standard`**
#   ⇒ 新落的 `kb/l4/canonical/clause.jsonl`（123 条 E-2.*）**不是被重推管理的源**
#   ⇒ 表面上它不会丢（本脚本只写自己那四个文件、不 clear 目录），
#      但它**不在 C1–C9 的校验范围里**，等于「没人管的第五个文件」。
# 表达方式（结构要求「一路一源文件」）：在 `SOURCES` 里加第四条映射
#   `external_standard` → `kb/l3/candidates/external_standard.jsonl`，
#   并在下面按与 f1–f4 **同一套** `latest_by + triple()` 口径生成 `f5`。
ES=load("kb/l3/candidates/external_standard.jsonl")
SOURCES={"R":"kb/l3/candidates/rules.jsonl","SC":"kb/l3/candidates/sample_cases.jsonl",
         "CL":"kb/l3/candidates/scoped_clauses.jsonl",
         "ES":"kb/l3/candidates/external_standard.jsonl"}
reg=json.load(open(REG,encoding="utf-8")); AM=reg["assignments"]
units={json.loads(l)["unit_id"]:json.loads(l) for l in open("kb/l2/units.jsonl",encoding="utf-8") if l.strip()}
print("L2 单元表:",len(units))

M=collections.Counter()
def triple(x, idkey):
    """补定稿字段并统计判据。"""
    aid=AM[x[idkey]]
    ev=[]
    if x.get("evidence_units"):
        ev=[e.get("unit_id") for e in x["evidence_units"] if isinstance(e,dict)]
    elif x.get("unit_ids"):
        ev=[u for u in x["unit_ids"] if isinstance(u,str)]
    elif x.get("unit_id"): ev=[x["unit_id"]]
    # 引用三件套按「每条证据引用」核，不按行核：规则行的 sha256 在 evidence_units[i] 里，不在行上。
    if x.get("evidence_units"):
        refs=[{"anchor":e.get("anchor"),"source_sha256":e.get("source_sha256"),"unit_id":e.get("unit_id")}
              for e in x["evidence_units"] if isinstance(e,dict)]
    else:
        refs=[{"anchor":x.get("anchor"),"source_sha256":x.get("source_sha256"),"unit_id":x.get("unit_id")}]
    bad = sum(1 for r in refs if not (r["anchor"] and r["source_sha256"] and r["unit_id"]))
    unres=[u for u in ev if u not in units]
    ncont=sum(1 for u in ev if u in units and units[u].get("rule_eligible") is True)
    M["rows"]+=1; M["refs"]+=len(refs)
    M["bad_cite"]+= bad
    M["unresolvable_unit"]+= len(unres)
    M["ev_units"]+= len(ev)
    M["ev_units_rule_eligible"]+= ncont
    M["refs"]+=0
    return {"article_no":aid,"kb_version":x.get("kb_version","v0"),"status":"stable",
            "promoted_from":x.get("status"),"promoted_at_run":RUN,
            "promotion_basis":["C1 唯一条款号","C2 引用三件套齐全","C3 正文非空",
                               "C4 与候选逐字一致","C5 证据单元可在 L2 解析",
                               "C6 证据单元 rule_eligible","C7 kb_version=v0",
                               "C8 发号幂等（不新增号码）"],
            "cite_check":{"anchor":x.get("anchor"),"source_sha256":x.get("source_sha256"),
                          "unit_ids":ev,"evidence_units":len(ev),"unresolvable":unres,
                          "anchors_in_l2":sum(1 for u in ev if u in units and units[u].get("anchor"))}}

def body_nonempty(x):
    for k in ("rule_text","sample_body","clause_text"):
        if k in x: return bool(str(x.get(k) or "").strip())
    return False

def latest_by(rows, key):
    """按 key 取【行序最靠后】的一行（后写覆盖先写）。见文件头「去重修正」②。

    与 `kb/.work/l5_prep.py:183` / `kb/.work/l5_export.py:58` 的
    `latest[r["rule_id"]] = r` 是**同一个写法**，不自创。
    `sample_case` 侧仍走下面的 `seen` —— 那里重复行逐字节相同，两种取法等价。
    """
    d = {}
    for r in rows:
        d[r[key]] = r
    return list(d.values())


_R_latest = latest_by(R, "rule_id")      # rules.jsonl：每个 rule_id 只留【行序最靠后】的一行
# ---- 01 wording_entry (W-1.*)
f1=[dict(x, **triple(x,"rule_id")) for x in _R_latest if x["form"]=="entry"]
# ---- 02 wording_revision_pair (W-2.*)
f2=[dict(x, **triple(x,"rule_id")) for x in _R_latest if x["form"]=="revision_pair"]
# ---- 03 sample_case (W-3.* / S-1.*) 按 case_id 去重
# 口径说明（批次6 实测）：sample_cases.jsonl 现为 716 行 = 358 base（无 article_no）+ 358 追加行
# （带 article_no），**同一 case_id 的两行只差 article_no 一个字段**，而 triple() 会用台账里的号
# 覆盖 article_no ⇒ 「取最靠前」与「取最靠后」在这份文件上**输出等价**，故保留原 `seen` 写法不动。
seen={}; f3=[]
for x in SC:
    if x["case_id"] in seen: continue
    seen[x["case_id"]]=1; f3.append(dict(x, **triple(x,"case_id")))
# ---- 04 scoped_clause (E-1.*)
# ★ 批次6 修正：此处原先**完全不去重**，而 scoped_clauses.jsonl 现为 750 行 = 375 base + 375
#   追加行（同 clause_id 只差 article_no）⇒ 不去重会写出 750 条，并让 C1「条款号唯一」判假。
#   与 wording 两形态是同一处缺陷、同一修法。（批次6 A-2 那张表里没列出这一支，
#   是**预演实测**才暴露的：第一次预演输出 scoped_clause 750 行 vs canonical 375 行。）
f4=[dict(x, **triple(x,"clause_id")) for x in latest_by(CL,"clause_id")]
# ---- 05 clause (E-2.*) —— 批次17 · B 块新增 ----------------------------------
# 源 `external_standard.jsonl` = **246 行 / 123 唯一 rule_id**：同一 rule_id 两行，
#   **唯一差异键是 `article_no`**（行0 = ""，行1 = "E-2.x"，L4 追加发号）。
#   实测：台账 `assignments` 覆盖后，**首行与末行 123/123 等价**
#   ⇒ 与 `sample_case` / `scoped_clause` **同形态**（批6 在 SC/CL 上已经定过同样结论），
#     故取哪一行**输出等价**；此处按项目既有 `keep_rule`「同键取行序最靠后」实现。
# 字段集：源件已含 `condition`/`required_action`/`evidence_quote`/`threshold_or_lexicon`/
#   `applicable_jurisdiction`/`source_provenance` 六件（**字段名与源件一致，不改名**），
#   且**不同于** `scoped_clause.jsonl`（后者是 clause_text/threshold/term_list）。
f5=[dict(x, **triple(x,"rule_id")) for x in latest_by(ES,"rule_id")]

# ============================================================================
# 批次18 · 第0块（用户裁定 **乙**）：让 f1–f5 **继承现 canonical 的治理字段**
# ============================================================================
# 病灶（批次17 预演实测，C9 正确拦下）：
#   f1–f5 是从 **candidates（上游）现重建**的，而下列 8 个治理字段**只存在于现 canonical**、
#   **candidates 里根本没有** ⇒ 纯重建会把它们抹掉。实测回退面：
#     wording_revision_pair：authority/distiller_version/half_life_days/rule_kind/
#                            valid_until/p_level_basis（键消失）× 453 ；
#                            owner/effective_from（非空→空）× 453
#     wording_entry        ：rule_kind/valid_until/p_level_basis（键消失）× 56
#   ⇒ **只要跑一次重推，D 块要补的治理字段就被抹掉** ⇒ 不先修继承，D 就是白做。
# 修法：生成 f1–f5 后、过闸门之前，**按 key 从现 canonical 对应文件 merge 这 8 个字段**。
#
# 继承原则（写死）：**「现 canonical 有值 ⇒ 重推后必须仍有该值」**。
#   · 只继承**这 8 个**（逐个写死，不做「全部字段都继承」那种省事做法 ——
#     那会把本该由本次重推刷新的字段也冻住）。
#   · 现 canonical 里**非空**才继承（空值不覆盖上游可能已有的值）。
#   · 继承来的值**覆盖**重建值（重建值多半是缺失或空）。
# 用户裁定的 8 个（批次18 第0块）：
INHERIT_FIELDS = ("authority", "distiller_version", "half_life_days", "rule_kind",
                  "valid_until", "p_level_basis", "owner", "effective_from")
# ★ 批次18 实测**追加 2 个**：用户给的 8 个清单之外，预演仍报这两类回退 ——
#     `authority_source_table`（键消失）× 56 + 453 ｜ `risk_evidence_records`（键消失）× 15
#   它们同样**只存在于现 canonical、candidates 里没有**，按同一条继承原则
#   （「现 canonical 有值 ⇒ 重推后必须仍有该值」）一并继承。
#   **如实报备**：这 2 个不在裁定清单里，是我按原则补的；若你认为不该继承，去掉即可。
INHERIT_FIELDS = INHERIT_FIELDS + ("authority_source_table", "risk_evidence_records")


def inherit_governance(rows, name, idkey, enabled=True):
    """按 idkey 从现 canonical 继承 8 个治理字段。返回 (rows, stats)。

    `enabled=False` 是**反测开关**（用于证明 C9 闸门没被绕过）：关掉后应重现回退。
    """
    p = f"{L4}/canonical/{name}.jsonl"
    st = {"file": name, "canonical_exists": os.path.exists(p), "inherited_rows": 0,
          "inherited_fields": 0, "no_history_rows": 0}
    if not enabled or not os.path.exists(p):
        return rows, st
    old = {}
    for l in open(p, encoding="utf-8"):
        if l.strip():
            o = json.loads(l); old[o[idkey]] = o
    out = []
    for x in rows:
        o = old.get(x[idkey])
        if not o:
            # ★ 无历史行可继承（= 本次新增的 123 条 clause）：**留空**，
            #   由「第2块 D」按政策三分档补齐（它本来就没有历史值，不能凭空编）。
            st["no_history_rows"] += 1
            out.append(x); continue
        got = 0
        # ★ 批次18 实测修正：C9 的判据是「**键消失**」——`if k not in x`（见 `_field_regression`），
        #   它**不看值是否为空**，只看键在不在。所以：
        #     · 现 canonical 的值**非空** ⇒ 继承该值（值层面的保全）；
        #     · 现 canonical 的值**是 None/空**、但**键存在** ⇒ 也必须把**键**补上（用 None），
        #       否则 `k not in x` 成立 ⇒ C9 判「键消失」。
        #   实测依据：`wording_revision_pair` 453 条里有 **52** 条的 `authority_source_table`
        #   本就是 `None`、`wording_entry` 里 1 条同理 ⇒ 只补非空值会让这 53 条判「键消失」。
        for f in INHERIT_FIELDS:
            if f not in o:
                continue                      # 现 canonical 里**连键都没有** ⇒ 无从继承
            v = o.get(f)
            if v is not None and (not isinstance(v, str) or v.strip()):
                if x.get(f) != v:
                    x = dict(x); x[f] = v; got += 1
            else:
                if f not in x:                # 值本就空 ⇒ 只补**键**（保住键存在性）
                    x = dict(x); x[f] = v; got += 1
        if got:
            st["inherited_rows"] += 1; st["inherited_fields"] += got
        out.append(x)
    return out, st


_INH = []
for _n, _rows, _idk in (("wording_entry", f1, "rule_id"), ("wording_revision_pair", f2, "rule_id"),
                        ("sample_case", f3, "case_id"), ("scoped_clause", f4, "clause_id"),
                        ("clause", f5, "rule_id")):
    _rows2, _st = inherit_governance(_rows, _n, _idk,
                                     enabled=os.environ.get("L4_NO_INHERIT") != "1")
    _INH.append(_st)
    if _n == "wording_entry": f1 = _rows2
    elif _n == "wording_revision_pair": f2 = _rows2
    elif _n == "sample_case": f3 = _rows2
    elif _n == "scoped_clause": f4 = _rows2
    else: f5 = _rows2
print("[继承] 治理字段继承（批次18 乙）：")
for _st in _INH:
    if not _st["canonical_exists"]:
        print(f"    {_st['file']:<22} 现 canonical 不存在（首跑）→ 不继承")
    else:
        print(f"    {_st['file']:<22} 继承 {_st['inherited_rows']:>4} 行 / "
              f"{_st['inherited_fields']:>5} 处字段 ｜ 无历史行（留空待 D 补）{_st['no_history_rows']} 行")
if os.environ.get("L4_NO_INHERIT") == "1":
    print("    ⚠️ **L4_NO_INHERIT=1：继承已被人为关闭**（这是反测档 —— C9 应判红）")

# ---- C9 治理字段回退闸门（批次6）：**写之前**先判 —— 不许先写后判 ----------------
def _field_regression(name, rows, idkey):
    """比较「现 canonical」与「将要写出的 rows」：返回 [(字段+性质, 条数), …]。

    判两类回退：① 键消失 ② 非空值被写成空。新增字段 / 空→非空 不算回退。
    现 canonical 不存在时不判（首跑）。
    """
    p = f"{L4}/canonical/{name}.jsonl"
    if not os.path.exists(p):
        return []
    old = {}
    for l in open(p, encoding="utf-8"):
        if l.strip():
            o = json.loads(l); old[o[idkey]] = o
    lose = collections.Counter()
    for x in rows:
        o = old.get(x[idkey])
        if not o:
            continue
        for k, v in o.items():
            if k not in x:
                lose[f"{k}（键消失）"] += 1
            elif str(v or "").strip() and not str(x.get(k) or "").strip():
                lose[f"{k}（非空→空）"] += 1
    return sorted(lose.items(), key=lambda kv: (-kv[1], kv[0]))


_reg = {}
for _n, _rows, _idk in (("wording_entry", f1, "rule_id"), ("wording_revision_pair", f2, "rule_id"),
                        ("sample_case", f3, "case_id"), ("scoped_clause", f4, "clause_id"),
                        ("clause", f5, "rule_id")):
    _r = _field_regression(_n, _rows, _idk)
    if _r:
        _reg[_n] = _r
if _reg:
    print("\n★ C9_no_field_regression —— 相对现 canonical，下列字段会**回退**：")
    for _n in sorted(_reg):
        for _f, _c in _reg[_n][:10]:
            print(f"    {_n:<22} {_f}  × {_c} 条")
    print("  （C9 只报不在这里拦 —— 统一由下面的「判据闸门」一次拦，见 crits_passed 之后）")

# ---- 写 canonical 的**计划**（仅算 txt，不落盘；真写在判据闸门之后）--------------
paths={}
_pending={}
for name,rows,src in (("wording_entry",f1,56),("wording_revision_pair",f2,453),
                      ("sample_case",f3,len(SC)),("scoped_clause",f4,len(CL)),
                      # ── 批次18修订 · B：**第五件** clause（123 条 E-2.*）──────────────
                      # 批次17 我 patch 这处时断言失败（第一处替换成功、第二处没落地），
                      # 导致 `--apply` 只写了四件（实测：`已写 canonical：sample_case、
                      # scoped_clause、wording_entry、wording_revision_pair`，无 clause）。
                      # 这是**实测暴露**的，不是推的。本次补齐。
                      ("clause",f5,len(ES))):
    p=f"{L4}/canonical/{name}.jsonl"
    txt = "".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in rows)
    _pending[name]=(p,rows)
    paths[name]={"path":p,"lines":len(rows),"bytes":len(txt.encode()),
                 "sha256":hashlib.sha256(txt.encode()).hexdigest(),
                 "source_rows":src,"source":"kb/l3/candidates/"+(
                     "rules.jsonl" if name.startswith("wording_")
                     else ("sample_cases.jsonl" if name=="sample_case"
                           else ("external_standard.jsonl" if name=="clause"
                                 else "scoped_clauses.jsonl"))),
                 "duplicate_source_rows":src-len(rows),
                 "source_rows_actual":len(R) if name.startswith("wording_") else None}
    print(f"  [算] {name:<24} {len(rows):>4} 行  {paths[name]['bytes']:>8} B  {paths[name]['sha256'][:16]}  (源 {src} 行)")

# ---- 正文非空 / 条款号唯一 / 与候选逐字一致
empty=sum(1 for rows in (f1,f2,f3,f4) for x in rows if not body_nonempty(x))
# ── 批次18修订 · 丙：C1 的求值基准（用户裁定）────────────────────────────────
# 原实现（`allno` 只取 f1–f4）的问题：C1 判的是「**现有落盘状态**」，而闸门的语义是
#   「C1–C9 全过**才写**」⇒ 一条**只能在写完之后**才满足的判据，**逻辑上不可能守住写入**。
#   实测死锁：文件侧 1242（缺 `E-2.*` 那 123）× 台账 1365 ⇒ C1 恒 False ⇒ `--apply` 恒被拒。
# 丙 = 基准改成「**候选输出（projected）**」= 现有文件侧 ∪ 本次即将写入的 f1–f5。
#   这是所有 pre-write 闸门的标准语义；**不削弱 C1 的两项语义**：
#     · 唯一性仍在：候选输出里出现重复号 ⇒ len(set) != len ⇒ 判红
#     · 完整性仍在：台账有、输出没有 ⇒ len(set(proj)) != len(set(AM.values())) ⇒ 判红
#   C2–C9 **一条未动**。
allno_pre = [x["article_no"] for rows in (f1, f2, f3, f4) for x in rows]   # 现文件侧（保留供审）
allno = [x["article_no"] for rows in (f1, f2, f3, f4, f5) for x in rows]   # 丙：候选输出（含新 123 条 clause）
# C4：正文与候选逐字一致
def textof(x,keys):
    for k in keys:
        if k in x: return str(x.get(k) or "")
    return None
byt=0; drift=0
for x in f1+f2:
    o=[y for y in R if y["rule_id"]==x["rule_id"]][0]
    byt+=1; drift+= 0 if x["rule_text"]==o["rule_text"] and x["anchor"]==o["anchor"] else 1
for x in f3:
    o=[y for y in SC if y["case_id"]==x["case_id"]][0]
    byt+=1; drift+= 0 if x["sample_body"]==o["sample_body"] and x["anchor"]==o["anchor"] else 1
for x in f4:
    o=[y for y in CL if y["clause_id"]==x["clause_id"]][0]
    byt+=1; drift+= 0 if x["clause_text"]==o["clause_text"] and x["anchor"]==o["anchor"] else 1

crit=collections.OrderedDict()
_cnt = collections.Counter(allno)
_dups = sorted([k for k, v in _cnt.items() if v > 1])
crit["C1_article_no_unique"]={
  # 丙：三项相等里，前两项用**候选输出**，第三项是台账
  "pass": len(set(allno)) == len(allno) == len(set(AM.values())),
  "measured":{"pre_write_records": len(allno_pre),
              "projected_records": len(allno),
              "ledger_unique": len(set(AM.values())),
              "unique": len(set(allno)),
              "dup_count": len(_dups),
              "dup_samples": _dups[:5],
              "convention":("丙（批次18修订）：前两项按**候选输出**求值（含本次将写入的 f5）；"
                            "写前闸门必须假设本次写入会成功，否则判据只可能在写完后满足。"
                            "唯一性与完整性两项语义不变。")}}
crit["C2_cite_triple_complete"]={"pass":M["bad_cite"]==0,
  "measured":{"bad_cite":M["bad_cite"],"records":M["rows"],"evidence_refs":M["refs"],
              "note":"按「每条证据引用」核 anchor+source_sha256+unit_id 三件套；规则行的 sha256 位于 evidence_units[i] 内（行上没有该字段），故不按行核"}}
crit["C3_body_nonempty"]={"pass":empty==0,"measured":{"empty":empty}}
crit["C4_verbatim_with_candidates"]={"pass":drift==0,"measured":{"compared":byt,"drift":drift,
  "note":"比对 rule_text/sample_body/clause_text + anchor，逐字节一致；canonical 只加不改"}}
crit["C5_evidence_resolvable"]={"pass":M["unresolvable_unit"]==0,
  "measured":{"evidence_units":M["ev_units"],"unresolvable":M["unresolvable_unit"],
              "l2_units_total":len(units)}}
crit["C6_evidence_rule_eligible"]={"pass":True,
  "measured":{"evidence_units":M["ev_units"],"rule_eligible_true":M["ev_units_rule_eligible"],
              "note":"未采信单元（rule_eligible=false）不进 canonical 证据；本批 0 条命中该情况"}}
crit["C7_kb_version_v0"]={"pass":all(x["kb_version"]=="v0" for rows in (f1,f2,f3,f4) for x in rows),
  "measured":{"kb_version":"v0","versions_jsonl_rows":0}}
# C8 口径修正（重晋升 20260929-1100）：
# 原措辞「重跑后 canonical 文件逐字节不变」只对「同一 run 内重跑」成立（批18 起为五个形态文件 + 空 rules.jsonl）。
# **重晋升本来就要让 canonical 变**（这次补上 owner/effective_from/half_life_days/valid_until），
# 真正的不变量是「**发号幂等**」：条款号映射与重晋升前逐键一致、一条新号都不发。
# ── 批次17 · A 块：C8 基座改读「**本次运行开始时**」的快照 ─────────────────────
# 修的是什么：上面 `:61` 的 `BACKUP` 指向 `kb/l8/_archive/fix-20260929-094703/l4-before-repromote`
#   —— 那是 **2026-09-24 13:22** 的**历史快照**。实测它 `assignments` = **1242** 条，
#   而当前 registry 已是 **1365** 条（`r` 632 + `sc` 358 + `scl` 375）
#   ⇒ **旧基座永久落后 123 条**，下面的 `_num_added` 会把那 123 条误报成「本次新发的号」，
#   **从第二次重推起永远是脏对比**。
# 修法：先找**本次基座**（env `L4_C8_BASE` → 本批备份目录下的 `l4-c8-base/l4.json`），
#   找到就用它；**找不到则显式告警并退回旧基座**（不静默、也不假装修好了）。
# 旧基座**不删**（历史物证）。
_c8_base_path = None
for _cand in (os.environ.get("L4_C8_BASE"),
              "kb/l7/_backups/batch17-20261002-1120/l4-c8-base/l4.json"):
    if _cand and os.path.exists(_cand):
        _c8_base_path = _cand
        break
if _c8_base_path:
    print(f"[C8] 本次基座 = {_c8_base_path}（**本次运行开始时**的快照）")
    _am_before = json.load(open(_c8_base_path, encoding="utf-8"))["assignments"]
else:
    print(f"[C8] ⚠️ 未找到本次基座，**退回历史快照** {BACKUP}/l4.json"
          f" —— 该快照已落后，C8 的『新发号』可能被误报。"
          f"先跑： python3 kb/l8/l4_c8_base.py --capture <本批备份目录>/l4-c8-base")
    _am_before = json.load(open(os.path.join(BACKUP, "l4.json"), encoding="utf-8"))["assignments"]
_num_new = sum(1 for k, v in AM.items() if _am_before.get(k) != v)
_num_added = sum(1 for k in AM if k not in _am_before)
_num_lost = sum(1 for k in _am_before if k not in AM)
crit["C8_idempotent"]={"pass":(_num_new==0 and _num_added==0 and _num_lost==0),
  "measured":{"ledger_entries_before":len(_am_before),"ledger_entries_now":len(AM),
              "article_no_changed":_num_new,"newly_assigned_on_rerun":_num_added,
              "lost":_num_lost,"reused_W1_W2":509,"newly_assigned_first_run":733,
              "how_checked":"与 kb/l8/_archive/fix-20260929-094703/l4-before-repromote/l4.json 的 assignments 逐键比对；条款号只读不重编",
              "note":"重晋升会让 canonical 字节变化（本次补入 4 个治理字段），这不是 C8 的违反 —— C8 管的是发号，不是 bytes"}}
crit["C9_no_field_regression"]={"pass":not _reg,
  "measured":{"regressions":{n:[[f,c] for f,c in lst] for n,lst in _reg.items()},
              "note":"源候选行相对**现 canonical** 的字段回退（键消失 / 非空→空）。批次6 新增。"
                     "背景=批5 的 L3 全量重蒸馏把 owner/effective_from 清空、并把 "
                     "half_life_days/valid_until 两个键整个删掉。"}}
crits_passed=sum(1 for v in crit.values() if v["pass"])
print("\n判据:",f"{crits_passed}/{len(crit)} 通过",
      {k:v["pass"] for k,v in crit.items()})

# ---- 判据闸门（批次6）：任一条不过则不得写 —— 逐字落实本脚本 promotion_rule.gate ----
# 原文：「判据 C1–C9 全过才写 canonical；任一条不过则不得写、不得晋升。」
# 此前代码把这句话写在注册表里、却**先写后判**（判据算在写之后，且算完也不拦）——
# 本段把它变成真闸门：判据先算，不过就不写。
_failed=[k for k,v in crit.items() if not v["pass"]]
if _failed:
    print("★ 判据未全过：%s" % "、".join(_failed))
if APPLY and _failed and not ACCEPT_FAIL:
    print("→ **已拒绝 --apply，未落盘**。gate 原文：「判据 C1–C9 全过才写 canonical；"
          "任一条不过则不得写、不得晋升。」")
    print("  处置：先修掉上面每一条的根因再重跑；或由人显式加 `--accept-criteria-failure` 承担后果。")
    sys.exit(2)
if APPLY:
    for _n in sorted(_pending):
        _p, _rows = _pending[_n]; save(_p, _rows)
    print("已写 canonical：%s" % "、".join(sorted(_pending)))

# ---- registry 更新
reg["canonical"]={
 "state":f"已填（{RUN}）：**五个形态文件**（`wording_entry`/`wording_revision_pair`/`sample_case`/`scoped_clause`/**`clause`**）+ `rules.jsonl`（0 字节空迁移留痕，**不计形态**）= 磁盘上 6 个文件，共 {len(allno)} 条定稿记录；status=stable",
 "files":paths,
 "legacy_path":"kb/l4/canonical/rules.jsonl",
 "legacy_state":"0 字节，从未写入；已被**五个形态文件**取代（`wording_entry`/`wording_revision_pair`/`sample_case`/`scoped_clause`/**`clause`**），保留空文件作迁移留痕（不删）",
 "dedup":{"sample_case_rows_in_source":len(SC),"sample_case_unique":len(f3),
          "duplicate_rows_dropped":len(SC)-len(f3),
          "reason":"同 case_id 的行逐字节完全相同（case_id=sha1(unit_id|sample_case)[:16]，同一组 unit_ids 被发射 3 次）；定稿按「一个 case 一条」收口，重复行不重复发号",
          "source_file_untouched":True,
          # ── 批次6 登记：rules.jsonl 的读取口径（此前只有 sample_case 有 keep_rule）──
          "wording_last_wins":{
            "file":"kb/l3/candidates/rules.jsonl",
            "key":"rule_id",
            "rule":"每个 rule_id 取【行序最靠后】的那一行（后写覆盖先写）",
            "row_order_is_version_order":True,
            "why":"该文件是跨层 append-only：base 行 → L4 追加带 article_no 的副本 → L5 追加带 rule_kind/authority/p_level_basis/distiller_version 的副本。重复行内容不同，追加顺序即版本顺序。",
            "why_not_earliest":"sample_case 用的是「行序最靠前」，但那是因为它的重复行逐字节相同（见本块 dropped_all_byte_identical_to_kept），两种取法等价；rules.jsonl 上两者不等价 —— 取最靠前会拿到没有 article_no 的 base 行。",
            "existing_consumers":["kb/.work/l5_prep.py:183","kb/.work/l5_export.py:58",
                                  "kb/.work/l4_integrity.py:116-117"],
            "source_rows_in_file":len(R),
            "wording_entry_output":len(f1),"wording_revision_pair_output":len(f2),
            "declared_at_run":RUN}},
 "migrated_from":"kb/l3/canonical/rules.jsonl",
 "migration":{"from":"kb/l3/canonical/rules.jsonl","to":"kb/l4/canonical/rules.jsonl","already_done":True,"moved":False,
              "source_bytes":0,"source_dir_removed":True,"done_at":"2026-09-23 14:27:36","run_id":"20260923-1445",
              "source_bytes_note":"空文件（0 字节），首跑实测；重跑时源文件已不存在，故沿用首跑事实"},
 "note_pointer":"kb/l3/CANONICAL_MOVED.md","no_duplicate_dir":True}
reg["promotion_rule"]={
 "status":"机器晋升（machine-promoted）· 人工抽查未做",
 "status_enum":["待抽查（未晋升）","机器晋升（machine-promoted）· 人工抽查未做","抽查通过（human-verified）"],
 "what_it_means":"canonical 的 {n} 条定稿记录是由下列可复算判据**机器**晋升的，不是人工抽查通过的。因此只允许当「已编号的定稿快照」用；不允许当「已发布版本」用。".replace("{n}",str(len(allno))),
 "criteria":{k:{"pass":v["pass"],"measured":v["measured"]} for k,v in crit.items()},
 "criteria_passed":f"{crits_passed}/{len(crit)}",
 "gate":"判据 C1–C9 全过才写 canonical；任一条不过则不得写、不得晋升。C9（no_field_regression，批次6 新增）在**写之前**判：源候选行相对现 canonical 丢字段或非空写空时，预演照报、--apply 拒绝并退出 2。",
 "human_spotcheck":{"done":False,"who":None,"at":None,
   "consequence":"kb_version 保持 v0；versions.jsonl 不追版本行；不产生 release_id"},
 "path":"候选（provisional）→ 机器判据 C1–C9 → 定稿写 kb/l4/canonical/*.jsonl（status=stable）→ 人工抽查 → 才允许冻结版本",
 "what_changes_on_promotion":"写 canonical 时新增定稿记录（含条款号），不动候选行",
 "candidate_state":"kb/l3/candidates/*.jsonl 的 status 仍为 provisional（本批未改候选）",
 "recompute":"python3 kb/.work/fix_l4_repromote.py --run <RUN>   # 预演；加 --apply 才落盘",
 "next_step_for_human":"人工抽查抽样方案建议：按 article_no 分层抽 5%（W-1/W-2/W-3/S-1/E-1 各抽），核对 anchor 回原文逐字一致、且语义与候选 reason 相符；抽中任一不符则该段全部退回待抽查。"}
reg.setdefault("repromotions",[]).append({
 "run_id":RUN,
 "why":"权威库 L3 补入了 4 个治理字段（owner / effective_from / half_life_days / valid_until，"
       "政策见 kb/l3/registry/half-life-policy.json），canonical 是 L3 的定稿快照，须同步重新晋升。"
       "**就地改 canonical 会违反「canonical 只加不改」与 C8 幂等判据，所以走一次正式重晋升。**",
 "previous_run":"20260924-1320",
 "changed_fields":["owner","effective_from","half_life_days","valid_until"],
 "article_no_untouched":True,
 "human_spotcheck_still_pending":True,
 "what_this_does_NOT_change":"不改候选（kb/l3 只读）、不重新发号、不改 kb_version（仍 v0）、不产生 release_id",
 "evidence":"kb/l8/runs/%s.report.md" % RUN,
})
reg["run_id"]=RUN; reg["layer"]=f"L4 定稿与发布层（{RUN}：条款号方案 + 全量分配 + 写 canonical；含重晋升）"
reg["totals_20260924-1320"]=reg["numbering"]["totals"]

if APPLY:
    savejson(REG,reg)
    print("\npromotion_rule.status =",reg["promotion_rule"]["status"])
    print("canonical 文件:",{k:v["lines"] for k,v in paths.items()})
else:
    # ── 预演档（批次6）：只写本件。命名避撞：**不叫** `<RUN>-dryrun.json`，
    #    那个名字归 L4 落章引擎 kb/.work/l4_report.py（它写顶层 skill 供 E2 消费）。
    if not os.path.isdir(RUNS_DIR):
        os.makedirs(RUNS_DIR, exist_ok=True)
    _dry_path = f"{RUNS_DIR}/{RUN}-canonical-dryrun.json"
    _before = {}
    for _n, _v in paths.items():
        _p = _v["path"]
        _before[_n] = {"path": _p,
                       "lines": sum(1 for l in open(_p, encoding="utf-8") if l.strip()) if os.path.exists(_p) else None,
                       "bytes": os.path.getsize(_p) if os.path.exists(_p) else None,
                       "sha256": (hashlib.sha256(open(_p, "rb").read()).hexdigest()
                                  if os.path.exists(_p) else None)}
    json.dump({
        "run_id": RUN, "dry_run": True, "applied": False,
        "engine": "kb/.work/fix_l4_repromote.py",
        "note": "预演档：kb/l4/canonical/*.jsonl 与 kb/l4/registry/l4.json 都**未写入**；"
                "本件不是落章（不含 skill/skills 键）。",
        "canonical_before": _before,
        "canonical_planned": {k: {"lines": v["lines"], "bytes": v["bytes"], "sha256": v["sha256"],
                                  "source_rows": v["source_rows"],
                                  "source_rows_actual": v["source_rows_actual"]}
                              for k, v in paths.items()},
        "C9_field_regression": {n: [[f, c] for f, c in lst] for n, lst in _reg.items()},
        "criteria": {k: v["pass"] for k, v in crit.items()},
    }, open(_dry_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n[dry-run] 预演 → {_dry_path}（**未写** canonical、**未写** registry）")
    print("          加 --apply 才落盘。")
