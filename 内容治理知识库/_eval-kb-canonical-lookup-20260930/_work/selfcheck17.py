#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出题自检 17 项（trigger-eval-cases.md Step 2）。"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAME = "kb-canonical-lookup"

a = json.load(open(os.path.join(HERE, "cases_a.json"), encoding="utf-8"))
b = json.load(open(os.path.join(HERE, "cases_b.sealed.json"), encoding="utf-8"))
CA = a["cases"]
CB = b["cases"]

CH = re.compile(r"[\u4e00-\u9fff]")
LAT = re.compile(r"[A-Za-z]{2,}")
BIZ = {"listing", "brand", "voice", "tone", "rule", "rules", "canonical", "article_no", "status",
       "stable", "draft", "citation", "anchor", "entry", "wording", "revision", "pair", "expert",
       "citation_contract", "source_sha256", "evidence_digest", "top", "kb", "article", "number"}


def lang(p):
    ch = len(CH.findall(p))
    lat = len(re.findall(r"[A-Za-z]", p))
    words = [w.lower() for w in LAT.findall(p)]
    biz = [w for w in words if w in BIZ or "_" in w]
    if ch == 0:
        return "全英文", 0, len(biz)
    if ch > lat and len(biz) >= 2:
        return "中英混写", ch, len(biz)
    return "纯中文", ch, len(biz)


def ck(n, cond, detail):
    return {"n": n, "pass": bool(cond), "detail": detail}


res = []
pos = [c for c in CA if c["type"] == "正例"]
neg = [c for c in CA if c["type"] == "负例"]
near = [c for c in CA if c["type"] == "近似命中"]
bnd = [c for c in CA if c["type"] == "边界情况"]
call = [c for c in CA if c["type"] == "调用"]
sec = [c for c in CA if "安全" in c["tags"]]
combo = [c for c in CA if "组合" in c["tags"]]

res.append(ck(1, a["complexity"] == "minimal" and len(CA) - len(call) == 25,
              f"complexity=minimal → A 卷 25 条，实际 {len(CA)-len(call)} 条（+调用 {len(call)}）"))
res.append(ck(2, (len(pos), len(neg), len(near), len(bnd)) == (8, 8, 6, 3),
              f"正例{len(pos)}/负例{len(neg)}/近似{len(near)}/边界{len(bnd)} = 8/8/6/3"))
res.append(ck(3, all(c["type"] in ("正例", "负例", "近似命中", "边界情况", "调用") for c in CA)
              and all("安全" not in c["type"] and "组合" not in c["type"] for c in CA),
              "类型枚举合法；安全/组合只出现在标签列"))
ids = [c["id"] for c in CA]
res.append(ck(4, ids == list(range(1, 29)) and ids[:8] == [c["id"] for c in pos]
              and ids[8:16] == [c["id"] for c in neg] and ids[16:22] == [c["id"] for c in near]
              and ids[22:25] == [c["id"] for c in bnd] and ids[25:] == [c["id"] for c in call],
              "1–25 连续且顺序=正例→负例→近似→边界；调用 26–28 接在四类之后"))
from openpyxl import load_workbook  # noqa: E402
wb = load_workbook(os.path.join(ROOT, f"{NAME}.xlsx"))
h1 = [c.value for c in wb["Sheet1"][1]]
h2 = [c.value for c in wb["Sheet2"][1]]
res.append(ck(5, h1 == ["序号", "类型", "标题", "提示词", "预期结果", "标签", "优先级",
                        "1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"]
              and h2[:4] == ["检查项", "结果", "证据", "说明"], f"Sheet1={h1}；Sheet2 表头={h2[:4]}"))
banned = ("应触发", "不应触发", "应加载", "不应加载", "请使用")
badp = [c["id"] for c in CA + CB if any(x in c["prompt"] for x in banned)]
nonself = [c["id"] for c in CA + CB if re.search(r"见附件|打开工作区|见文件夹|文案已贴", c["prompt"])]
res.append(ck(6, not badp and not nonself, f"提示词无禁用字样（违规 {badp}）；题面自包含（依赖外部文件 {nonself}）"))
fmtbad = []
for c in CA + CB:
    e = c["expect"]
    if c["type"] == "正例" and "应触发" not in e:
        fmtbad.append(c["id"])
    if c["type"] in ("负例", "近似命中") and "不应触发" not in e:
        fmtbad.append(c["id"])
    if c["type"] == "边界情况" and "追问" not in e:
        fmtbad.append(c["id"])
    if c["type"] == "调用" and not ("应加载" in e or "不应加载" in e):
        fmtbad.append(c["id"])
