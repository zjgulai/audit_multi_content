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

out = []
stat = collections.Counter()
for r in R:
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

# ---------- 只追加：写新行（旧行已在文件里不动）
with open(f"{L3}/candidates/rules.jsonl", "a", encoding="utf-8") as fh:
    for r in out:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

# 取每个 rule_id 的最新一行（旧行保留，取数取新行）
latest = {}
for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); latest[r["rule_id"]] = r

# ---------- 台账追加
with open(f"{L3}/manifest_l3.jsonl", "a", encoding="utf-8") as fh:
    for r in out:
        fh.write(json.dumps({"rule_id": r["rule_id"], "evidence_digest": r["evidence_digest"],
                             "support_count": r["support_count"], "form": r["form"],
                             "rule_kind": r["rule_kind"], "authority": r["authority"],
                             "p_level": r["p_level"], "status": "provisional",
                             "distiller_version": DISTILLER_VERSION, "observed_at": RUN},
                            ensure_ascii=False, sort_keys=True) + "\n")

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
           "appended": len(out), "latest_total": len(latest),
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
