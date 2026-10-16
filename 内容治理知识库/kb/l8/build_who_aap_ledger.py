#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_who_aap_ledger.py —— WHO / AAP **条款号台账**（目标 10）。

## 它补的是溯源契约的第一段

库的硬规矩是四段溯源：**条款号(L4) + 规则与命中片段(L3) + 锚点/指纹(L2/L1) + 逐字原文(L0)**，
**缺一段不许出结论**。实测：L2 里含 WHO 的单元 **205** 条、含 AAP 的 **142** 条
（全称各 38 / 31），**但它们一个条款号都给不出** ⇒ 这批医学共识**进不了任何一条能出的结论**。
本台账把「出自 WHO/AAP 哪一条、哪个地区、不早于哪年生效」抽出来。

## 三条纪律（每条都有反向对照）

1. **假阳性要挡住**：样本里 `Section 2` / `Section 1` 来自一本育儿书，**不是** WHO/AAP 条款
   ⇒ 判据要求**条款号附近出现 WHO/AAP 主体词**，不是"整段里随便提了一句"。
2. **抽不到就留空、并写清原因** —— `region` / `not_before_year` 取不到一律 `null` ＋ 进 `unresolved`，
   **不许用常识补**（PRD 与库纪律都要求）。
3. **每条可回指**：`unit_id + anchor + source_sha256 + resource_id` 四样齐，
   少一样**不许进台账**（宁可进 `unresolved`）。

用法：
    python3 kb/l8/build_who_aap_ledger.py [--apply]      # 默认干跑
    python3 kb/l8/build_who_aap_ledger.py --selftest     # 反向对照
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L2 = os.path.join(ROOT, "kb/l2/units.jsonl")
OUT_DIR = os.path.join(ROOT, "kb/l3/registry")
OUT = os.path.join(OUT_DIR, "who-aap-clause-ledger.jsonl")
OUT_SUM = os.path.join(OUT_DIR, "who-aap-clause-ledger.json")

#: 主体词 —— 条款号**附近**（WINDOW 字符内）必须出现其中之一
BODY = re.compile(r"AAP|American Academy of Pediatrics|\bWHO\b|World Health Organization", re.I)
#: 条款号形态（WHO/AAP 指南的实际写法）
CLAUSE = [
    re.compile(r"(?i)\b(?:conditional|context-specific|strong|weak)?\s*recommendation\s+(\d+[a-z]?(?:\.\d+)*)"),
    re.compile(r"(?i)\bpolicy\s+statement\b[^.\n]{0,60}?\b(\d{4})\b"),
    re.compile(r"(?i)\b(?:WHO|AAP)\b[^.\n]{0,60}?\b(?:section|§)\s*(\d+(?:\.\d+)*)"),
    re.compile(r"(?i)\brecommendations?\s+(?:on|for)\b[^.\n]{0,60}?\b(19|20)\d{2}\b"),
]
WINDOW = 220
YEAR = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")
REGION = re.compile(r"(?i)\b(low HIV burden|high HIV burden|low-income|middle-income|"
                    r"low- and middle-income|united states|u\.?s\.?|global|worldwide|"
                    r"sub-saharan africa|europe|africa|asia)\b")


def _excerpt(text: str, lo: int, hi: int) -> str:
    return " ".join(re.sub(r"\s+", " ", text[max(0, lo):hi]).split())


def mine(unit: dict):
    """一个 L2 单元 → (records, unresolved)。**抽不到不猜，落到 unresolved 并写明原因。**"""
    t = re.sub(r"\s+", " ", str(unit.get("text") or ""))
    if not BODY.search(t):
        return [], []
    recs, unres = [], []
    seen = set()
    for rx in CLAUSE:
        for m in rx.finditer(t):
            clause = m.group(1)
            lo, hi = max(0, m.start() - WINDOW), min(len(t), m.end() + WINDOW)
            win = t[lo:hi]
            if not BODY.search(win):            # ★ 判据①：条款号附近必须有主体词
                continue
            key = (clause, unit.get("unit_id"))
            if key in seen:
                continue
            seen.add(key)
            body = BODY.search(win).group(0)
            api = "AAP" if body.lower().startswith(("aap", "american")) else "WHO"
            years = [int(y) for y in YEAR.findall(win)]
            yr = max(years) if years else None
            reg = REGION.search(win)
            # 回指四样齐才进台账（纪律③）
            need = {"unit_id": unit.get("unit_id"), "anchor": unit.get("anchor"),
                    "source_sha256": unit.get("source_sha256"),
                    "resource_id": unit.get("resource_id")}
            miss = [k for k, v in need.items() if not v]
            if miss:
                unres.append({"unit_id": unit.get("unit_id"), "clause": clause,
                              "why": "回指不齐，缺 %s" % miss})
                continue
            rec = {"api": api, "clause": clause, "document_hint": _excerpt(t, lo, lo + 90),
                   "excerpt": _excerpt(t, lo, hi), "region": reg.group(0) if reg else None,
                   "not_before_year": yr, "**": None, **need}
            rec.pop("**", None)
            rec["extractor_version"] = "who-aap-ledger-0.1"
            rec["observed_at"] = time.strftime("%Y-%m-%d")
            if reg is None:
                unres.append({"unit_id": unit.get("unit_id"), "clause": clause,
                              "why": "**取不到适用地区** —— 留空，不用常识补"})
            if yr is None:
                unres.append({"unit_id": unit.get("unit_id"), "clause": clause,
                              "why": "**取不到生效年** —— 留空，不用常识补"})
            recs.append(rec)
    return recs, unres


