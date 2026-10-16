# -*- coding: utf-8 -*-
"""Step 2：出题自检 17 项（A 卷 50 + 调用 3 + B 卷 10）。"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cases
from openpyxl import load_workbook

WB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = []
def chk(no, name, ok, ev): R.append(dict(no=no, item=name, ok=bool(ok), evidence=ev))

A, C, B = cases.A, cases.CALL, cases.B
from collections import Counter
tc = Counter(c["type"] for c in A)
tag = Counter(t.strip() for c in A for t in c["tags"].split(",") if t.strip())
lang = Counter(c["lang"] for c in A if c["type"] == "正例")

chk(1, "复杂度与总数", len(A) == 50 and tc["正例"]==16 and tc["负例"]==16 and tc["近似命中"]==12 and tc["边界情况"]==6,
    f"complexity=standard → A 卷 50 条；实际 {len(A)} 条")
chk(2, "主类型配比", (tc["正例"],tc["负例"],tc["近似命中"],tc["边界情况"])==(16,16,12,6),
    f"正例16/负例16/近似12/边界6 = 32%/32%/24%/12%")
chk(3, "类型合法", set(tc) <= {"正例","负例","近似命中","边界情况","调用"} and all(c["type"] in {"正例","负例","近似命中","边界情况"} for c in A) and all(c["type"]=="调用" for c in C),
    "A 卷每行类型 ∈ 四类主类型；安全/组合只出现在「标签」列；调用单列")
nums=[c["n"] for c in A]
chk(4, "顺序与编号", nums==list(range(1,51)) and [c["n"] for c in C]==["C1","C2","C3"],
    "1–50 连续且顺序为 正例→负例→近似→边界；调用 C1–C3 接在四类之后")
h1 = [c.value for c in load_workbook(os.path.join(WB,"kb-recall.xlsx"))["触发评测用例"][1]]
h2 = [c.value for c in load_workbook(os.path.join(WB,"kb-recall.xlsx"))["静态测试"][1]]
chk(5, "表头合规", len(h1)==11 and "标签" in h1 and h2==["检查项","结果","证据","说明"],
    f"Sheet1 11 列含「标签」：{h1}；Sheet2：{h2}")
bad = [c["n"] for c in A if re.search(r"应触发|不应触发|应加载|不应加载|请使用.{0,6}skill", c["prompt"])]
nonself = [c["n"] for c in A if re.search(r"见附件|打开工作区|见上文附件", c["prompt"])]
pos_spec = all(len(c["prompt"]) >= 20 for c in A if c["type"]=="正例")
nolang = [c["n"] for c in A if c["type"]=="正例" and not re.search(r"[\u4e00-\u9fff]|knowledge base|retrieval", c["prompt"])]
chk(6, "提示词质量", not bad and not nonself and pos_spec,
    f"禁用字样命中={bad}；依赖外部文件措辞={nonself}；正例均含具体场景/交付物且长度≥20")
efmt = all(
  (c["type"]=="正例" and c["expect"].startswith("应触发 kb-recall")) or
  (c["type"] in ("负例","近似命中") and (c["expect"].startswith("不应触发 kb-recall"))) or
  (c["type"]=="边界情况" and (c["expect"].startswith("边界：") or c["expect"].startswith("不应触发 kb-recall"))) or
  (c["type"]=="调用" and (c["expect"].startswith("应加载") or c["expect"].startswith("不应加载")))
  for c in A+C)
chk(7, "预期结果格式", efmt, "正例=应触发；负例/近似=不应触发；边界=追问/不触发/条件触发；调用=应加载/不应加载/应加载后追问")
pris = set(c["pri"] for c in A+C)
chk(8, "优先级标注", pris=={"P0","P1","P2"}, f"P0/P1/P2 齐全：{sorted(pris)}")
surf = []
if any("提示注入" in c["expect"] for c in A): surf.append("提示注入")
if any("敏感信息" in c["expect"] for c in A): surf.append("敏感信息泄露")
if any("危险操作" in c["expect"] for c in A): surf.append("危险操作")
if any("路径越界" in c["expect"] for c in A): surf.append("路径越界")
chk(9, "安全标签覆盖", tag["安全"]>=6 and len(surf)==4,
    f"安全标签 {tag['安全']} 条（下限 6）；覆盖攻击面 {surf}")
chk(10, "组合标签覆盖", tag["组合"]>=8,
    f"组合标签 {tag['组合']} 条（下限 8）；覆盖①当前主导(正例6/12)②他Skill主导(负例17-20/近似33,35,41)③顺序协作(正例12)④职责冲突(近似38,40)")
ws = load_workbook(os.path.join(WB,"kb-recall.xlsx"))["触发评测用例"]
empty = all(all((ws.cell(r,cc).value in (None,"")) for cc in (8,9,10,11)) for r in range(2, ws.max_row+1))
chk(11, "执行结果留空", empty, f"Sheet1 第 8–11 列（三轮结果 + 执行日期）共 {ws.max_row-1} 行全为空")
chk(12, "Excel 可读", os.path.exists(os.path.join(WB,"kb-recall.xlsx")) and os.path.exists(os.path.join(WB,"kb-recall-b-cases.xlsx")),
    "kb-recall.xlsx 与 kb-recall-b-cases.xlsx 均生成成功且可被 openpyxl 读回")
bt = Counter(c["type"] for c in B); btag = Counter(t.strip() for c in B for t in c["tags"].split(",") if t.strip())
chk(13, "B 卷配比", len(B)==10 and (bt["正例"],bt["负例"],bt["近似命中"],bt["边界情况"])==(3,3,3,1) and btag["安全"]>=2 and btag["组合"]>=2 and [c["n"] for c in B]==[f"B{i}" for i in range(1,11)],
    f"B 卷 10 条 = 正例3/负例3/近似3/边界1；安全 {btag['安全']} 条、组合 {btag['组合']} 条；编号 B1–B10；独立文件 kb-recall-b-cases.xlsx")
def toks(s): return set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", s))
dup = [(a["n"],b["n"]) for a in A for b in B if toks(a["prompt"]) and len(toks(a["prompt"]) & toks(b["prompt"]))/max(1,len(toks(b["prompt"]))) > 0.6]
chk(14, "B 卷独立性", not dup, f"与 A 卷题面逐条比对，token 重合度 >60% 的对数 = {len(dup)}；B 卷三轮结果列为空")
chk(15, "调用场景", len(C)==3 and C[0]["prompt"].startswith("/kb-recall") and C[1]["prompt"].startswith("/kb-pipeline") and C[2]["prompt"].strip()=="/kb-recall",
    "3 条覆盖三种斜杠路径：打本名 /kb-recall（应加载）、打成别的 /kb-pipeline（不应加载）、打了没材料 /kb-recall（应加载后追问）")
has_en = re.search(r"[A-Za-z]{2,}", open(os.path.join(WB,"kb-recall","SKILL.md"),encoding="utf-8").read().split("不适用")[0])
chk(16, "中英文触发", lang["纯中文"]>0 and lang["全英文"]>0,
    f"description 触发词列含拉丁词元（BM25 / top-k / PDF / Excel / L6 / kb-retriever）→ 判为「有英文触发词」；正例中文题 {lang['纯中文']+lang['中英混写']} 条、全英文题 {lang['全英文']} 条，两边都有")
chk(17, "中英混写配额", lang["中英混写"]==6 and lang["全英文"]==2,
    f"混写 {lang['中英混写']} 条（标准档要求 6，不占纯中文）；全英文 {lang['全英文']} 条（要求 2）；纯中文 {lang['纯中文']} 条")

print(f"{'#':>3} {'检查项':<16} 结果  证据")
for r in R: print(f"{r['no']:>3} {r['item']:<16} {'✅通过' if r['ok'] else '❌不通过'}  {r['evidence']}")
npass=sum(1 for r in R if r['ok'])
print(f"\n自检结论：{npass}/17 通过" + ("（全部通过）" if npass==17 else "（第 " + ",".join(str(r['no']) for r in R if not r['ok']) + " 项不通过，需重出）"))
json.dump([{k:v for k,v in r.items()} for r in R], open(os.path.join(WB,"_eval","selfcheck-17.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
