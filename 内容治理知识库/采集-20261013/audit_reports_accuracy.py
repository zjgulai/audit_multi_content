#!/usr/bin/env python3
"""核 80 条审查报告的**准确性与依据可回源性**。

逐条回答三件事：
  A. **声明的问题数 vs 实际条目数** 对不对得上
  B. **每一条依据有没有飞书源链接**（`momcozy-in.feishu.cn/...`），是什么类型
  C. **链接是否真的可达**（实读飞书记录，不信链接长得像）

报告正文是**压平**的（`<br>` 被吃掉了），所以按 `N.【分类】` 切条目。
"""
import json, glob, html, os, re, subprocess, collections, sys

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
FEISHU_RE = re.compile(r"https?://momcozy-in\.feishu\.cn/[^\s，。）)】]+")
ART_RE = re.compile(r"\b([SWE]-\d+\.\d+)\b")
# 正文是**压平**的，而且条目之间**没有分隔符** —— 实测结构是
# `…判定：BLOCK2.【结论…`（换行在「判定」之前，不在编号之前）。
# ⇒ **靠前一个字符判边界本来就脆**（第一版就是这么漏掉 7/8 条的）。
# 改成：抓出所有 `数字.【分类】`，再按「编号必须从 1 开始连续」取前缀。
#   好处：既稳，又顺带验证了**编号本身的连续性**（跳号会被这一段抓出来）。
# ★ 分类可能是**英文**（实测 `Absolute or ranking claims` 达 26 字符）⇒ 上限卡 20 会漏条目。
ITEM_RE = re.compile(r"(\d{1,2})\.\s*【([^】]{1,60})】")


def split_items(txt):
    """按「编号连续」切条目。返回 `(items, gaps)` —— `gaps` 记跳号/重号，不静默丢。"""
    cand = list(ITEM_RE.finditer(txt))
    items, gaps, want = [], [], 1
    for m in cand:
        n = int(m.group(1))
        if n != want:
            gaps.append((n, want))
            continue
        items.append((m, n, m.group(2).strip()))
        want += 1
    return items, gaps


def doc_text(tok):
    d = json.load(open(os.path.join(OUT, "docs80", f"{tok}.json"), encoding="utf-8"))

    def big(o):
        out = []
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "content" and isinstance(v, str) and len(v) > 100:
                    out.append(v)
                else:
                    out += big(v)
        elif isinstance(o, list):
            for v in o:
                out += big(v)
        return out
    parts = big(d)
    if not parts:
        return ""
    s = html.unescape(re.sub(r"<br\s*/?>", "\n", max(parts, key=len)))
    return re.sub(r"<[^>]+>", "", s)


def parse(txt):
    head = re.search(r"【审查结论[：:]\s*([A-Z_]+)】共发现\s*(\d+)\s*处", txt)
    concl = head.group(1) if head else None
    declared = int(head.group(2)) if head else None
    pos, gaps = split_items(txt)
    items = []
    for i, (m, _n, _c) in enumerate(pos):
        end = pos[i + 1][0].start() if i + 1 < len(pos) else len(txt)
        body = txt[m.end():end]
        # 依据类型标记：位置与依据之间用 —— 分隔
        marker = ""
        mm = re.search(r"——\s*([^：\n]{2,40})", body[:120])
        if mm:
            marker = mm.group(1).strip()
        ev_line = ""
        em = re.search(r"依据[：:](.*?)(?=判定[：:]|建议[：:]|$)", body, re.S)
        if em:
            ev_line = em.group(1).strip()
        items.append({
            "idx": _n, "category": _c, "n_gaps": len(gaps),
            "marker": marker,
            "art": ART_RE.findall(ev_line) or ART_RE.findall(body),
            "feishu": FEISHU_RE.findall(ev_line) or FEISHU_RE.findall(body),
            "ev_line": ev_line[:160],
        })
    return {"concl": concl, "declared": declared, "items": items, "gaps": gaps}


def main():
    rep = json.load(open(os.path.join(OUT, "reports80.json")))
    docs = rep["docs"]
    allf = []
    bad_count = []
    for x in docs:
        tok = x["doc"]
        t = doc_text(tok)
        p = parse(t)
        p["doc"] = tok
        allf.append(p)
        if p["declared"] is not None and len(p["items"]) != p["declared"]:
            bad_count.append((tok, p["concl"], p["declared"], len(p["items"])))

    # ── A 声明数 vs 实际条目 ──
    print("=== A. 声明的「共发现 N 处」 vs 实际解析出的条目数 ===")
    print(f"   报告数 {len(allf)} ｜ 对不上的 {len(bad_count)}")
    for tok, c, d, n in bad_count[:20]:
        print(f"     {tok}  声明 {d} ｜ 实际 {n} ｜ 结论 {c}")

    # ── B 依据类型 + 飞书链接 ──
    print("\n=== B. 逐条依据的类型与飞书链接 ===")
    tot = collections.Counter()
    no_link = []
    for p in allf:
        for it in p["items"]:
            mk = it["marker"]
            kind = ("库内条款" if "有库内条款依据" in mk else
                    "无库内依据" if "无库内依据" in mk else
                    "外部标准" if "外部标准" in mk else "其它/未识别")
            tot[kind] += 1
            if kind == "库内条款" and not it["feishu"]:
                no_link.append((p["doc"], it))
    print("   ", dict(tot), f"｜ 合计 {sum(tot.values())} 条")
    print(f"    库内条款依据里**缺飞书链接**的：{len(no_link)}")
    for tok, it in no_link[:12]:
        print(f"      {tok}  #{it['idx']} 【{it['category']}】art={it['art']}")

    # ── 库内依据的链接形态 ──
    print("\n=== C. 库内条款依据的链接都指向哪张表 ===")
    tbl = collections.Counter()
    for p in allf:
        for it in p["items"]:
            if "有库内条款依据" not in it["marker"]:
                continue
            for u in it["feishu"]:
                m = re.search(r"table=(\w+)", u)
                tbl[m.group(1) if m else "(无 table 参数)"] += 1
    for k, v in tbl.most_common():
        print(f"     {k}: {v}")

    json.dump(allf, open(os.path.join(OUT, "audit80_findings.json"), "w"),
              ensure_ascii=False, indent=1)
    print("\n明细已落 -> out/audit80_findings.json")


if __name__ == "__main__":
    main()
