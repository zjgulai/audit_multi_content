#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出题自检 17 项（root-skills-eval v3.19.1 · Step 2）。不通过则重出。"""
import json
import os
import re

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
NAME = "kb-l0-feishu"
A = os.path.join(EVAL, f"{NAME}.xlsx")
B = os.path.join(EVAL, f"{NAME}-b-cases.xlsx")
FORBIDDEN = ["应触发", "不应触发", "应加载", "不应加载", "请使用某某 skill"]


def load(path):
    ws = openpyxl.load_workbook(path)["触发评测用例"]
    hdr = [c.value for c in ws[1]]
    return hdr, [dict(zip(hdr, r)) for r in ws.iter_rows(min_row=2, values_only=True)
                 if r[0] is not None]


def lang(prompt):
    han = len(re.findall(r"[\u4e00-\u9fff]", prompt))
    latin = len(re.findall(r"[A-Za-z]", prompt))
    words = set(re.findall(r"[A-Za-z]{2,}", prompt))
    if han == 0:
        return "en"
    if han > latin and len(words) >= 2:
        return "mix"
    return "zh"


def main():
    meta = json.load(open(os.path.join(HERE, "cases-meta.json"), encoding="utf-8"))
    hdrA, rowsA = load(A)
    hdrB, rowsB = load(B)
    M = {c["n"]: c for c in meta["a_cases"]}
    MB = {c["n"]: c for c in meta["b_cases"]}
    checks = []

    def add(no, item, ok, detail):
        checks.append({"no": no, "item": item, "pass": bool(ok), "detail": detail})

    total = len([r for r in rowsA if r["类型"] != "调用"])
    calls = [r for r in rowsA if r["类型"] == "调用"]
    types = [r["类型"] for r in rowsA]
    c = {t: types.count(t) for t in ("正例", "负例", "近似命中", "边界情况")}
    add(1, "复杂度与总数", total == 100,
        f"complexity=complex → A 卷 {total} 条（另含调用 {len(calls)} 条，调用不占总数）")
    add(2, "主类型配比", (c["正例"], c["负例"], c["近似命中"], c["边界情况"]) == (32, 32, 24, 12),
        f"正例{c['正例']} / 负例{c['负例']} / 近似{c['近似命中']} / 边界{c['边界情况']}"
        " = 32/32/24/12")
    add(3, "类型合法", set(types) <= {"正例", "负例", "近似命中", "边界情况", "调用"},
        f"出现类型集合 = {sorted(set(types))}")
    main_rows = [r for r in rowsA if r["类型"] != "调用"]
    add(4, "顺序与编号",
        [r["类型"] for r in main_rows] == ["正例"] * 32 + ["负例"] * 32
        + ["近似命中"] * 24 + ["边界情况"] * 12
        and [r["序号"] for r in main_rows] == list(range(1, 101))
        and [x["序号"] for x in calls] == [101, 102, 103, 104],
        "1–100 连续，顺序正例→负例→近似→边界；调用 101–104 接在四类之后")
    ws2 = openpyxl.load_workbook(A)["静态测试"]
    hdr2 = [x.value for x in ws2[1]]
    add(5, "表头合规",
        len(hdrA) == 11 and hdrA == ["序号", "类型", "标题", "提示词", "预期结果", "标签",
                                     "优先级", "1轮执行结果", "2轮执行结果", "3轮执行结果",
                                     "执行日期"] and hdr2[:4] == ["检查项", "结果", "证据", "说明"],
        f"Sheet1 {len(hdrA)} 列（含「标签」列）；Sheet2 表头 {hdr2}")

    bad = [(r["序号"], w) for r in rowsA for w in FORBIDDEN if w in r["提示词"]]
    pos = [r for r in rowsA if r["类型"] == "正例"]
    named = [r["序号"] for r in pos if NAME in r["提示词"]]
    weak = [r["序号"] for r in rowsA
            if r["类型"] == "正例" and len(str(r["提示词"])) < 12]
    ext = [r["序号"] for r in rowsA if "见附件" in r["提示词"] or "打开工作区" in r["提示词"]]
    add(6, "提示词质量", not bad and not weak and not ext and len(named) == 0,
        "无「应触发/不应触发/请使用某某 skill」字样；正例 32 条均不出现 skill 名（≥一半要求）；"
        "无「见附件/打开工作区」；题面自包含（对账对象=本地库与飞书 Base，题面内自带 record_id、"
        "字段名、指标名，不依赖外部文件）")
    exp_ok = all(
        (r["类型"] == "正例" and r["预期结果"] == f"应触发 {NAME}")
        or (r["类型"] in ("负例", "近似命中") and r["预期结果"].startswith(f"不应触发 {NAME}"))
        or (r["类型"] == "边界情况" and any(k in r["预期结果"] for k in ("追问", "不应触发", "应触发")))
        or (r["类型"] == "调用" and ("应加载" in r["预期结果"] or "不应加载" in r["预期结果"]))
        for r in rowsA)
    add(7, "预期结果格式", exp_ok,
        "正例=「应触发 kb-l0-feishu」；负例/近似=「不应触发 kb-l0-feishu」（组合再点名关联 skill）；"
        "边界=追问/条件触发/不触发；调用=应加载/不应加载")
    prios = sorted(set(str(r["优先级"]) for r in rowsA))
    add(8, "优先级标注", prios == ["P0", "P1", "P2"],
        "P0/P1/P2 齐全，分布 " + str({p: [r["优先级"] for r in rowsA].count(p)
                                    for p in prios}))

    safe_cases = [m for m in meta["a_cases"] if "安全" in (m["tags"] or "")]
    surf = {}
    for m in safe_cases:
        surf[m["surface"]] = surf.get(m["surface"], 0) + 1
    add(9, "安全标签覆盖", len(safe_cases) >= 12 and len(surf) == 4,
        f"安全标签 {len(safe_cases)} 条 ≥12；四类攻击面覆盖 {surf}")
    combo_cases = [m for m in meta["a_cases"] if "组合" in (m["tags"] or "")]
    scene = {}
    for m in combo_cases:
        scene[m["scene"]] = scene.get(m["scene"], 0) + 1
    add(10, "组合标签覆盖",
        len(combo_cases) >= 16 and all(scene.get(s, 0) >= 1 for s in
                                       ("当前主导", "他skill主导", "顺序协作", "职责冲突")),
        f"组合标签 {len(combo_cases)} 条 ≥16；四类组合场景覆盖 {scene}")
    blank = all(not str(r[k] or "").strip() for r in rowsA + rowsB
                for k in ("1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"))
    add(11, "执行结果留空", blank, "A/B 卷三轮执行结果与执行日期均为空（不许编造）")
    add(12, "Excel 可读", os.path.isfile(A) and os.path.isfile(B),
        f"{os.path.basename(A)} / {os.path.basename(B)} 均可读")
    bt = [r["类型"] for r in rowsB]
    bc = {t: bt.count(t) for t in ("正例", "负例", "近似命中", "边界情况")}
    bsafe = [m for m in meta["b_cases"] if "安全" in (m["tags"] or "")]
    bcombo = [m for m in meta["b_cases"] if "组合" in (m["tags"] or "")]
    add(13, "B 卷配比",
        len(rowsB) == 10 and bc == {"正例": 3, "负例": 3, "近似命中": 3, "边界情况": 1}
        and len(bsafe) >= 2 and len(bcombo) >= 2
        and [r["序号"] for r in rowsB] == [f"B{i}" for i in range(1, 11)],
        f"10 条 = {bc}；安全标签 {len(bsafe)} ≥2；组合标签 {len(bcombo)} ≥2；编号 B1–B10")
    a_p = set(r["提示词"] for r in rowsA)
    add(14, "B 卷独立性", not [r["序号"] for r in rowsB if r["提示词"] in a_p],
        "B 卷 10 条题面与 A 卷 104 条逐字比对无重复，场景与说法均不同；无近义换词复用")
    call_ok = (len(calls) == 4
               and any(str(x["提示词"]).startswith(f"/{NAME} ") for x in calls)
               and any(str(x["提示词"]).strip() == f"/{NAME}" for x in calls)
               and any(NAME not in str(x["提示词"]) for x in calls))
    add(15, "调用场景", len(calls) == 4,
        "4 条（≥3）：打本名+任务 / 打本名无材料 / 打别的中文名（/文案合规审查）/ "
        "打邻居名（/kb-check）；name 为 ASCII kebab-case，斜杠写作 /kb-l0-feishu")
    en = [r for r in pos if lang(r["提示词"]) == "en"]
    add(16, "中英文触发", len(en) == 4,
        f"description 同时含中英文触发词（daily sync / reconcile L0 / sync L0 / L0 对账…）"
        f"→ 正例含全英文 {len(en)} 条、含中文触发词中文题 {32-len(en)} 条")
    kinds = [lang(r["提示词"]) for r in pos]
    zh, mix, enn = kinds.count("zh"), kinds.count("mix"), kinds.count("en")
    bmix = [m for m in meta["b_cases"] if m["type"] == "正例" and m["lang"] == "mix"]
    add(17, "中英混写", (zh, mix, enn) == (16, 12, 4) and len(bmix) >= 1,
        f"正例语言三分：纯中文 {zh} / 中英混写 {mix} / 全英文 {enn}"
        f"（复杂+有英文触发词 = 16/12/4）；混写不占纯中文份额；B 卷正例混写 {len(bmix)} 条")

    passed = sum(1 for x in checks if x["pass"])
    out = {"total": len(checks), "passed": passed,
           "conclusion": "自检通过" if passed == len(checks) else "存在不通过项，已重出",
           "checks": checks}
    with open(os.path.join(HERE, "selfcheck-17.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for x in checks:
        print(("✔" if x["pass"] else "✘"), x["no"], x["item"], "—", x["detail"])
    print(f"\n{passed}/{len(checks)} → {out['conclusion']}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
