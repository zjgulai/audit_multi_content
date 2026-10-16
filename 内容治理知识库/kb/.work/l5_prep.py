#!/usr/bin/env python3
"""前置 A：给候选规则追加 rule_kind / authority，并据源侧风险信号精确化 risk_level / p_level。
kb/l0~l2 只读；kb/l3 只追加（旧行原样保留）。
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

import json, os, re, hashlib, collections, sys, shutil

# ── 批次11 · C-2：台账去重实现只有一份（kb/kb_ledger.py），这里只取用 ──────────
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import kb_ledger as _ledger_mod
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
    print(
        "[dry-run] 本脚本会写入：L5 前置：**去重追加** kb/l3/manifest_l3.jsonl（富化字段唯一真源）。\n"
        "[dry-run] ★ 2026-10-10 起**不再写** kb/l3/candidates/rules.jsonl —— 它是上游每天重建的派生件，"
        "追加进去的富化行下一次日更必然消失；且消失前的这一轮会让读者读到过期富化（判定静默漂移，"
        "实测 P0 会从 21 掉到 18）。读者统一走 kb/kb_ledger.py::rules_enriched_view。")

    print("[dry-run] 加 --apply 才落盘（补档原因：原先运行即写盘，已发生过一次未授权写入）")
    _sys.exit(0)
# ──────────────────────────────────────────────────────────────────────────
RUN = sys.argv[1]
L0, L2, L3 = "kb/l0", "kb/l2", "kb/l3"
DISTILLER_VERSION = "l3-0.2"

# ---------- 旧行前缀哈希（自检证据）
before_lines = [l.rstrip("\n") for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8") if l.strip()]
before_sha = hashlib.sha256(("\n".join(before_lines) + "\n").encode()).hexdigest()
print(f"基线：候选规则 {len(before_lines)} 行 sha256={before_sha[:16]}")

R = [json.loads(l) for l in before_lines]
U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]

# ---------- 源侧风险信号（按记录）——这些是 L2 里已存在的源事实，只是被元数据过滤挡在规则外
by_rec = collections.defaultdict(dict)
for u in U:
    if u["unit_type"] == "entry":
        by_rec[u["resource_id"]][u.get("heading_path")] = u

def rec_risk(rid):
    for key in ("风险等级", "灯色状态"):
        v = by_rec.get(rid, {}).get(key)
        if v:
            return v["text"]
    return None

def risk_tier(t):
    if not t:
        return None
    if "高危" in t or "红" in t:
        return "P0"
    if "审慎" in t or "黄" in t:
        return "P1"
    if "合规" in t or "绿" in t:
        return "P2"
    if "待复核" in t or "灰" in t:
        return "P3"
    return None

# ---------- 规则来源表推断（决定 authority）
def source_table_of(r):
    st = (r.get("scope") or {}).get("source_table")
    if st:
        return st
    code = (r.get("rule_code") or "")
    if code and re.match(r'^[A-Z]{1,2}\d{2}$', code):
        return "广告文案明细"
    if r["rule_text"].startswith("建议表达："):
        return "W1卖点表达边界（品线反馈0910）"
    if "边界：" in r["rule_text"]:
        return "品线内容边界规则库"
    return None

AUTHORITY_BY_TABLE = {
    "专家修订汇总表": "expert",              # 来源是专家逐条修订
    "广告文案明细": "expert",                # 来源是人工合规审计（检查人 + 风险等级判定）
    "品线内容边界规则库": "inferred",         # 内部品线规则，无外部权威背书
    "W1卖点表达边界（品线反馈0910）": "inferred",
}

# ★★ 2026-10-10 修（**潜伏的翻倍**，被"永远的 no-op"掩盖至今）：
#   原实现 `for r in R` 对**读到的全部原始行**逐行富化。而 `rules.jsonl` 里同一 rule_id 本来就有
#   两行（基线生行 + 上一次追加的生行，实测 1018 行 / 509 个 id）⇒ `out` = **1018 行**，
#   一次追加就把文件从 1018 顶到 2036，而 `l3_distill_run.py` 的口径写死了这是
#   「509 行生行、单行/rule_id」的文件 ⇒ 直接违反那条不变量。
#   这个缺陷此前**看不出来**：两道幂等守卫让 `out` 永远被清成 0，追加语句一次都没真正执行过
#   （10-10 实测：改前那次跑 `本次追加 1018 → 0 行`、文件纹丝不动）。
#   修法：富化前先把 R 归一到**每个 rule_id 的最后一行**（后写者胜，与所有读者的取数口径一致）。
_R_latest = {}
for _r in R:
    _R_latest[_r["rule_id"]] = _r
_R_norm = list(_R_latest.values())
if len(_R_norm) != len(R):
    print(f"[归一] 读入 {len(R)} 行 → 按 rule_id 取最新后 {len(_R_norm)} 条"
          f"（同一 rule_id 有多行：上游重建后遗留的旧行）")

out = []
stat = collections.Counter()
for r in _R_norm:
    r2 = dict(r)
    # ---- rule_kind
    # 判据：源侧若已有「规则码」作为该规则的主键（一个码 = 一条规则），则是原子映射；
    # 只有把多条证据归纳成一个模式的（修订成簇）才是 inductive。
    has_code = bool(re.match(r'^[A-Z]{1,2}\d{2}$', r.get("rule_code") or "")) or "边界：" in r["rule_text"]
    if has_code:
        r2["rule_kind"] = "atomic"
    elif r["form"] == "revision_pair" and r["support_count"] == 1:
        r2["rule_kind"] = "atomic"          # 一对修订本身就是一条规则
    else:
        r2["rule_kind"] = "inductive"       # 多条证据归纳出的模式
    # ---- authority
    if "边界：" in r["rule_text"] and not re.match(r'^[A-Z]{1,2}\d{2}$', r.get("rule_code") or ""):
        rc = by_rec.get(r.get("resource_id"), {}).get("规则编号")
        if rc:
            r2["rule_code"] = rc["text"]
    tbl = source_table_of(r)
    r2["authority"] = AUTHORITY_BY_TABLE.get(tbl, "inferred")
    r2["authority_source_table"] = tbl
    # ---- 风险信号回填 + 精确化 p_level
    codes = [r["rule_code"]] if re.match(r'^[A-Z]{1,2}\d{2}$', r.get("rule_code") or "") else []
    if r["form"] == "entry" and codes:
        # 入口规则：聚合了多个记录，取这些记录的风险等级分布
        risks = collections.Counter()
        code_set = set(codes)
        if not code_set:
            code_set = set(re.findall(r'\b([A-Z]{1,2}\d{2})\b', r.get("forbidden_expression") or ""))
        for rid, d in by_rec.items():
            h = d.get("命中片段")
            if not h:
                continue
            if set(re.findall(r'\b([A-Z]{1,2}\d{2})\b', h["text"])) & code_set:
                t = rec_risk(rid)
                if t:
                    risks[t] += 1
        tiers = {risk_tier(t) for t in risks}
        all_high = tiers == {"P0"}
        r2["risk_level"] = "；".join(sorted(risks)) if risks else "unknown"
        r2["risk_evidence_records"] = sum(risks.values())
        r2["p_level"] = "P0" if all_high else ("P1" if "P1" in tiers or "P0" in tiers else "P2")
        r2["p_level_basis"] = ("全部支撑记录的风险等级均为高危·红 → P0"
                               if all_high else
                               f"支撑记录风险等级混合（{'；'.join(sorted(risks))}）→ 不升 P0")
    elif "边界：" in r["rule_text"]:
        # 品线边界：单记录规则，直接取该记录的风险等级
        rid = r.get("resource_id")
        t = rec_risk(rid); tier = risk_tier(t)
        r2["risk_level"] = t or "unknown"
        r2["p_level"] = tier or "P1"
        r2["p_level_basis"] = f"来源记录风险等级={t}"
    elif r["rule_text"].startswith("建议表达："):
        rid = r.get("resource_id")
        t = rec_risk(rid); tier = risk_tier(t)
        r2["risk_level"] = t or "unknown"
        r2["p_level"] = tier or "P1"
        r2["p_level_basis"] = f"来源记录灯色状态={t}"
    else:
        # revision_pair：源表无风险等级字段，保持 P1
        r2["risk_level"] = "unknown"
        r2["p_level"] = "P1"
        r2["p_level_basis"] = "专家修订表无风险等级字段，按 P1 处理"
    r2["distiller_version"] = DISTILLER_VERSION
    out.append(r2)
    stat[(r2["rule_kind"], r2["authority"], r2["p_level"])] += 1

# ---------- 幂等守卫（批次6 加）：**不改数据模型**，只防「同日重跑 2× 变 4×」----------
# 病灶（批次6 实测）：本脚本的追加是**无条件**的，重复跑一次就把文件再复制一遍
#   （1018 → 2036）。R 是本次读到的**全部**旧行，故只要某个 rule_id 已经有
#   `distiller_version == l3-0.2` 的行，就说明本层的前置 A 已经跑过 —— 不再重复追加。
# ★ 本守卫**不**改「整块追加逐行富化副本」这个数据模型（那是另一个议题，另立一批）；
#   它只在「同一批 rule_id 已被富化过」时把 out 过滤为空，因此首次跑的行为一字不变。
_already_enriched = {r["rule_id"] for r in _R_norm if r.get("distiller_version") == DISTILLER_VERSION}

# ── 批次13 · A-1（2026-10-02）：**上游覆盖会把这个守卫清零**，故补第二道基于历史的守卫 ──
# 病灶（批次12 判据 3 红，批次13 复现）：
#   上面这道守卫的判据是「`rules.jsonl` 里有没有我这个版本号的富化行」。
#   但 `kb/l8/l3_distill_run.py:426` **每遍把 `rules.jsonl` 整个覆盖**成只有生行的版本
#   （`:192` 本脚本是 append，两边打开方式不同）⇒ **第二遍起，守卫读到的富化行数恒为 0**。
#   实测：`rules.jsonl` 现 2036 行，按 `distiller_version` = {None: 1018, 'l3-0.2': 1018}
#   ——生行/富化行各积了 1018（= 509 × 2 遍），正是这个循环的产物。
#   ⇒ **根因不是守卫写错了，是它把「一个每遍被上游覆盖的文件」当成了幂等状态存储。**
# 修法（A-1 方向①「幂等状态改存到不被覆盖的独立位置」的具体落地）：
#   幂等状态改从**本层自己的历史落点** `manifest_l3.jsonl` 读 —— 那是 append-only，没人覆盖它。
#   判据 = 同一 `rule_id` 的**富化行**（同形态）里，已有 `evidence_digest` 与本轮相同的行。
#   与 C-2 的 `evidence_digest` 比较同源（`kb_ledger` 的形态分桶也用同一套键）。
# 边界：**不改数据模型、不改 `rules.jsonl` 的写入方式、不动 `:192` 的 append**；
#   只把「要不要富化」这个判断换成读历史。首次跑行为一字不变（历史里没有 → 照常富化）。
_hist_enriched = {}
try:
    import kb_ledger as _kl
    for _k, _row in _kl.read_last_per_key(f"{L3}/manifest_l3.jsonl", "rule_id").items():
        # 只认**富化形态**的最后一行（与 _shape_of 同一套 ENRICH_KEYS）
        if all(kk in _row for kk in _kl.ENRICH_KEYS):
            _hist_enriched[_row["rule_id"]] = _row.get("evidence_digest")
except Exception as _e:
    print(f"[幂等守卫·历史] 读 manifest_l3 失败，退回只靠 rules.jsonl 守卫：{_e}")

_hist_dup = {r["rule_id"] for r in out
             if _hist_enriched.get(r["rule_id"]) == r.get("evidence_digest")}
if _hist_dup:
    _before_n = len(out)
    out = [r for r in out if r["rule_id"] not in _hist_dup]
    print(f"[幂等守卫·历史] manifest_l3 里已有 {len(_hist_dup)} 个 rule_id 的富化行且 "
          f"evidence_digest 相同（**不受 rules.jsonl 被覆盖影响**）→ "
          f"本次追加 {_before_n} → {len(out)} 行")

if _already_enriched:
    _before_n = len(out)
    out = [r for r in out if r["rule_id"] not in _already_enriched]
    print(f"[幂等守卫] 已有 {len(_already_enriched)} 个 rule_id 带 {DISTILLER_VERSION} 行 → "
          f"本次追加 {_before_n} → {len(out)} 行（重跑不重复富化）")

# ---------- ★ 2026-10-10（方案 A）：**不再往 `rules.jsonl` 追加富化行** ----------
# 为什么改（当天全库普查的结论，不是洁癖）：
#   `kb/l3/candidates/rules.jsonl` 是**上游每天重建的派生件** ——
#   `kb/l8/l3_distill_run.py:162` 起 `rules = []` + 按硬编码字段 `rules.append(dict(...))`
#   重新生成（`_serialize` 也不剥键）⇒ **往它追加的富化行，下一次日更必然消失**（实测成立）。
#   更要命的是"消失前那一轮"：追加进去的富化行**认不出来**（`distiller_version` 也没了）
#   ⇒ 守卫判成"已富化"⇒ 不重写 ⇒ 文件里的富化**永远定格在上一次快照**。沙盒实测后果：
#   `l5_export` 直接采用文件里那份旧富化 ⇒ **P0 从 21 掉到 18、白名单准入从 4 掉到 0**
#   —— 一条**静默的判定漂移**，比崩溃更坏（崩溃有人来修，漂移没人回头）。
#   ⇒ 富化字段的唯一真源就是 `manifest_l3.jsonl`（append-only、没人覆盖它，实测对当前
#     509 条候选的 evidence_digest **509/509 一致**）；读者统一走
#     `kb/kb_ledger.py::rules_enriched_view`（唯一实现，含 digest 校验）。
# 保留"归一"与两道守卫：归一是防哪天有人再让 `out` 翻倍，守卫是防重复富化。
# 逃生口：确实要恢复旧行为（往派生件追加）时设 `KB_L3_APPEND_ENRICH=1`；
#   但那样会立刻恢复上面那条判定漂移 —— **只在排查时用，不许常态化**。
if os.environ.get("KB_L3_APPEND_ENRICH") == "1":
    with open(f"{L3}/candidates/rules.jsonl", "a", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"[⚠ 逃生口] KB_L3_APPEND_ENRICH=1：仍按旧行为追加 {len(out)} 行到派生件 "
          f"（这会恢复「文件富化定格」的漂移，仅限排查）")
else:
    print(f"[富化去向] 本轮富化 {len(out)} 条**只落 `manifest_l3`**（唯一真源）；"
          f"`rules.jsonl` 保持派生件形态（生行，由上游重建）——不追加。"
          f"读者走 `kb_ledger.rules_enriched_view`。")

# 取每个 rule_id 的最新一行（旧行保留，取数取新行）
latest = {}
_FULL_HIST = {}
try:
    import kb_ledger as _kl2
    for _kk, _rr in _kl2.read_last_per_key(f"{L3}/manifest_l3.jsonl", "rule_id").items():
        if all(x in _rr for x in _kl2.ENRICH_KEYS):
            _FULL_HIST[_rr["rule_id"]] = _rr
except Exception:
    _FULL_HIST = {}
for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); latest[r["rule_id"]] = r
# ── 批次14 兜底：幂等守卫跳过追加时，`rules.jsonl` 里该 rule_id 的最后一行是**生行**
#    （缺 rule_kind/authority/p_level），而下游 registry 汇总要读这三个字段
#    ⇒ KeyError（批次14 第三遍实测踩到）。修法：**富化字段从历史兜底**，
#    不因「本次没追加」而让下游读到生行。只补缺失的键，不覆盖已有值。
for _rid, _row in list(latest.items()):
    _h = _FULL_HIST.get(_rid)
    if _h and not all(x in _row for x in _kl2.ENRICH_KEYS):
        _merged = dict(_row)
        for _x in _kl2.ENRICH_KEYS:
            if _x in _h: _merged[_x] = _h[_x]
        latest[_rid] = _merged

# ---------- 台账追加（批次11 · C-2 写入点③：改走**去重追加**）
# 原为无条件 `"a"` 追加：每跑一遍就把同一批 rule_id 整段再抄一行（实测 manifest_l3 每遍
# +1527 行，而 633 个键里有 509 个组只有 observed_at 在变）。去重判定与读侧「同键取最后
# 一行」对应：同键且除运行元数据外全等 ⇒ 读侧结果不变 ⇒ 不追加。
# 实现只有一份：kb/kb_ledger.py（``out`` 已在上面的幂等守卫里被过滤过一轮）。
_dd_l3man = _ledger_mod.dedup_append(
    f"{L3}/manifest_l3.jsonl",
    [{"rule_id": r["rule_id"], "evidence_digest": r["evidence_digest"],
      "support_count": r["support_count"], "form": r["form"],
      "rule_kind": r["rule_kind"], "authority": r["authority"],
      "p_level": r["p_level"], "status": "provisional",
      "distiller_version": DISTILLER_VERSION, "observed_at": RUN} for r in out],
    "rule_id", label="@l5_prep.py/manifest_l3",
    last_seen_path="kb/l3/registry/last_seen.json", run=RUN)

# ---------- registry 追加说明
reg = json.load(open(f"{L3}/registry/l3.json", encoding="utf-8"))
reg["distiller_version"] = DISTILLER_VERSION
reg["appended_fields"] = {
    "at": RUN, "mode": "append",
    "fields": {
        "rule_kind": {"atomic": "原子映射型：一对修订 / 一个词条本身就是一条规则",
                      "inductive": "归纳型：由多条证据归纳出的模式"},
        "authority": {"expert": "来源是专家修订 / 人工合规审计",
                      "legal": "来源是法务词表 / 法规（本数据集无此类来源，故 0 条）",
                      "inferred": "由模型归纳，无外部权威背书"},
    },
    "why": "support_count=1 对 atomic 是正常的（一对修订天然只有一条支撑），只对 inductive 才是证据不足；"
           "两类判据不同，故必须分开。",
    "authority_mapping": AUTHORITY_BY_TABLE,
    "p_level_refined": {
        "why": "上一批把入口规则统一记为 P2、仅当「任一记录高危」才 P0，判据过粗；本批按源侧风险信号精确化",
        "rule": "入口规则：全部支撑记录风险等级均为「高危·红」→ P0；混合 → P1；"
                "品线边界规则：取该记录风险等级（高危→P0 / 审慎→P1 / 合规→P2 / 待复核→P3）；"
                "W1：取灯色状态（红色-禁用→P0 / 黄色-需限定→P1 / 绿色-可用→P2）；"
                "revision_pair：专家修订表无风险等级字段 → P1",
        "note": "风险信号取自 L2 里已存在的源事实单元；它们是元数据字段、不参与规则生成，但可作为 p_level 的判定依据",
    },
    "old_lines_untouched": {"lines": len(before_lines), "sha256": before_sha},
}
with open(f"{L3}/registry/l3.json", "w", encoding="utf-8") as fh:
    json.dump(reg, fh, ensure_ascii=False, indent=2); fh.write("\n")

json.dump({"before_lines": len(before_lines), "before_sha256": before_sha,
           # ★ 2026-10-10：`appended` 的语义改为「**本轮算出的富化条数**」（不再等于写进
           #   rules.jsonl 的行数 —— 那条路已停）。`appended_to_file` 如实记 0。
           "appended": len(out), "appended_to_file": 0,
           "enrich_home": "manifest_l3.jsonl（唯一真源；rules.jsonl 是上游重建的派生件）",
           "latest_total": len(latest),
           "kinds": dict(collections.Counter(r["rule_kind"] for r in latest.values())),
           "authority": dict(collections.Counter(r["authority"] for r in latest.values())),
           "p_level": dict(collections.Counter(r["p_level"] for r in latest.values())),
           "stat": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in stat.items()},
           "latest": {k: {"rule_id": v["rule_id"], "rule_kind": v["rule_kind"],
                          "authority": v["authority"], "p_level": v["p_level"],
                          "authority_source_table": v.get("authority_source_table"),
                          "risk_level": v["risk_level"], "form": v["form"],
                          "support_count": v["support_count"]}
                      for k, v in latest.items()}},
          open("kb/.work/l5_prep.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"追加 {len(out)} 行 | 最新 {len(latest)} 条")
print("  rule_kind:", dict(collections.Counter(r['rule_kind'] for r in latest.values())))
print("  authority:", dict(collections.Counter(r['authority'] for r in latest.values())))
print("  p_level:", dict(collections.Counter(r['p_level'] for r in latest.values())))
