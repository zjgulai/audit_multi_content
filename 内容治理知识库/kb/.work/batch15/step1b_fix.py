#!/usr/bin/env python3
"""自我更正（本批自己刚写坏的两处）：
1) 台账被追加了 3 行**完全相同的** audit 行（脚本前两次在解析文件名时中断后重跑）→ 去重保留 1 行
2) L1 台账 46 行被写了 provenance，但应是**每资源最新行 1 条 = 15 行** → 撤掉多写的 31 行
两处都是本批自己几分钟前的产物，不是历史行；改动逐项留痕。"""
import json,os,hashlib,collections
L0,L1="kb/l0","kb/l1"; RUN="20260924-1700"
def atomic(p,t):
    x=p+".tmp"; open(x,"w",encoding="utf-8").write(t); open(x,encoding="utf-8").read(); os.replace(x,p)
# ---- 1) 台账去重（只去本批的重复 audit 行）----
MAN=f"{L0}/manifest.jsonl"
rows=[l for l in open(MAN,encoding="utf-8") if l.strip()]
before=len(rows)
seen=set(); out=[]
for l in rows:
    r=json.loads(l)
    if r.get("change")=="restore_provenance_ratified":
        key=json.dumps(r,sort_keys=True)
        if key in seen: continue
        seen.add(key)
    out.append(l)
atomic(MAN,"".join(out))
after=len(out)
print(f"台账去重：{before} → {after}（去掉本批重复 audit 行 {before-after} 行）")
# ---- 2) L1 只留每资源最新行的 provenance ----
l1=[json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl",encoding="utf-8") if l.strip()]
latest_idx={}
for i,r in enumerate(l1): latest_idx[r["resource_id"]]=i
removed=0; kept=0
for i,r in enumerate(l1):
    if r.get("provenance")=="excluded_table_source_link":
        if latest_idx[r["resource_id"]]==i: kept+=1
        else:
            r=dict(r); r.pop("provenance",None); l1[i]=r; removed+=1
atomic(f"{L1}/manifest_l1.jsonl","".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in l1))
print(f"L1 台账 provenance：保留 {kept} 行（每资源最新行），撤掉多写的 {removed} 行")
