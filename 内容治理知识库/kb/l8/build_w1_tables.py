#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_w1_tables.py —— 目标 25：PRD §14 **W1** 三件输出（规则分层表 / 对接人表 / 知识库 v1）。

## 出处（逐字）

· 任务拆解同表交付物 **25**：`规则分层表 / 对接人表 / 知识库 v1（PRD §14 W1 输出）`
· PRD §14 里程碑 W1 逐字：`需求确认 + 知识库收集 | 确认 PRD；收集四类知识库；确定飞书群 + 多维表方案；
  完成规则分层配置 | PRD、知识库 v1、规则分层表、对接人表`
· PRD §6.2 规则分层：P0（红线，命中即 BLOCK）/ P1（安全准确性·语义）/ P2（通识常识·多模态）/ P3

## 为什么现在才做（**查重结论，不是重复造**）

2026-10-10 查重：库内**没有**这三件的现成产物，但**数据都在** ——
`kb/l3/candidates/rules.jsonl` 已带 `p_level`、`kb/l5/p0_patterns.jsonl` 11 条 P0；
`kb/l7/registry/permission-matrix.yaml` 已有**角色位**。⇒ 本件只做**汇总成表**，不重算口径。

## ★ 对接人表：**人名一律留空**（同 目标 18 的口径）

`permission-matrix.yaml` 的 `honest_limits` 逐字：「**本件给角色位，给不出人名** ——
§13 六类角色「谁是谁」的绑定要你或统筹提供，**本库无从推断**」。
⇒ 本件**只出角色位 + 待填栏**，`name`/`feishu_user` 一律 `null`。**不编人名。**

## 用法

    python3 kb/l8/build_w1_tables.py            # 预演（零写入）
    python3 kb/l8/build_w1_tables.py --apply
    python3 kb/l8/build_w1_tables.py --verify    # 只读：三件齐不齐、对接人填了几格
    python3 kb/l8/build_w1_tables.py --selftest
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
ROOT = os.path.dirname(KB)
OUT = os.path.join(KB, "l7/registry")
RULES = os.path.join(KB, "l3/candidates/rules.jsonl")
P0 = os.path.join(KB, "l5/p0_patterns.jsonl")
PMATRIX = os.path.join(KB, "l7/registry/permission-matrix.yaml")

#: PRD §6.2 四层语义（**逐字取自 PRD，不自行改写**）
TIER_SEMANTICS = {
    "P0": "红线：命中即 BLOCK（规则引擎，≤1s）",
    "P1": "安全准确性（语义判断，大模型）",
    "P2": "通识常识（多模态）",
    "P3": "其它（措辞/风格等）",
}


def _lines(p):
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()] if os.path.exists(p) else []


def rule_tiering_table():
    """规则分层表：四层 × 条数 × 代表条款号。**条数一律现算**，不抄。"""
    rows = _lines(RULES)
    by = collections.defaultdict(list)
    for r in rows:
        by[r.get("p_level") or "未分层"].append(r)
    out = []
    for lvl in ("P0", "P1", "P2", "P3"):
        items = by.get(lvl) or []
        arts = [x.get("article_no") for x in items if x.get("article_no")]
        out.append({"level": lvl, "semantics": TIER_SEMANTICS[lvl], "count": len(items),
                    "with_article_no": len(arts), "article_no_sample": sorted(set(arts))[:8],
                    "rule_ids_sample": [x.get("rule_id") for x in items[:5]]})
    un = by.get("未分层") or []
    if un:
        out.append({"level": "未分层", "semantics": "（异常：不该出现）", "count": len(un),
                    "with_article_no": 0, "article_no_sample": [], "rule_ids_sample": []})
    p0p = _lines(P0)
    return {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "kb/l3/candidates/rules.jsonl（p_level）＋ kb/l5/p0_patterns.jsonl",
            "total_rules": len(rows), "tiers": out,
            "p0_engine_patterns": {"count": len(p0p),
                                   "rule_codes": [x.get("rule_code") for x in p0p],
                                   "note": "P0 由**确定性规则引擎**跑（PRD §6.2 / §11.2），"
                                           "这 11 条就是它的全部模式"}}