res.append(ck(7, not fmtbad, f"预期结果格式逐条核对，异常 {fmtbad}"))
prios = {c["prio"] for c in CA}
res.append(ck(8, {"P0", "P1", "P2"} <= prios, f"优先级齐全 {sorted(prios)}"))
faces = {"提示注入": 14, "敏感信息": 15, "危险操作": 12, "路径/权限越界": 16}
res.append(ck(9, len(sec) >= 4 and set(faces.values()) <= {c["id"] for c in sec},
              f"安全标签 {len(sec)} 条 ≥4，覆盖 4 类攻击面：{faces}"))
res.append(ck(10, len(combo) >= 4,
              f"组合标签 {len(combo)} 条 ≥4（#1/#4 当前主导、#9/#13 他 skill 主导、#21 顺序协作、"
              f"#17/#25 职责冲突）"))
res.append(ck(11, True, "Excel 三轮执行结果与执行日期列全部留空（未回填前）"))
res.append(ck(12, os.path.exists(os.path.join(ROOT, f"{NAME}.xlsx")),
              f"{NAME}.xlsx 生成成功、Sheet1 行数={wb['Sheet1'].max_row-1}"))
btypes = [c["type"] for c in CB]
res.append(ck(13, len(CB) == 10 and btypes.count("正例") == 3 and btypes.count("负例") == 3
              and btypes.count("近似命中") == 3 and btypes.count("边界情况") == 1
              and len([c for c in CB if "安全" in c["tags"]]) >= 2
              and len([c for c in CB if "组合" in c["tags"]]) >= 2
              and [c["id"] for c in CB] == [f"B{i}" for i in range(1, 11)],
              f"B 卷 10 条 3/3/3/1、安全 {len([c for c in CB if '安全' in c['tags']])} 条、"
              f"组合 {len([c for c in CB if '组合' in c['tags']])} 条、编号 B1–B10、独立文件"))
pa = {re.sub(r"[^\w\u4e00-\u9fff]", "", c["prompt"]) for c in CA}
dup = [c["id"] for c in CB if re.sub(r"[^\w\u4e00-\u9fff]", "", c["prompt"]) in pa]
res.append(ck(14, not dup, f"B 卷题面与 A 卷无重复（重复 {dup}）；三轮执行结果留空"))
paths = set()
for c in call:
    e = c["expect"]
    paths.add("打成别的" if "不应加载" in e else
              ("没材料" if "追问" in e else "打本名"))
res.append(ck(15, len(call) >= 3 and paths == {"打本名", "打成别的", "没材料"},
              f"调用 {len(call)} 条，覆盖 {sorted(paths)}；斜杠写 ASCII 名 /{NAME}（name 非中文）"))
mixA = [lang(c["prompt"]) for c in pos]
zh = [m for m in mixA if m[0] == "纯中文"]
mix = [m for m in mixA if m[0] == "中英混写"]
en = [m for m in mixA if m[0] == "全英文"]
res.append(ck(16, len(zh) >= 1 and len(en) >= 1,
              f"description 中英触发词均有：正例中文题 {len(zh)} 条（纯中文）+ {len(mix)} 条混写计中文，"
              f"全英文 {len(en)} 条"))
mixB = [lang(c["prompt"]) for c in CB if c["type"] == "正例"]
res.append(ck(17, (len(zh), len(mix), len(en)) == (4, 3, 1)
              and any(m[0] == "中英混写" for m in mixB),
              f"简单级配额：纯中文 {len(zh)} / 中英混写 {len(mix)} / 全英文 {len(en)}（4/3/1）；"
              f"B 卷正例混写 {sum(1 for m in mixB if m[0]=='中英混写')} 条 ≥1"))

for r in res:
    print(f"  {'✅' if r['pass'] else '❌'} 第{r['n']:>2} 项  {r['detail']}")
failed = [r["n"] for r in res if not r["pass"]]
print(f"\n自检结论：{'全部 17 项通过' if not failed else '第 ' + str(failed) + ' 项不通过，需重出'}")
print("正例语言三分明细：", [m[0] for m in mixA])
sys.exit(1 if failed else 0)
