#!/usr/bin/env python3
"""冻结送审文本（RT-20261005-YOGA-03 · 独立复算）。

规则（写死在本文，不引用任何前一轮的中间件）：
  输入 = `lark-cli docs +fetch --doc-format xml` 的原始响应 JSON（未编辑）
  1) <figure ...>...</figure> → "[视频]"
  2) <sheet ...></sheet> / <sheet .../> → "[表格]"
  3) <img .../> → "[图片]"
  4) <br/> → 换行
  5) 块级结束标签（p/h1..h6/li/title/callout/column/grid/ol/ul/tr/td）→ 换行
  6) 其余标签剥掉；HTML 实体反转义
  7) 行内空白折叠为单空格；行首尾去空白；连续空行折叠为一个空行
输出 = UTF-8 文本；同时打印 sha256（对 UTF-8 字节）。
"""
import json, re, html, hashlib, sys, pathlib

src, dst = sys.argv[1], sys.argv[2]
t = json.load(open(src))["data"]["document"]["content"]

t = re.sub(r"<figure\b[^>]*>.*?</figure>", "[视频]", t, flags=re.S)
t = re.sub(r"<sheet\b[^>]*>\s*</sheet>", "[表格]", t, flags=re.S)
t = re.sub(r"<sheet\b[^>]*/>", "[表格]", t, flags=re.S)
t = re.sub(r"<img\b[^>]*/>", "[图片]", t, flags=re.S)
t = re.sub(r"<br\s*/?>", "\n", t)
for tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "title",
            "callout", "column", "grid", "ol", "ul", "tr", "td", "table"):
    t = re.sub(r"</%s\s*>" % tag, "\n", t)
t = re.sub(r"<[^>]+>", "", t)
t = html.unescape(t)

lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in t.split("\n")]
out_lines, prev_blank = [], False
for ln in lines:
    if ln == "":
        if prev_blank:
            continue
        prev_blank = True
    else:
        prev_blank = False
    out_lines.append(ln)
out = "\n".join(out_lines).strip() + "\n"

pathlib.Path(dst).write_text(out, encoding="utf-8")
b = out.encode("utf-8")
print("bytes", len(b), "lines", out.count("\n"), "sha256", hashlib.sha256(b).hexdigest())
