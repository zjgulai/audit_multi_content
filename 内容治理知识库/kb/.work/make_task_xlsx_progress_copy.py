#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在线生成「实际进度」版 xlsx 副本：读**当前正本** → 只改 G 列 → 落**新份**。

为什么落新份而不就地改：
  · `版本规矩.md` 要求就地改，但那预设"独占写入"。本文件在 2026-10-10 14:07 之后
    **有第三方写入**（G3 试算字数从 2112 回到 452、文件大小 17861 → 20683），
    就地改会与该写入互相覆盖。
  · 所以本脚本**不碰正本**：产出 `内容治理知识库搭建任务详情_实际进度-<时间>.xlsx`，
    由 Owner 确认后再由本人/本脚本替补。

纪律：G 列之外一个字节不动；改完逐格回读校验；断言行数与行高属性不变。
"""
import zipfile, os, re, html, sys, xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from task_xlsx_g_values import G  # noqa: E402

SRC = os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx")
from datetime import datetime
STAMP = datetime.now().strftime("%Y%m%d-%H%M")
DST = os.path.expanduser(f"~/Desktop/内容治理知识库搭建任务详情_实际进度-{STAMP}.xlsx")
SHEET = "xl/worksheets/sheet1.xml"

z = zipfile.ZipFile(SRC)
items = z.infolist()
xml = z.read(SHEET).decode("utf-8")

# 逐格精确取单元格（`<c ...>...</c>`，G 列都是自闭合不了的 inlineStr）
def pick(x, ref):
    i = x.index(f'<c r="{ref}"')
    j = x.index("</c>", i) + 4
    return x[i:j]

orig = {f"G{r}": pick(xml, f"G{r}") for r in G}
print("正本 G 列现字数：" + " ".join(f"G{r}={len(re.sub('<[^>]+>', '', orig[f'G{r}']))}" for r in sorted(G)))

new_xml = xml
for r in sorted(G):
    ref = f"G{r}"
    old = orig[ref]
    attrs = re.match(r'<c r="%s"([^>]*)>' % ref, old).group(1)
    new = f'<c r="{ref}"{attrs}><is><t xml:space="preserve">{html.escape(G[r], quote=False)}</t></is></c>'
    assert old in new_xml, ref
    new_xml = new_xml.replace(old, new, 1)

# ── 校验 ───────────────────────────────────────────────────────────────
assert "ns0" not in new_xml, "引入了 ns0 前缀"
assert new_xml.count("<row ") == xml.count("<row "), "行数变了"
assert new_xml.count('customHeight="1"') == xml.count('customHeight="1"'), "行高属性丢了"
assert '<mergeCell ref="A1:G1"' in new_xml, "合并单元格丢了"
ET.fromstring(new_xml)
print("XML 校验：可解析 / 无 ns0 / 行数与行高一致 ✅")

with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as out:
    for it in items:
        out.writestr(it, new_xml.encode("utf-8") if it.filename == SHEET else z.read(it.filename))
z.close()

# ── 回读 ───────────────────────────────────────────────────────────────
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
s2 = ET.fromstring(zipfile.ZipFile(DST).read(SHEET))
got = {}
for row in s2.iter(NS + "row"):
    for c in row.iter(NS + "c"):
        ref = c.attrib.get("r", "")
        if ref.startswith("G") and ref[1:].isdigit() and int(ref[1:]) in G:
            got[int(ref[1:])] = "".join(t.text or "" for t in c.iter(NS + "t"))
bad = [k for k in G if got.get(k) != G[k]]
assert not bad, f"回读不一致：{bad}"
assert "ns0" not in zipfile.ZipFile(DST).read(SHEET).decode("utf-8")

# 其余列未被触碰：逐格比对源与产物
def allcells(path):
    sh = ET.fromstring(zipfile.ZipFile(path).read(SHEET))
    return {c.attrib["r"]: "".join(t.text or "" for t in c.iter(NS + "t")) for row in sh.iter(NS + "row") for c in row.iter(NS + "c")}
a, b = allcells(SRC), allcells(DST)
diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
nong = [k for k in diff if not (k.startswith("G") and k[1:].isdigit() and int(k[1:]) in G)]
assert not nong, f"误改非目标格：{nong}"
print(f"回读校验：15 格全等 ✅｜其余 {len(a)-15} 格逐字未变 ✅｜改动格 = {diff}")
print("产物：", DST, os.path.getsize(DST), "字节")
