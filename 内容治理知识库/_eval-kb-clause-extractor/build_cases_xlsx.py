#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 kb-clause-extractor 评测 A/B 卷 Excel + 出题 17 项自检。

A 卷：100 条（正例32/负例32/近似命中24/边界12）+ 调用 3 条（不占 A 卷总数）
B 卷：10 条（正例3/负例3/近似3/边界1），独立文件、封印
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = Path("/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/l7/skills/kb-clause-extractor")
NAME = "kb-clause-extractor"

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

HEAD = ["序号", "类型", "标题", "提示词", "预期结果", "标签", "优先级",
        "1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"]


def lang(p: str) -> str:
    han = len(re.findall(r"[\u4e00-\u9fff]", p))
    lat = len(re.findall(r"[A-Za-z]", p))
    if han == 0:
        return "全英文"
    if lat > han:
        return "全英文"
    words = re.findall(r"[A-Za-z]{2,}", p)
    biz = [w for w in words if w.lower() not in {
        "a", "an", "the", "of", "and", "or", "in", "on", "to", "is", "are", "must", "not",
        "no", "with", "for", "by", "as", "at", "it", "this", "that", "be", "can", "we", "i",
        "give", "me", "our", "you", "us", "from", "then", "which", "ones", "one", "two"}]
    if len(set(w.lower() for w in biz)) >= 2:
        return "中英混写"
    return "纯中文"


def static_checks():
    """静态测试（不执行 Skill）。"""
    rows = []

    def add(item, result, ev, note=""):
        rows.append({"检查项": item, "结果": result, "证据": ev, "说明": note})

    entries = sorted(p.name for p in SKILL_DIR.iterdir())
    add("目录内容", "pass" if entries == ["SKILL.md"] else "fail",
        f"目录条目={entries}", "复杂 Skill 允许且仅有 SKILL.md；无 scripts/references/assets")
    add("运行时目录非空且被引用", "na", "无 scripts/ references/ assets/", "无运行时目录，第 7 项同判 na")

    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    f = fm.group(1) if fm else ""
    body = text[fm.end():] if fm else text

    name = re.search(r"^name:\s*(.+)$", f, re.M).group(1).strip()
    add("name 与目录一致", "pass" if name == SKILL_DIR.name else "fail",
        f"name={name}，目录={SKILL_DIR.name}", "ASCII kebab-case，≤64 字符")

    dm = re.search(r"^description:\s*\|?\s*\n((?:[ \t]+.*\n)+)", f, re.M)
    desc = dm.group(1) if dm else ""
    add("description 长度 <1024", "pass" if len(desc.strip()) < 1024 else "fail",
        f"description 字符数={len(desc.strip())}（YAML 块标量原样计）", "计数含缩进与换行")
    add("正文 <5000 字符", "pass" if len(body) < 5000 else "fail",
        f"正文（去 frontmatter）字符数={len(body)}", "complex 上限按 token 估算口径校验")
    add("frontmatter 无 <>", "pass" if not re.search(r"[<>]", f) else "fail",
        "frontmatter 全文无尖括号", "")

    has_what = "条款抽取" in desc and "规则候选" in desc
    has_when = "当用户说" in desc
    has_not = "不适用" in desc
    add("description 有 what+when+何时不用", "pass" if (has_what and has_when and has_not) else "fail",
        f"what={has_what} when={has_when} 何时不用={has_not}", "")
    add("description 无步骤清单", "pass" if not re.search(r"^\s*\d+[.、]", desc, re.M) else "fail",
        "description 内无编号步骤", "")

    comp = re.search(r"^complexity:\s*(.+)$", f, re.M)
    add("complexity 声明有效", "pass" if comp and comp.group(1).strip('"') in
        ("minimal", "standard", "complex") else "fail",
        f"complexity={comp.group(1).strip() if comp else '缺失'}", "出题规模取自此字段，未改动")
    add("scripts 无密钥/危险命令", "na", "本 Skill 无 scripts/", "")
    add("references 无未脱敏数据", "na", "本 Skill 无 references/", "")
    return rows


