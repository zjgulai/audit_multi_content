#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正文口径：从整页渲染文本里剔除「页面自己每天会动」的区块，供 sha 只反映正文。

背景（Owner 2026-10-08 批准口径①）：
  链接类走的是「整页渲染取文本」，于是 sha 把**评论数/评论人、促销横幅、价格与配送时效、
  页脚相关文章推荐位**都算进去了 ⇒ 「数据一样就保留」机械上永不成立：实测 145 页里 71 页
  摘要变了，而剥开看绝大多数正文一字未动。

判据（**这是启发式，不是库里的既有规则**；所以每条都留痕、可复核、可回退）：
  · `WIDGET`  评论组件脚手架：评论数、推荐率、有用投票、写评论入口、折叠态、评论展开
  · `PROMO`   促销横幅：同一行里**同时**出现促销词与折扣/行动号召（避免把讲「autumn」的正文误删）
  · `PRICE`   价格与配送时效：货币金额、Order within、delivery <weekday>、Member price
  · `REVIEW`  评论正文：**不做通用正则**（那是自由文本）——只按**站点级块表**逐字命中才删
  · `FOOTER`  页脚推荐位：同上，只按站点级块表逐字命中才删

★ 诚实的边界（不许当成「噪声全清干净了」）：
  REVIEW / FOOTER 这两类**没有通用判据**。块表是**实测导出**的：把跨页高频行挑出来存进
  `kb/l8/body_blocks.json`（带版本号，参与口径命名）。站点轮换推荐位后，新标题**不在表里
  ⇒ 会被当正文 ⇒ sha 仍会变**。那是已知缺口，靠「重导块表」收敛，不靠正则假装解决。

用法：
    python3 kb/l8/body_only.py --selftest
    python3 kb/l8/body_only.py <spool.jsonl> [--report out.json]     # 在真实抓取上量化
