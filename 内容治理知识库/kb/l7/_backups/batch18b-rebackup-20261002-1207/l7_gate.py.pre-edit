#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l7_gate.py —— L7 层闸门（**独立复算档**）：把「引用契约」从一段话变成可跑的前置条件。

## 它补的是哪个洞

`layers.yaml` 里 L7 的闸门原文是一句话：

    citation_contract.hard_gate：引用不到本地锚点（anchor 解析失败 或 source_sha256 对不上
    或 摘录与原文不逐字一致）的结论，一律不输出

这句话本身**没有落点**：谁来判、判什么文件、判据是什么，都没写。
本闸门把它的**前置条件**跑出来 —— 契约里承诺的每一个要素，今天在库上到底物化得出来吗：

  C1 库名不得自造 —— `citation_contract.libraries` 的每个 key 必须与
                     `kb/l0/registry/kb.json → kb_types` 的 `label` + `dir` **逐字一致**
                     （契约原文：「不得自造库名」），且 kb_types 里 5 个库一个都不能漏。
  C2 现行规则库名可复算 —— 契约声明 `library_of_current_rules = wording`，
                     必须能从 `kb/l3/candidates/*.jsonl` 复算：候选记录的 `kb_type` 全为 wording。
  C3 六要素可物化 —— 契约 `must_include = [库名, 版本, 条款号, anchor, source_sha256, 逐字摘录]`：
                     定稿必须有非空 `article_no`、非空逐字正文、至少一条带 anchor+source_sha256 的
                     证据引用。缺一 = 红（**引用不出来的东西，硬闸门就是空话**）。
  C4 条款号出处对得上 —— 契约 `article_no_source.field_lives_in` 点名的位置必须真的存在且含该字段。

## 说明项（不是红）

  N1 hard_gate / format / version_in_citation 原文照打（契约文本本身）。
  N2 六要素在多少条定稿上物化成功（覆盖率）。
  N3 「硬闸门」真正的执行点在评审链（kb-content-review）运行时 —— 本闸门只保证**前置条件成立**，
     运行时的引用完整性由那条链自己的硬闸门负责；本闸门不替它签字。

## 只读

只读 kb/l0、kb/l3、kb/l4、kb/l7 的 json/jsonl，**不写任何文件**。

用法：
    kb/kbpy l7/scripts/l7_gate.py [--json] [--quiet]
    KB_GATE_KB=<夹具目录> kb/kbpy l7/scripts/l7_gate.py     # 反测用（默认真库）
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
L7_REG = os.environ.get("KB_GATE_L7_FILE") or os.path.join(KB, "l7/registry/l7.json")
KB_TYPES = os.path.join(KB, "l0/registry/kb.json")
CANDIDATES = os.path.join(KB, "l3/candidates/*.jsonl")
CANON = os.path.join(KB, "l4/canonical/*.jsonl")
TEXT_FIELDS = ("rule_text", "sample_body", "clause_text", "body", "text")
CAP = 6


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
            return v
    return None


