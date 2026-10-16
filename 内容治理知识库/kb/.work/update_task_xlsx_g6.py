#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只改 G6（10/12–10/16 行）—— **续写**，不整格覆盖。

为什么只改 G6：正本 G 列已被另一轮作业扩写过（G5 2172 字含「不计入完成度项」备注块、
G12 含【是否要做】），整格覆盖会删掉那些内容。本脚本**只在 G6 的锚点行后插入一块**，
原文一个字不删、其他 14 格与全部非 G 格一个字节不动。

锚点：`【承接】r5 转来的「真源统一」仍在，见 r5 第 ④ 条。` —— 插在它后面、
〔备注〕块之前，语义上正好接得上。
"""
import zipfile, os, re, html, shutil, sys
import xml.etree.ElementTree as ET
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from task_xlsx_g6_insert import INSERT  # noqa: E402

P = os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx")
TMP = P + ".new"
SHEET = "xl/worksheets/sheet1.xml"
ANCHOR = "【承接】r5 转来的「真源统一」仍在，见 r5 第 ④ 条。"

z = zipfile.ZipFile(P)
items = z.infolist()
xml = z.read(SHEET).decode("utf-8")

i = xml.index('<c r="G6"')
j = xml.index("</c>", i) + 4
cell = xml[i:j]
m = re.search(r"<t[^>]*>(.*?)</t>", cell, re.S)
assert m, "G6 里没找到 <t>"
old_text = html.unescape(m.group(1))
assert ANCHOR in old_text, "G6 里找不到锚点，中止（内容已被别人改过，先人工看一眼）"
assert "【承接】" in old_text and "〔备注〕" in old_text
# 锚点必须只出现一次
assert old_text.count(ANCHOR) == 1, "锚点出现多次，中止"
# 幂等：已经有本轮插入块就不重复插
if "【10/10 14:20 本轮实测补充" in old_text:
    print("已经插过了，不重复。")
    raise SystemExit(0)

new_text = old_text.replace(ANCHOR, ANCHOR + "\n" + INSERT, 1)
assert len(new_text) > len(old_text)
assert old_text.count("【是否要做｜10/10 查证】") == 1 and new_text.count("【是否要做｜10/10 查证】") == 1, "备注块被破坏"

new_cell = cell.replace(m.group(0), f"<t xml:space=\"preserve\">{html.escape(new_text, quote=False)}</t>", 1)
new_xml = xml.replace(cell, new_cell, 1)

# 校验
assert "ns0" not in new_xml
assert new_xml.count("<row ") == xml.count("<row ")
assert new_xml.count('customHeight="1"') == xml.count('customHeight="1"')
assert '<mergeCell ref="A1:G1"' in new_xml
ET.fromstring(new_xml)
print(f"G6：{len(old_text)} 字 → {len(new_text)} 字（+{len(new_text)-len(old_text)}）")

with zipfile.ZipFile(TMP, "w", zipfile.ZIP_DEFLATED) as out:
    for it in items:
        out.writestr(it, new_xml.encode("utf-8") if it.filename == SHEET else z.read(it.filename))
z.close()

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
def cells(p):
    sh = ET.fromstring(zipfile.ZipFile(p).read(SHEET))
    return {c.attrib["r"]: "".join(t.text or "" for t in c.iter(NS + "t")) for r in sh.iter(NS + "row") for c in r.iter(NS + "c")}

a, b = cells(P), cells(TMP)
diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
assert diff == ["G6"], f"改动了非目标格：{diff}"
assert b["G6"].startswith(a["G6"][:200]), "原开头被破坏"
assert INSERT in b["G6"], "插入块没进去"
# 原文逐行都在（插入块自身允许带换行）
orig_lines = [ln for ln in a["G6"].split("\n") if ln.strip()]
lost = [ln for ln in orig_lines if ln not in b["G6"]]
assert not lost, f"原有内容丢失：{lost[:3]}"
print(f"回读校验：只有 G6 变了 ✅｜原文 {len(orig_lines)} 行逐行保留 ✅｜插入 {len(INSERT)} 字")
shutil.move(TMP, P)
print(f"已写回 {P}（{os.path.getsize(P)} 字节）")
