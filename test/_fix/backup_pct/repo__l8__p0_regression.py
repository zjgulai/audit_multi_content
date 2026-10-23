#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""p0_regression.py —— P0 层**定期回归测试**（PRD §16 应对后半句）。

## 出处（逐字）

· PRD §16 风险与依赖，风险「**P0 规则误配**」→ 影响「红线漏放或误伤」→ 应对
  「P0 规则上线前由法务逐条确认；**P0 层定期回归测试**」。
  （前半 = 目标 18，已交付台账 `kb/l5/registry/p0-legal-signoff-ledger.jsonl`；**本件是后半**。）
· PRD §11.3：「**P0 层漏报率 = P0 规则应命中但未命中的数量 / P0 规则应命中总数（目标为 0）**」
· PRD §15 验收标准「准确率」行逐字含「**P0 层漏报率 = 0**」—— 这是**上线判定表里的一格**。

## 为什么需要它（正则是确定的，但会被人改坏）

11 条 P0 模式是确定性正则，**正则不会自己坏**；但改模式表、改词表、改 `rule_code→article_no`
接线，任何一次都可能让某条红线**静默不命中** —— 而 P0 漏放的后果是**红线直接发出去**。
现存的 `p0_fastpath.py --selftest` 证明的是「**判据不是恒真**」（自证），
**没有任何东西定期证明「这 11 条对真实的红线表达仍然命中」**。本件补的就是这一格。

## ★ 用例从哪来（**不自己编**）

每条模式的 `match_terms` 里带 `basis="verbatim_source"` 的 `term` —— 那是**逐字取自 L0 源记录**
的红线表达（不是我们造的例句）。本件**只取这些**；`basis` 不是 `verbatim_source` 的一律不用。

## ★ 本件只观测、不参与判定

回归测试**不改 P0 快路的行为**，也不被快路调用 —— 它与 `trace.perf` 同一种做法：
**观测不许影响被测对象**。

## 用法

    python3 kb/l8/p0_regression.py            # 跑回归（真调 P0 引擎，只读）
    python3 kb/l8/p0_regression.py --selftest # 自证（含反向对照与变异测试）
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
ROOT = os.path.dirname(KB)
PATTERNS = os.path.join(KB, "l5/p0_patterns.jsonl")
P0FP = os.path.join(KB, "l5/p0_fastpath.py")

#: PRD §15：P0 层漏报率必须为 0
MISS_LIMIT = 0

#: 反向对照用的无关文本（**不许**命中任何 P0 模式）
NEGATIVE = "今天天气不错，我们去公园走走吧。"


def _p0():
    """真调 P0 引擎（**不重写第二份匹配逻辑** —— 判据必须与被测对象同一把尺子）。"""
    spec = importlib.util.spec_from_file_location("p0fp", P0FP)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def positive_cases(patterns_path=PATTERNS):
    """每条的 `verbatim_source` 正例。**basis 不是 verbatim_source 的一律不用。**"""
    pats = [json.loads(l) for l in io.open(patterns_path, encoding="utf-8") if l.strip()]
    out = []
    for p in pats:
        terms = []
        for t in (p.get("match_terms") or []):
            if not isinstance(t, dict):
                continue
            # ★ 2026-10-21：`verbatim_rule_text` 也收 —— 它们**逐字取自规则自己的边界/处理字段**
            #   （如 H03 的边界表述「未经备案的临床/科学背书」，源字段「边界内容」），
            #   同样属于「P0 规则应命中」；不收的话这类新增词**永远没有回归守着**。
            #   实测（宽化前）：19 条 verbatim_rule_text 词 **19/19 命中** ⇒ 不引入假红。
            if (t.get("basis") or "") not in ("verbatim_source", "verbatim_rule_text"):
                continue
            term = (t.get("term") or "").strip()
            if term:
                terms.append(term)
        out.append({"rule_code": p.get("rule_code"), "rule_id": p.get("rule_id"),
                    "article_no": p.get("article_no"), "terms": terms})
    return out


def codes_of(res):
    """从引擎返回里取命中的模式标识集合。**取不到键就报出来，不许静默当 0 命中。**"""
    fs = res.get("findings")
    if fs is None:
        # ★ 引擎契约（见 `evaluate` docstring）：「`hit=false` 时只有 mode/elapsed」——
        #   所以 findings 缺失时，**要看 hit**：hit=false ⇒ 那是「确实没命中」⇒ 空集（正常）；
        #   只有 hit=true 却拿不到 findings，才算解析口径变了（engine_odd）。
        #   ⚠️ 我第一版把两者都当成 None ⇒ 反向对照被读成"读不到"，判据**假红**。
        return set() if not res.get("hit") else None
    s = set()
    for f in fs:
        if isinstance(f, dict):
            s.add(f.get("rule_code") or f.get("pattern_id"))
    return s


def regression(patterns_path=PATTERNS, p0mod=None):
    m = p0mod or _p0()
    cases = positive_cases(patterns_path)
    per, total, missed, no_case, engine_odd = [], 0, 0, [], []
    for c in cases:
        if not c["terms"]:
            no_case.append(c["rule_code"])
            continue
        ok = 0
        for term in c["terms"]:
            total += 1
            res = m.evaluate(term)
            codes = codes_of(res)
            if codes is None:
                engine_odd.append(term)
                continue
            if c["rule_code"] in codes:
                ok += 1
            else:
                missed += 1
        per.append({"rule_code": c["rule_code"], "article_no": c["article_no"],
                    "cases": len(c["terms"]), "hit": ok})
    # 反向对照：无关文本不许命中
    neg_res = m.evaluate(NEGATIVE)
    neg_codes = codes_of(neg_res)
    return {"patterns": len(cases), "total_cases": total, "hit": total - missed, "missed": missed,
            "no_case": no_case, "engine_odd": engine_odd, "per": per,
            "neg_hit": (None if neg_codes is None else len(neg_codes)),
            "miss_rate": (missed / total) if total else None}


