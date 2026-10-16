#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""链接类「变化」的性质判定：把 sha 变化拆成【动态区块噪声】与【实质正文改动】。

为什么必须拆（2026-10-08 实测）：
  链接类 71 条摘要变化里，绝大多数变的是页面上**每天自己会动**的部分 ——
  评论数/评论人、促销横幅、页脚「相关文章」推荐位轮换。
  若按「sha 变了就是有新增 ⇒ 补库」执行，会把「Up to 60% Off」「Reviews 1,845」
  当知识单元重新入库，而这类文本**明天还会变**，于是每天都要全量重跑，且可能污染 L3 措辞层。

判据（★ 这是我定的启发式，不是库里的既有规则，已在报告里如实标注）：
  · 动态区块行 —— 命中评论/促销/推荐位模式；
  · 实质改动行 —— 其余行；
  · 一条 URL：只要有 ≥1 行实质改动 ⇒ 判【实质】；否则判【仅动态区块】。
  代价：模式表可能把「真的促销文案改写」也归进动态区块（那一类**可能**是实质的，
  因为促销表述本身是 L3 措辞的来源之一）—— 所以本脚本把两类都逐行打出来，**交人裁**。

用法：
  python3 kb/l8/url_diff_nature.py <spool.jsonl> [--out report.json]
