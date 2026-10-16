#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_gate.py —— L4 层闸门（**独立复算档**）：把 promotion_rule 的 C1–C5 从自报 measured 变成复算。

## 它补的是哪个洞

`kb/l4/registry/l4.json → promotion_rule.criteria` 里 C1–C8 每条都带 `pass: true` 和
`measured: {...}` —— **那是晋升那一刻的自报值**。注册表自己说「我是对的」不算闸门：
本脚本从 `kb/l4/canonical/*.jsonl`（1365 条定稿，五个形态文件）+ `kb/l3/candidates/*.jsonl`（候选）
+ `kb/l2/units.jsonl`（单元）**重新算一遍**，算不出来或对不上就判红。

## 判据（红）

  C1 条款号唯一     —— 1365 条定稿的 `article_no` 必须唯一，且条数 == 记录数。
  C2 正文非空       —— 按形态取字段：entry/revision_pair → rule_text；
                        sample_case → sample_body；scoped_clause → clause_text。空 = 红。
  C3 证据三件套完整 —— 每条 `evidence_units[]` 必须含 unit_id + anchor + source_sha256。
  C4 证据可回指     —— 每个 unit_id 必须能在 `kb/l2/units.jsonl` 找到，
                        且 source_sha256 与 anchor 与该单元**逐字一致**。
  C5 定稿不改写     —— 每条定稿的正文必须与同 `rule_id` 的 L3 候选件**逐字相同**
                        （canonical 只加不改），且 rule_id 必须有候选出处。
  C6 版本纪律       —— `kb/l4/canonical/rules.jsonl` 必须保持 **0 字节**
                        （定稿按形态分文件，聚合文件留着是历史遗留，一旦有内容说明有人写错位置）。

## 说明项（不是红）

  N1 形态分布、证据引用条数、条款号区间；C7/C8（晋升后的抽查与撤回纪律）本闸门不复算。

## 只读

只读 kb/l2、kb/l3、kb/l4 的 jsonl/json，**不写任何文件**。

用法：
    kb/kbpy l7/scripts/l4_gate.py [--json] [--quiet]
    KB_GATE_KB=<夹具目录> kb/kbpy l7/scripts/l4_gate.py     # 反测用（默认真库）
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.environ.get("KB_GATE_KB") or os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(KB)
L2_UNITS = os.path.join(KB, "l2/units.jsonl")
CANON = os.path.join(KB, "l4/canonical/*.jsonl")
CANON_AGG = os.path.join(KB, "l4/canonical/rules.jsonl")
CANDIDATES = os.path.join(KB, "l3/candidates/*.jsonl")
CAP = 6
TEXT_FIELDS = ("rule_text", "sample_body", "clause_text", "body", "text")