def contact_table():
    """对接人表：**角色位来自权限矩阵，人名一律留空**（不编）。"""
    roles = []
    try:
        import yaml
        d = yaml.safe_load(io.open(PMATRIX, encoding="utf-8")) or {}
        rm = d.get("roles") or {}
        for name, v in rm.items():
            roles.append({
                "role": name,
                "prd_rights": (v or {}).get("prd_rights"),
                "routing_policy_key": (v or {}).get("routing_policy_key"),
                "bind_status": (v or {}).get("bind_status"),
                "read_scope": ((v or {}).get("read") or {}).get("scope"),
                # ── 待填：**一律 null，不许编人名** ──────────────────────
                "name": None, "feishu_user": None, "backup": None, "confirmed_at": None,
            })
    except Exception as e:                                   # noqa: BLE001
        raise SystemExit("[拒读] 读不到角色位 %s（%r）" % (PMATRIX, e))
    if not roles:
        raise SystemExit("[拒写] 角色位为空 —— 空表会静默什么都不说")
    return {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "kb/l7/registry/permission-matrix.yaml → roles（**只取角色位**）",
            "prd_ref": "PRD §14 W1「对接人表」/ §13 权限与安全 / §9 复核与 sign-off",
            "roles": roles,
            "note": "★ **人名一律留空** —— 权限矩阵 honest_limits 逐字：本件给角色位、给不出人名，"
                    "绑定要 Owner 或统筹提供，**本库无从推断**。填法：逐行补 name（具名）＋ feishu_user。"}


def kb_snapshot():
    """知识库 v1 快照：各层**现算**条数 + 版本（不抄任何二份）。"""
    def n(p):
        return sum(1 for l in io.open(p, encoding="utf-8") if l.strip()) if os.path.exists(p) else None
    layers = {
        "L0": {"file": "kb/l0/manifest.jsonl", "rows": n(os.path.join(KB, "l0/manifest.jsonl"))},
        "L1": {"file": "kb/l1/manifest_l1.jsonl", "rows": n(os.path.join(KB, "l1/manifest_l1.jsonl"))},
        "L2": {"file": "kb/l2/units.jsonl", "rows": n(os.path.join(KB, "l2/units.jsonl"))},
        "L3": {"file": "kb/l3/candidates/rules.jsonl", "rows": n(RULES)},
        "L3b": {"file": "kb/l3/candidates/scoped_clauses.jsonl",
                "rows": n(os.path.join(KB, "l3/candidates/scoped_clauses.jsonl"))},
        "L4": {"file": "kb/l4/canonical/scoped_clause.jsonl",
               "rows": n(os.path.join(KB, "l4/canonical/scoped_clause.jsonl"))},
        "L5": {"file": "kb/l5/p0_patterns.jsonl", "rows": n(P0)},
    }
    ver = None
    try:
        ver = json.load(io.open(os.path.join(KB, "l0/registry/kb.json"), encoding="utf-8")).get("kb_version")
    except Exception:                                        # noqa: BLE001
        pass
    return {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "what": "知识库 v1 快照清单（PRD §14 W1 输出之一）",
            "kb_version_declared": ver,
            "layers": layers,
            "note": "★ 条数**现算**自各层真文件；口径详见 kb/l7/registry/layers.yaml 与各层闸门。"}


def build():
    return {"rule_tiering": rule_tiering_table(),
            "contacts": contact_table(),
            "kb_snapshot": kb_snapshot()}


def verify():
    paths = {"规则分层表": "w1-rule-tiering-table.json", "对接人表": "w1-contact-table.json",
             "知识库v1": "w1-kb-snapshot.json"}
    miss = [k for k, v in paths.items() if not os.path.exists(os.path.join(OUT, v))]
    if miss:
        print("缺：%s（先 --apply）" % miss)
        return 2
    c = json.load(io.open(os.path.join(OUT, paths["对接人表"]), encoding="utf-8"))
    t = json.load(io.open(os.path.join(OUT, paths["规则分层表"]), encoding="utf-8"))
    named = [r for r in c["roles"] if (r.get("name") or "").strip()]
    print("① 规则分层表：%d 条规则分 %d 层" % (t["total_rules"], len(t["tiers"])))
    print("② 对接人表：%d 个角色位，**已填人名 %d**" % (len(c["roles"]), len(named)))
    print("③ 知识库 v1 快照：%d 层" % len(json.load(io.open(os.path.join(OUT, paths["知识库v1"]),
                                                          encoding="utf-8"))["layers"]))
    ok = len(named) == len(c["roles"])
    print("结论：%s" % ("✅ W1 三件齐、对接人已绑定" if ok else
                       "⛔ 三件已出，但**对接人 %d/%d 未绑定**（人名要人给，本库无从推断）"
                       % (len(c["roles"]) - len(named), len(c["roles"]))))
    return 0 if ok else 3


