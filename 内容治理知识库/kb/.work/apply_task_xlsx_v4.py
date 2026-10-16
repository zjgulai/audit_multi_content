#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整表重写 G3–G17：每行两段（已完成 / 未完成），去掉全部 🟡 与 ⚠。

只改 G3…G17 的 <is><t> 内容；其余字节不动（命名空间 / 行高 / 合并单元格）。
写前断言、写后回读，任何一条不符即中止。
"""
import zipfile, os, re, html, shutil, sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from task_xlsx_g_values_v4 import G  # noqa: E402

P = os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx")
TMP = P + ".new"; SHEET = "xl/worksheets/sheet1.xml"

# 红线①：目标文本里不许再有黄点/黄色提示符
for r, t in G.items():
    for bad in ("🟡", "⚠", "⚠️"):
        assert bad not in t, f"G{r} 里仍有 {bad}"
print("待写文本自检：15 行无 🟡/⚠ ✅")

z = zipfile.ZipFile(P); items = z.infolist(); xml = z.read(SHEET).decode("utf-8")

def pick(x, ref):
    i = x.index(f'<c r="{ref}"'); j = x.index("</c>", i) + 4
    return x[i:j]

orig = {r: pick(xml, f"G{r}") for r in G}
_g6 = html.unescape(re.search(r"<t[^>]*>(.*?)</t>", orig[6], re.S).group(1))
assert "562 条" in _g6, "G6 不是我们改过的那版，中止"

new_xml = xml
for r in sorted(G):
    ref = f"G{r}"; old = orig[r]
    attrs = re.match(r'<c r="%s"([^>]*)>' % ref, old).group(1)
    new = f'<c r="{ref}"{attrs}><is><t xml:space="preserve">{html.escape(G[r], quote=False)}</t></is></c>'
    assert old in new_xml
    new_xml = new_xml.replace(old, new, 1)

assert "ns0" not in new_xml
assert new_xml.count("<row ") == xml.count("<row ")
assert new_xml.count('customHeight="1"') == xml.count('customHeight="1"')
assert '<mergeCell ref="A1:G1"' in new_xml
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
diff = sorted((k for k in set(a) | set(b) if a.get(k) != b.get(k)), key=lambda s: (s[0], int(s[1:])))
assert diff == [f"G{r}" for r in sorted(G)], f"改动的格子不对：{diff}"
assert b["G2"] == a["G2"] and b["A1"] == a["A1"], "表头被动过"

shutil.move(TMP, P)
print("已写回：", P, os.path.getsize(P), "字节")
print("逐格字数：" + ", ".join(f"G{r}={len(b[f'G{r}'])}" for r in sorted(G)))
