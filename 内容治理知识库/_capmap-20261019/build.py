# -*- coding: utf-8 -*-
"""校验 + 生成写入用的 ndjson / JSON payload"""
import json, sys, collections
sys.path.insert(0, '.')
from rows_a import ROWS_A
from rows_b import ROWS_B
from rows_c import ROWS_C
from rows_base import BASE_ROWS

T1 = ROWS_A + ROWS_B + ROWS_C
L1_OK = {"数据通道","分析判定","交互编排","知识治理","推送投放","运营交付","底座"}
ST_OK = {"live","limited","degraded","broken","gap","not_built"}
TY_OK = {"实测","构造"}

errs = []
ids = collections.Counter()
for r in T1:
    ids[r["ID"]] += 1
    for k in ["ID","L1","L2","Q","用法","案例","类型","证据","代码","边界","状态"]:
        if not str(r.get(k) or "").strip():
            errs.append(f"{r['ID']} 空字段 {k}")
    if r["L1"] not in L1_OK: errs.append(f"{r['ID']} L1底座非法：{r['L1']}")
    if r["状态"] not in ST_OK: errs.append(f"{r['ID']} 状态非法：{r['状态']}")
    if r["类型"] not in TY_OK: errs.append(f"{r['ID']} 案例类型非法：{r['类型']}")
    # 硬惯例 1：构造 ⇒ 证据必须是「无」且案例含「未实际验证」
    if r["类型"] == "构造":
        if r["证据"] != "无": errs.append(f"{r['ID']} 构造件证据必须是「无」，实际：{r['证据'][:20]}")
        if "未实际验证" not in r["案例"]: errs.append(f"{r['ID']} 构造件案例缺「未实际验证」")
    else:
        if r["证据"] == "无": errs.append(f"{r['ID']} 实测件证据不许是「无」")
    # 硬惯例 2：业务问题以？结尾
    if not r["Q"].rstrip().endswith("？"): errs.append(f"{r['ID']} L3业务问题未以？结尾")
    # 硬惯例 3：代码引用要指到行号或用；分隔文件
    if ":" not in r["代码"] and ";" not in r["代码"]:
        errs.append(f"{r['ID']} 代码引用无行号/多文件")
    if ":;" in r["代码"] or ";:" in r["代码"]:
        errs.append(f"{r['ID']} 代码引用有格式错误 ':;'")

for i, c in ids.items():
    if c > 1: errs.append(f"能力ID 重复：{i} ×{c}")

# 底座健康
BF = ["组件","额度","影响","状态","代码","实测","风险"]
for r in BASE_ROWS:
    for k in BF:
        if not str(r.get(k) or "").strip(): errs.append(f"[底座] {r['组件'][:16]} 空字段 {k}")
    if r["状态"] not in {"正常","降级","故障"}: errs.append(f"[底座] {r['组件'][:16]} 状态非法：{r['状态']}")

print(f"表① 行数 {len(T1)} / 表② 行数 {len(BASE_ROWS)}")
print("L1 分布:", dict(collections.Counter(r["L1"] for r in T1)))
print("状态分布:", dict(collections.Counter(r["状态"] for r in T1)))
print("案例类型:", dict(collections.Counter(r["类型"] for r in T1)))
print("底座状态:", dict(collections.Counter(r["状态"] for r in BASE_ROWS)))
print("关键项 True:", [r["ID"] for r in T1 if r["关键"]])
print("字段长度均值:")
for k,kk in [("L2","L2"),("Q","Q"),("用法","用法"),("案例","案例"),("证据","证据"),("代码","代码"),("边界","边界")]:
    L=[len(r[kk]) for r in T1]; print(f"  {k:4s} avg={sum(L)//len(L):4d} max={max(L):4d}")

if errs:
    print(f"\n❌ 校验失败 {len(errs)} 条：")
    for e in errs[:40]: print("  -", e)
    sys.exit(1)

# 输出前统一清洗：飞书文本格不渲染 markdown，** 会变成字面星号（旧表 174 行只有 2 处 **）
def clean(s):
    return str(s).replace("**", "")

t1_records = [{
    "能力ID": r["ID"], "L1底座": r["L1"], "L2入口": clean(r["L2"]), "L3业务问题": clean(r["Q"]),
    "使用方法": clean(r["用法"]), "案例": clean(r["案例"]), "案例类型": r["类型"], "案例证据": clean(r["证据"]),
    "代码引用": clean(r["代码"]), "边界限制": clean(r["边界"]), "状态": r["状态"],
    "关键项": bool(r["关键"]), "as_of": "2026-10-19",
} for r in T1]

t2_records = [{
    "组件": clean(r["组件"]), "额度或余量": clean(r["额度"]), "失效影响": clean(r["影响"]), "当前状态": r["状态"],
    "代码引用": clean(r["代码"]), "最近实测": r["实测"], "已知风险": clean(r["风险"]),
} for r in BASE_ROWS]

with open("t1_shouheng_records.json","w",encoding="utf-8") as f:
    json.dump(t1_records,f,ensure_ascii=False,indent=1)
with open("t2_shouheng_records.json","w",encoding="utf-8") as f:
    json.dump(t2_records,f,ensure_ascii=False,indent=1)
with open("t1_shouheng.ndjson","w",encoding="utf-8") as f:
    for r in t1_records: f.write(json.dumps(r,ensure_ascii=False)+"\n")
with open("t2_shouheng.ndjson","w",encoding="utf-8") as f:
    for r in t2_records: f.write(json.dumps(r,ensure_ascii=False)+"\n")
print("\n✅ 校验通过，已生成 t1_shouheng-records.json / t2_shouheng-records.json / *.ndjson")
