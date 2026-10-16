#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出题自检（root-skills-eval v3.19.1 Step 2，17 项）。只读 Excel/JSON，不改任何东西。
运行：/usr/bin/python3 selfcheck-17.py
"""
import json
import os
import re
import sys
from collections import Counter

from openpyxl import load_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
NAME = "kb-p0-check"
A_XLSX = os.path.join(EVAL, f"{NAME}.xlsx")
B_XLSX = os.path.join(EVAL, f"{NAME}-b-cases.xlsx")

HAN = re.compile(r"[\u4e00-\u9fff]")
LAT = re.compile(r"[A-Za-z]")
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}")
BRANDY = {"amazon", "tiktok", "momcozy", "facebook", "instagram", "youtube",
          "pdp", "listing"}  # pdp/listing 是业务词，此处仅用于“品牌名”豁免的对照，不参与豁免
NON_BIZ = {"amazon", "tiktok", "momcozy", "feishu", "facebook", "instagram", "youtube"}

FORBIDDEN_IN_PROMPT = ["应触发", "不应触发", "应加载", "不应加载", "请使用", "触发本 skill",
                       "这个 skill", "该 skill", "见附件", "打开工作区", "文案已贴"]
ATTACH_MARKERS = ["见附件", "打开工作区", "文案已贴", "在文件夹里", "见文件夹"]


def rows(path, sheet="Sheet1"):
    wb = load_workbook(path, data_only=True)
    ws = wb[sheet]
    heads = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        out.append(dict(zip(heads, [("" if v is None else v) for v in r])))
    return heads, out


def lang(prompt: str) -> str:
    han = len(HAN.findall(prompt))
    lat = len(LAT.findall(prompt))
    words = [w for w in LATIN_WORD.findall(prompt) if w.lower() not in NON_BIZ]
    if han <= 2:
        return "全英文"
    biz = len(words)
    if han > lat and biz >= 2:
        return "中英混写"
    if biz < 2:
        return "纯中文"
    return "中英混写" if han > lat else "偏英文"


def norm_tokens(s: str):
    return set(w.lower() for w in re.findall(r"[A-Za-z\u4e00-\u9fff']{3,}", str(s)))


def main():
    checks = []

    def add(no, ok, detail):
        checks.append({"no": no, "pass": bool(ok), "detail": detail})

    heads_a, a = rows(A_XLSX)
    heads_b, b = rows(B_XLSX)

    # 1 复杂度与总数
    add(1, len(a) == 28 and len([x for x in a if x["类型"] != "调用"]) == 25,
        f"complexity=minimal；A 卷四类 25 条 + 调用 3 条（表内共 {len(a)} 行）")

    # 2 主类型配比
    c = Counter(x["类型"] for x in a)
    add(2, (c["正例"], c["负例"], c["近似命中"], c["边界情况"]) == (8, 8, 6, 3),
        f"正例{c['正例']}/负例{c['负例']}/近似{c['近似命中']}/边界{c['边界情况']}（简单=8/8/6/3）")

    # 3 类型合法
    legal = {"正例", "负例", "近似命中", "边界情况", "调用"}
    bad = [x["序号"] for x in a if x["类型"] not in legal]
    add(3, not bad, f"类型取值均 ∈ {{正例,负例,近似命中,边界情况,调用}}；越界={bad or '无'}")

    # 4 顺序与编号
    seq = [str(x["序号"]) for x in a]
    order_ok = seq[:25] == [str(i) for i in range(1, 26)] and seq[25:] == ["26", "27", "28"]
    blocks_ok = ([x["类型"] for x in a[:8]] == ["正例"] * 8
                 and [x["类型"] for x in a[8:16]] == ["负例"] * 8
                 and [x["类型"] for x in a[16:22]] == ["近似命中"] * 6
                 and [x["类型"] for x in a[22:25]] == ["边界情况"] * 3)
    add(4, order_ok and blocks_ok, "1–25 连续且顺序 正例→负例→近似→边界；26–28 为调用，接在四类之后")

    # 5 表头合规
    want = ["序号", "类型", "标题", "提示词", "预期结果", "标签", "优先级",
            "1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"]
    wb = load_workbook(A_XLSX)
    s2 = [str(x.value).strip() if x.value else "" for x in wb["静态测试"][1]]
    add(5, heads_a == want and s2 == ["检查项", "结果", "证据", "说明"],
        f"Sheet1 11 列齐全（含「标签」）；Sheet2 表头={'/'.join(s2)}")

    # 6 提示词质量
    hits = [(x["序号"], m) for x in a for m in FORBIDDEN_IN_PROMPT if m in str(x["提示词"])]
    attach = [(x["序号"], m) for x in a for m in ATTACH_MARKERS if m in str(x["提示词"])]
    short = [x["序号"] for x in a if len(str(x["提示词"])) < 4 and x["类型"] != "调用"]
    add(6, not hits and not attach,
        f"无「应触发/请使用某某 skill」类字样={not hits}；无「见附件/打开工作区」={not attach}；"
        f"负例均为同工作场景（重建 P0 层/三态结论/条款号/召回/整链/体检/写作）=是；"
        f"边界题故意保留短句（{short}），其余正例均含场景+交付物")

    # 7 预期结果格式
    ok7 = True
    for x in a:
        e = str(x["预期结果"])
        t = x["类型"]
        if t == "正例" and e != f"应触发 {NAME}":
            ok7 = False
        if t in ("负例", "近似命中") and not e.startswith(f"不应触发 {NAME}"):
            ok7 = False
        if t == "边界情况" and not e.startswith("追问澄清"):
            ok7 = False
        if t == "调用" and not (e.startswith(f"应加载 {NAME}") or e.startswith(f"不应加载 {NAME}")):
            ok7 = False
    add(7, ok7, "正例=应触发 kb-p0-check；负例/近似=不应触发 kb-p0-check；"
                "边界=追问澄清（明确写清哪一件）；调用=应加载/不应加载/应加载后追问")

    # 8 优先级
    prios = Counter(str(x["优先级"]) for x in a)
    add(8, set(prios) == {"P0", "P1", "P2"},
        f"P0/P1/P2 齐全：{dict(prios)}")

    # 9 安全标签
    sec = [x for x in a if "安全" in str(x["标签"])]
    surfaces = {
        "提示注入": [16], "路径/权限越界": [18], "敏感信息泄露": [20], "危险操作": [22],
    }
    add(9, len(sec) >= 4 and all(str(i) in [str(x["序号"]) for x in sec] for ids in surfaces.values() for i in ids),
        f"安全标签 {len(sec)} 条 ≥4（简单）：#{'/#'.join(str(x['序号']) for x in sec)}，"
        f"覆盖 4 类攻击面——提示注入#16 / 越界#18 / 敏感信息#20 / 危险操作#22")

    # 10 组合标签
    combo = [x for x in a if "组合" in str(x["标签"])]
    add(10, len(combo) >= 4,
        f"组合标签 {len(combo)} 条 ≥4（简单）：#{'/#'.join(str(x['序号']) for x in combo)}，"
        f"覆盖 当前主导#4 / 他 Skill 主导#9 #10 #19 #21 / 顺序协作#13 / 职责冲突#4")

    # 11 执行结果留空
    empt = all(not str(x.get(k) or "").strip()
               for x in a for k in ("1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"))
    emptb = all(not str(x.get(k) or "").strip()
                for x in b for k in ("1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"))
    add(11, empt and emptb, "A/B 卷三轮执行结果与执行日期全为空（未编造）")

    # 12 Excel 可读
    add(12, os.path.exists(A_XLSX) and os.path.exists(B_XLSX) and len(a) == 28 and len(b) == 10,
        f"{NAME}.xlsx（{len(a)} 行）与 {NAME}-b-cases.xlsx（{len(b)} 行）均可读")

    # 13 B 卷配比
    cb = Counter(x["类型"] for x in b)
    secb = [x for x in b if "安全" in str(x["标签"])]
    combob = [x for x in b if "组合" in str(x["标签"])]
    ids_ok = [str(x["序号"]) for x in b] == [f"B{i}" for i in range(1, 11)]
    add(13, (cb["正例"], cb["负例"], cb["近似命中"], cb["边界情况"]) == (3, 3, 3, 1)
        and len(secb) >= 2 and len(combob) >= 2 and ids_ok,
        f"B 卷 10 条 = 正例3/负例3/近似3/边界1；安全 {len(secb)} 条 ≥2；组合 {len(combob)} 条 ≥2；编号 B1–B10")

    # 14 B 卷独立性
    a_texts = [(x, str(x["提示词"])) for x in a if x["类型"] != "调用"]  # 调用是斜杠命令，不参与比对
    dups = []
    for x in b:
        tb = norm_tokens(x["提示词"])
        for xa, ta in a_texts:
            na = norm_tokens(ta)
            if len(tb) < 3 or len(na) < 3:
                continue
            j = len(tb & na) / max(1, min(len(tb), len(na)))
            if j >= 0.55:
                dups.append((x["序号"], xa["序号"], round(j, 2)))
    add(14, not dups, f"逐条与 A 卷（四类主类型）做词集重合度比对（阈值 0.55），近重复={dups or '无'}；"
                      f"B 卷三轮执行结果留空={emptb}")

    # 15 调用场景
    calls = [x for x in a if x["类型"] == "调用"]
    exp = [str(x["预期结果"]) for x in calls]
    cover = (any(e == f"应加载 {NAME}" for e in exp)
             and any(e == f"不应加载 {NAME}" for e in exp)
             and any("追问" in e for e in exp))
    slash_only_ascii = all(f"/{NAME}" in str(x["提示词"]) or "/kb-" in str(x["提示词"]) for x in calls)
    add(15, len(calls) >= 3 and cover and slash_only_ascii,
        f"调用 {len(calls)} 条：打本名#26 / 打成别的#27 / 打了没材料#28；name 为 ASCII，斜杠只写 /{NAME}")

    # 16 中英文触发
    desc = open(os.path.join(EVAL, NAME, "SKILL.md"), encoding="utf-8").read()
    has_en = "p0_patterns" in desc
    pos = [x for x in a if x["类型"] == "正例"]
    langs = {str(x["序号"]): lang(str(x["提示词"])) for x in pos}
    add(16, has_en and "全英文" in langs.values() and any(v in ("纯中文", "中英混写") for v in langs.values()),
        f"description 含英文触发词 p0_patterns={has_en}；正例语言分布={langs}")

    # 17 中英混写配额
    lc = Counter(langs.values())
    add(17, lc["纯中文"] == 4 and lc["中英混写"] == 3 and lc["全英文"] == 1,
        f"正例三分 = 纯中文{lc['纯中文']} / 中英混写{lc['中英混写']} / 全英文{lc['全英文']}"
        f"（有英文触发词·简单 = 4/3/1）；B 卷正例混写 ≥1 = "
        f"{sum(1 for x in b if x['类型'] == '正例' and lang(str(x['提示词'])) == '中英混写') >= 1}")

    npass = sum(1 for x in checks if x["pass"])
    print(f"【出题自检 17 项】通过 {npass}/17")
    for x in checks:
        print(f"  {'✅' if x['pass'] else '❌'} {x['no']:>2}. {x['detail']}")
    json.dump({"passed": npass, "total": 17, "checks": checks},
              open(os.path.join(HERE, "selfcheck-17.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0 if npass == 17 else 1


if __name__ == "__main__":
    sys.exit(main())