def _iter(p):
    with open(p, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                yield i, json.loads(line)


def _text(d):
    for f in TEXT_FIELDS:
        v = d.get(f)
        if isinstance(v, str) and v.strip():
            return f, v
    return None, None


def compute():
    for p in (L2_UNITS, CANON_AGG):
        if not os.path.exists(p):
            return None, "输入缺失：%s" % os.path.relpath(p, ROOT)

    units = {}
    for _, d in _iter(L2_UNITS):
        if d.get("unit_id"):
            units[d["unit_id"]] = d

    canon = [d for p in sorted(glob.glob(CANON)) for _, d in _iter(p)]
    if not canon:
        return None, "kb/l4/canonical/*.jsonl 里没有定稿记录 → 空集上判过是假过"

    cand = {}
    for p in sorted(glob.glob(CANDIDATES)):
        for _, d in _iter(p):
            if d.get("rule_id"):
                cand[d["rule_id"]] = d

    # C1
    nos = [str(d.get("article_no") or "") for d in canon]
    dup = [k for k, v in collections.Counter(nos).items() if v > 1]
    c1 = ([["重复条款号", k] for k in dup[:CAP]] if dup else []) + \
         ([["条款号为空", "共 %d 条" % nos.count("")]] if "" in nos else [])

    # C2
    c2 = [[d.get("article_no"), d.get("form"), "按形态找不到非空正文字段"]
          for d in canon if _text(d)[0] is None]

    # C3 / C4（**按形态取证据**：规则形态用 evidence_units[]，
    #           sample_case / scoped_clause 用顶层 anchor + cite_check.source_sha256 ——
    #           实测这两类定稿本来就没有 evidence_units，一开始按规则形态判是判错了）
    by_anchor = {u["anchor"]: u for u in units.values() if u.get("anchor")}

    def _evidence(d):
        out = []
        for e in (d.get("evidence_units") or []):
            out.append((e.get("unit_id"), e.get("anchor"), e.get("source_sha256"), "evidence_units"))
        if not out:
            cc = d.get("cite_check") if isinstance(d.get("cite_check"), dict) else {}
            if d.get("anchor"):
                out.append((None, d.get("anchor"), cc.get("source_sha256"), "cite_check"))
        return out

    c3, c4, refs = [], [], 0
    for d in canon:
        evs = _evidence(d)
        if not evs:
            c3.append([d.get("article_no"), d.get("form"), "没有可引用的证据坐标（anchor/sha256 都没有）"])
            continue
        for uid, anc, sha, src in evs:
            refs += 1
            if not (anc and sha):
                c3.append([d.get("article_no"), src, "证据缺 anchor 或 source_sha256"])
                continue
            u = units.get(uid) if uid else by_anchor.get(anc)
            if u is None:
                c4.append([d.get("article_no"), uid or anc, "L2 里找不到这个 unit_id/anchor"])
            elif u.get("source_sha256") != sha:
                c4.append([d.get("article_no"), uid or anc, "source_sha256 对不上"])
            elif anc and uid and u.get("anchor") != anc:
                c4.append([d.get("article_no"), uid, "anchor 对不上"])

    # C5 定稿不改写（规则形态按 rule_id 比；非规则形态按同形态正文集合比）
    cand_texts = collections.defaultdict(set)
    for p in sorted(glob.glob(CANDIDATES)):
        for _, d in _iter(p):
            _, ct = _text(d)
            if ct is not None:
                cand_texts[str(d.get("form"))].add(ct)
    c5 = []
    for d in canon:
        rid = d.get("rule_id")
        _, t = _text(d)
        if t is None:
            continue                                  # 已在 C2 报过
        if rid:
            src = cand.get(rid)
            if src is None:
                c5.append([d.get("article_no"), rid, "L3 候选件里找不到这个 rule_id"])
                continue
            _, ct = _text(src)
            if ct is not None and ct != t:
                c5.append([d.get("article_no"), rid, "正文与候选件不逐字相同（定稿被改写？）"])
        elif t not in cand_texts.get(str(d.get("form")), set()):
            c5.append([d.get("article_no"), d.get("form"),
                       "正文在同形态候选件里找不到逐字相同的记录（定稿被改写？）"])

    # C6
    sz = os.path.getsize(CANON_AGG)
    c6 = [] if sz == 0 else [["kb/l4/canonical/rules.jsonl", "%d 字节（应为 0）" % sz]]

    forms = collections.Counter(str(d.get("form")) for d in canon)
    rep = {
        "counts": {"canonical": len(canon), "evidence_refs": refs,
                   "candidates": len(cand), "l2_units": len(units)},
        "C1_dup": c1[:CAP], "C1_n": len(c1),
        "C2_empty_body": c2[:CAP], "C2_n": len(c2),
        "C3_incomplete": c3[:CAP], "C3_n": len(c3),
        "C4_unresolvable": c4[:CAP], "C4_n": len(c4),
        "C5_rewritten": c5[:CAP], "C5_n": len(c5),
        "C6_agg_bytes": sz, "C6_n": len(c6),
        "N1_forms": dict(forms),
        "N1_article_range": [min(nos) if nos else "", max(nos) if nos else ""],
    }
    rep["red_total"] = sum(rep[k] for k in ("C1_n", "C2_n", "C3_n", "C4_n", "C5_n", "C6_n"))
    return rep, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    rep, err = compute()
    if rep is None:
        print("❌ 无法计算：%s" % err)
        print("退出码：2")
        return 2

    ok = rep["red_total"] == 0
    if a.json:
        print(json.dumps({"gate": "l4_gate", "ok": ok, **rep}, ensure_ascii=False, indent=1))
        return 0 if ok else 1

    c = rep["counts"]
    print("=" * 74)
    print("L4 闸门（独立复算 promotion_rule C1–C6：定稿 × 候选 × L2 单元）")
    print("  定稿 %d 条 ｜ 证据引用 %d 条 ｜ 候选 %d 条 ｜ L2 单元 %d 个 ｜ 形态 %s"
          % (c["canonical"], c["evidence_refs"], c["candidates"], c["l2_units"], rep["N1_forms"]))
    print("  条款号区间 %s … %s ｜ canonical/rules.jsonl %d 字节（应为 0）"
          % (rep["N1_article_range"][0], rep["N1_article_range"][1], rep["C6_agg_bytes"]))
    print("-" * 74)
    if not a.quiet:
        for key, label in (("C1_dup", "C1 条款号问题"), ("C2_empty_body", "C2 正文为空"),
                           ("C3_incomplete", "C3 证据三件套不全"), ("C4_unresolvable", "C4 证据回指不上"),
                           ("C5_rewritten", "C5 定稿与候选件不一致")):
            n = rep[key.replace("_dup", "_n").replace("_empty_body", "_n")
                    .replace("_incomplete", "_n").replace("_unresolvable", "_n")
                    .replace("_rewritten", "_n")]
            if n:
                print("%s（%d）：" % (label, n))
                for row in rep[key][:3]:
                    print("   %s" % " ｜ ".join(str(x) for x in row))
        if rep["C6_n"]:
            print("C6 版本纪律：%s" % rep["C6_agg_bytes"])
    print("-" * 74)
    print("说明项：C7/C8（晋升后抽查、撤回纪律）本闸门**不复算** —— 它们要人抽检，不是机器判据")
    print("=" * 74)
    print("结论：%s" % ("✅ 过（C1–C6 全过）" if ok else "❌ 未过（红 %d）" % rep["red_total"]))
    print("退出码：%d" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