"""
import json
import os
import re
import sys
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOCKS = os.path.join(ROOT, "kb/l8/body_blocks.json")
CALIBER = "url_text_rendered_v2_bodyonly"

# ---- ① 评论组件脚手架（多语言）----
WIDGET = [
    # 不锚行尾：该行常是 "Reviews 1,845 (tab expanded) Questions 6 (tab collapsed)"
    (re.compile(r"^\s*(Reviews?|Rezensionen|Avis|Valutazioni|Reseñas|Recensioni|Opiniones)\s*[\(\[]?\s*[\d.,]{1,12}\b", re.I), "评论数"),
    (re.compile(r"\(\s*(tab|onglet|Tab|pestaña)\s+(expanded|collapsed|élargi|réduit|aufgeklappt|eingeklappt|expandida|contraída)\s*\)", re.I), "折叠态"),
    (re.compile(r"^\s*[\d.,]+\s*%?\s*(would recommend|würden|recommander|lo recomiendan)", re.I), "推荐率"),
    (re.compile(r"^\s*Basierend auf\s+[\d.,]+\s+Rezensionen", re.I), "评论数"),
    (re.compile(r"^\s*(Was this helpful|War das hilfreich|Cela a-t-il été utile|¿Te resultó útil|"
                r"È stato utile)", re.I), "有用投票"),
    (re.compile(r"review from\s+.{1,40}\s+was helpful|avis de\s+\S+\s+était utile|"
                r"Rezension von\s+.{1,40}\s+war hilfreich", re.I), "评论人"),
    (re.compile(r"\b(people voted yes|personnes ont voté oui|Leute fanden das hilfreich|"
                r"personas encontraron esto útil)", re.I), "有用投票"),
    (re.compile(r"^\s*(Write a Review|Écrire un avis|Rezension schreiben|Escribir una reseña|"
                r"Scrivi una recensione)\b", re.I), "写评论入口"),
    (re.compile(r"^\s*(Read More|Lire la suite|Weiterlesen|Leer más)\b.*(review|Rezension|avis|reseña)",
                re.I), "评论展开"),
    (re.compile(r"^\s*(Noch nicht ausprobiert|Ich wei\? es noch nicht)", re.I), "评论壳"),
]
# ---- ② 促销横幅：必须同时有「促销词」与「折扣/行动」两个信号 ----
PROMO_HINT = re.compile(r"(\d{1,2}\s*%|%\s*(off|OFF|rabatt|RABATT)|\b(sale|Sale|SALE|deal|Deal|"
                        r"rabatt|RABATT|wyprzedaż|ofertas|offres|promo)\b)", re.I)
PROMO_ACT = re.compile(r"(shop now|kup teraz|compra ahora|acheter|jetzt einkaufen|profitez|"
                       r"mix\s*&\s*match|code\b|save\s+\d|bis zu|hasta|jusqu|up to)", re.I)
# ---- ③ 价格与配送时效 ----
PRICE = [
    (re.compile(r"^\s*(HKD|USD|US\$|\$|€|£|CDN\$|AUD\$|PLN|zł)\s?[\d.,]+\s*(/\s*\w+)?\s*$"), "价格"),
    # 单价行：形如 "HKD1,921.23 HKD 1,921 . 23 (HKD 1,921.23/count)" ——
    # 用「剥掉货币/数字/单位后剩不下几个字母」判，比反引用稳（实测反引用版漏判）
    (re.compile(r"^\s*(?:[A-Z]{2,3}\$?|US\$|[$€£¥])\s?[\d.,\s]+(?:\([^)]*\))?\s*$"), "单价"),
    (re.compile(r"Order within\s+\d+\s*hrs?\s*\d*\s*mins?", re.I), "配送倒计时"),
    (re.compile(r"(delivery|Lieferung|livraison|entrega)\s+(on\s+)?(Monday|Tuesday|Wednesday|Thursday|"
                r"Friday|Saturday|Sunday|Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)",
                re.I), "配送日"),
    (re.compile(r"Member price\b|From\s+\$[\d.,]+\s+Code\b", re.I), "会员价"),
    (re.compile(r"^\s*\{\s*\"desktop_buybox_group_1\"", re.I), "购买框 JSON"),
    (re.compile(r"^\s*[\d.,]+\s+in\s+(Baby Products|Kitchen|Health)\b", re.I), "类目排名"),
]
# ---- ④ 跨页高频的页脚推荐位 / 评论正文 —— 只按块表逐字命中 ----
_BLOCK_CACHE = None


def load_blocks():
    global _BLOCK_CACHE
    if _BLOCK_CACHE is None:
        try:
            d = json.load(open(BLOCKS, encoding="utf-8"))
        except Exception:
            d = {"version": "none", "exact": {}, "regex": []}
        _BLOCK_CACHE = (d.get("version") or "none",
                        set(d.get("exact") or []),
                        [re.compile(p) for p in (d.get("regex") or [])])
    return _BLOCK_CACHE


def blocks_version():
    return load_blocks()[0]


_PRICEY = re.compile(r"(HKD|USD|EUR|GBP|CAD|AUD|PLN|US\$|[$€£¥]|/\s*(count|stuk|pièce|Stück|pack|pcs))", re.I)
_WORDY = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


def _looks_price_only(s):
    """整行剥掉货币/数字/括号/单位后，剩下的成词字母 < 3 个 ⇒ 判价格行。

    比逐条写货币正则稳：实测 `HKD1,921.23 HKD 1,921 . 23 (HKD 1,921.23/count)` 这种
    被拆散的价格行，反引用版会漏。判据只看「还剩多少词」，与币种无关。
    """
    if not _PRICEY.search(s):
        return False
    rest = _PRICEY.sub(" ", s)
    rest = re.sub(r"[\d.,;:()\[\]/|\-–—+%*\s]+", " ", rest)
    return len(_WORDY.findall(rest)) < 3


_SENT_END = re.compile(r"[.。]\s*$")


def _looks_sentence(s):
    """整句以句号收尾、且成词 ≥ 6 个 ⇒ 判**正文句子**，不判横幅。

    为什么需要（实测反例）：`Save 30% when you buy two pumps together this week.`
    带 `30%` 与 `save` 两个促销信号，会被横幅规则误删 —— 但它是一条**正文**，
    而促销表述恰恰是文案合规审查要看的对象，删掉就是把该审的东西藏起来。
    横幅（`🔥 Autumn Sale: Up to 60% Off Shop Now`）不以句号收尾。
    ⚠️ 代价：以 `!` 收尾的**正文**句仍会被当横幅（已知，未修）。
    """
    return bool(_SENT_END.search(s)) and len(_WORDY.findall(s)) >= 6


def classify(line):
    """返回命中原因，未命中返回 None。"""
    s = line.strip()
    if not s:
        return None
    for rx, why in WIDGET:
        if rx.search(s):
            return f"WIDGET/{why}"
    for rx, why in PRICE:
        if rx.search(s):
            return f"PRICE/{why}"
    if _looks_price_only(s):
        return "PRICE/价格行"
    if PROMO_HINT.search(s) and PROMO_ACT.search(s) and not _looks_sentence(s):
        return "PROMO/横幅"
    _v, exact, regexes = load_blocks()
    if s in exact:
        return "BLOCK/站点块表"
    for rx in regexes:
        if rx.search(s):
            return "BLOCK/站点正则"
    return None


def body_only(text):
    """返回 (正文, 统计)。剔除行不进正文；其余原样、原序保留。"""
    kept, dropped = [], collections.Counter()
    for line in (text or "").split("\n"):
        why = classify(line)
        if why:
            dropped[why] += 1
        else:
            kept.append(line)
    return "\n".join(kept), dict(dropped)


def _selftest():
    ok = bad = 0
    cases = [
        # (行, 期望是否算噪声)
        ("Reviews 1,845 (tab expanded) Questions 6 (tab collapsed)", True),
        ("Reviews 1,840", True),
        ("89% would recommend this product", True),
        ("Was this helpful? Yes, this review from Crystal was helpful. 0 people voted yes", True),
        ("Write a Review (Opens in a new tab)", True),
        ("Read More Read more about this review", True),
        ("HKD 185.28 delivery Tuesday, 13 October . Order within 3 hrs 44 mins", True),
        ("HKD1,921.23 HKD 1,921 . 23 (HKD 1,921.23/count)", True),
        ("Member price From $329.99 Code Save 30%", True),
        ("🔥 Autumn Sale: Up to 60% Off Shop Now", True),
        ("🎊Jesienna wyprzedaż do -60% Kup teraz", True),
        ("Basierend auf 1,842 Rezensionen", True),
        ("1,832 in Baby Products ( See Top 100 in Baby Products )", True),
        # 不该被删（正文）
        ("How to Choose a Stroller During the First Six Weeks After a C-Section", False),
        ("The information provided in this article is for general informational purposes only and does not "
         "constitute medical advice, diagnosis, or treatment.", False),
        ("Its main advantage is a 30% smaller motor while keeping the same suction.", False),
        ("Momcozy M5 Smart is the everyday wearable breast pump for most UK mums.", False),
        ("We tested this in autumn 2026 across 12 households.", False),
        ("A wearable breast pump sits in your bra so you can keep moving.", False),
        ("Momcozy M5 costs $199.99 and ships free in the US.", False),
        ("Save 30% when you buy two pumps together this week.", False),
    ]
    for s, want_noise in cases:
        got = classify(s) is not None
        if got == want_noise:
            ok += 1
        else:
            bad += 1
            print(f"   ✗ {'应删' if want_noise else '应留'}：{s[:80]}")
    print(f"自证：通过 {ok} / 失败 {bad}")
    return 0 if bad == 0 else 1


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    spool = sys.argv[1]
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
    import hashlib
    same = changed = 0
    was_changed = 0
    drop = collections.Counter()
    rows = []
    for k, r in cur.items():
        g = got.get(k)
        if not g or int(g.get("chars") or 0) < 300:
            continue
        if r.get("sha256_input") != "url_text_rendered_v1":
            continue
        if hashlib.sha256(g["text"].encode()).hexdigest() != r.get("sha256"):
            was_changed += 1
        body, dr = body_only(g["text"])
        for kk, vv in dr.items():
            drop[kk] += vv
        rows.append({"key": k, "chars_all": len(g["text"]), "chars_body": len(body),
                     "dropped": dr})
    print(f"口径 {CALIBER}｜块表版本 {blocks_version()}")
    print(f"  参与量化的页：{len(rows)}｜原口径下摘要已变：{was_changed}")
    print(f"  剔除行合计：{sum(drop.values())} 行｜分布 {dict(drop)}")
    tot_all = sum(r['chars_all'] for r in rows)
    tot_body = sum(r['chars_body'] for r in rows)
    print(f"  正文体量 {tot_all:,} → {tot_body:,} 字（剔掉 {tot_all-tot_body:,}，"
          f"{(tot_all-tot_body)/max(1,tot_all)*100:.1f}%）")
    if "--report" in sys.argv:
        p = sys.argv[sys.argv.index("--report") + 1]
        tmp = p + ".swtmp"
        json.dump({"caliber": CALIBER, "blocks_version": blocks_version(),
                   "pages": len(rows), "was_changed": was_changed,
                   "dropped": dict(drop), "items": rows},
                  open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        print(f"  报告 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
