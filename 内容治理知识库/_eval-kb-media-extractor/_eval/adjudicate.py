#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回填员定案器：把「提到本 skill」升级为「归口本 skill」的判据。

定案口径（写进评测过程，全程一致）
────────────────────────────────────────────────────────────
判「触发」= 回复把这条请求的**归口**落在 kb-media-extractor 上：
  A 明确归口句（归/是/按/走/路由到/加载 + kb-media-extractor，且该句无否定）；
  B 无明确归口句，但回复按本 skill 的口径给出处理方案（引擎清单 / kb/l1/media 落盘 /
    l1_gate 验收），且开头段没有把归口让出去的否定句。
判「不触发」= 回复的主结论
  N1 明确声明本 skill 不接（不归/不是/不该由/不属于/不接/不碰/不管 + kb-media-extractor）；
  N2 kb-media-extractor + 不是本/之外/范围外；
  N3 开头段把归口让给别的成员（归/走/交给/应由 + 其他成员）且无 A；
  N4 开头段明确「不触发」，或（边界情况）先追问要什么材料。
边界情况：不触发且回复在追问 → 记「追问」。

用法： /usr/bin/python3 adjudicate.py
"""
import json
import os
import re
import glob
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
NAME = "kb-media-extractor"
OTHER = (r"kb-l0-feishu|kb-ingest-extractor|kb-clause-extractor|kb-pipeline|kb-check|kb-repair|"
         r"kb-recall|kb-canonical-lookup|kb-p0-check|kb-manage|图片安全审查|视频安全审查|文案合规审查|"
         r"内容审查总控|shuorenhua|蒸馏")
NEGW = r"(不|没|无|别|拒绝|不能|不该|不用|并非|绝非)"

A_OWN = re.compile(r"(归|是|按|走|路由到|路由给了|加载了|已加载|交给|由)\s*[`\*\s]*" + NAME +
                   r"|" + NAME + r"\s*(这条路|这条线|的活|的活儿|的职责|负责|管这|入口)")
N1 = re.compile(NEGW + r"[^。；\n]{0,24}" + NAME + r"|" + NAME + r"[^。；\n]{0,24}(不接|不碰|不管|不归|之外|范围外|不是本)")
N2 = re.compile(r"不触发|不该触发|结论是[^\n]{0,6}不触发")
N3 = re.compile(r"(归|走|交给|应由|让位给|转给|路由到)\s*[`\*\s]*(" + OTHER + r")")
ENGINE = re.compile(r"kb/kbpy\s+l8/(ocr_attachments|drill_links_2levels|store_l0_attachments|apply_ocr_to_l1)"
                    r"|l8/(ocr_attachments|drill_links_2levels|store_l0_attachments|apply_ocr_to_l1)\.py")
LAND = re.compile(r"kb/l1/media|media 区|L1 media|manifest_l1|ocr\.json|ocr_cache_reusable|l1_gate")
ASK = re.compile(r"(需要你(补充|提供|确认|给)|请(补充|提供|确认|告诉|给)|先(确认|补|问)|"
                 r"是哪(批|一个|条|张)|哪批|哪个批次|麻烦(你)?(确认|提供|补充)|能(不能)?(先)?告诉我|"
                 r"你(能)?给我|还差|缺少(材料|输入)|需要确认|确认一下|材料在哪|落(到)?哪一层|给我(图|链接|文本))")


def first_block(reply, n=420):
    return reply[:n]


def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[。！？\n])", t) if s.strip()]


def decide(typ, reply):
    head = first_block(reply)
    a = None
    for s in sentences(reply):
        if A_OWN.search(s) and not N1.search(s) and not re.search(NEGW + r"[^。；\n]{0,10}" + NAME, s):
            a = s[:160]
            break
    n1 = N1.search(reply)
    n2 = N2.search(reply)
    n3 = N3.search(head)
    b = bool(ENGINE.search(reply) and LAND.search(reply))
    if a and not (n1 and not b):
        concl = "触发"
        why = f"A 明确归口：{a}"
    elif n1:
        concl = "不触发"
        why = "N1 声明本 skill 不接：" + n1.group(0)[:120]
    elif n2 and not b:
        concl = "不触发"
        why = "N2 明确不触发：" + n2.group(0)[:100]
    elif n3 and not b:
        concl = "不触发"
        why = "N3 归口让给别的成员：" + n3.group(0)[:100]
    elif b:
        concl = "触发"
        why = "B 按本 skill 口径给出引擎+落盘+验收方案"
    else:
        concl = "不触发"
        why = "无归口本 skill 的证据"
    if typ == "边界情况" and concl == "不触发" and ASK.search(reply):
        concl = "追问"
    return concl, why


def main():
    ws = openpyxl.load_workbook(os.path.join(EVAL, f"{NAME}.xlsx"))["触发评测用例"]
    hdr = [c.value for c in ws[1]]
    exp = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        d = dict(zip(hdr, r))
        exp[d["序号"]] = d
    out, table = {}, []
    for f in sorted(glob.glob(os.path.join(HERE, "a-round-*.jsonl"))):
        rnd = int(os.path.basename(f).split("-")[-1].split(".")[0])
        for line in open(f, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            n = r["n"]
            typ = exp[n]["类型"]
            concl, why = decide(typ, r["reply"])
            out.setdefault(str(n), {})[str(rnd)] = {"结论": concl, "why": why}
            oracle = "触发" if r["oracle"]["triggered_hint"] else "不触发"
            table.append((n, rnd, typ, oracle, concl, why))
    with open(os.path.join(HERE, "adjudicated.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    for n, rnd, typ, oracle, concl, why in table:
        mark = "  " if oracle == concl else "≠≠"
        print(f"{mark} #{n:<3} r{rnd} [{typ:<4}] 粗筛={oracle:<3} 定案={concl:<3} | {why[:150]}")
    print(f"\n合计 {len(table)} 条；与粗筛不一致 {sum(1 for t in table if t[3]!=t[4])} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
