#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新《内容治理知识库搭建任务详情.xlsx》G 列 —— **字节级保守**版。

为什么重做：第一版用 ElementTree 序列化整份 sheet XML，把默认命名空间改写成了
`ns0:`（`<ns0:worksheet xmlns:ns0="...">`）—— 很多读取器不认。<-- 已回滚，改用本版。

本版纪律：
  · **只做文本替换**，只动 G3…G17 的 `<is><t>…</t></is>` 内容；其余字节逐字保留
    （命名空间、行高 customHeight、mergeCells、dimension 全不动）。
  · 先断言原值是我们读过的那一版；不匹配即中止。
  · 写临时件 → 回读校验（解析 + 逐格等值 + 无 ns0 + 行高仍在）→ 才覆盖原件。
"""
import zipfile, shutil, os, re, html, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_xlsx_g_values import G  # noqa: E402

P = os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx")
TMP = P + ".new"
SHEET = "xl/worksheets/sheet1.xml"

z = zipfile.ZipFile(P)
items = z.infolist()
xml = z.read(SHEET).decode("utf-8")

orig = {}
for row in sorted(G):
    ref = f"G{row}"
    m = re.search(r'<c r="%s"[^>]*>.*?</c>' % ref, xml, re.S)
    assert m, f"找不到 {ref} 单元格"
    orig[ref] = m.group(0)

# 断言：G6 必须仍是含「口径更正 / 112」的那一版
assert "口径更正" in orig["G6"] and "112" in orig["G6"], "G6 不是预期版本，中止"
assert orig["G3"].count("<t>") == 1, "G3 不是单段 inlineStr，中止"
print("原值核对通过：" + "，".join(f"{k}={len(re.sub('<[^>]+>','',v))}字" for k, v in list(orig.items())[:4]))

new_xml = xml
for row in sorted(G):
    ref = f"G{row}"
    old = orig[ref]
    attrs = re.match(r'<c r="%s"([^>]*)>' % ref, old).group(1)
    esc = html.escape(G[row], quote=False)
    new = f'<c r="{ref}"{attrs}><is><t xml:space="preserve">{esc}</t></is></c>'
    new_xml = new_xml.replace(old, new, 1)

# ── 校验 ────────────────────────────────────────────────────────────────
assert "ns0" not in new_xml, "引入了 ns0 前缀，中止"
assert new_xml.count("<row ") == xml.count("<row "), "行数变了"
assert new_xml.count('customHeight="1"') == xml.count('customHeight="1"'), "行高属性丢了"
assert '<mergeCell ref="A1:G1"' in new_xml, "合并单元格丢了"
import xml.etree.ElementTree as ET
ET.fromstring(new_xml)  # 能解析
print("XML 校验通过：可解析 / 无 ns0 / 行高与合并单元格仍在")

with zipfile.ZipFile(TMP, "w", zipfile.ZIP_DEFLATED) as out:
    for it in items:
        out.writestr(it, new_xml.encode("utf-8") if it.filename == SHEET else z.read(it.filename))
z.close()

# 回读
s2 = ET.fromstring(zipfile.ZipFile(TMP).read(SHEET))
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
got = {}
for r in s2.iter(NS + "row"):
    for c in r.iter(NS + "c"):
        ref = c.attrib.get("r", "")
        if ref.startswith("G") and ref[1:].isdigit() and int(ref[1:]) in G:
            got[int(ref[1:])] = "".join(t.text or "" for t in c.iter(NS + "t"))
bad = [k for k in G if got.get(k) != G[k]]
assert not bad, f"回读不一致：{bad}"
raw2 = zipfile.ZipFile(TMP).read(SHEET).decode("utf-8")
assert "ns0" not in raw2
print("回读校验：15 格全等 ✅｜ns0 = 0")

shutil.move(TMP, P)
print(f"已写回 {P}（{os.path.getsize(P)} 字节）")
