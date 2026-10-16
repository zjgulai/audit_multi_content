#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修 G6 末尾【是否要做】块的重复片段。"""
import zipfile, os, re, html, shutil
import xml.etree.ElementTree as ET

P = os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx")
TMP = P + ".new"; SHEET = "xl/worksheets/sheet1.xml"

BAD = "【是否要做｜10/10 查证】**本条能力面无遗留必做项**（跑通 562 run 超额；三个写死的默认值已改成真读库；「谁负责/何时生效」10/10 补完 1018/1018）（跑通 562 run 超额；「谁负责 / 何时生效」今天补完 1018/1018；三个写死的默认值已改成真读库，`governance_fallbacks: []` 为证）。**不做 6 项**：⑤ 风险等级 · ⑥ 模态 · ⑭ 9 场景覆盖表 · ⑮ 蒸馏工单 · ⑯ W-4 编号段 · ⑰ 基线表（依据见 10/8–10/10 行备注块）。"
GOOD = "【是否要做｜10/10 查证（原文，⑭ 一项已被上块更正）】**本条能力面无遗留必做项**（跑通 562 run 超额；三个写死的默认值已改成真读库，`governance_fallbacks: []` 为证；「谁负责 / 何时生效」今天补完 1018/1018）。**不做 5 项**：⑤ 风险等级 · ⑥ 模态 · ⑮ 蒸馏工单 · ⑯ W-4 编号段 · ⑰ 基线表。⑭ 9 场景覆盖表 **改判为必须做**（见上块）。"

z = zipfile.ZipFile(P); items = z.infolist(); xml = z.read(SHEET).decode("utf-8")
i = xml.index('<c r="G6"'); j = xml.index("</c>", i) + 4
cell = xml[i:j]
t = html.unescape(re.search(r"<t[^>]*>(.*?)</t>", cell, re.S).group(1))
assert BAD in t, "找不到待修的重复片段"
tn = t.replace(BAD, GOOD, 1)

new_cell = cell.replace(re.search(r"<t[^>]*>.*?</t>", cell, re.S).group(0),
                        f'<t xml:space="preserve">{html.escape(tn, quote=False)}</t>', 1)
new_xml = xml.replace(cell, new_cell, 1)
assert "ns0" not in new_xml and new_xml.count("<row ") == xml.count("<row ")
ET.fromstring(new_xml)

with zipfile.ZipFile(TMP, "w", zipfile.ZIP_DEFLATED) as out:
    for it in items:
        out.writestr(it, new_xml.encode("utf-8") if it.filename == SHEET else z.read(it.filename))
z.close()
shutil.move(TMP, P)
print(f"G6 {len(t)} → {len(tn)} 字｜已写回 {os.path.getsize(P)} 字节")
