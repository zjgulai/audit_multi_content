#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G6 内一处**自相矛盾**的取代标注（只加一句，不删原文）。

上半段（10/9 写的）：「基线表 🟡 … 没有落成独立基线表」
下半段（本轮插入）：「基线表 ✅ 已落成独立产物」
同一格两个答案 ⇒ 后人会读错。本脚本在旧的 🟡 那句**后面**加一行取代标注，
并**顺手把 △ 标进句首**（把 🟡 改成 ✅ 会删掉"当时的判断"这条历史，不做）。
"""
import zipfile, os, re, html, shutil
import xml.etree.ElementTree as ET

P = os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx")
TMP = P + ".new"
SHEET = "xl/worksheets/sheet1.xml"

OLD = "基线表 🟡 三个数体检侧都有"
NEW = "基线表 🟡（**已被本格下方 14:20 块取代**：独立产物 `baseline-latest.*` 已建成）三个数体检侧都有"
MARK = "【替代说明】"

z = zipfile.ZipFile(P); items = z.infolist(); xml = z.read(SHEET).decode("utf-8")
i = xml.index('<c r="G6"'); j = xml.index("</c>", i) + 4
cell = xml[i:j]
m = re.search(r"<t[^>]*>(.*?)</t>", cell, re.S)
old_text = html.unescape(m.group(1))

if MARK in old_text:
    print("已标注过，跳过。"); raise SystemExit(0)
assert old_text.count(OLD) == 1, "锚点不唯一或不存在，中止"
new_text = old_text.replace(OLD, NEW, 1)

new_cell = cell.replace(m.group(0), f'<t xml:space="preserve">{html.escape(new_text, quote=False)}</t>', 1)
new_xml = xml.replace(cell, new_cell, 1)
assert "ns0" not in new_xml
assert new_xml.count("<row ") == xml.count("<row ")
assert new_xml.count('customHeight="1"') == xml.count('customHeight="1"')
ET.fromstring(new_xml)

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
assert diff == ["G6"], diff
lost = [ln for ln in a["G6"].split("\n") if ln.strip() and ln not in b["G6"]]
# 被替换的那一行允许不同
assert all("基线表 🟡 三个数体检侧都有" in ln for ln in lost), f"有内容丢失：{lost[:2]}"
print(f"G6：{len(a['G6'])} → {len(b['G6'])} 字｜只有 G6 变 ✅｜除被标注行外逐行保留 ✅")
shutil.move(TMP, P)
print("已写回：", P, os.path.getsize(P), "字节")
