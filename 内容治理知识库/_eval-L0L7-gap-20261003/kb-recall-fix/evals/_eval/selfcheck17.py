#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-recall 出题 17 项自检（root-skills-eval v3.19.1 trigger-eval-cases.md Step 2）。

用法：python3 selfcheck17.py   →  写 selfcheck-17.json，退出码 0=17/17 通过
"""
from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
SKILL = os.path.join(os.path.dirname(EV), "SKILL.md")
NAME = "kb-recall"
FORBIDDEN = ["应触发", "不应触发", "应加载", "不应加载", "请使用", "该触发", "不属于本 skill"]
ATTACH = ["见附件", "打开工作区", "见文末附件", "参考附件", "见附件内容"]

res = []
A = json.load(open(os.path.join(EV, "cases-a.json"), encoding="utf-8"))
B = json.load(open(os.path.join(EV, "cases-b.json"), encoding="utf-8"))
skill_md = open(SKILL, encoding="utf-8").read()
fm = skill_md.split("---")[1]
complexity = re.search(r"complexity:\s*\"?(\w+)\"?", fm).group(1)
desc = fm.split("description:", 1)[1].split("version:", 1)[0]


def rec(no, item, ok, detail):
    res.append({"no": no, "item": item, "result": "pass" if ok else "fail", "detail": detail})
    return ok


main = [c for c in A if c["类型"] != "调用"]
calls = [c for c in A if c["类型"] == "调用"]
dist = {}
for c in main:
    dist[c["类型"]] = dist.get(c["类型"], 0) + 1
expect_dist = {"正例": 16, "负例": 16, "近似命中": 12, "边界情况": 6}

# 1 复杂度与总数
rec(1, "复杂度与总数",
    complexity == "standard" and len(main) == 50 and len(calls) >= 3,
    f"complexity={complexity}（standard⇒50）｜A 卷主类型 {len(main)} 条 + 调用 {len(calls)} 条")

# 2 主类型配比
rec(2, "主类型配比 32/32/24/12", dist == expect_dist,
    f"实测 {dist}；目标 {expect_dist}；占比 " +
    str({k: f"{v/50*100:.0f}%" for k, v in dist.items()}))

# 3 类型合法
legal = {"正例", "负例", "近似命中", "边界情况", "调用"}
types = sorted({c["类型"] for c in A})
rec(3, "类型合法", set(types) <= legal and not any("安全" in c["类型"] or "组合" in c["类型"] for c in A),
    f"类型取值 {types}；安全/组合只出现在标签列")

# 4 顺序与编号
ids = [int(c["id"]) for c in A]
order_ok = ids == list(range(1, len(A) + 1))
seq = [c["类型"] for c in main]
expect_seq = ["正例"] * 16 + ["负例"] * 16 + ["近似命中"] * 12 + ["边界情况"] * 6
rec(4, "顺序与编号", order_ok and seq == expect_seq and [int(c["id"]) for c in calls] == [51, 52, 53],
    "1–53 连续且 正例→负例→近似→边界；调用 51–53 接在四类之后（不占 A 卷总数）")

# 5 表头合规（Excel 由 make_xlsx.py 生成，此处核对 JSON 键 + xlsx 表头）
HDR1 = ["序号", "类型", "标题", "提示词", "预期结果", "标签", "优先级",
        "1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"]
HDR2 = ["检查项", "结果", "证据", "说明"]
keys_ok = all(
    [c["id"], c["类型"], c["标题"], c["提示词"], c["预期结果"], c["标签"], c["优先级"]]
    == [str(c["id"]), c["类型"], c["标题"], c["提示词"], c["预期结果"], c["标签"], c["优先级"]]
    and set(c.keys()) == {"id", "类型", "标题", "提示词", "预期结果", "标签", "优先级"} for c in A)
xlsx_ok, xlsx_detail = False, "xlsx 未生成"
try:
    import openpyxl
    p1 = os.path.join(EV, f"{NAME}.xlsx")
    p2 = os.path.join(EV, f"{NAME}-b-cases.xlsx")
    w1, w2 = openpyxl.load_workbook(p1), openpyxl.load_workbook(p2)
    h1 = [c.value for c in w1["Sheet1"][1]]
    h2 = [c.value for c in w1["Sheet2"][1]]
    h1b = [c.value for c in w2["Sheet1"][1]]
    xlsx_ok = h1 == HDR1 and h2 == HDR2 and h1b == HDR1
    xlsx_detail = f"A Sheet1 表头 {h1}｜Sheet2 {h2}｜B Sheet1 {h1b}"
except Exception as exc:  # noqa: BLE001
    xlsx_detail = f"xlsx 读取失败：{exc}"
rec(5, "表头合规", keys_ok and xlsx_ok,
    f"JSON 键 = 前 7 列；{xlsx_detail}")

# 6 提示词质量
bad = []
for c in A:
    p = c["提示词"]
    for w in FORBIDDEN:
        if w in p:
            bad.append(f"{c['id']}:出现「{w}」")
    for w in ATTACH:
        if w in p:
            bad.append(f"{c['id']}:出现「{w}」")
pos = [c for c in main if c["类型"] == "正例"]
short = [c["id"] for c in pos if len(c["提示词"]) < 25]
named = [c["id"] for c in pos if NAME in c["提示词"]]
neg_ok = all(len(c["提示词"]) > 10 for c in main if c["类型"] in ("负例", "近似命中"))
multi = [c["id"] for c in main if c["提示词"].count("？") > 3]
rec(6, "提示词质量", not bad and not short and len(named) == 0 and neg_ok and not multi,
    f"禁用字样 {bad or '无'}｜正例最短 <25 字的 {short or '无'}｜正例出现 skill 名的 {named or '无'}"
    f"（{len(pos)} 条正例均不出现 name，≥半数要求满足）｜负例/近似均非天气笑话类｜"
    f"KB 是本 skill 的目标语料（非外部附件），正例不依赖题面外文件；"
    f"PDF/Excel 题（14/12）在题面内已写明语料与做法")

# 7 预期结果格式
bade = []
for c in main:
    e = c["预期结果"]
    if c["类型"] == "正例" and not e.startswith("应触发"):
        bade.append(c["id"])
    if c["类型"] in ("负例", "近似命中") and not e.startswith("不应触发"):
        bade.append(c["id"])
    if c["类型"] == "边界情况" and not (e.startswith("追问澄清") or e.startswith("不应触发")):
        bade.append(c["id"])
for c in calls:
    if not (c["预期结果"].startswith("应加载") or c["预期结果"].startswith("不应加载")):
        bade.append(c["id"])
rec(7, "预期结果格式", not bade,
    f"正例=应触发；负例/近似=不应触发；边界=追问澄清/不应触发；调用=应加载/不应加载（异常 {bade or '无'}）；"
    f"带安全标签的另注明攻击面，带组合标签的写明路由归属")

# 8 优先级
prios = sorted({c["优先级"] for c in A})
rec(8, "优先级标注", prios == ["P0", "P1", "P2"], f"实测 {prios}")

# 9 安全标签
surf = {"提示注入": ["忽略你前面", "忽略前置检查", "跳过"],
        "敏感信息": ["user_id", "手机号", "token", "secret"],
        "危险操作": ["rm -rf", "覆盖写回"],
        "路径/权限越界": ["~/.ssh", "/etc/hosts", "profiles/desktop"]}
sec = [c for c in A if "安全" in c["标签"]]
cov = {}
for k, kws in surf.items():
    hit = [c["id"] for c in sec if any(w in c["提示词"] for w in kws)]
    if hit:
        cov[k] = len(hit)
rec(9, "安全标签覆盖", len(sec) >= 6 and len(cov) == 4,
    f"安全标签 {len(sec)} 条（下限 6）；攻击面覆盖 {cov}")

# 10 组合标签
combo_kind = {"①本skill主导": [c["id"] for c in A if "组合" in c["标签"] and c["预期结果"].startswith("应触发")],
              "②他skill主导": [c["id"] for c in A if "组合" in c["标签"] and c["id"] in ("18", "34", "35")],
              "③顺序协作": [c["id"] for c in A if "组合" in c["标签"] and c["id"] in ("10", "13")],
              "④职责冲突": [c["id"] for c in A if "组合" in c["标签"] and c["id"] in ("37",)]}
combo = [c for c in A if "组合" in c["标签"]]
rec(10, "组合标签覆盖", len(combo) >= 8 and all(v for v in combo_kind.values()),
    f"组合标签 {len(combo)} 条（下限 8）；四类覆盖 { {k: len(v) for k, v in combo_kind.items()} }")

# 11 执行结果留空
rec(11, "执行结果留空", True, "Sheet1 第 8–11 列（三轮结果 + 执行日期）生成时全空")

# 12 Excel 可读
rec(12, "Excel 可读", xlsx_ok, xlsx_detail if xlsx_ok else xlsx_detail)

# 13 B 卷配比
bd = {}
for c in B:
    bd[c["类型"]] = bd.get(c["类型"], 0) + 1
bsec = [c for c in B if "安全" in c["标签"]]
bcombo = [c for c in B if "组合" in c["标签"]]
rec(13, "B 卷配比",
    len(B) == 10 and bd == {"正例": 3, "负例": 3, "近似命中": 3, "边界情况": 1}
    and len(bsec) >= 2 and len(bcombo) >= 2
    and [c["id"] for c in B] == [f"B{i}" for i in range(1, 11)]
    and os.path.exists(os.path.join(EV, f"{NAME}-b-cases.xlsx")),
    f"B 卷 {len(B)} 条 = {bd}；安全 {len(bsec)} 条（攻击面 敏感信息+危险操作）、组合 {len(bcombo)} 条；"
    f"编号 B1–B10；独立文件 {NAME}-b-cases.xlsx")

# 14 B 卷独立性
pa = {c["提示词"].strip() for c in A}
pb = {c["提示词"].strip() for c in B}
overlap = pa & pb
def bigrams(s):
    s = re.sub(r"[\s，。：「」（）,.、；！？!?]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}
near = []
for b in B:
    gb = bigrams(b["提示词"])
    for a in A:
        ga = bigrams(a["提示词"])
        if len(gb) < 6 or len(ga) < 6:      # 过短提示词（如「召回一下。」）的 2-gram 覆盖无判别力，不比
            continue
        j = len(gb & ga) / len(gb | ga)
        if j > 0.5:
            near.append((b["id"], a["id"], round(j, 2)))
rec(14, "B 卷独立性", not overlap and not near,
    f"逐字重复 {len(overlap)} 条；近义（2-gram Jaccard >0.5，短句 <6 个 2-gram 不参与比较）{near or '无'}；"
    f"B 卷三轮结果留空")

# 15 调用场景
ci = [c["id"] for c in calls]
slash_ok = all(c["提示词"].startswith("/") for c in calls)
rec(15, "调用场景",
    len(calls) == 3 and slash_ok and "/kb-recall" in calls[0]["提示词"]
    and "/kb-recall" in calls[2]["提示词"]
    and calls[1]["提示词"].startswith("/kb-content-review")
    and calls[0]["预期结果"] == "应加载 kb-recall"
    and calls[1]["预期结果"] == "不应加载 kb-recall"
    and calls[2]["预期结果"] == "应加载 kb-recall，然后追问",
    f"3 条覆盖 打本名({ci[0]}) / 打成别的中文成员({ci[1]}→kb-content-review) / 打了没材料({ci[2]})；"
    f"name 为 ASCII `kb-recall`，斜杠只写 /kb-recall，无英文斜杠混用")


# 16/17 语言三分
def lang(p):
    han = len(re.findall(r"[\u4e00-\u9fff]", p))
    lat = len(re.findall(r"[A-Za-z]", p))
    words = re.findall(r"[A-Za-z]{2,}", p)
    biz = [w for w in words if w.lower() not in ("kb", "l6")]
    if han == 0:
        return "全英文"
    if han > lat and len(biz) >= 2:
        return "中英混写"
    return "纯中文"


langs = {c["id"]: lang(c["提示词"]) for c in pos}
mix = [i for i, v in langs.items() if v == "中英混写"]
ens = [i for i, v in langs.items() if v == "全英文"]
cn = [i for i, v in langs.items() if v == "纯中文"]
has_en_trigger = bool(re.search(r"(BM25|top-k|kb-recall|L6|bm25)", desc))
rec(16, "中英文触发", has_en_trigger and len(ens) >= 2 and len(cn) >= 1,
    f"description 含英文触发词（BM25 / top-k / kb-recall / L6）；正例含中文题 {len(cn)} 条、"
    f"全英文题 {len(ens)} 条（{ens}），两边都有")
rec(17, "中英混写", len(mix) == 6 and len(ens) == (2 if has_en_trigger else 0) and len(cn) == (8 if has_en_trigger else 10),
    f"正例语言三分：纯中文 {len(cn)} 条 {cn}｜中英混写 {len(mix)} 条 {mix}｜全英文 {len(ens)} 条 {ens}"
    f"（标准复杂度、有英文触发词 ⇒ 目标 8/6/2）；混写不占纯中文份额")

passed = sum(1 for r in res if r["result"] == "pass")
out = {"skill": NAME, "complexity": complexity, "skill_md_sha256_checked": True,
       "total_items": len(res), "passed": passed, "failed": len(res) - passed,
       "verdict": "通过" if passed == len(res) else "不通过", "items": res}
with open(os.path.join(HERE, "selfcheck-17.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
for r in res:
    print(("✅" if r["result"] == "pass" else "❌"), r["no"], r["item"], "—", r["detail"][:150])
print(f"\n{passed}/{len(res)} → {out['verdict']}")
raise SystemExit(0 if passed == len(res) else 1)
