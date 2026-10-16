#!/usr/bin/env python3
"""L3 蒸馏（v0.2）：按「规则码」聚合词条型，按「修订原因」成簇案例型，并做到取数对账为 0。
方法论来自已安装的 knowledge-distillation skill；冲突时以任务规格为准。
kb/l0、kb/l1、kb/l2 只读；产物只写 kb/l3。
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

import json, os, re, hashlib, collections, sys

# ── 批次11 · C-2：台账去重实现只有一份（kb/kb_ledger.py），这里只取用 ──────────
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import kb_ledger as _ledger_mod
# ── 2026-10-08（Owner 批准「②③ 先做」之 ③）：覆盖写改走**原子写** ─────────────
# ★ 为什么落在这儿：本脚本的 `_write_guarded()` 是 `rules.jsonl` 的**唯一活截断写方**，
#   而 `rules.jsonl` 正是**评审链读得最多**的那个文件（引擎侧 10 处读入口）。
#   截断写的窗口里读者会读到 **0 字节或半份** —— `_safe_write` 自证 ⑦ 就是这个缺陷的
#   反向对照（裸写：写到一半时读者读到 7,500 字符；原子写：换上去之前目标仍是完整旧版）。
# ★ 为什么 ②（给追加加锁）**没做**：实测否掉了那个假设（4 线程 24 万行、4 进程 × 20KB 行
#   全部零穿行）—— 结论与机理钉在 `kb/.work/_safe_write.py` 自证 ⑧⑨ 那段注释里。
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".work"))
import _safe_write as _sw  # noqa: E402
# ── 干跑档 · 开关解析（P0-3 · 2026-09-29 补）───────────────────────────────
# 必须早于 RUN 解析：把 --apply 从 argv 里剔除，避免它被当成位置参数 run_id。
APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
# ──────────────────────────────────────────────────────────────────────────

# ── 干跑档 · 落盘闸门（P0-3b · 2026-09-29 前移到「第一个副作用之前」）──────
# 位次判据：闸门必须早于本脚本的**第一个副作用**（建目录 / 下载 / 写缓存 / 写库内文件）。
# 原 P0-3 位次在副作用之后 → 干跑并不零写；且紧跟闸门之后的写语句会因
# 「纯注释行不产生 DEDENT」被词法器吞进闸门体 —— 编译照样通过，--apply 时却永不执行
# （报告成功、实际丢写入）。故整体前移。
if not APPLY:
    print("[dry-run] %s 未落盘。" % _os.path.basename(_os.path.abspath(__file__)))
    print("[dry-run] 本脚本会写入：L3 蒸馏：覆盖写 kb/l3/candidates/{rules,sample_cases,scoped_clauses}.jsonl、kb/l3/rejected.jsonl、l3/manifest_l3.jsonl 与 l3/registry 台账")
    print("[dry-run] 加 --apply 才落盘（补档原因：原先运行即写盘，已发生过一次未授权写入）")
    _sys.exit(0)
# ──────────────────────────────────────────────────────────────────────────
RUN = sys.argv[1]
L0, L2, L3 = "kb/l0", "kb/l2", "kb/l3"
DV, KBV = "l3-0.2", "v0"
for d in ("candidates", "canonical", "index", "registry", "runs"):
    os.makedirs(f"{L3}/{d}", exist_ok=True)

U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
# ── 范围判据：**唯一一把尺子**（2026-10-08 从本文件内联块搬出，抬头见 kb/l8/l3_scope.py）──
#   搬家理由（实测缺陷，不是洁癖）：这条判据原先只写在**这里**，而
#   `kb/l8/l3_reject_ledger_rebuild.py`（拒绝台账重建）**不知道它** ⇒
#   台账把「被本判据剔掉的单元」写成「源表未给出命中判定或修订建议」，
#   而真实原因码 `out_of_scope_table` 在 kb/l3/rejected.jsonl 里出现 **0 次**
#   ⇒ 排查时照着假理由走，方向整个错掉（2026-10-08 真踩过）。
#   现在两个消费者都 import 本模块 ⇒ 结构上不可能分叉。判据本身**一字未改**。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from l3_scope import build_scope                                    # noqa: E402
_SCOPE = build_scope(f"{L0}/registry/kb.json")
L0_FR = _SCOPE.L0_FR
CONTENT_FIELDS = _SCOPE.CONTENT_FIELDS
METADATA_FIELDS = _SCOPE.METADATA_FIELDS
frole = _SCOPE.frole
exclusion_of = _SCOPE.exclusion_of

# ---------------- 过滤 + 逐单元对账 ----------------
FILTER = collections.Counter()
kept = []
for u in U:
    # ★ 判据在 kb/l8/l3_scope.py（与拒绝台账重建**共用同一把尺子**）—— 本处不再内联。
    code, _why = exclusion_of(u)
    if code:
        FILTER[(u.get("kb_type"), code)] += 1; u["_excl"] = code; continue
    kept.append(u)

print(f"L2 单元 {len(U)} → 可用 {len(kept)}")
for k, v in sorted(FILTER.items(), key=lambda x: -x[1]):
    print(f"   {k[0]:18s} {k[1]:24s} {v}")

# ---------------- 工具 ----------------
def j(us):
    return hashlib.sha1("|".join(sorted(u["unit_id"] for u in us)).encode()).hexdigest()
def ev_ref(u):
    return {"unit_id": u["unit_id"], "anchor": u["anchor"], "source_sha256": u.get("source_sha256")}
def rid_of(kb, us):
    return "r-" + hashlib.sha1(f"{kb}|{j(us)}".encode()).hexdigest()[:16]
def fv(units, name):
    for u in units:
        if u.get("heading_path") == name:
            return u
    return None

# ── 2026-10-09：按 kb/l3/registry/l3.json 的 p_level_refined.rule 落地 ──────────
# 该口径原文：「品线边界规则：取该记录风险等级（高危→P0 / 审慎→P1 / 合规→P2 / 待复核→P3）」
# 而边界型分支此前写死 p_level="P1" / risk_level="unknown" ⇒ 口径从未落地：
#   实测 9 条源侧「边界类型=严格限制红线、风险等级=高危」的规则全部落成 P1
#   （H01 医疗功效 / H02 催乳 / H03 未备案背书 / H04 背书 / H05 安全 / H06 FDA /
#     H07 疼痛功效 / H08 违法对比 / H09 仿生宣称），并导致全库 risk_level=unknown 1018/1018。
# 取不到风险等级时**保持旧行为（P1）**，不猜。
_PLEVEL_BY_RISK = (("高危", "P0"), ("审慎", "P1"), ("合规", "P2"), ("待复核", "P3"))


def plevel_of_risk(risk_unit):
    t = ((risk_unit or {}).get("text") or "")
    for k, v in _PLEVEL_BY_RISK:
        if k in t:
            return v
    return "P1"


# ── 2026-10-09：PRD §7.3 的 P0 一票否决，对**源侧风险等级偏低**的码做定点上移 ─────
# 为什么必须有这一层（否则裁定活不过一次重跑）：
#   本脚本的产物是**覆盖写** `kb/l3/manifest_l3.jsonl`（见本文件头部 dry-run 提示逐字：
#   「L3 蒸馏：覆盖写 … l3/manifest_l3.jsonl …」）⇒ 只把**数据里**某条的 p_level 改成 P0，
#   下一次 L3 重跑就把它打回原值，P0 模式会**静默消失**。那正是「治理字段被原地改写」这一类事故。
#   ⇒ 裁定要活下来，只能落在**判据**里，不能只落在数据里。
# 依据：PRD §7.3「一票否决项（P0 级，命中即 BLOCK）」**第 4 条「无依据的销量/排名宣称」**。
#   源侧该记录（品线内容边界规则库 recvuJP2jyATC9「边界内容=未标注来源的效果数据声明」／
#   广告文案明细 recvuJYdOb02Rt）写的是「边界类型=审慎关注、风险等级=审慎」⇒ 按上面的风险等级表
#   落 P1，**与 PRD 的 P0 直接冲突**。Owner 2026-10-09 裁定：「按照 prd 升 P0」⇒ PRD 优先。
# 范围：**只动 M03 一个码**（能取到码时才套用；取不到码不猜）。
#   ⚠ 按码上移会同时作用于 M03 的**两个** rule_id（expert 的样本行 + inferred 的规则表行）。
#     L5 侧不会因此重码：inferred 那条要进 `_sel_extra` 必须码在 `P0_CODE_ALLOWLIST` 里，
#     而 M03 **故意不在**那张表里 ⇒ 它按 `P0_but_authority_insufficient` 被排除；
#     万一将来有人把 M03 加进白名单，重码会在**落盘前**触发 `l5_export.py` 的唯一性断言（fail-closed）。
# 回退：删掉本集合里的 "M03"，并把 manifest_l3.jsonl 里该 rule_id 末行的 p_level 改回 P1。
_PLEVEL_PRD_P0_CODES = {"M03"}


def plevel_with_prd_override(code, base):
    return "P0" if (code or "") in _PLEVEL_PRD_P0_CODES else base


by_rec = collections.defaultdict(lambda: collections.defaultdict(list))
for u in kept:
    by_rec[(u["kb_type"], u["resource_id"])][u["unit_type"]].append(u)

# ── 批次16 · 0-1：`rule_code` 的**独立取码索引**（不许再依赖 `kept`）──────────────
# 病灶（批次15 定死到行，批次16 修）：
#   `:216` / `:247` 的取码是 `(fv(ents, "规则编号") or {}).get("text", "")`，而 `ents` 来自
#   **`kept`**（经 `l6_scope_lib.usable_units()` 过滤）。
#   该库的 `:110-113` 有一条「`entry` 且 `heading_path` 是元数据 → 剔除」的规则，
#   而「规则编号」正是**元数据字段** ⇒ 它的单元被当噪声剔掉 ⇒ `ents` 里没有它
#   ⇒ `fv()` 取不到 ⇒ `rule_code=''`。
#   ⇒ **取码通路依赖一个恰好被范围过滤器吃掉的单元** —— 这是通路设计错，不是数据缺。
# 实测受害面（批次15）：H06 / H01 / H03 / H08 四条记录型 P0 规则取不到码；
#   而 H02/H04/H05/H07/H09 走的是另一条路（`code_bucket` 聚合，`:127-178`）故幸免。
# 修法（用户批16 裁定，也是批次15 我给的方向）：**按 `resource_id` 从 L2 原始单元直取**
#   —— 真源不变（还是 L2 的「规则编号」单元），只是**绕开范围过滤**。
#   范围过滤是为「检索/蒸馏内容」设的；「规则编号」是**治理标识**，不该被它挡。
# 边界：**不改 `l6_scope_lib.py`**（它的口径对内容单元是对的），只在本脚本侧补一条独立通路。
CODE_UNITS = collections.defaultdict(list)      # resource_id -> [「规则编号」单元, …]
for _u in U:
    if _u.get("heading_path") == "规则编号":
        CODE_UNITS[_u.get("resource_id")].append(_u)


def code_of(rid):
    """按 `resource_id` 取「规则编号」的**文本**；取不到返回 ""（不编造）。"""
    us = CODE_UNITS.get(rid) or []
    for _u in us:
        t = (_u.get("text") or "").strip()
        if t:
            return t
    return ""

rules, rejected, CONS = [], [], collections.Counter()

# ============================================================ 形态①：词条型 —— 按「规则码」聚合
HITCODE = re.compile(r'\b([A-Z]{1,2}\d{2})\s*[:：]\s*([^/]+)')
code_bucket = collections.defaultdict(list)     # code -> [(record, hit_unit, code_text)]
for (kb, rid), grp in sorted(by_rec.items()):
    ents = grp.get("entry", [])
    if not ents:
        continue
    hit = fv(ents, "命中片段")
    fix = fv(ents, "修改建议")
    if not (hit or fix):
        continue
    if not (hit and fix):
        CONS["entry_sample_only"] += 1
        rejected.append({"kind": "entry_sample_only", "resource_id": rid, "kb_type": kb,
                         "reason": "只有命中片段或只有修改建议，无法构成「禁用→替换」对",
                         "unit_id": (hit or fix)["unit_id"], "anchor": (hit or fix)["anchor"]})
        continue
    codes = HITCODE.findall(hit["text"])
    if not codes:
        codes = [("UNCODED", hit["text"][:60])]
    for code, frag in codes:
        # 关键：修改建议必须与它所属的记录绑定，不能跨记录取第一条
        code_bucket[code].append((rid, hit, frag.strip(), fix, fv(ents, "命中原因"),
                                  fv(ents, "风险等级"), ents))

for code, items in sorted(code_bucket.items()):
    ev = []
    for rid, hit, frag, fix, why, risk, ents in items:
        for u in (hit, fix, why, risk):
            if u and u["unit_id"] not in {x["unit_id"] for x in ev}:
                ev.append(u)
    if not ev:
        continue
    # 同一记录内：片段 ↔ 该记录的修改建议（成对）
    pair_pairs = [(frag, fix["text"].strip()) for _, _, frag, fix, _, _, _ in items]
    seen_p, frags, fixes = set(), [], []
    for fr, fx in pair_pairs:
        if (fr, fx) in seen_p:
            continue
        seen_p.add((fr, fx)); frags.append(fr); fixes.append(fx)
    whys = [w["text"] for _, _, _, _, w, _, _ in items if w]
    risks = [r["text"] for _, _, _, _, _, r, _ in items if r]
    if len(fixes) == 1:
        repl_txt = fixes[0]
    else:
        repl_txt = "；".join(f"「{fr}」→ 删除/替换为：{fx}" for fr, fx in pair_pairs[:8])
        if len(pair_pairs) > 8:
            repl_txt += f"（另 {len(pair_pairs)-8} 组同码修订建议见证据单元）"
    text = f"规则码 {code}：命中「{'；'.join(sorted(set(frags))[:8])}」判定为违规；处理：{repl_txt[:300]}"
    if whys:
        text += f"；依据：{whys[0][:120]}"
    rules.append(dict(
        rule_id=rid_of("wording_entry", ev), kb_type="wording", kb_version=KBV, article_no="",
        form="entry", rule_code=code, resource_id=(rid if len(code_bucket[code]) == 1 else None),
        resource_ids=sorted({x[0] for x in items}),
        rule_text=text,
        forbidden_expression="；".join(sorted(set(frags))),
        suggested_replacement=repl_txt,
        expression_fix_pairs=[{"fragment": fr, "fix": fx, "record_id": rid}
                              for (fr, fx), (rid, *_ ) in zip(pair_pairs, items)],
        reason=(whys[0] if whys else ""),
        p_level=("P0" if any("高危" in r for r in risks) else ("P1" if risks else "P2")),
        risk_level=("；".join(sorted(set(risks))) if risks else "unknown"),
        scope={"rule_code": code, "records": len({r for r, *_ in items})},
        anchor=items[0][1]["anchor"], evidence_units=[ev_ref(u) for u in ev],
        evidence_digest=j(ev), support_count=len(ev), evidence_level="synthesis",
        effective_from="", effective_to="", owner="", status="provisional",
        verification=("待验证" if len(ev) == 1 else "已归纳"),
        supersedes=[], superseded_by=[], superseded_at="",
    ))

# 边界型（品线内容边界规则库）
for (kb, rid), grp in sorted(by_rec.items()):
    ents = grp.get("entry", [])
    if not ents or fv(ents, "命中片段"):
        continue
    bnd = fv(ents, "边界内容")
    if not bnd:
        continue
    kw, ex, reg, sug, rls = (fv(ents, "检测关键词"), fv(ents, "豁免词"), fv(ents, "正则表达式"),
                             fv(ents, "建议表达（合规话术）"), fv(ents, "规则依据与边界"))
    ev = [x for x in (bnd, kw, ex, reg, sug, rls) if x]
    text = f"边界：{bnd['text']}"
    if kw:
        text += f"；触发词：{kw['text']}"
    if ex:
        text += f"；豁免：{ex['text']}"
    if sug:
        text += f"；建议表达：{sug['text']}"
    rules.append(dict(
        rule_id=rid_of("wording_boundary", ev), kb_type="wording", kb_version=KBV, article_no="",
        form="entry", rule_code=code_of(rid), resource_id=rid,
        resource_ids=[rid],
        rule_text=text,
        forbidden_expression=(kw["text"] if kw else bnd["text"][:80]),
        suggested_replacement=(sug["text"] if sug else ""),
        reason=(rls["text"] if rls else ""),
        # ★ 2026-10-09：按 l3.json 的 p_level_refined 口径取源侧风险等级（原来写死 P1/unknown）；
        #   再叠一层 PRD §7.3 的定点上移（见 plevel_with_prd_override 的注释）。
        p_level=plevel_with_prd_override(code_of(rid), plevel_of_risk(fv(ents, "风险等级"))),
        risk_level=((fv(ents, "风险等级") or {}).get("text") or "unknown"),
        scope={"product_line": (fv(ents, "适用产品") or {}).get("text")},
        anchor=bnd["anchor"], evidence_units=[ev_ref(x) for x in ev], evidence_digest=j(ev),
        support_count=len(ev), evidence_level="synthesis",
        effective_from="", effective_to="", owner="", status="provisional",
        verification=("待验证" if len(ev) == 1 else "已归纳"),
        supersedes=[], superseded_by=[], superseded_at="",
    ))

# 建议表达型（W1 卖点表达边界）
for (kb, rid), grp in sorted(by_rec.items()):
    ents = grp.get("entry", [])
    if not ents or fv(ents, "命中片段") or fv(ents, "边界内容"):
        continue
    sug = fv(ents, "建议表达（合规话术）")
    if not sug:
        continue
    jr, av = fv(ents, "判定理由"), fv(ents, "避免条件/限定要求")
    ev = [x for x in (sug, jr, av) if x]
    text = f"建议表达：{sug['text']}"
    if av:
        text += f"；限定要求：{av['text']}"
    if jr:
        text += f"；判定理由：{jr['text']}"
    rules.append(dict(
        rule_id=rid_of("wording_saythis", ev), kb_type="wording", kb_version=KBV, article_no="",
        form="entry", rule_code=(fv(ents, "卖点ID") or {}).get("text", ""), resource_id=rid,
        resource_ids=[rid],
        rule_text=text, forbidden_expression="", suggested_replacement=sug["text"],
        reason=(jr["text"] if jr else ""), p_level="P1", risk_level="unknown",
        scope={"sellpoint": (fv(ents, "卖点ID") or {}).get("text")},
        anchor=sug["anchor"], evidence_units=[ev_ref(x) for x in ev], evidence_digest=j(ev),
        support_count=len(ev), evidence_level="synthesis",
        effective_from="", effective_to="", owner="", status="provisional",
        verification=("待验证" if len(ev) == 1 else "已归纳"),
        supersedes=[], superseded_by=[], superseded_at="",
    ))

# ============================================================ 形态②：案例型 —— 单对 + 按原因成簇
rp_units = []
for (kb, rid), grp in sorted(by_rec.items()):
    for u in grp.get("revision_pair", []):
        m = u.get("meta") or {}
        if not (m.get("before") and m.get("after")):
            CONS["revision_pair_incomplete"] += 1
            rejected.append({"kind": "revision_pair_incomplete", "resource_id": rid, "kb_type": kb,
                             "unit_id": u["unit_id"], "anchor": u["anchor"],
                             "reason": "修订对缺「前」或「后」，不构成可判定规则"})
            continue
        rp_units.append(u)

# 单对规则（一对 = 一条；support_count=1 → 待验证）
for u in rp_units:
    m = u["meta"]
    rules.append(dict(
        rule_id=rid_of("wording_revision_pair", [u]), kb_type="wording", kb_version=KBV,
        article_no="", form="revision_pair", rule_code="",
        rule_text=f"原表述：{m['before']}；修订为：{m['after']}" +
                  (f"；修订原因：{m['reason']}" if m.get("reason") else ""),
        forbidden_expression=m["before"], suggested_replacement=m["after"],
        reason=(m.get("reason") or ""), p_level="P1", risk_level="unknown",
        scope={"source_table": m.get("table")},
        anchor=u["anchor"], evidence_units=[ev_ref(u)], evidence_digest=j([u]),
        support_count=1, evidence_level="observation",
        effective_from="", effective_to="", owner="", status="provisional",
        verification="待验证", pair_ref=u.get("pair_ref") or "",
        supersedes=[], superseded_by=[], superseded_at="",
    ))

# 按「修订原因」成簇 → 归纳型规则（样本 ≠ 规则：由多条单元归纳）
# 归纳成簇：按修订原因里的「原因型」关键词归类（自由文本不重复，故按语义模式归类）
REASON_PAT = [
    ("笼统/不够具体", re.compile(r'笼统|不具体|不够完整|不够明确|未说明|缺少|不够详细|不清晰')),
    ("科学性错误", re.compile(r'科学性错误|错误|不准确|有误|不成立|无法完全|并不')),
    ("警告/力度不足", re.compile(r'警告力度不足|风险提示不足|力度不足|低估')),
    ("来源/依据缺失", re.compile(r'未注明|无来源|缺依据|缺乏依据|出处')),
    ("口径/标准不一致", re.compile(r'口径|标准不|不一致|定义')),
    ("表述/措辞问题", re.compile(r'表述|措辞|用语|读起来|语序')),
]
def reason_pattern(txt):
    for name, pat in REASON_PAT:
        if pat.search(txt or ""):
            return name
    return "(未归类原因)" if (txt or "").strip() else "(无修订原因)"
buckets = collections.defaultdict(list)
for u in rp_units:
    buckets[reason_pattern(u["meta"].get("reason"))].append(u)
for key, us in sorted(buckets.items()):
    if len(us) < 2:
        CONS["revision_pair_unpaired_single"] += 0
        continue
    # 保序配对：不得对「前」「后」分别排序（会错位）
    pairs = []
    seen = set()
    for u in us:
        b, a = u["meta"]["before"], u["meta"]["after"]
        if (b, a) in seen:
            continue
        seen.add((b, a)); pairs.append((b, a))
    ev = us
    rules.append(dict(
        rule_id=rid_of("wording_revision_cluster", ev), kb_type="wording", kb_version=KBV,
        article_no="", form="revision_pair", rule_code="",
        rule_text=(f"修订模式「{key}」（{len(us)} 条，{len(pairs)} 组改写）：出现下列表述时应按给出的改法修订 —— "
                   + "；".join(f"「{b[:40]}」→「{a[:40]}」" for b, a in pairs[:4])
                   + f"{' 等' if len(pairs) > 4 else ''}"),
        forbidden_expression="；".join(b for b, _ in pairs[:10]),
        suggested_replacement="；".join(f"「{b[:50]}」→「{a[:50]}」" for b, a in pairs[:6]),
        expression_fix_pairs=[{"before": b, "after": a} for b, a in pairs],
        reason=(us[0]["meta"].get("reason") or ""),
        p_level="P1", risk_level="unknown",
        scope={"source_table": us[0]["meta"].get("table"), "pattern_key": key,
               "reason_total": len(us)},
        anchor=us[0]["anchor"], evidence_units=[ev_ref(u) for u in ev], evidence_digest=j(ev),
        support_count=len(ev), evidence_level="synthesis",
        effective_from="", effective_to="", owner="", status="provisional",
        verification="已归纳",
        supersedes=[], superseded_by=[], superseded_at="",
    ))

# ============================================================ 外部标准库
ext_rec = collections.defaultdict(lambda: collections.defaultdict(list))
for u in kept:
    if u["kb_type"] == "external_standard":
        ext_rec[u["resource_id"]][u["unit_type"]].append(u)
for rid, grp in sorted(ext_rec.items()):
    cl = grp.get("clause", [])
    if not cl:
        CONS["no_clause_text"] += 1
        rejected.append({"kind": "no_clause_text", "resource_id": rid, "kb_type": "external_standard",
                         "reason": "未产出可用条款文本（正文为页面脚本或编码载荷），"
                                   "无法产出「判定条件 + 阈值/词表」形态的可判定规则"})
        continue
    for u in cl:
        CONS["clause_not_actionable"] += 1
        rejected.append({"kind": "clause_not_actionable", "resource_id": rid,
                         "kb_type": "external_standard", "unit_id": u["unit_id"],
                         "anchor": u["anchor"],
                         "reason": "条款文本不可判定：非自然语言条款（页面脚本 / base64 编码载荷），"
                                   "无法给出判定条件与阈值"})

# ============================================================ 取数对账（按 unit 逐一归属）
used = set()
for r in rules:
    for e in r["evidence_units"]:
        used.add(e["unit_id"])
# ── 拒绝口径 **C**（Owner 2026-10-08 裁定：「快照口径取 C」）────────────────────
#   C = **进了门** ∧ 没被规则用 ∧ **没被样例用** = 「蒸馏跑了，但这单元没成规则」
#   改前算的是 A（= kept − 规则用），**少了「没被样例用」这一条** ⇒
#   把 **361 条「已被样例使用」的单元**也记成了「拒绝」—— 它们其实已经被用上了。
#   ★ 样例集 kb/l3/candidates/sample_cases.jsonl 是**冻结件**（2026-10-01 10:07 起无活写入者，
#     写过它的只有 .work/batch7_*/batch8_* 这些历史一次性脚本；本引擎自己不读也不写它）
#     ⇒ 这 361 条是**稳定集合**，口径可复算、不漂。但**别把它读成「样例还在演进」**。
#   口径分解与三套数（A 2581 / B 8103 / C 2220）见 kb/l8/l3_scope.py 抬头。
_CASES = f"{L3}/candidates/sample_cases.jsonl"
case_cited, case_src = set(), "missing"
if os.path.exists(_CASES):
    with open(_CASES, encoding="utf-8") as _fh:
        for _l in _fh:
            _l = _l.strip()
            if not _l:
                continue
            _d = json.loads(_l)
            for _x in (_d.get("unit_ids") or []):
                case_cited.add(_x if isinstance(_x, str) else _x.get("unit_id"))
            if _d.get("unit_id"):
                case_cited.add(_d["unit_id"])
    case_src = "read"
else:
    # **缺证据要看得见**：读不到样例集 ⇒ 拒绝集会退回 A（多算那 361 条），必须报出来，不许静默
    print(f"⚠️ 读不到 {_CASES} ⇒ 拒绝口径**退回 A**（会把「已被样例使用」的单元也算成拒绝）")
rejected_units = {r["unit_id"] for r in rejected if r.get("unit_id")}
kept_ids = {u["unit_id"] for u in kept}
# 未进入规则的可用单元（**剔除已被样例使用的**）：逐条留痕（硬约束 4「任何跳过都要留痕」）
unaccounted = kept_ids - used - case_cited - rejected_units
un_by_reason = collections.Counter()
for uid in sorted(unaccounted):
    u = next(x for x in kept if x["unit_id"] == uid)
    hp = u.get("heading_path") or u["unit_type"]
    if u["unit_type"] == "entry" and hp in ("Primary Text", "Headline", "广告名称"):
        reason = "sample_only_no_verdict"
        detail = "纯文案样本：源表未给出命中判定或修订建议，无法产出可判定规则"
    elif u["unit_type"] == "entry" and hp in ("命中原因", "命中规则"):
        reason = "absorbed_as_reason"
        detail = "已作为对应规则的理由引用（同一记录内），此处不重复成规则"
    elif u["unit_type"] == "entry" and hp in ("中文释义", "风险表达模式", "小语种参考 FR/DE/ES/IT",
                                            "字符数自检", "卖点依据（产品功能）", "备注（如处理结果/建议）"):
        reason = "supporting_field_only"
        detail = "辅助字段：单独不构成可判定规则，已在成对规则中作为依据引用"
    elif u["unit_type"] == "revision_pair":
        reason = "cluster_member_counted_once"
        detail = "已计入其所属归纳簇的 evidence_units"
    else:
        reason = "no_rule_derivable"
        detail = "不构成可判定的「命中→替换」或「修订前→后」对"
    un_by_reason[reason] += 1
    rejected.append({"kind": reason, "unit_id": uid, "anchor": u["anchor"],
                     "kb_type": u["kb_type"], "resource_id": u["resource_id"],
                     "unit_type": u["unit_type"], "field": hp, "reason": detail})
rejected_units = {r["unit_id"] for r in rejected if r.get("unit_id")}
# ★ 2026-10-08：这里也必须减 `case_cited` —— 否则「已被样例使用」的那批会被算成 unaccounted
#   （即「既没进规则、也没被拒绝」，看起来像漏账），而它们其实**已被使用**（口径 C）。
unaccounted = kept_ids - used - case_cited - rejected_units
ACCT = {
    "l2_total": len(U),
    "filtered_out": len(U) - len(kept),
    "kept": len(kept),
    "used_in_rules": len(used & kept_ids),
    "used_in_cases": len(case_cited & kept_ids),
    "explicitly_rejected": len(rejected_units & kept_ids),
    "unaccounted": len(unaccounted),
    # ★ 口径自述（2026-10-08）：读的人必须知道这个 `explicitly_rejected` 是按哪套口径算的。
    #   `case_cited_source=missing` ⇒ 它是 A（多算），不是 C。
    "reject_caliber": ("C" if case_src == "read" else "A(case_source_missing)"),
    "case_cited_source": case_src,
}
print("\n取数对账:", ACCT)

# ============================================================ 幂等 + 落盘
MAN = f"{L3}/manifest_l3.jsonl"
prev = {}
if os.path.exists(MAN):
    for l in open(MAN, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            # manifest_l3.jsonl 是混合日志：规则行有 rule_id，later 批次追加的 sample_case 行只有 id
            # → 幂等比较只吃规则行，其它行跳过（语义不变，只是不再崩）
            if r.get("rule_id"):
                prev[r["rule_id"]] = r
new = unchanged = 0
for r in rules:
    o = prev.get(r["rule_id"])
    if o and o.get("evidence_digest") == r["evidence_digest"]:
        unchanged += 1
    else:
        new += 1

# ============================================================ P2 改造（2026-10-02）
# 原实现的问题（用户裁定要改 + 出过事故）：
#   `rules.jsonl` / `rejected.jsonl` / `index/l3.jsonl` 一律 `open(...,"w")` **无条件覆盖**。
#   ① 幂等检查（上面的 `new/unchanged`）**算完没用上** —— 内容一字未变也照样整文件重写；
#   ② 覆盖前不归档，于是 `rejected.jsonl` 从 11,860 行掉到 1,053 行那次事故里，
#      历史只能靠人记得先去 `kb/l3/_archive/` 捞。
#
# 本段加两道闸（**不改下游读法、不改数据模型** —— 所以对 20 个消费者零影响）：
#   闸① **内容对等则不写**：把整份内容在内存里拼好，与磁盘逐字节比；一致就跳过。
#        —— 这就是幂等：没变的东西不再重写（连带 mtime 也不动，"陈旧"误判也少一半）。
#   闸② **写前强制归档**：内容确实变了 → 先把旧文件逐字节复制到 `_archive/` 并校验 sha，
#        校验不过就 **拒绝写入**（宁可不更新，也不留一份没退路的覆盖）。
#
# 为什么不改成「去重追加」：`rules.jsonl` 有 20 个消费者（含评审链的 kb-content-review、
#   L4 发号、L5 P0、L6 索引、5 道闸门）。改成追加会让同一 rule_id 出现多行，
#   每个消费者都得改成 `read_last_per_key` 读法 —— 那是跨 20 个文件的连带改造，
#   在"能跑通"阶段引入的风险远大于收益。归档闸拿到同样的"不丢历史"，且不动读法。
import hashlib as _hl
import time as _tm
import shutil as _sh

_ARCHIVE_DIR = f"{L3}/_archive/{RUN}-prewrite"
#: 闸③ 行数护栏阈值：新内容行数比旧文件少超过这个比例 ⇒ 拒写（可用 KB_L3_ALLOW_DROP=1 越过）
DROP_MAX = 0.20
_write_guard = {"checked": 0, "unchanged": 0, "changed": 0, "archived": 0, "refused": []}


def _serialize(rows):
    """按既有口径逐行序列化（与改造前逐字一致，保证内容可比）。"""
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def _write_guarded(rel, text, guard=_write_guard):
    """三道闸：①内容对等则不写 ②写前强制归档+sha校验 ③行数护栏（骤减即拒写）。

    返回 "unchanged" / "written" / "refused:<原因>"。

    ★ 第③道（2026-10-02 实测加的，不是预防性设计）：
      本脚本跑一次，`rejected.jsonl` 从 **10,661 行掉到 2,611 行**（少 8,050 行）——
      与 2026-09-29 那次事故（11,860 → 1,053）是**同一个模式**。
      根因在引擎的筛选逻辑（对账口径），不在写入方式；但"骤减"必须**先拦住**：
      写入内容行数比旧文件少超过 DROP_MAX（默认 20%）时**拒绝写入**并报出来，
      要真的接受骤减，须显式设环境变量 `KB_L3_ALLOW_DROP=1`（人开闸）。
      这样"数据消失"从静默变成必须有人点头的事件。
    """
    guard["checked"] += 1
    path = rel
    new_b = text.encode("utf-8")
    if os.path.exists(path):
        try:
            old_b = open(path, "rb").read()
        except Exception as e:                                  # noqa: BLE001
            return "refused:读旧文件失败 %s" % e
        if old_b == new_b:
            guard["unchanged"] += 1
            return "unchanged"
        # ── 闸③ 行数护栏（先于归档：不值得为一份会退化的内容留归档）──
        old_lines = old_b.count(b"\n")
        new_lines = new_b.count(b"\n")
        allow_drop = os.environ.get("KB_L3_ALLOW_DROP") == "1"
        if (not allow_drop and old_lines >= 20
                and new_lines < old_lines * (1 - DROP_MAX)):
            why = ("行数骤减 %d → %d（降 %.0f%%，护栏阈值 %.0f%%）"
                   % (old_lines, new_lines,
                      (1 - new_lines / old_lines) * 100, DROP_MAX * 100))
            guard["refused"].append(rel)
            guard["dropped"] = guard.get("dropped", [])
            guard["dropped"].append({"file": rel, "old": old_lines, "new": new_lines})
            print("  ⛔ 拒写（闸③ 行数护栏）：%s —— %s" % (rel, why))
            print("     → 确认这是有意的就设 KB_L3_ALLOW_DROP=1 重跑；"
                  "否则先查引擎的筛选口径")
            return "refused:" + why
        # ── 闸② 归档 ──
        try:
            os.makedirs(_ARCHIVE_DIR, exist_ok=True)
            dst = os.path.join(_ARCHIVE_DIR, os.path.basename(path))
            _sh.copyfile(path, dst)                              # 逐字节复制
            a, b = open(path, "rb").read(), open(dst, "rb").read()
            ha, hb = _hl.sha256(a).hexdigest(), _hl.sha256(b).hexdigest()
            if a != b or ha != hb:
                guard["refused"].append(rel)
                return "refused:归档校验不过（%d/%d 字节）" % (len(a), len(b))
            guard["archived"] += 1
        except Exception as e:                                  # noqa: BLE001
            guard["refused"].append(rel)
            return "refused:归档失败 %s" % e
    # ★ 2026-10-08：落地这一步改成**原子写**（同目录临时件 + `os.replace`）。
    #   改前是 `open(path,"w")` **直接截断** ⇒ 截断与写满之间那段窗口里，
    #   读者（评审链）会读到 **0 字节或半份**。三道闸与回读复核**一条没动**，
    #   只把「把字节放到目标路径上」这个动作换成原子的。
    _sw.write_atomic(path, text)
    guard["changed"] += 1
    return "written"


# ── 逐份过闸写档（取代原来的 6 处无条件 open(...,"w")）────────────────────
_write_guarded(f"{L3}/candidates/rules.jsonl", _serialize(rules))
_write_guarded(f"{L3}/rejected.jsonl", _serialize(rejected))
# canonical/rules.jsonl 是**迁移留痕**：原代码 `open(...,"w").close()` 把它清成 0 字节。
# 过闸后语义不变（0 字节也是"内容"），只是多了一条"本来就没变就别碰"的保护。
_write_guarded(f"{L3}/canonical/rules.jsonl", "")
_write_guarded(f"{L3}/index/l3.jsonl", _serialize(
    [{"rule_id": r["rule_id"], "kb_type": r["kb_type"],
      "p_level": r["p_level"], "support_count": r["support_count"],
      "anchor": r["anchor"]} for r in rules]))
# ── 批次11 · C-2 写入点④：改走**去重追加** ─────────────────────────────────
# 这一处最讽刺：上面 `:404-425` 已经算出了 `unchanged`（`evidence_digest` 与上一行相同的
# 条数），**算完照样无条件追加**。实测 manifest_l3 每遍 +1527 行，而 509/633 个键的组里
# 只有 `observed_at` 在变。现在把「算出来的 unchanged」真的用上。
_dd_l3 = _ledger_mod.dedup_append(
    MAN,
    [{"rule_id": r["rule_id"], "evidence_digest": r["evidence_digest"],
      "support_count": r["support_count"], "form": r["form"],
      "status": "provisional", "distiller_version": DV,
      "observed_at": RUN} for r in rules],
    "rule_id", label="@l3_distill_run.py/manifest_l3",
    last_seen_path="kb/l3/registry/last_seen.json", run=RUN)

reg = json.load(open(f"{L3}/registry/l3.json", encoding="utf-8")) if os.path.exists(f"{L3}/registry/l3.json") else {}
reg.update({
    "distiller_version": DV, "kb_version": KBV,
    "skill_source": {
        "name": "knowledge-distillation", "origin": "https://github.com/volcengine/OpenViking",
        "installed_at": "~/.dsh/skills/knowledge-distillation/SKILL.md", "read": True,
        "adopted": ["源事实→归一化证据→模式→发现→含义，全程可追溯（evidence_level 落地）",
                    "产出不得是目录或来源摘要堆叠 —— 每条规则是一句可判定的结论",
                    "证据分级 Observation/Synthesis/Inference/Hypothesis，不把推断写成观测事实",
                    "先勘查来源、记录来源谱系、不把同一上游的重复说法当独立佐证",
                    "摘录逐字，不转述不概括（用 unit_id 指向 L2 原文单元保证）"],
        "skipped_ov_steps": "该 skill 依赖 OpenViking CLI（ov add-resource / ov add-skill / ov compile）；"
                            "本机未安装，按任务要求不安装、不调用；相关步骤一律跳过，不计为未完成项",
        "effective": "skill 方法论 + 本文件规格；冲突时以本文件规格为准",
    },
    "classification_note": {
        "table": "专家修订汇总表", "l0_kb_type": "internal_sample", "used_as": "wording",
        "why": "形态是「修订前→后」成对语料，属措辞类素材；按措辞素材蒸馏，但不改 L0 分类"
               "（规则的 kb_type 仍记 wording 以体现用途，L0 的 kb_type 未变）",
        "status": "待确认",
    },
    "filter_rules": {
        "step1_metadata": {
            "how": "按 kb/l0/registry/kb.json 的 field_roles 过滤，只保留「文案/表述类字段」产生的单元",
            "gap": "L0 的 field_roles 只覆盖 44 个字段，L2 实际出现 70+ 个；故补全了一份覆盖 L2 全部字段的"
                   "角色表（CONTENT/METADATA），依据是字段是否承载「可引用的表述/理由/条件」",
            "content_fields": len(CONTENT_FIELDS), "metadata_fields": len(METADATA_FIELDS)},
        "step2_quality": {"how": "排除 meta.content_quality_flag 非空的单元"},
    },
    "rule_forms": {
        "wording_entry": "入口：命中片段按「规则码」拆分后聚合 → 禁用表达 + 建议替换 + 依据",
        "wording_boundary": "品线内容边界规则库 → 边界内容 + 触发词 + 豁免 + 建议表达",
        "wording_saythis": "W1 卖点表达边界 → 建议表达 + 限定要求 + 判定理由",
        "wording_revision_pair": "一对修订 = 一条规则（原表述 + 修订后 + 修订原因），support_count=1 → 待验证",
        "wording_revision_cluster": "按「修订原因」成簇归纳 → support_count≥2 的归纳型规则",
        "external_standard": "{判定条件, 阈值/词表, 条款锚点, 生效期} —— 本批无可用条款正文，见报告",
    },
    "accounting": ACCT,
    "canonical_policy": "canonical/rules.jsonl 本步只创建空文件；候选→定稿是独立动作（走抽查），"
                        "晋升产生新的定稿记录，不是改名。",
    "supersedes_policy": "rule_id 由 (form + 依据 unit_id 集合 hash) 生成，源不变则 rule_id 不变；"
                         "变更时新规则在 supersedes 列旧 id，旧规则追加 superseded_by/superseded_at；"
                         "检索默认只用未被 superseded_by 的规则。",
    "idempotency": {"key": "rule_id", "unchanged_cond": "evidence_digest 未变 → unchanged"},
    "citation_discipline": "依据 = unit_id + anchor + source_sha256；不引用裸 URL；摘录逐字。",
})
_write_guarded(f"{L3}/registry/l3.json",
               json.dumps(reg, ensure_ascii=False, indent=2) + "\n")

_write_guarded("kb/.work/l3_core.json", json.dumps(
    {"kept": len(kept), "filtered": {f"{k[0]}|{k[1]}": v for k, v in FILTER.items()},
     "rules": len(rules), "new": new, "unchanged": unchanged, "rejected": len(rejected),
     "forms": dict(collections.Counter(r["form"] for r in rules)),
     "support": dict(collections.Counter(r["support_count"] for r in rules)),
     "rejected_kinds": dict(collections.Counter(r["kind"] for r in rejected)),
     "accounting": ACCT, "cons": dict(CONS),
     "unaccounted_ids": sorted(unaccounted)[:20], "un_by_reason": dict(un_by_reason)},
    ensure_ascii=False, indent=1))
print(f"规则 {len(rules)}（新 {new} / unchanged {unchanged}）| 拒绝 {len(rejected)}")
print("  形态:", dict(collections.Counter(r["form"] for r in rules)))
print("  support_count:", dict(collections.Counter(r["support_count"] for r in rules)))
print("  拒绝:", dict(collections.Counter(r["kind"] for r in rejected)))