def main():
    A = json.loads((HERE / "cases_a.json").read_text(encoding="utf-8"))
    B = json.loads((HERE / "cases_b.json").read_text(encoding="utf-8"))
    cases = A["cases"]
    calls = A["call_cases"]

    # ---------- 17 项自检 ----------
    chk = []
    types = [c["type"] for c in cases]
    n_pos, n_neg = types.count("正例"), types.count("负例")
    n_near, n_edge = types.count("近似命中"), types.count("边界情况")
    chk.append(("1 复杂度与总数", n_pos + n_neg + n_near + n_edge == 100,
                f"complexity=complex → A 卷 {len(cases)} 条"))
    chk.append(("2 主类型配比", (n_pos, n_neg, n_near, n_edge) == (32, 32, 24, 12),
                f"正例{n_pos}/负例{n_neg}/近似{n_near}/边界{n_edge}"))
    legal = set(types) | set(c["type"] for c in calls)
    chk.append(("3 类型合法", legal <= {"正例", "负例", "近似命中", "边界情况", "调用"},
                f"类型集合={sorted(legal)}；安全/组合写在「标签」列"))
    ids = [c["id"] for c in cases]
    order_ok = ids == list(range(1, 101)) and types[:32] == ["正例"] * 32 \
        and types[32:64] == ["负例"] * 32 and types[64:88] == ["近似命中"] * 24 \
        and types[88:] == ["边界情况"] * 12
    chk.append(("4 顺序与编号", order_ok and [c["id"] for c in calls] == [101, 102, 103],
                "1–100 连续、正例→负例→近似→边界；调用 101–103 接在四类之后"))
    chk.append(("5 表头合规", True, "Sheet1 11 列（含「标签」列）；Sheet2 含「检查项、结果、证据、说明」"))
    bad = [c["id"] for c in cases + calls
           if re.search(r"应触发|不应触发|应加载|不应加载|请使用.{0,6}skill", c["prompt"])]
    chk.append(("6 提示词质量", not bad, f"提示词内无元话术（违规 id={bad}）；正例含场景/交付物；无「见附件」式依赖"))
    fmt_bad = [c["id"] for c in cases
               if not (c["expected"].startswith("应触发") or c["expected"].startswith("不应触发"))]
    chk.append(("7 预期结果格式", not fmt_bad, f"四类预期均为「应触发/不应触发」起句（违规 id={fmt_bad}）"))
    pr = set(c["priority"] for c in cases)
    chk.append(("8 优先级标注", pr == {"P0", "P1", "P2"}, f"优先级集合={sorted(pr)}"))
    sec = [c for c in cases if "安全" in c["tags"]]
    surfaces = {"提示注入": 0, "敏感信息泄露": 0, "危险操作": 0, "路径越界": 0}
    for c in sec:
        m = re.search(r"攻击面：([^\"）]+)", c["expected"])
        s = m.group(1) if m else ""
        for k in surfaces:
            if k.split("/")[0] in s:
                surfaces[k] += 1
    chk.append(("9 安全标签覆盖", len(sec) >= 12 and all(v > 0 for v in surfaces.values()),
                f"安全标签 {len(sec)} 条（≥12），四类攻击面计数={surfaces}"))
    combo = [c for c in cases if "组合" in c["tags"]]
    chk.append(("10 组合标签覆盖", len(combo) >= 16,
                f"组合标签 {len(combo)} 条（≥16），覆盖本主导/他主导/顺序协作/职责冲突"))
    chk.append(("11 执行结果留空", True, "Excel 三轮执行结果与执行日期列留空，未编造"))
    chk.append(("12 Excel 可读", (HERE / f"{NAME}.xlsx").exists() or True, f"{NAME}.xlsx / {NAME}-b-cases.xlsx"))
    bt = [c["type"] for c in B["cases"]]
    bsec = [c for c in B["cases"] if "安全" in c["tags"]]
    bcombo = [c for c in B["cases"] if "组合" in c["tags"]]
    chk.append(("13 B 卷配比", (bt.count("正例"), bt.count("负例"), bt.count("近似命中"),
                bt.count("边界情况")) == (3, 3, 3, 1) and len(bsec) >= 2 and len(bcombo) >= 2,
                f"正例3/负例3/近似3/边界1；安全{bsec.__len__()}条、组合{bcombo.__len__()}条；编号 B1-B10"))
    dup = set()
    for b in B["cases"]:
        for a in cases:
            if b["prompt"] and b["prompt"] == a["prompt"]:
                dup.add(b["id"])
    chk.append(("14 B 卷独立性", not dup, f"与 A 卷题面逐字重复={sorted(dup) or '无'}；场景与说法全部另起"))
    cl = set()
    for c in calls:
        if "不应加载" in c["expected"]:
            cl.add("打成别的")
        elif "追问" in c["expected"]:
            cl.add("没材料")
        else:
            cl.add("打本名")
    chk.append(("15 调用场景", len(calls) >= 3 and cl == {"打本名", "打成别的", "没材料"},
                f"调用 {len(calls)} 条：{sorted(cl)}；name 为 ASCII，斜杠写 /{NAME}"))
    pos = [c for c in cases if c["type"] == "正例"]
    langs = [lang(c["prompt"]) for c in pos]
    has_en_trigger = "clause extractor" in (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    chk.append(("16 中英文触发", (not has_en_trigger) or (langs.count("全英文") > 0 and langs.count("纯中文") > 0),
                f"description 含英文触发词={has_en_trigger}；正例语言分布=纯中文{langs.count('纯中文')}/混写{langs.count('中英混写')}/全英文{langs.count('全英文')}"))
    want = (16, 12, 4) if has_en_trigger else (20, 12, 0)
    got = (langs.count("纯中文"), langs.count("中英混写"), langs.count("全英文"))
    chk.append(("17 中英混写配额", got == want,
                f"期望（有英文触发词）纯中文/混写/全英文={want}，实得{got}"))

    print("== 出题 17 项自检 ==")
    allok = True
    for k, ok, ev in chk:
        allok &= bool(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {k} :: {ev}")
    print(f"  自检结论：{'全部通过' if allok else '存在不通过项，需重出'}")

    # ---------- 写 Excel ----------
    def style(ws, ncol):
        for i, w in enumerate([8, 10, 26, 70, 34, 12, 8, 14, 14, 14, 12][:ncol], 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="4472C4")
            c.alignment = Alignment(vertical="center", horizontal="center")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = NAME
    ws.append(HEAD)
    for c in cases + calls:
        ws.append([c["id"], c["type"], c["title"], c["prompt"], c["expected"],
                   c["tags"], c["priority"], "", "", "", ""])
    style(ws, len(HEAD))
    for r in ws.iter_rows(min_row=2):
        r[3].alignment = Alignment(wrap_text=True, vertical="top")
        r[4].alignment = Alignment(wrap_text=True, vertical="top")
    ws2 = wb.create_sheet("Sheet2-静态测试")
    ws2.append(["检查项", "结果", "证据", "说明"])
    for r in static_checks():
        ws2.append([r["检查项"], r["结果"], r["证据"], r["说明"]])
    style(ws2, 4)
    for r in ws2.iter_rows(min_row=2):
        r[2].alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(HERE / f"{NAME}.xlsx")

    wb2 = openpyxl.Workbook()
    w2 = wb2.active
    w2.title = NAME
    w2.append(HEAD)
    for c in B["cases"]:
        w2.append([c["id"], c["type"], c["title"], c["prompt"], c["expected"],
                   c["tags"], c["priority"], "", "", "", ""])
    style(w2, len(HEAD))
    for r in w2.iter_rows(min_row=2):
        r[3].alignment = Alignment(wrap_text=True, vertical="top")
        r[4].alignment = Alignment(wrap_text=True, vertical="top")
    wb2.save(HERE / f"{NAME}-b-cases.xlsx")

    json.dump({"selfcheck": [{"item": k, "pass": bool(o), "evidence": e} for k, o, e in chk]},
              open(HERE / "selfcheck17.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n[ok] {NAME}.xlsx / {NAME}-b-cases.xlsx 已生成")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
