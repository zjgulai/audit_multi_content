#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G5 加决策头 + G6 换成精简判定块。只动这两格，其余字节不动。"""
import zipfile, os, re, html, shutil, sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from task_xlsx_rewrite_v2 import G5_DECISION_HEAD, G6_NEW  # noqa: E402

P = os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx")
TMP = P + ".new"; SHEET = "xl/worksheets/sheet1.xml"

G5_ANCHOR = "【不计入完成度项（12 项）｜**不阻塞本任务、不计入任务完成统计**】"
G6_START = "【10/10 14:20 本轮实测补充（独立复核，只读库；本块与上面各块并列，不覆盖）】"
G6_END = "（口径：可疑项≠造假，机器只报疑似、判归人。）"

z = zipfile.ZipFile(P); items = z.infolist(); xml = z.read(SHEET).decode("utf-8")

def cell_text(ref):
    i = xml.index(f'<c r="{ref}"'); j = xml.index("</c>", i) + 4
    m = re.search(r"<t[^>]*>(.*?)</t>", xml[i:j], re.S)
    return xml[i:j], html.unescape(m.group(1))

cell5, t5 = cell_text("G5")
cell6, t6 = cell_text("G6")

# ── G5：决策头插在标题后 ──────────────────────────────────────────────
assert G5_ANCHOR in t5, "G5 锚点不在"
if "**本块 17 项的判**" not in t5:
    t5n = t5.replace(G5_ANCHOR, G5_ANCHOR + "\n" + G5_DECISION_HEAD, 1)
else:
    t5n = t5; print("G5 已加过决策头")

# ── G6：整块替换我那节 ────────────────────────────────────────────────
assert G6_START in t6 and G6_END in t6, "G6 我那块不在（可能已被别人改）"
i6 = t6.index(G6_START); j6 = t6.index(G6_END) + len(G6_END)
t6n = t6[:i6] + G6_NEW + t6[j6:]

def rebuild(cell_old, text_new):
    m = re.search(r"<t[^>]*>.*?</t>", cell_old, re.S)
    return cell_old.replace(m.group(0), f'<t xml:space="preserve">{html.escape(text_new, quote=False)}</t>', 1)

new_xml = xml.replace(cell5, rebuild(cell5, t5n), 1).replace(cell6, rebuild(cell6, t6n), 1)

assert "ns0" not in new_xml
assert new_xml.count("<row ") == xml.count("<row ")
assert new_xml.count('customHeight="1"') == xml.count('customHeight="1"')
assert '<mergeCell ref="A1:G1"' in new_xml
ET.fromstring(new_xml)
print(f"G5 {len(t5)}→{len(t5n)} 字｜G6 {len(t6)}→{len(t6n)} 字")

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
assert diff == ["G5", "G6"], f"改到了别的格：{diff}"
# 原有内容逐行保留（被替换的那一块除外）
for ref, old, new in (("G5", a["G5"], b["G5"]), ("G6", a["G6"], b["G6"])):
    lost = [ln for ln in old.split("\n") if ln.strip() and ln not in new]
    assert not lost or ref == "G6", f"{ref} 丢了内容：{lost[:2]}"
print("回读校验：只改了 G5/G6 ✅")
shutil.move(TMP, P)
print("已写回：", P, os.path.getsize(P), "字节")