def run():
    print("P0 层定期回归测试 —— PRD §16「P0 层定期回归测试」/ §15「P0 层漏报率 = 0」")
    print("★ 用例 = 每条模式的 `match_terms` 里 basis=verbatim_source / verbatim_rule_text 的"
          "**逐字源表达**（不自己编；后者=规则自己的边界/处理字段，2026-10-21 起纳入）\n")
    r = regression()
    for x in r["per"]:
        flag = "✅" if x["hit"] == x["cases"] else "❌"
        print("  %s %-4s %-8s 正例 %2d ｜ 命中 %2d" % (flag, x["rule_code"], x["article_no"] or "-",
                                                     x["cases"], x["hit"]))
    if r["no_case"]:
        print("  ⚠️ **没有正例**的模式 %d 条：%s —— 它们**没有被回归覆盖**（不是通过！）"
              % (len(r["no_case"]), r["no_case"]))
    if r["engine_odd"]:
        print("  ⚠️ 引擎返回里取不到 findings 的用例 %d 条 —— 解析口径可能变了" % len(r["engine_odd"]))
    print("\n用例总数 %d ｜ 命中 %d ｜ **未命中 %d** ｜ 漏报率 %s"
          % (r["total_cases"], r["hit"], r["missed"],
             ("%.4f" % r["miss_rate"]) if r["miss_rate"] is not None else "—"))
    print("反向对照（无关文本）：命中 %s（必须是 0）" % r["neg_hit"])
    ok = (r["missed"] <= MISS_LIMIT and r["neg_hit"] == 0 and not r["no_case"] and not r["engine_odd"])
    print("结论：%s" % ("✅ 通过 —— 11 条红线对逐字源表达**全部仍命中**，漏报率 0"
                       if ok else
                       "❌ **未通过** —— 见上面逐条：未命中 %d ／ 无正例 %d ／ 无关文本误命中 %s"
                       % (r["missed"], len(r["no_case"]), r["neg_hit"])))
    if not ok:
        print("   ⚠️ 这是**红线漏放**方向的问题：先查是不是模式表/词表/article_no 接线被动过。")
    return 0 if ok else 3


def selftest():
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    m = _p0()
    r = regression(p0mod=m)
    ck("① 11 条模式全部被回归覆盖（无「无正例」的空档）", not r["no_case"] and not r["engine_odd"],
       "no_case=%s odd=%d" % (r["no_case"], len(r["engine_odd"])))
    ck("①b 用例数 > 0（挡住「一条用例都没取到」的假绿）", r["total_cases"] > 0, "n=%d" % r["total_cases"])
    ck("② 逐字源表达全部命中（漏报率 0）", r["missed"] == 0,
       "missed=%d / %d" % (r["missed"], r["total_cases"]))
    ck("③ 反向对照：无关文本**不许命中**（判据不是恒真）", r["neg_hit"] == 0, "neg_hit=%s" % r["neg_hit"])
    # ④ 变异测试：把一条正例**改坏**（加一个不该命中的词）⇒ 判据必须精确变红
    import tempfile
    pats = [json.loads(l) for l in io.open(PATTERNS, encoding="utf-8") if l.strip()]
    first = pats[0]
    terms = [t for t in (first.get("match_terms") or [])
             if isinstance(t, dict) and t.get("basis") == "verbatim_source" and t.get("term")]
    ck("④ 前置：第 1 条模式确有正例可改", bool(terms), "terms=%d" % len(terms))
    if terms:
        bad = json.loads(json.dumps(first))
        orig = terms[0]["term"]
        bad["match_terms"] = [{"term": "zzz-这条已改坏-zzz", "basis": "verbatim_source"}]
        tmp = tempfile.mkdtemp(prefix="p0reg-")
        fp = os.path.join(tmp, "p.jsonl")
        io.open(fp, "w", encoding="utf-8").write(
            json.dumps(bad, ensure_ascii=False) + "\n" +
            "\n".join(json.dumps(p, ensure_ascii=False) for p in pats[1:]) + "\n")
        r2 = regression(fp, p0mod=m)
        ck("⑤ 变异测试：把第 1 条的正例改坏 ⇒ 判据**精确变红**（missed>0）", r2["missed"] > 0,
           "missed=%d" % r2["missed"])
        # ⑥ 反向对照：把正例抽掉（basis 改成非 verbatim_source）⇒ 该条进 no_case，**不许算通过**
        bad2 = json.loads(json.dumps(first))
        bad2["match_terms"] = [{"term": orig, "basis": "not_verbatim"}]
        fp2 = os.path.join(tmp, "p2.jsonl")
        io.open(fp2, "w", encoding="utf-8").write(
            json.dumps(bad2, ensure_ascii=False) + "\n" +
            "\n".join(json.dumps(p, ensure_ascii=False) for p in pats[1:]) + "\n")
        r3 = regression(fp2, p0mod=m)
        ck("⑥ 反向对照：非逐字源表达**不当正例**（该条落 no_case，不许静默通过）",
           r3["no_case"] == [first.get("rule_code")], "no_case=%s" % r3["no_case"])
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print("p0_regression --selftest（PRD §16 后半）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + str(ex)) if ex else ""))
    bad_n = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad_n, len(res), "" if not bad_n else "  ← 有失败"))
    return 1 if bad_n else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run())