def run(apply=False):
    units = [json.loads(l) for l in open(L2, encoding="utf-8") if l.strip()]
    all_r, all_u = [], []
    for u in units:
        r, x = mine(u)
        all_r += r
        all_u += x
    # 同一 (api, clause, document_hint 前 40) 去重，保留首条（回指最全的那条）
    ded, key = [], set()
    for r in all_r:
        k = (r["api"], r["clause"], r["document_hint"][:40])
        if k in key:
            continue
        key.add(k)
        ded.append(r)
    print("WHO/AAP 条款号台账（只读 L2 单元）")
    print(f"  扫单元 {len(units)}｜命中 {len(all_r)}｜去重后 **{len(ded)}** 条")
    import collections
    print("  按主体：", dict(collections.Counter(r["api"] for r in ded)))
    print("  回指齐备：", sum(1 for r in ded if r["anchor"] and r["source_sha256"]))
    print("  有地区的：", sum(1 for r in ded if r["region"]), "｜有生效年的：",
          sum(1 for r in ded if r["not_before_year"]))
    print("  未决（留空 + 写明原因）：", len(all_u))
    for x in all_u[:4]:
        print("    ·", x["why"][:64])
    if not apply:
        print("\n  [干跑] 未落盘。加 --apply 才写。")
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in ded:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    json.dump({"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "target": "10 WHO/AAP 条款号台账",
               "source": "kb/l2/units.jsonl", "entries": len(ded), "unresolved": len(all_u),
               "unresolved_detail": all_u,
               "note": "region / not_before_year 取不到一律 null —— 不许用常识补"},
              open(OUT_SUM, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n  ✅ 台账 {len(ded)} 条 → {os.path.relpath(OUT, ROOT)}")
    print(f"  ✅ 摘要 → {os.path.relpath(OUT_SUM, ROOT)}")
    return 0


def selftest():
    P, F = [], []

    def chk(n, c, e=""):
        (P if c else F).append(n)
        print("  %s %s%s" % ("✅" if c else "❌", n, ("  " + e) if e else ""))

    base = {"unit_id": "u1", "anchor": "#正文", "source_sha256": "x" * 64,
            "resource_id": "url__x"}
    # ① 真 WHO 条款（逐字取自 L2 单元 c2ff83fdd527f2afbe04）
    real = dict(base, text=("In low HIV burden settings, catch-up postpartum HIV testing can be considered. "
                            "Context-specific recommendation 2b. Adapted and integrated from the 2015 "
                            "WHO recommendations on antenatal care."))
    r, _ = mine(real)
    chk("① 真 WHO 条款 ⇒ 抽出且主体判为 WHO", bool(r) and r[0]["api"] == "WHO",
        f"clause={r[0]['clause'] if r else None}")
    chk("①b 生效年取到 2015（不是猜）", bool(r) and r[0]["not_before_year"] == 2015)
    chk("①c 适用地区取到（原文逐字）", bool(r) and (r[0]["region"] or "").lower().startswith("low hiv"))
    # ② 反向对照：育儿书的 "Section 2" **不许**进台账
    book = dict(base, text="boost your confidence as a mother or father, too. Section 2 The second half "
                           "of this book contains a breakdown of each new milestone in your baby's life.")
    chk("② 反向对照：育儿书 Section 2 ⇒ **不许**进台账", mine(book)[0] == [])
    # ③ 取不到地区/年 ⇒ 留空 + 进 unresolved（不许编）
    vague = dict(base, text="WHO recommendation 5 should be followed in all settings for infant care.")
    r3, u3 = mine(vague)
    chk("③ 取不到年份 ⇒ not_before_year 为 null 且进 unresolved",
        bool(r3) and r3[0]["not_before_year"] is None and any("生效年" in x["why"] for x in u3))
    # ④ 回指不齐 ⇒ 不许进台账
    bad = dict(real); bad["source_sha256"] = None
    r4, u4 = mine(bad)
    chk("④ 反向对照：缺 source_sha256 ⇒ 不进台账、落 unresolved",
        r4 == [] and any("回指不齐" in x["why"] for x in u4))
    print("\n反向对照：通过 %d / 失败 %d" % (len(P), len(F)))
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if F else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="WHO/AAP 条款号台账")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        print("build_who_aap_ledger · 反向对照")
        raise SystemExit(selftest())
    raise SystemExit(run(apply=a.apply))
