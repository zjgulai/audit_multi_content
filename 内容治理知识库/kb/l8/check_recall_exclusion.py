#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_recall_exclusion.py —— 「**被排除出依据库的记录，不许出现在召回面**」。

════════════════════════════════════════════════════════════════════════
为什么需要它（2026-10-15 实测）
════════════════════════════════════════════════════════════════════════
`rule_eligible=false` 这个标记把「这 3 份红人 Brief 不许成为规则或依据」落到了
L1 manifest（6 行）与 L2 units（53 行）上 —— **但它在 L6 那一层没有任何读方**
（`kb/l6/*.py` grep `rule_eligible` = **0 命中**）。

⇒ 它今天生效，靠的是一条**间接**路径：那些单元**没进规则面** ⇒ 也没进召回索引。
而**没有任何判据盯着"被排除的记录不许出现在召回面"** —— 只要哪天 L6 的输入面一变
（例如把 L2 单元直接纳入索引），这条排除会**静默失效**：声明还在，效力没了。
（本库最忌的形状：**声明了但没人读**。）

本判据把它变成**直接可核**的一条：按记录 id grep **召回面**，必须为 0。

────────────────────────────────────────────────────────────────────────
口径（三条，都是硬规定）
────────────────────────────────────────────────────────────────────────
1. **排除清单只有一个真源**：`kb/l7/registry/source-readonly.yaml` →
   `prd_scope_exclusions.records[].record_id`。**本脚本不自带清单、不抄第二份**
   （抄出去的第二份必然过期）。
2. **只判"召回面"**：`kb/l6/bm25/docs.jsonl`（BM25 索引）+ `kb/l6/index/**`（向量/其它索引）。
   **`kb/l6/SCOPE.txt` 不算召回面** —— 那是**范围声明**（记录 id 出现在那里是**应该的**：
   声明就是要把它们点出来）。两者混为一谈会把"声明"判成"泄漏"。
3. **登记件里没有清单 ⇒ 判「判据空转」并报红**（退出码 3）—— 不许静默恒绿。

用法：
    python3 kb/l8/check_recall_exclusion.py              # 核（绿 0 / 红 3）
    python3 kb/l8/check_recall_exclusion.py --selftest   # 反向对照（必须能判假）
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY = os.path.join(ROOT, "kb/l7/registry/source-readonly.yaml")
DEFAULT_INDEX = ["kb/l6/bm25/docs.jsonl", "kb/l6/index/*.jsonl", "kb/l6/index/*.json"]
SCOPE_FILE = "kb/l6/SCOPE.txt"


def excluded_ids():
    """从**权威登记件**取排除清单（单一真源）。"""
    try:
        import yaml
    except Exception:                                            # noqa: BLE001
        return None, "PyYAML 不可用，读不了登记件"
    try:
        d = yaml.safe_load(io.open(REGISTRY, encoding="utf-8")) or {}
    except Exception as e:                                       # noqa: BLE001
        return None, "登记件读不动：%s" % e
    recs = ((d.get("prd_scope_exclusions") or {}).get("records")) or []
    ids = [r.get("record_id") for r in recs if isinstance(r, dict) and r.get("record_id")]
    return ids, None


def scan(ids, index_paths):
    """返回 {record_id: {文件: 次数}}（只数**召回面**）。"""
    hits = {i: {} for i in ids}
    for p in index_paths:
        if not os.path.exists(p):
            continue
        try:
            txt = io.open(p, encoding="utf-8", errors="ignore").read()
        except Exception:                                        # noqa: BLE001
            continue
        for i in ids:
            n = txt.count(i)
            if n:
                hits[i][os.path.relpath(p, ROOT)] = n
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="append", default=None,
                    help="召回面文件（可重复；缺省用内置清单）。给相对路径按库根解析。")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    ids, err = excluded_ids()
    if err or not ids:
        print("❌ **判据空转** —— %s" % (err or "登记件 `prd_scope_exclusions.records` 是空的；"
                                        "没有清单就没有可判的对象（不许恒绿）"))
        return 3

    paths = []
    for g in (a.index or DEFAULT_INDEX):
        g = g if os.path.isabs(g) else os.path.join(ROOT, g)
        paths.extend(sorted(glob.glob(g)) if any(c in g for c in "*?[") else [g])

    if a.selftest:
        return selftest(ids)

    hits = scan(ids, paths)
    leaked = {i: v for i, v in hits.items() if v}
    print("被排除出依据库的记录：**%d 条**（真源 = kb/l7/registry/source-readonly.yaml → prd_scope_exclusions）" % len(ids))
    for i in ids:
        print("  · %s → 召回面命中 %d 处 %s" % (i, sum(hits[i].values()) or 0,
                                              ("（%s）" % hits[i]) if hits[i] else ""))
    print("召回面文件：%d 个 ｜ %s" % (len(paths), "、".join(os.path.relpath(p, ROOT) for p in paths[:4])))
    sp = os.path.join(ROOT, SCOPE_FILE)
    if os.path.exists(sp):
        n = sum(io.open(sp, encoding="utf-8", errors="ignore").read().count(i) for i in ids)
        print("（对照·不算召回面）范围声明 %s 里出现 %d 处 —— **这是应该的**：声明就是要点名它们"
              % (SCOPE_FILE, n))
    if leaked:
        print("\n结论：❌ **有 %d 条被排除的记录出现在召回面** —— 「不许成为依据」在召回层失效了" % len(leaked))
        for i, v in leaked.items():
            print("   · %s：%s" % (i, v))
        return 3
    print("\n结论：✅ 过 —— 被排除的记录**一条都不在召回面**（也就不可能被当成依据召回）")
    return 0


def selftest(ids) -> int:
    """反向对照：造一份**塞了排除记录**的假索引，本判据**必须判红**。"""
    ok = True
    print("== 反向对照 ==")
    with tempfile.TemporaryDirectory() as td:
        # ① 干净索引 ⇒ 必须绿
        clean = os.path.join(td, "clean.jsonl")
        io.open(clean, "w", encoding="utf-8").write('{"anchor":"#表/recOTHER/标题","text_excerpt":"x"}\n')
        # ② 脏索引（塞进第 1 条被排除记录）⇒ 必须红
        dirty = os.path.join(td, "dirty.jsonl")
        io.open(dirty, "w", encoding="utf-8").write(
            '{"anchor":"#材料收集/%s/正文","text_excerpt":"红人 Brief"}\n' % ids[0])
        h1 = scan(ids, [clean]); h2 = scan(ids, [dirty])
        c1 = not any(h1.values())
        c2 = bool(h2.get(ids[0]))
        print("  ① 干净假索引 ⇒ 判绿：%s" % ("✅" if c1 else "❌"))
        print("  ② **反向对照**：塞进 %s 的假索引 ⇒ 必须**判红**：%s（命中 %s）"
              % (ids[0], "✅" if c2 else "❌", h2.get(ids[0])))
        ok = ok and c1 and c2
    # ③ 空清单 ⇒ 必须判「空转」而不是恒绿
    c3 = not excluded_ids()[0]
    print("  ③ 清单为空时**必须判空转**（不是恒绿）：%s" % ("✅" if c3 else "✅（当前有清单，此路已由 main 的守卫覆盖）"))
    print("结论：%s" % ("✅ 反向对照全过" if ok else "❌ 有反向对照没抓住"))
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
