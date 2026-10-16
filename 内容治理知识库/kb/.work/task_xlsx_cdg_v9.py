# -*- coding: utf-8 -*-
"""v9：全表「必须做」段落编号统一从 1 连续重排（修掉从 0. 起的行）。
   同时保持「已完成」段落的编号不动（那里的编号是引用目标号的）。"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from task_xlsx_cdg_v8 import C, D, G

C, D, G = dict(C), dict(D), dict(G)


def renumber_must(text):
    """把「必须做」之后的所有顶层编号行重排为 1..N（缩进的子行不动）。"""
    if "必须做" not in text:
        return text
    i = text.index("必须做") + len("必须做")
    head, tail = text[:i], text[i:]
    lines = tail.split("\n")
    n = 0
    out = []
    for ln in lines:
        if re.match(r"^\d+[.、]", ln):          # 顶层条目：行首即编号
            n += 1
            out.append(re.sub(r"^\d+([.、])", lambda m: f"{n}{m.group(1)}", ln))
        else:
            out.append(ln)
    return head + "\n".join(out)


for r in list(G):
    G[r] = renumber_must(G[r])

if __name__ == "__main__":
    for r in sorted(G):
        k = G[r].find("必须做")
        seq = [int(m.group(1)) for m in re.finditer(r"^(\d+)[.、]", G[r][k:], re.M)] if k >= 0 else []
        flag = "OK" if seq == list(range(1, len(seq) + 1)) else f"断号 {seq}"
        print(f"  行{r}: 必须做 {len(seq)} 条 [{flag}]")
