#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从库内 5 份达人稿快照抽取「客户/钛动反馈」判例（美国市场内容要求）。

**为什么用它**（而不是让模型自己想美国文化）：Owner 2026-10-13 明确要求
「不要只盯知识库和 skill」。这些反馈是**客户与钛动对真实达人内容的实际修改要求**，
有出处（哪份稿、哪一列），是"美国市场到底要求什么"的**判例**。

数据源（**只读**）：`kb/l0/snapshots/*.md` —— 5 份达人稿快照，
来源租户 `biu6ihvvco.feishu.cn`（**飞书源只读，本脚本不写任何飞书侧数据**）。

输出：`out/kol_feedback.json`（逐条：文档 / 列名 / 原文）

用法：cd 本地化源-20261013 && python3 extract_feedback.py
"""
import glob
import html
import json
import os
import re

#: 反馈列（中英各版表头）
FEEDBACK_COLS = ["钛动反馈", "客户反馈", "Tec-do Feedback", "Brand Feedback",
                 "Feedback by TecDo", "Feedback by client"]
#: 认稿标记（标题里出现即认为是达人稿）
DOC_MARK = re.compile(r"Draft|Script|横测")


def cell_text(c):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip()


def main():
    rows = []
    docs = 0
    # 本脚本在 <库根>/本地化源-20261013/ 下跑 ⇒ 快照在 ../kb/l0/snapshots/
    cands = sorted(glob.glob("../kb/l0/snapshots/*.md")) or sorted(glob.glob("kb/l0/snapshots/*.md"))
    for p in cands:
        t = open(p, encoding="utf-8").read()
        if not DOC_MARK.search(t[:400]):
            continue
        docs += 1
        title = re.search(r"title: (.*)", t)
        body = t.split("-->", 1)[-1]
        for m in re.finditer(r"<table>.*?</table>", body, re.S):
            trs = re.findall(r"<tr>(.*?)</tr>", m.group(0), re.S)
            if not trs:
                continue
            hdr = [cell_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", trs[0], re.S)]
            for tr in trs[1:]:
                cells = [cell_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
                for i, h in enumerate(hdr):
                    if h in FEEDBACK_COLS and i < len(cells) and len(cells[i]) > 8:
                        rows.append({"doc": title.group(1)[:44] if title else "",
                                     "col": h, "text": cells[i]})

    os.makedirs("out", exist_ok=True)
    json.dump(rows, open("out/kol_feedback.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"达人稿 {docs} 份 ｜ 抽到反馈 {len(rows)} 条 → out/kol_feedback.json")
    by = {}
    for r in rows:
        by[r["col"]] = by.get(r["col"], 0) + 1
    print("按列:", by)


if __name__ == "__main__":
    main()
