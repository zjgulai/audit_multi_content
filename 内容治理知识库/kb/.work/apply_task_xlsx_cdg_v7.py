#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C 目标 / D 交付物 / G 实际进度 三列一起改成 1/2/3 编号并互相对齐。
   只改 C/D/G 三列的第 3–17 行；A/B/E/F/H 与其它字节一律不动。"""
import zipfile, os, re, html, shutil, sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from task_xlsx_cdg_v7 import C, D, G  # noqa: E402

P = os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx")
TMP = P + ".new"; SHEET = "xl/worksheets/sheet1.xml"
CELLS = {**{f"C{r}": C[r] for r in C}, **{f"D{r}": D[r] for r in D}, **{f"G{r}": G[r] for r in G}}

for ref, t in CELLS.items():
    for bad in ("🟡", "⚠"):
        assert bad not in t, f"{ref} 里仍有 {bad}"
print(f"待写 {len(CELLS)} 格（C/D/G × 15 行）：无 🟡/⚠ ✅")

z = zipfile.ZipFile(P); items = z.infolist(); xml = z.read(SHEET).decode("utf-8")

def pick(x, ref):
    i = x.index(f'<c r="{ref}"'); j = x.index("</c>", i) + 4
    return x[i:j]

orig = {ref: pick(xml, ref) for ref in CELLS}
# 断言：G6 仍是我们改过的版（防写到别人的版本上）
t6 = html.unescape(re.search(r"<t[^>]*>(.*?)</t>", orig["G6"], re.S).group(1))
assert "562 条" in t6, "G6 不是预期版本，中止"

new_xml = xml
for ref, txt in CELLS.items():
    old = orig[ref]
    attrs = re.match(r'<c r="%s"([^>]*)>' % ref, old).group(1)
    new = f'<c r="{ref}"{attrs}><is><t xml:space="preserve">{html.escape(txt, quote=False)}</t></is></c>'
    assert old in new_xml, ref
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
expect = sorted([k for k in CELLS if CELLS[k] != a.get(k)], key=lambda s: (s[0], int(s[1:])))
assert diff == expect, f"改动的格子不对：改={diff}\n预期={expect}"
# A/B/E/F/H 与 G2 不许动
for k in diff:
    assert k[0] in "CDG", f"改到了非目标列：{k}"
print(f"改动格 {len(diff)} 个（C/D/G）；未变：{[k for k in CELLS if k not in diff]}")

shutil.move(TMP, P)
print("已写回：", P, os.path.getsize(P), "字节")
