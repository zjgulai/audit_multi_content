#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 cases-a.json / cases-b.json 落成 Excel（Sheet1 用例 11 列 + Sheet2 静态测试）。"""
from __future__ import annotations

import json
import os

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
NAME = "kb-recall"
HDR1 = ["序号", "类型", "标题", "提示词", "预期结果", "标签", "优先级",
        "1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"]
HDR2 = ["检查项", "结果", "证据", "说明"]

STATIC = [
    ("目录结构", "pass",
     "ls -1 被测副本 → SKILL.md / references/{excel_analysis,excel_reading,layer-playbook,pdf_reading}.md / scripts/convert_pdf_to_images.py（+ 本次评测自建 evals/）",
     "SKILL.md 必需项齐备；references/ 4 个文件（1742–9486 字节）、scripts/ 1 个脚本（1123 字节）均非空"),
    ("runtime 被正文点名引用", "pass",
     "SKILL.md §2 点名 references/pdf_reading.md、excel_reading.md、excel_analysis.md；§2/§4 点名 references/layer-playbook.md",
     "4 个 references 全部被正文写读取条件，无「默认全量加载」"),
    ("路径引用有效性", "pass",
     "SKILL.md §1/§2/§4 引 kb/kbpy、kb/l6/retriever.py、kb/l7/registry/layers.yaml、references/layer-playbook.md",
     "以本次库根为基准逐条 stat：四条全部存在（OK）"),
    ("name 长度 1–64", "pass", "name: kb-recall（9 字符）", "≤64"),
    ("name=目录名", "pass", "name: kb-recall == 副本目录名 kb-recall", "ASCII kebab-case，本项不记 na"),
    ("description < 1024", "pass", "description 实测 988 字符", "<1024"),
    ("正文 < 5000 token", "pass", "SKILL.md 全文 6311 字节 / 正文 2156 字符（57 行）", "远低于 5000"),
    ("references 单文件 < 5000 token", "pass",
     "wc -c：pdf_reading.md 9486 / layer-playbook.md 5698 / excel_analysis.md 2745 / excel_reading.md 1742 字节",
     "最大者 9486 字节（中文按 1 字≈1 token 上界估算 ≈3.2k token）<5000"),
    ("frontmatter 无 <>", "pass", "正则 [<>] 扫 frontmatter → False", "无非法字符"),
    ("description 有 what+when+何时不用", "pass",
     "what=「L6（召回层）的只读检索入口」；when=「当用户说…时使用」+ 14 个中文触发词；何时不用=各自点名 6 条（kb-canonical-lookup / kb-p0-check / kb-review / kb-content-review / kb-pipeline / kb-check / kb-manage）",
     "三要素齐全，description 内无步骤清单"),
    ("scripts 无密钥 / rm -rf / curl|sh", "pass",
     "grep -nE '(rm -rf|curl .*\\|.*sh|api[_-]?key|secret|password)' SKILL.md scripts/*.py → 0 命中",
     "convert_pdf_to_images.py 仅做本地 PDF→图片转换"),
    ("references 无未脱敏数据", "pass", "references/*.md 内无 token / 手机号 / 邮箱等未脱敏数据", "均为方法说明文本"),
    ("from skills._shared", "na", "SKILL.md / scripts/ 内无 from skills._shared 或 import skills._shared（0 命中）",
     "不涉及；即便出现也只记 warning、不阻断、不为修它改 name"),
]


def dump(cases, path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(HDR1)
    for c in cases:
        ws.append([c["id"], c["类型"], c["标题"], c["提示词"], c["预期结果"], c["标签"], c["优先级"],
                   "", "", "", ""])
    for col, w in zip("ABCDEFGHIJK", (6, 10, 34, 62, 30, 10, 8, 12, 12, 12, 12)):
        ws.column_dimensions[col].width = w
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("Sheet2")
    ws2.append(HDR2)
    for r in STATIC:
        ws2.append(list(r))
    for cell in ws2[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E2EFDA")
    for col, w in zip("ABCD", (24, 8, 70, 60)):
        ws2.column_dimensions[col].width = w
    for row in ws2.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)
    print("wrote", path, len(cases), "rows")


if __name__ == "__main__":
    A = json.load(open(os.path.join(EV, "cases-a.json"), encoding="utf-8"))
    B = json.load(open(os.path.join(EV, "cases-b.json"), encoding="utf-8"))
    dump(A, os.path.join(EV, f"{NAME}.xlsx"))
    dump(B, os.path.join(EV, f"{NAME}-b-cases.xlsx"))
