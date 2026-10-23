#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_attribution_gate.py —— 「串图」闸门（2026-10-20）

## 守什么

用户发一张 **Giveaway 长图**给守衡，回来的依据是「N-1.39 → record=recvwC9IMVHb0Q」；
点开那条记录，看到的是**美国 BJs 渠道图**。根因不是同图判据，而是**归属**：
这张图只是那条记录的**附图**（该记录 4 张图里 2 张是它、还重复挂了两次），
而且同一张图还挂在另外 2 条**内容完全不同**的记录里（Costco 套装 / 品牌日 banner）。

⇒ 本闸门守两条：

  A. **串图单不许再出「这张图的依据」**：那张图的命中必须全部落在 `not_subject`
     （`shared_reference` / `record_level` / `unknown`），且**带齐回源坐标**
     （record_id + file_token + image_sha256 + image_anchor）—— 不静默丢；
     没有别的 findings 时结论必须是**拒答（覆盖缺口）**，**不许落 PASS**。
  B. **不许一刀切清空**（反向对照）：一条「单图独占记录」的图仍然要能作为依据
     （`attribution == subject`；引擎端仍出 findings）。

## 用法

    python3 kb/l8/check_attribution_gate.py              # 判据级（快，<2s）
    python3 kb/l8/check_attribution_gate.py --engine     # 再加端到端（各跑一次引擎，约 20~40s）
    python3 kb/l8/check_attribution_gate.py --selftest   # 反向对照：把产物弄坏 ⇒ 必须变红

