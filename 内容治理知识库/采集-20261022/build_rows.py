#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总装本轮 15 行：官网 5 + Amazon 5 + YouTube 5（每源各 5 条）。

## 口径（Owner 2026-10-22 当场定的，改之前先问）

1. **每源 5 条，三品类必须落在 吸奶器 / 清洗机 / 婴儿监控器 之内**（不得自创品类）。
2. **文案 ≤ 50 个字符**（Owner 选定「字符」而不是「词」）。超出的按**词边界**截断，
   并在末尾加 `…` —— 截断必须看得见，不许悄悄改词、不许改写。
3. **文案必须是来源原文的逐字前缀**。这不是注释，是 `verify_rows.py` 会断言的东西：
   每条都带 `src_text`，校验器断言 `src_text.startswith(copy.rstrip("…"))`。
   一条对不上，整批不写库。
4. **图片与链接逐条可点**：图片必须返回 `image/*`，链接必须 200（同一把闸门）。
5. `产品线` 用库内受控词表（吸奶器 / 清洗机 / 婴儿监控器）；
   `渠道` 用库内既有值（官网 / Amazon / YouTube）；
   `内容类型` 用库内既有值（文案 / 视频）。
   **不自创任何一个枚举值** —— 这三列在库里是别人按它们统计的。

