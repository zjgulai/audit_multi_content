#!/usr/bin/env python3
"""盲测评分器：把 N 轮判官的 verdicts 汇总成 P/R/F1。

用法：
  python3 score.py verdicts-r1.json verdicts-r2.json [verdicts-r3.json]

verdicts-rN.json 格式： [{"id":"P-eval-1","loads":["root-skills-eval"],"short":"..."}]
口径（与 cases.json 的 target / expected_not 对齐）：
- 正例/调用/边界-有目标：target ∈ loads ⇒ TP，否则 FN
- 期望不加载（近似命中/负例/无目标的边界/跨家族撞车）：target ∉ loads ⇒ TN；若加载了家族成员但非 target ⇒ FP(跨成员)
- 表 A：所有权命中（该接的接上了没） 表 B：严格 FP（该家族该不该被加载）
"""
import json, sys, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
FAMILY = ["root-skills-creator","root-skills-doctor","root-skills-eval","root-skills-opt",
          "root-skills-check","root-skills-manage","root-skills-batch-driver"]

cases = {c["id"]: c for c in json.load(open(os.path.join(HERE,"cases.json")))}

rounds = []
for p in sys.argv[1:]:
    v = json.load(open(p))
    rounds.append({x["id"]: x.get("loads",[]) for x in v})
n_rounds = len(rounds)

own   = defaultdict(lambda: {"tp":0,"fn":0})          # 表 A
strict= defaultdict(lambda: {"tp":0,"fn":0,"fp":0})  # 表 B
unseen= defaultdict(int)
cross = []   # 跨家族撞车逐条
detail = []

for cid, c in cases.items():
    tgt = c.get("target"); fam_target = tgt if (tgt in FAMILY) else None
    for r, R in enumerate(rounds, 1):
        loads = R.get(cid) or []
        fam_loaded = [s for s in loads if s in FAMILY]
        k = cid.split("-")[0]
        if k == "X":
            cross.append((cid, r, tgt, loads, c["type"]))
            continue
        if fam_target:
            hit = fam_target in loads
            own[fam_target]["tp" if hit else "fn"] += 1
            strict[fam_target]["tp" if hit else "fn"] += 1
        else:
            # 期望不加载本家族
            for s in fam_loaded:
                strict[s]["fp"] += 1
        for s in fam_loaded:
            pass

def prf(d):
    p = d["tp"]/(d["tp"]+d["fp"]) if (d["tp"]+d["fp"]) else float('nan')
    r = d["tp"]/(d["tp"]+d["fn"]) if (d["tp"]+d["fn"]) else float('nan')
    f = 2*p*r/(p+r) if (p==p and r==r and (p+r)>0) else float('nan')
    return p, r, f

print(f"轮数={n_rounds}  用例={len(cases)}  判定={len(cases)*n_rounds}")
print("\n=== 表 A：所有权命中（该接的有没有接上）===")
print(f"{'成员':<28}{'应触发':>6}{'TP':>5}{'FN':>4}{'召回':>8}")
ta=0;tt=0
for m in FAMILY:
    d=own[m]; n=d['tp']+d['fn']
    if n==0: continue
    ta+=d['tp']; tt+=n
    print(f"{m:<28}{n:>6}{d['tp']:>5}{d['fn']:>4}{(d['tp']/n if n else 0):>8.2f}")
print(f"{'合计':<28}{tt:>6}{ta:>5}{tt-ta:>4}{(ta/tt if tt else 0):>8.2f}")

print("\n=== 表 B：严格口径（多加载了家族成员就算 FP）===")
print(f"{'成员':<28}{'TP':>5}{'FN':>4}{'FP':>4}{'P':>7}{'R':>7}{'F1':>7}")
for m in FAMILY:
    d=strict[m]
    if d['tp']+d['fn']+d['fp']==0: continue
    p,r,f=prf(d)
    print(f"{m:<28}{d['tp']:>5}{d['fn']:>4}{d['fp']:>4}{p:>7.3f}{r:>7.3f}{f:>7.3f}")

print("\n=== 跨家族撞车逐条（表 C）===")
agg=defaultdict(list)
for cid,r,tgt,loads,typ in cross:
    agg[cid].append(loads)
for cid,rows in sorted(agg.items()):
    tgt=cases[cid].get("target")
    ok=sum(1 for L in rows if tgt and tgt in L)
    print(f"{cid:<6} 期望={tgt:<26} 命中 {ok}/{len(rows)}  实际={rows}")
