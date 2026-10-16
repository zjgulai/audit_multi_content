#!/usr/bin/env python3
# 冻结送审文本（RT-20261005-YOGA-02）
# 目的：把 lark markdown 正文里**非正文的结构/媒体引用**去掉，保留人类可读文字，
#       且**不许把词粘起来**（前一版规则 `[ \t]*\*\*[ \t]*`→'' 会把
#       "put all ... essentials in" 粘成 "putall ... essentialsin"，进而伪造出
#       nursingpillows / awardwinning 这类假 n-gram）。
# 规则（可复算）：
#  1) <figure>（含 <source>/<img>）按 mime 归一成 [视频] / [图片]
#  2) 独立 <img/> → [图片]；<sheet></sheet> → [表格]
#  3) markdown ![](url) → [图片]；[](url) → 文本
#  4) 去剩余 HTML 标签；HTML 实体反转义
#  5) 只删标记符号本身（#、**、*、>），**不删它两侧的空白**
#  6) 折叠行内空白为单空格；空行折叠为单换行
import json, re, html, hashlib, sys, pathlib

here = pathlib.Path(__file__).resolve().parent
raw = json.load(open(here / "doc-raw.json", encoding="utf-8"))
t = raw["data"]["document"]["content"]

t = re.sub(r"<figure\b[^>]*>(.*?)</figure>",
           lambda m: "[视频]" if "video" in m.group(1) else "[图片]", t, flags=re.S)
t = re.sub(r"<img\b[^>]*/>", "[图片]", t)
t = re.sub(r"<sheet\b[^>]*>\s*</sheet>", "[表格]", t)
t = re.sub(r"<sheet\b[^>]*/>", "[表格]", t)
t = re.sub(r"<source\b[^>]*/>", "[视频]", t)
t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "[图片]", t)
t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
t = re.sub(r"<[^>]+>", " ", t)
t = html.unescape(t)
t = re.sub(r"^\s{0,3}#{1,6}[ \t]*", "", t, flags=re.M)
t = t.replace("**", "").replace("*", "")
t = re.sub(r"^\s*>[ \t]?", "", t, flags=re.M)

lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in t.split("\n")]
out = re.sub(r"\n{2,}", "\n", "\n".join(lines)).strip() + "\n"

sys.stdout.write(out)
print("chars %d bytes %d sha256 %s" % (
    len(out), len(out.encode("utf-8")),
    hashlib.sha256(out.encode("utf-8")).hexdigest()), file=sys.stderr)