退出码：0 全绿 / 3 有红。
"""
import json
import os
import subprocess
import sys
import tempfile
import importlib.util

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
ROLES = os.path.join(KB, "l3", "registry", "image_roles.json")
RULES = os.path.join(KB, "l3", "candidates", "negative_rules.jsonl")
REVIEW = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts", "review.py")

# Giveaway 长图（真单素材的 OCR，IM 压缩版；20261020-154622）
GIVEAWAY_OCR = """MOmCOZY
Momcozy Mom and More
Your Chance To Min
A Momcozy W1
Wearable Breast Pump
Giveaway 4
Join the Momcozy Fans Club
for weekly rewards and real
nom support.
Easy to Join.
Rewards to Win.
comment. pksy. or tharea post
fc chirv.es c win wecky rewrds
Real Moms. Real Support.
from moms whove been there too，
How to enter
1.Join the group
ioin tho Momcory Fara Chb
2.Find the featured post
soction at the top cfthe Facobook group
3.Enter the giveaway
Find the #MamAndMare giveanay Poot
and folkow the instructions to onter.
Already a member？
giveaway post
cin & Hind tne owiww.y
Wherever you are in motherhood，
there's a place for you here.
Jon other moms、
"""


def _nrm():
    spec = importlib.util.spec_from_file_location(
        "_nrm_gate", os.path.join(KB, "l8", "negative_rule_match.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _roles_for(rec_id):
    d = json.load(open(ROLES, encoding="utf-8"))
    return d


def _subject_sample():
    """挑一条「单图独占」记录，返回它的图内文字（反向对照用）。"""
    d = json.load(open(ROLES, encoding="utf-8"))
    rules = [json.loads(l) for l in open(RULES, encoding="utf-8") if l.strip()]
    ocr_by_tok = {}
    for r in rules:
        for im in (r.get("image_refs") or []):
            t = im.get("ocr_text") or ""
            if t and len(t) > 40:
                ocr_by_tok.setdefault(im.get("file_token"), t)
    for rid, p in d["records"].items():
        for im in p.get("images") or []:
            if im.get("role") == "subject" and ocr_by_tok.get(im.get("token")):
                return rid, im, ocr_by_tok[im["token"]]
    return None, None, None


def judge_level():
    """判据级：不跑引擎，只看匹配层给的归属。"""
    nrm = _nrm()
    rules = nrm.load_rules(RULES)
    cases = []

    hits = nrm.match(GIVEAWAY_OCR, None, top=8, min_score=0.45, rules=rules)
    attrs = [h.get("attribution") for h in hits]
    cases.append(("A1 串图单：命中不为空（同图判据仍然要认得出这张图）", len(hits) >= 1, attrs[:6]))
    cases.append(("A1 串图单：**没有一条**是 subject",
                  bool(hits) and all(a != "subject" for a in attrs), attrs[:6]))
    cases.append(("A1 串图单：至少一条 shared_reference，且理由点名 ≥2 条记录",
                  any(a == "shared_reference" and "内容不同" in (h.get("attribution_why") or "")
                      for h, a in zip(hits, attrs)),
                  [(h.get("article_no"), h.get("attribution_why", "")[:40]) for h in hits][:3]))
    mi_ok = []
    for h in hits:
        mi = h.get("matched_image") or {}
        mi_ok.append(bool(mi.get("record_id") and mi.get("file_token")
                          and mi.get("sha256") and mi.get("anchor")))
    cases.append(("A1 串图单：每条命中都带齐回源坐标（record/token/sha/anchor）",
                  bool(hits) and all(mi_ok), mi_ok[:6]))
    cases.append(("A1 串图单：命中的记录就是真单里那三条之一（可回源）",
                  any((h.get("matched_image") or {}).get("record_id") == "recvwC9IMVHb0Q" for h in hits),
                  [(h.get("matched_image") or {}).get("record_id") for h in hits][:4]))

    rid, im, ocr = _subject_sample()
    cases.append(("B0 反向对照样本存在（库里至少还有一条单图独占记录）", bool(rid), rid))
    if rid:
        h2 = nrm.match(ocr, None, top=8, min_score=0.45, rules=rules)
        a2 = [h.get("attribution") for h in h2]
        cases.append(("B1 反向对照：单图独占记录的图 ⇒ 有 subject 命中（不许一刀切清空）",
                      any(a == "subject" for a in a2), a2[:6]))
        cases.append(("B1 反向对照：命中的那条记录就是该图所属记录",
                      any(h.get("attribution") == "subject"
                          and (h.get("matched_image") or {}).get("record_id") == rid for h in h2),
                      [(h.get("article_no"), (h.get("matched_image") or {}).get("record_id")) for h in h2][:4]))

    # C：产物缺失 ⇒ 不门控（`no_roles_artifact`），且**不许**把整层判成不可引用
    saved = nrm._ROLES_CACHE
    try:
        nrm._ROLES_CACHE = {"records": {}, "sha": {}, "stats": {}, "missing": True}
        a3 = [h.get("attribution") for h in nrm.match(GIVEAWAY_OCR, None, top=4, min_score=0.45, rules=rules)]
    finally:
        nrm._ROLES_CACHE = saved
    cases.append(("C 产物缺失 ⇒ no_roles_artifact（不门控、不静默清空）",
                  bool(a3) and all(a == "no_roles_artifact" for a in a3), a3[:4]))
    return cases


def engine_state(text, content_type="image"):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        p = fh.name
    try:
        out = subprocess.run([sys.executable, REVIEW, "--i-am-the-entry", "--file", p,
                              "--content-type", content_type, "--json"],
                             cwd=ROOT, capture_output=True, text=True, timeout=300)
        raw = out.stdout
        i = raw.find("{")
        if i < 0:
            return {"state": "ERR", "raw": (raw + out.stderr)[-400:]}
        d = json.loads(raw[i:])
        tr = d.get("trace") or {}
        return {"state": d.get("state"), "findings": len(d.get("findings") or []),
                "covered": (tr.get("coverage") or {}).get("covered"),
                "gap": (tr.get("coverage") or {}).get("coverage_gap"),
                "not_subject": ((tr.get("negative_rules") or {}).get("not_subject_count") or 0)}
    finally:
        os.unlink(p)


def engine_level():
    cases = []
    a = engine_state(GIVEAWAY_OCR)
    cases.append(("A2 引擎端（串图单）：结论 = 拒答（覆盖缺口），不许 PASS",
                  a.get("state") == "拒答", a))
    cases.append(("A2 引擎端（串图单）：0 findings，且 coverage_gap=True",
                  a.get("findings") == 0 and a.get("gap") is True, a))
    cases.append(("A2 引擎端（串图单）：not_subject 有留痕（不静默丢）",
                  (a.get("not_subject") or 0) >= 1, a))
    rid, im, ocr = _subject_sample()
    if rid:
        b = engine_state(ocr)
        cases.append(("B2 引擎端（反向对照）：单图独占记录仍能出 findings",
                      (b.get("findings") or 0) >= 1, b))
    return cases


def selftest():
    """反向对照：**把产物真弄坏一遍**，尺子必须精确变红。"""
    cases = []
    bad = {"records": {"recvwC9IMVHb0Q": {"record_id": "recvwC9IMVHb0Q", "n_dedup": 1,
                                         "content_key": "x", "images": [
                                             {"sha256": "b9328ba2c5ce138554ac5f2a49193b83fa4f26b84e19bd2dba04dffeae55fbe1",
                                              "file_token": "L8BYbsBa7ormvYxvsbacA6hMnfg",
                                              "anchor": "#素材/recvwC9IMVHb0Q/图片素材/#img.1",
                                              "role": "subject", "why": "（故意弄坏：把它标成 subject）"}]}},
           "sha": {"b9328ba2c5ce138554ac5f2a49193b83fa4f26b84e19bd2dba04dffeae55fbe1": "subject"},
           "stats": {}}
    nrm = _nrm()
    saved = nrm._ROLES_CACHE
    try:
        nrm._ROLES_CACHE = bad
        hits = nrm.match(GIVEAWAY_OCR, None, top=8, min_score=0.45, rules=nrm.load_rules(RULES))
        got_subject = any(h.get("attribution") == "subject" for h in hits)
    finally:
        nrm._ROLES_CACHE = saved
    cases.append(("变异自证：把那张图人为标成 subject ⇒ 归属判据必须立刻跟着变（证明闸门真的在读产物）",
                  got_subject, [h.get("attribution") for h in hits][:6]))
    cases.append(("变异自证：恢复真产物后，同图单又回到非 subject（证明读数来自文件，不是常量）",
                  all(h.get("attribution") != "subject"
                      for h in nrm.match(GIVEAWAY_OCR, None, top=8, min_score=0.45,
                                         rules=nrm.load_rules(RULES))), None))
    ok = all(c[1] for c in cases)
    for name, okc, detail in cases:
        print(("  ✅ " if okc else "  ❌ ") + name + ("" if okc else "  ← " + str(detail)))
    print("check_attribution_gate --selftest %s（%d/%d）"
          % ("PASS" if ok else "FAIL", sum(1 for c in cases if c[1]), len(cases)))
    return 0 if ok else 3


def main(argv):
    if "--selftest" in argv:
        return selftest()
    cases = judge_level()
    if "--engine" in argv:
        cases += engine_level()
    ok = all(c[1] for c in cases)
    for name, okc, detail in cases:
        print(("  ✅ " if okc else "  ❌ ") + name + ("" if okc else "  ← " + str(detail)[:300]))
    print("check_attribution_gate %s（%d/%d）%s"
          % ("PASS" if ok else "FAIL", sum(1 for c in cases if c[1]), len(cases),
             "" if "--engine" in argv else "（未跑引擎端；加 --engine）"))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