"""
import json
import os
import re
import sys
import glob
import difflib
import hashlib
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- 动态区块模式（多语言）----
NOISE = [
    (re.compile(r"\b(Reviews?|Rezensionen|Avis|Valutazioni|Reseñas|Recensioni)\s*[\d,\.]+", re.I), "评论数"),
    (re.compile(r"Basierend auf\s+[\d,\.]+\s+Rezensionen", re.I), "评论数"),
    (re.compile(r"\d{1,3}\s*%\s*(would recommend|würden|recommander)", re.I), "推荐率"),
    (re.compile(r"Was this helpful|War das hilfreich|Cela a-t-il été utile|¿Te resultó útil", re.I), "有用投票"),
    (re.compile(r"review from\s+[A-ZÄÖÜ][\w\.\- ]{0,28}\s+was helpful|avis de\s+\w+\s+était utile", re.I), "评论人"),
    (re.compile(r"people voted yes|personnes ont voté oui|Leute fanden das hilfreich", re.I), "有用投票"),
    (re.compile(r"Write a Review|Écrire un avis|Rezension schreiben|Escribir una reseña|Scrivi una recensione", re.I), "写评论入口"),
    (re.compile(r"^(Read More|Lire la suite|Weiterlesen|Leer más)\b.*review|über diese Rezension", re.I), "评论展开"),
    (re.compile(r"tab (expanded|collapsed)|onglet (élargi|réduit)|Tab (aufgeklappt|eingeklappt)|pestaña (expandida|contraída)", re.I), "评论折叠态"),
    (re.compile(r"Opens in a new tab|S'ouvre dans un nouvel onglet|neuen Tab geöffnet|nouvelle fenêtre|nueva pestaña", re.I), "评论入口注"),
    (re.compile(r"RABATT|% ?OFF|% ?Off|Off\b.*Shop Now|Sale\b|wyprzedaż|ofertas de otoño|offres d.automne|"
                r"Jetzt einkaufen|Kup teraz|Compra ahora|Shop Now|Profitez-en|Mix ?& ?Match|"
                r"Care Event|Big Sale|Autumn|Herbst|Spring", re.I), "促销横幅"),
]
# 页脚「相关文章/推荐位」：在 ≥5 条 URL 上同时出现的新增行（正文标题题面）
FOOTER_TITLES = {
    "Breast Engorgement Relief: Why Common Remedies Sometimes Make It Worse",
    "Bottle Warmer Routines for Combo-Fed Babies: Separate Cycles, Shared Safety Checks",
    "Why the Same Bottle-Warmer Setting Heats Cold Storage Breast Milk Differently From Fresh Milk",
    "Cold Compression vs Heated Massager for Engorgement and Ductal Narrowing",
    "What Makes a Nursing Pillow Non-Toxic? How to Evaluate Materials, Certifications & Product Claims",
    "Using a Nursing Pillow With a Reflux Baby: The Safe Answer on Elevation Angles",
    "Firm vs Plush Nursing Pillow: Positioning Support in the First 6 Weeks",
    "How to Pump During Chemotherapy or Medication Windows: A Safe, Drug-Specific Discard Plan",
}
FOOTER = re.compile(r"^(Read More|Lire la suite)\b")


def why_noise(line):
    if line in FOOTER_TITLES:
        return "页脚推荐位"
    for rx, tag in NOISE:
        if rx.search(line):
            return tag
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    spool = sys.argv[1]
    out_p = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None

    got = {}
    for line in open(spool, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            got[r["key"]] = r

    cur = {}
    for line in open(os.path.join(ROOT, "kb/l0/manifest.jsonl"), encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            if r.get("source_kind") == "url":
                cur[r["resource_key"]] = r

    arts = {}
    for p in glob.glob(os.path.join(ROOT, "kb/l1/*/url__*.json")):
        try:
            a = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if a.get("resource_key") and a.get("segments"):
            arts[a["resource_key"]] = a

    real, dyn, nocmp = [], [], []
    tagc = collections.Counter()
    for k, r in sorted(cur.items()):
        g = got.get(k)
        if not g or int(g.get("chars") or 0) < 300:
            continue
        if r.get("sha256_input") != "url_text_rendered_v1":
            nocmp.append({"key": k, "why": f"口径 {r.get('sha256_input')}"})
            continue
        if hashlib.sha256(g["text"].encode()).hexdigest() == r.get("sha256"):
            continue
        a = arts.get(k)
        if not a:
            nocmp.append({"key": k, "why": "无 L1 归档可比对"})
            continue
        old = "".join(s["text"] for s in a["segments"])
        o, n = old.split("\n"), g["text"].split("\n")
        sm = difflib.SequenceMatcher(None, o, n, autojunk=False)
        adds, dels = [], []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("replace", "delete"):
                dels += o[i1:i2]
            if tag in ("replace", "insert"):
                adds += n[j1:j2]
        ra, rd, na, nd = [], [], [], []
        for x in adds:
            (na if why_noise(x) else ra).append(x)
        for x in dels:
            (nd if why_noise(x) else rd).append(x)
        for x in na:
            tagc[why_noise(x)] += 1
        for x in nd:
            tagc[why_noise(x)] += 1
        ent = {"key": k, "url": k.split(":", 1)[1],
               "delta_chars": len(g["text"]) - len(old),
               "real_add": ra, "real_del": rd,
               "noise_add": len(na), "noise_del": len(nd)}
        (real if (ra or rd) else dyn).append(ent)

    print("=" * 78)
    print("链接类「变化」性质判定")
    print(f"  可比且摘要变了：{len(real)+len(dyn)} 条  ⇒  实质 {len(real)} / 仅动态区块 {len(dyn)}")
    print(f"  动态区块行命中分布：{dict(tagc)}")
    print(f"  不可判（口径不同/无归档）：{len(nocmp)} 条")
    print("=" * 78)

    print(f"\n【仅动态区块·正文实质零改动】{len(dyn)} 条  ← 这些不是「有新增」")
    for e in sorted(dyn, key=lambda x: x["url"]):
        print(f"   {e['delta_chars']:+5d}字  噪声行 +{e['noise_add']}/-{e['noise_del']}  {e['url'][:74]}")

    print(f"\n【实质改动】{len(real)} 条  ← 这些才该按「有新增就补充」处理")
    for e in sorted(real, key=lambda x: -len(x["real_add"]) - len(x["real_del"])):
        print(f"\n  {e['url']}")
        print(f"     实质行 +{len(e['real_add'])}/-{len(e['real_del'])}  噪声行 +{e['noise_add']}/-{e['noise_del']}  Δ{e['delta_chars']:+d}字")
        for x in e["real_add"][:6]:
            print(f"       + {x[:150]}")
        for x in e["real_del"][:6]:
            print(f"       - {x[:150]}")

    if out_p:
        tmp = out_p + ".swtmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"real": real, "dynamic_only": dyn, "not_comparable": nocmp,
                       "noise_tags": dict(tagc)}, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, out_p)
        print(f"\n报告已落盘：{out_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