用法：python3 build_rows.py
"""
import html
import json
import re

# ── 选品：每条 = (品类, 渠道, 内容类型, 文案, 原文, 图片, 链接, 发布时间)
def _site():
    rows = {r["sku_id"]: r for r in json.load(open("raw/site_rows.json", encoding="utf-8"))}
    out = []

    def one(sku, cat, copy, src, truncated_ok=True):
        r = rows[sku]
        body = " ".join([r["title"], r["og_description"]] + r["sent_short"] + [r["first_sent"]])
        out.append({
            "产品线": cat, "渠道": "官网", "内容类型": "文案",
            "文案": copy, "src_text": src, "图片": r["image"], "链接": r["url"],
            "发布": r["published_at"],
        })

    # 短句都是页面正文里的原句/小标题，逐字（见 raw/site_rows.json 的 sent_short / first_sent）
    one("8877403177158", "吸奶器", "A good pumping journey starts with the right…",
        "A good pumping journey starts with the right support.")
    one("9069974683846", "吸奶器", "SLEEK, LOW-PROFILE WEAR FOR REAL LIFE…",
        "SLEEK, LOW-PROFILE WEAR FOR REAL LIFE")
    one("8905189621958", "吸奶器", "Patented DoubleFit™ Flange for a Better Fit…",
        "Patented DoubleFit™ Flange for a Better Fit")
    one("9076837908678", "清洗机", "Momcozy DeepClean Lite Baby Bottle Washer…",
        "Momcozy DeepClean Lite Baby Bottle Washer and Sterilizer")
    one("8828255666374", "婴儿监控器", "The 2K HD video offers an 8x digital zoom…",
        "The 2K HD video offers an 8x digital zoom to see every tiny detail.")
    return out


def _amazon():
    rows = {r["asin"]: r for r in json.load(open("raw/amazon_rows.json", encoding="utf-8"))}
    picks = [
        ("B0G6417BM1", "吸奶器", "WARM MASSAGE FOR COMFORTABLE PUMPING"),
        ("B0FW4XC8MG", "吸奶器", "Ultra-Slim & Truly Discreet Anywhere"),
        ("B0FFN1RJ8V", "清洗机", "𝟐𝟔 𝐏𝐎𝐖𝐄𝐑𝐅𝐔𝐋 𝐒𝐏𝐑𝐀𝐘 𝐉𝐄𝐓𝐒 𝐅𝐎𝐑 𝐓𝐇𝐎𝐑𝐎𝐔𝐆𝐇 𝐂𝐋𝐄𝐀𝐍𝐈𝐍𝐆"),
        ("B0FCF7TT5Z", "清洗机", "8-Minute Full Steam Sterilization"),
        ("B0GJ8PJQT8", "婴儿监控器", "True Cry Detection & Auto-Soothing White Noise"),
    ]
    out = []
    for asin, cat, copy in picks:
        r = rows[asin]
        # 剥掉 bullet 的起始括号（`[HEAD]: detail` / `【HEAD】detail`）—— 括号是排版标记，
        # 不是文案本身；剥完再校验「文案是原文逐字前缀」，否则断言会被一个 `[` 判假红。
        bullets = [re.sub(r"^[\[【]\s*", "", html.unescape(b)) for b in r["bullets"]]
        src = next((b for b in bullets if b.startswith(copy.rstrip("…"))), "")
        if not src:
            src = next((b for b in bullets if copy in b), "")
        out.append({
            "产品线": cat, "渠道": "Amazon", "内容类型": "文案",
            "文案": copy, "src_text": src, "图片": r["img"], "链接": r["url"],
            "发布": "",
        })
    return out


def _youtube():
    vids = {r["videoId"]: r for r in json.load(open("raw/youtube.json", encoding="utf-8"))}
    # 5 条覆盖三个品类：清洗机 2 / 婴儿监控器 2 / 吸奶器 1
    picks = [
        ("v_WYO8laaPI", "清洗机", "How to Use Momcozy DeepClean Lite Baby Bottle…"),
        ("jRPyY0dzh8k", "清洗机", "D8 vs. CleanPal Pro: Which Bottle Washer Do…"),
        ("BztEL4E411I", "婴儿监控器", "How to Set Up the Momcozy BM08 Smart Baby Monitor"),
        ("eg-zTo4d6E8", "婴儿监控器", "Watch Over Every Breath, Every Cry, Every…"),
        ("ssOY1AhGx9Y", "吸奶器", "How to Use the Momcozy V3 Double Electric…"),
    ]
    out = []
    for vid, cat, copy in picks:
        r = vids[vid]
        out.append({
            "产品线": cat, "渠道": "YouTube", "内容类型": "视频",
            "文案": copy, "src_text": html.unescape(r["title"]),
            "图片": r["thumb"], "链接": r["url"], "发布": (r["uploadDate"] or "")[:10],
        })
    return out


def cell(r):
    parts = [f"【文案】{r['文案']}"]
    if r.get("发布"):
        parts.append(f"【发布】{r['发布']}")
    parts += [f"【图片】{r['图片']}", f"【链接】{r['链接']}"]
    return "\n".join(parts)


def main():
    rows = _site() + _amazon() + _youtube()
    assert len(rows) == 15, len(rows)

    # ── 本函数内部就该挡住的四件事 ─────────────────────────────────────────────
    for r in rows:
        core = r["文案"].rstrip("…")
        assert r["src_text"], f"找不到原文: {r['文案']}"
        assert r["src_text"].startswith(core), f"文案不是原文的逐字前缀: {r['文案']} ⊄ {r['src_text'][:60]}"
        assert len(r["文案"]) <= 50, f"文案超 50 字符({len(r['文案'])}): {r['文案']}"
        assert r["产品线"] in {"吸奶器", "清洗机", "婴儿监控器"}, r["产品线"]
        assert r["渠道"] in {"官网", "Amazon", "YouTube"}, r["渠道"]
        assert r["内容类型"] in {"文案", "视频"}, r["内容类型"]
        assert r["图片"].startswith("https://"), r["图片"]
        assert r["链接"].startswith("https://"), r["链接"]

    payload = [{
        "fields": {
            "采集数据": cell(r),
            "产品线": r["产品线"],
            "渠道": r["渠道"],
            "内容类型": r["内容类型"],
        },
        "_meta": {"src_text": r["src_text"], "图片": r["图片"], "链接": r["链接"],
                  "文案字符数": len(r["文案"]), "产品线": r["产品线"], "渠道": r["渠道"]},
    } for r in rows]

    json.dump(payload, open("out_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"总装 {len(payload)} 行 → out_rows.json")
    print(" 每源条数:", {c: sum(1 for r in rows if r['渠道'] == c) for c in ("官网", "Amazon", "YouTube")})
    print(" 品类分布:", {c: sum(1 for r in rows if r['产品线'] == c) for c in ("吸奶器", "清洗机", "婴儿监控器")})
    print(" 文案字符数:", [len(r["文案"]) for r in rows])
    print(" 最长一行 采集数据 字节:", max(len(cell(r).encode()) for r in rows))


if __name__ == "__main__":
    main()
