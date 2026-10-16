#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出题 17 项自检（root-skills-eval v3.19.1 · trigger-eval-cases.md Step 2）。

用法：python3 selfcheck-17.py [--out selfcheck-17.json]
不通过 → 打印 FAIL 项；全通过 → 写 JSON 结论。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)

A_TOTAL = 50
MAIN = {"正例": 16, "负例": 16, "近似命中": 12, "边界情况": 6}
LANG = {"纯中文": 8, "中英混写": 6, "全英文": 2}
SAFETY_MIN, COMBO_MIN = 6, 8
B_MAIN = {"正例": 3, "负例": 3, "近似命中": 3, "边界情况": 1}
BANNED = ("应触发", "不应触发", "应加载", "不应加载", "请使用", "该用", "触发本 skill")


def lang(t: str) -> str:
    han = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    lat = sum(1 for ch in t if ch.isascii() and ch.isalpha())
    words = re.findall(r"[A-Za-z]{2,}", t)
    if han == 0:
        return "全英文"
    if han > lat and len(words) >= 2:
        return "中英混写"
    return "纯中文"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "selfcheck-17.json"))
    args = ap.parse_args()

    A = json.load(open(os.path.join(EV, "cases-a.json"), encoding="utf-8"))
    B = json.load(open(os.path.join(EV, "cases-b.json"), encoding="utf-8"))
    rows = [(k, v) for k, v in A.items()]
    main_rows = [(k, v) for k, v in rows if v["类型"] != "调用"]
    call_rows = [(k, v) for k, v in rows if v["类型"] == "调用"]
    checks = []

    def chk(no, name, ok, detail):
        checks.append({"no": no, "item": name, "result": "pass" if ok else "fail", "detail": detail})

    # 1 复杂度与总数
    sk = open(os.path.join(os.path.dirname(EV), "SKILL.md"), encoding="utf-8").read()
    cx = re.search(r'^complexity:\s*"?(\w+)"?', sk, re.M).group(1)
    chk(1, "复杂度与总数", cx == "standard" and len(main_rows) == A_TOTAL,
        f"complexity={cx}（standard⇒50）｜A 卷主类型 {len(main_rows)} 条 + 调用 {len(call_rows)} 条")

    # 2 主类型配比
    c = Counter(v["类型"] for _, v in main_rows)
    chk(2, "主类型配比 32/32/24/12", all(c[k] == v for k, v in MAIN.items()),
        f"实测 {dict(c)}；目标 {MAIN}")

    # 3 类型合法
    legal = {"正例", "负例", "近似命中", "边界情况", "调用"}
    chk(3, "类型合法", all(v["类型"] in legal for _, v in rows),
        f"类型取值 {sorted(set(v['类型'] for _, v in rows))}；安全/组合只出现在标签列")

    # 4 顺序与编号
    ids = [k for k, _ in rows]
    order_ok = ([A[k]["类型"] for k in ids[:A_TOTAL]] ==
                ["正例"] * 16 + ["负例"] * 16 + ["近似命中"] * 12 + ["边界情况"] * 6)
    cont_ok = ids[:A_TOTAL] == [str(i) for i in range(1, A_TOTAL + 1)]
    chk(4, "顺序与编号", order_ok and cont_ok and [k for k, _ in call_rows] == ["51", "52", "53"],
        "1–50 连续且 正例→负例→近似→边界；调用 51–53 接在四类之后（不占 A 卷总数）")

    # 5 表头合规
    from openpyxl import load_workbook
    wb = load_workbook(os.path.join(EV, "kb-check.xlsx"))
    h1 = [c.value for c in wb["Sheet1"][1]]
    h2 = [c.value for c in wb["Sheet2"][1]]
    need1 = ["序号", "类型", "标题", "提示词", "预期结果", "标签", "优先级",
             "1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"]
    chk(5, "表头合规", h1 == need1 and h2 == ["检查项", "结果", "证据", "说明"],
        f"Sheet1 11 列逐字一致（含「标签」）；Sheet2 = {h2}")

    # 6 提示词质量
    probs = []
    for k, v in rows:
        t = v["提示词"]
        if any(b in t for b in BANNED):
            probs.append(f"#{k} 含禁用措辞")
        if re.search(r"见附件|打开工作区|打开.{0,6}文件|附件里", t):
            probs.append(f"#{k} 依赖外部文件")
    pos_ok = all(len(v["提示词"]) >= 25 for k, v in rows if v["类型"] == "正例")
    neg_ok = not any(re.search(r"天气|斐波那契|写个脚本算", v["提示词"]) for k, v in rows if v["类型"] == "负例")
    chk(6, "提示词质量", not probs and pos_ok and neg_ok,
        f"无「应触发/不应触发/请使用某某 skill」字样、无「见附件/打开某文件」、正例均 ≥25 字且有交付物与场合、负例均属同一份工作场景（非天气笑话类）；异常 {probs or '无'}")

    # 7 预期结果格式
    bad7 = []
    for k, v in rows:
        e, t = v["预期结果"], v["类型"]
        if t == "正例" and not e.startswith("应触发 kb-check"):
            bad7.append(k)
        if t in ("负例", "近似命中") and "不应触发 kb-check" not in e:
            bad7.append(k)
        if t == "边界情况" and not (("不应触发" in e) and ("追问" in e or "应" in e)):
            bad7.append(k)
        if t == "调用" and not re.search(r"应加载 kb-check|不应加载 kb-check", e):
            bad7.append(k)
    chk(7, "预期结果格式", not bad7,
        f"正例=应触发；负例/近似=不应触发；边界=不触发+追问；调用=应加载/不应加载（异常 {bad7 or '无'}）")

    # 8 优先级
    pr = set(v["优先级"] for _, v in rows)
    chk(8, "优先级标注", {"P0", "P1", "P2"} <= pr, f"实测 {sorted(pr)}")

    # 9 安全标签
    sec = [(k, v) for k, v in rows if "安全" in v["标签"]]
    faces = Counter()
    for k, v in sec:
        for f in ("提示注入", "敏感信息", "危险操作", "路径/权限越界", "越界"):
            if f in v["预期结果"]:
                faces["越界类" if f == "越界" else f] += 1
    chk(9, "安全标签覆盖", len(sec) >= SAFETY_MIN and len([f for f in faces if f in ("提示注入", "敏感信息", "危险操作", "越界类")]) == 4,
        f"安全标签 {len(sec)} 条（下限 {SAFETY_MIN}）；攻击面覆盖 {dict(faces)}")

    # 10 组合标签
    comb = [(k, v) for k, v in rows if "组合" in v["标签"]]
    kinds = {"①本skill主导": 0, "②他skill主导": 0, "③顺序协作": 0, "④职责冲突": 0}
    for k, v in comb:
        ti = v["标题"]
        if v["类型"] == "正例" and "①" in ti:
            kinds["①本skill主导"] += 1
        if "②" in ti or ("不应触发 kb-check，应触发" in v["预期结果"] and "③" not in ti and "④" not in ti):
            kinds["②他skill主导"] += 1
        if "③" in ti:
            kinds["③顺序协作"] += 1
        if "④" in ti:
            kinds["④职责冲突"] += 1
    chk(10, "组合标签覆盖", len(comb) >= COMBO_MIN and all(v > 0 for v in kinds.values()),
        f"组合标签 {len(comb)} 条（下限 {COMBO_MIN}）；四类覆盖 {kinds}")

    # 11 执行结果留空
    blank = all((ws.cell(r, cc).value in (None, "")) for ws in (wb["Sheet1"],)
                for r in range(2, ws.max_row + 1) for cc in (8, 9, 10, 11))
    chk(11, "执行结果留空", blank, "Sheet1 第 8–11 列（三轮结果 + 执行日期）全空")

    # 12 Excel 可读
    chk(12, "Excel 可读", os.path.exists(os.path.join(EV, "kb-check.xlsx")),
        f"kb-check.xlsx Sheet1 {wb['Sheet1'].max_row - 1} 行；命名 = name")

    # 13 B 卷配比
    wbb = load_workbook(os.path.join(EV, "kb-check-b-cases.xlsx"))
    cb = Counter(v["类型"] for v in B.values())
    bsec = [k for k, v in B.items() if "安全" in v["标签"]]
    bcomb = [k for k, v in B.items() if "组合" in v["标签"]]
    chk(13, "B 卷配比", all(cb[k] == v for k, v in B_MAIN.items()) and len(B) == 10
        and len(bsec) >= 2 and len(bcomb) >= 2
        and list(B) == [f"B{i}" for i in range(1, 11)]
        and wbb["Sheet1"].max_row - 1 == 10,
        f"B 卷 {dict(cb)}；编号 B1–B10；安全 {len(bsec)} 条 ≥2、组合 {len(bcomb)} 条 ≥2；独立文件 kb-check-b-cases.xlsx")

    # 14 B 卷独立性
    ap = set(v["提示词"] for _, v in rows)
    overlap = ap & set(v["提示词"] for v in B.values())
    chk(14, "B 卷独立性", not overlap, f"与 A 卷题面逐字重复 {len(overlap)} 条；B 卷三轮结果留空")

    # 15 调用场景
    pats = set()
    for k, v in call_rows:
        e = v["预期结果"]
        if "不应加载" in e:
            pats.add("打别的")
        elif "应加载" in e and "追问" in e:
            pats.add("没材料")
        elif "应加载" in e:
            pats.add("打本名")
    slash_ok = all(v["提示词"].startswith("/kb-") for _, v in call_rows)
    chk(15, "调用场景", len(call_rows) >= 3 and pats == {"打本名", "打别的", "没材料"} and slash_ok,
        f"调用 {len(call_rows)} 条；覆盖 {sorted(pats)}；name 为 ASCII kb-check，斜杠只写 /kb-check（无中文斜杠）")

    # 16 中英文触发
    langs = Counter(lang(v["提示词"]) for _, v in main_rows if v["类型"] == "正例")
    name_in_pos = [k for k, v in main_rows if v["类型"] == "正例" and "kb-check" in v["提示词"]]
    chk(16, "中英文触发", langs["全英文"] >= 1 and langs["纯中文"] + langs["中英混写"] >= 1 and not name_in_pos,
        f"正例语言 {dict(langs)}（中文题 14 / 全英文题 2，两边都有；正例不出现 skill 名：{len(name_in_pos)} 条）")

    # 17 中英混写配额
    chk(17, "中英混写配额", langs["中英混写"] == LANG["中英混写"] and langs["全英文"] == LANG["全英文"],
        f"标准复杂度有英文触发词 ⇒ 混写 {langs['中英混写']}（应 6）、全英文 {langs['全英文']}（应 2）、纯中文 {langs['纯中文']}（应 8）；未对半劈")

    fails = [c for c in checks if c["result"] == "fail"]
    out = {"total_items": 17, "passed": 17 - len(fails), "failed": len(fails),
           "verdict": "通过" if not fails else "不通过，须重出",
           "items": checks}
    for c in checks:
        print(f"[{'PASS' if c['result'] == 'pass' else 'FAIL'}] 第{c['no']:>2}项 {c['item']}：{c['detail']}")
    print(f"\n自检结论：{out['passed']}/17 通过 —— {out['verdict']}")
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("->", args.out)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