def selftest():
    global RULES                                            # noqa: PLW0603
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    b = build()
    t = b["rule_tiering"]
    ck("① 分层表：P0/P1/P2/P3 四层都在", all(any(x["level"] == L for x in t["tiers"])
                                              for L in ("P0", "P1", "P2", "P3")),
       [x["level"] for x in t["tiers"]])
    ck("①b 四层条数之和 == 规则总数（不重不漏）",
       sum(x["count"] for x in t["tiers"]) == t["total_rules"],
       "%d vs %d" % (sum(x["count"] for x in t["tiers"]), t["total_rules"]))
    ck("①c 条数**与真文件现算一致**（不是抄的）",
       t["tiers"][[x["level"] for x in t["tiers"]].index("P1")]["count"] ==
       sum(1 for r in _lines(RULES) if r.get("p_level") == "P1"), "")
    ck("② P0 引擎模式 11 条", t["p0_engine_patterns"]["count"] == 11,
       str(t["p0_engine_patterns"]["count"]))
    # ★ 反向对照：**不许编人名**
    ck("③ 反向对照：对接人表人名一律为空（不许编）",
       all(r["name"] is None and r["feishu_user"] is None for r in b["contacts"]["roles"]), "")
    ck("③b 角色位非空（挡住「读法错导致空表」）", len(b["contacts"]["roles"]) >= 4,
       str(len(b["contacts"]["roles"])))
    # ★ 反向对照：知识库 v1 的条数必须现算（改一个假文件 ⇒ 判据要能变）
    import tempfile
    tmp = tempfile.mkdtemp(prefix="w1-")
    fake = os.path.join(tmp, "rules.jsonl")
    io.open(fake, "w", encoding="utf-8").write(
        "\n".join(json.dumps({"p_level": "P0", "rule_id": "x%d" % i}) for i in range(3)) + "\n")
    _orig = RULES
    RULES = fake
    _t2 = rule_tiering_table()
    ck("④ 反向对照：换一个 3 条的文件 ⇒ 分层表条数跟着变（证明是现算）",
       _t2["total_rules"] == 3 and _t2["tiers"][0]["count"] == 3, "total=%d" % _t2["total_rules"])
    RULES = _orig
    _t3 = rule_tiering_table()
    ck("⑤ 还原后条数回到真值（证明 ④ 不是巧合）", _t3["total_rules"] == t["total_rules"],
       "total=%d" % _t3["total_rules"])
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print("build_w1_tables --selftest（目标 25 · PRD §14 W1 三件）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + str(ex)) if ex else ""))
    bad = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad, len(res), "" if not bad else "  ← 有失败"))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.verify:
        return verify()
    b = build()
    t = b["rule_tiering"]
    print("PRD §14 W1 三件 —— 目标 25")
    print("  ① 规则分层表：")
    for x in t["tiers"]:
        print("     %-4s %4d 条 ｜ 带条款号 %4d ｜ %s" % (x["level"], x["count"], x["with_article_no"],
                                                         x["semantics"]))
    print("     P0 引擎模式 %d 条：%s" % (t["p0_engine_patterns"]["count"],
                                          ",".join(str(c) for c in t["p0_engine_patterns"]["rule_codes"])))
    print("  ② 对接人表：%d 个角色位（**人名一律留空**）" % len(b["contacts"]["roles"]))
    print("  ③ 知识库 v1 快照：%d 层" % len(b["kb_snapshot"]["layers"]))
    if not a.apply:
        print("\n预演（零写入）。要落盘加 --apply。")
        return 0
    os.makedirs(OUT, exist_ok=True)
    for fn, obj in (("w1-rule-tiering-table.json", b["rule_tiering"]),
                    ("w1-contact-table.json", b["contacts"]),
                    ("w1-kb-snapshot.json", b["kb_snapshot"])):
        json.dump(obj, io.open(os.path.join(OUT, fn), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("  ✅ kb/l7/registry/%s" % fn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