def compute():
    for p in (L7_REG, KB_TYPES):
        if not os.path.exists(p):
            return None, "输入缺失：%s" % os.path.relpath(p, ROOT)
    with open(L7_REG, encoding="utf-8") as fh:
        l7 = json.load(fh)
    with open(KB_TYPES, encoding="utf-8") as fh:
        kbt = (json.load(fh).get("kb_types") or {})
    cc = l7.get("citation_contract") or {}

    # C1
    c1 = []
    for key, v in (cc.get("libraries") or {}).items():
        ref = kbt.get(key)
        if ref is None:
            c1.append([key, "契约里有、kb_types 里没有（自造库名）"])
        elif (v.get("label") != ref.get("label")) or (v.get("dir") != ref.get("dir")):
            c1.append([key, "label/dir 与 kb_types 不一致",
                       "%s/%s" % (v.get("label"), v.get("dir")),
                       "%s/%s" % (ref.get("label"), ref.get("dir"))])
    for key in kbt:
        if key not in (cc.get("libraries") or {}):
            c1.append([key, "kb_types 里有、契约里漏登记"])

    # C2（只对**规则**：契约说的是 rules.jsonl 的 509 条候选规则；
    #     一开始拿全部候选件（1242 条，含样本/条款）去比是判错了）
    rules_file = os.path.join(KB, "l3/candidates/rules.jsonl")
    if not os.path.exists(rules_file):
        return None, "kb/l3/candidates/rules.jsonl 不存在"
    claimed = str(cc.get("library_of_current_rules") or "").split("（")[0].strip()
    rule_types, n_rule = collections.Counter(), 0
    for _, d in _iter(rules_file):
        n_rule += 1
        rule_types[str(d.get("kb_type"))] += 1
    all_types = collections.Counter()
    for p in sorted(glob.glob(CANDIDATES)):
        for _, d in _iter(p):
            all_types[str(d.get("kb_type"))] += 1
    c2 = []
    if n_rule == 0:
        return None, "kb/l3/candidates/rules.jsonl 没有记录 → 空集上判过是假过"
    if set(rule_types) != {claimed}:
        c2.append(["规则候选件 kb_type 分布", dict(rule_types), "契约声明 %s" % claimed])

    # C3（六要素**按形态**物化：规则形态证据在 evidence_units[]；
    #     样本/条款形态证据在顶层 anchor + cite_check.source_sha256）
    canon = [d for p in sorted(glob.glob(CANON)) for _, d in _iter(p)]
    if not canon:
        return None, "kb/l4/canonical/*.jsonl 没有定稿 → 空集上判过是假过"
    c3, full = [], 0
    for d in canon:
        art, txt = str(d.get("article_no") or ""), _text(d)
        evs = [e for e in (d.get("evidence_units") or [])
               if e.get("anchor") and e.get("source_sha256")]
        if not evs:
            # 变量名别用 cc —— 外层 cc 是 citation_contract，会被这个循环覆盖掉（踩过一次）
            ck = d.get("cite_check") if isinstance(d.get("cite_check"), dict) else {}
            if d.get("anchor") and ck.get("source_sha256"):
                evs = [{"anchor": d.get("anchor"), "source_sha256": ck.get("source_sha256")}]
        if art and txt and evs:
            full += 1
        else:
            c3.append([art or "(无条款号)", "正文" if not txt else "ok",
                       "证据引用" if not evs else "ok"])

    # C4（条款号出处：契约里写的是「kb/l4/canonical/*.jsonl（定稿，五个形态文件）+
    #     台账 kb/l4/registry/l4.json 的 numbering.issued」→ 要先剥括号、再按 glob 判）
    c4 = []
    aus = l7.get("article_no_source") or {}
    for raw in (aus.get("field_lives_in") or "").split("+"):
        p = raw.strip()
        p = p.split("（")[0].strip()          # 剥掉中文括号说明
        p = p.split("的 ")[0].strip()
        if not p.startswith("kb/"):
            continue
        q = os.path.join(ROOT, p)
        hits = glob.glob(q) if ("*" in p or "?" in p) else ([q] if os.path.exists(q) else [])
        if not hits:
            c4.append([p, "文件/目录不存在"])
            continue
        if os.path.isdir(hits[0]):
            if not glob.glob(os.path.join(hits[0], "*.jsonl")):
                c4.append([p, "目录里没有 jsonl"])
            continue
        if hits[0].endswith(".jsonl"):
            with open(hits[0], encoding="utf-8") as fh:
                first = next((json.loads(l) for l in fh if l.strip()), {})
            field = aus.get("field") or "article_no"
            if field not in first:
                c4.append([p, "缺字段 %s" % field])

    rep = {
        "counts": {"rule_candidates": n_rule, "all_candidates": sum(all_types.values()),
                   "canonical": len(canon), "six_elements_full": full},
        "C1_bad_libraries": c1[:CAP], "C1_n": len(c1),
        "C2_bad_library_of_rules": c2[:CAP], "C2_n": len(c2),
        "C3_missing_elements": c3[:CAP], "C3_n": len(c3),
        "C4_bad_source_path": c4[:CAP], "C4_n": len(c4),
        "N1_contract_text": {k: cc.get(k) for k in ("format", "version_in_citation", "hard_gate")},
    }
    rep["red_total"] = rep["C1_n"] + rep["C2_n"] + rep["C3_n"] + rep["C4_n"]
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
        print(json.dumps({"gate": "l7_gate", "ok": ok, **rep}, ensure_ascii=False, indent=1))
        return 0 if ok else 1

    c = rep["counts"]
    print("=" * 74)
    print("L7 闸门（引用契约的前置条件：库名 / 现行库可复算 / 六要素 / 条款号出处）")
    print("  规则候选 %d 条（全部候选 %d 条）｜ 定稿 %d 条 ｜ 六要素齐备 %d 条（覆盖率 %.1f%%）"
          % (c["rule_candidates"], c["all_candidates"], c["canonical"], c["six_elements_full"],
             100.0 * c["six_elements_full"] / max(1, c["canonical"])))
    print("-" * 74)
    if not a.quiet:
        for key, label in (("C1_bad_libraries", "C1 库名问题"), ("C2_bad_library_of_rules", "C2 现行规则库名"),
                           ("C3_missing_elements", "C3 六要素缺失"), ("C4_bad_source_path", "C4 条款号出处")):
            n = rep[key.replace("_bad_libraries", "_n").replace("_bad_library_of_rules", "_n")
                    .replace("_missing_elements", "_n").replace("_bad_source_path", "_n")]
            if n:
                print("%s（%d）：%s" % (label, n, [str(x)[:70] for x in rep[key][:3]]))
    print("-" * 74)
    print("说明项 N1 契约原文：格式 %s ｜ 版本 %s" % (rep["N1_contract_text"].get("format"),
                                                rep["N1_contract_text"].get("version_in_citation")))
    print("   hard_gate：%s" % rep["N1_contract_text"].get("hard_gate"))
    print("说明项 N3：运行时引用完整性由评审链（kb-content-review）自己的硬闸门负责；"
          "本闸门只保证**前置条件成立**")
    print("=" * 74)
    print("结论：%s" % ("✅ 过（前置条件全成立）" if ok else "❌ 未过（红 %d）" % rep["red_total"]))
    print("退出码：%d" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
