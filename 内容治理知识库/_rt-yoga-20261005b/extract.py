#!/usr/bin/env python3
# 冻结送审文本：从 lark markdown 正文剥离媒体/结构引用，保留人类可读文字。
# 规则（可复算）：
#  1) 去 <figure ...>...</figure>、<source .../>、<img .../>、<sheet ...></sheet>
#     —— 这些是内嵌媒体/表格引用，本体未到本机
#  2) 去剩余 HTML 标签（<callout>、<grid>、<column>、<p>、<b>、<br/> 等）
#  3) 去 markdown 标记：#、>、**、*、![]()、[](）
#  4) HTML 实体反转义
#  5) 折叠空白：行内空白合并为单空格；空行折叠为单换行
import json, re, html, hashlib, sys, pathlib

root = pathlib.Path(__file__).resolve().parent
raw = json.load(open(root / "doc-raw.json"))
content = raw["data"]["document"]["content"]

t = content
t = re.sub(r"<figure\b[^>]*>.*?</figure>", " ", t, flags=re.S)
t = re.sub(r"<sheet\b[^>]*>\s*</sheet>", " ", t, flags=re.S)
t = re.sub(r"<sheet\b[^>]*/>", " ", t, flags=re.S)
t = re.sub(r"<source\b[^>]*/>", " ", t, flags=re.S)
t = re.sub(r"<img\b[^>]*/>", " ", t, flags=re.S)
t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
t = re.sub(r"<[^>]+>", " ", t)
t = html.unescape(t)
t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
t = re.sub(r"[ \t]*\*\*[ \t]*", "", t)
t = re.sub(r"[ \t]*\*[ \t]*", "", t)
t = re.sub(r"^\s*>\s?", "", t, flags=re.M)

lines = []
for ln in t.split("\n"):
    ln = re.sub(r"[ \t\u00a0]+", " ", ln).strip()
    lines.append(ln)
out = "\n".join(lines)
out = re.sub(r"\n{2,}", "\n", out).strip() + "\n"

(root / "yoga-text.txt").write_text(out, encoding="utf-8")
b = out.encode("utf-8")
print("chars", len(out), "bytes", len(b), "sha256", hashlib.sha256(b).hexdigest())
