#!/usr/bin/env python3
"""§7：L1 / L2 跟随 L0 的 kb_type。只改 kb_type 一个字段，不搬文件、不动文本。"""
import json, os, hashlib, collections
RUN="20260924-1512"
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def atomic(p,t):
    x=p+".tmp"; open(x,"w",encoding="utf-8").write(t); open(x,encoding="utf-8").read(); os.replace(x,p)
latest={}
for l in open("kb/l0/manifest.jsonl",encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["resource_key"]]=r
recs=[v for v in latest.values() if v.get("table_name")=="材料收集" and v.get("record_id")
      and v.get("field_name") is None]
newkt={r["resource_key"].replace(":","__").replace("/","_"):r["kb_type"] for r in recs}
print("23 条记录的新 kb_type:",dict(collections.Counter(newkt.values())))

def edit_jsonl(path, key):
    rows=[json.loads(l) for l in open(path,encoding="utf-8") if l.strip()]
    changed=0
    for r in rows:
        k=r.get(key)
        if k in newkt and r.get("kb_type")!=newkt[k]:
            r["kb_type"]=newkt[k]
            r["kb_type_followed_l0_at_run"]=RUN
            changed+=1
    atomic(path,"".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in rows))
    return changed, len(rows)

res={}
for path,key,tag in (("kb/l1/index/l1.jsonl","resource_id","L1 index"),
                     ("kb/l1/manifest_l1.jsonl","resource_id","L1 manifest"),
                     ("kb/l2/manifest_l2.jsonl","resource_id","L2 manifest")):
    c,n=edit_jsonl(path,key); res[tag]={"changed":c,"rows":n,"path":path}
    print(f"  {tag}: 改 {c} 行 / 共 {n} 行")

# L1 产物 json 内的 kb_type
n=0
for d in os.listdir("kb/l1"):
    p=f"kb/l1/{d}"
    if not os.path.isdir(p): continue
    for f in os.listdir(p):
        if not f.endswith(".json"): continue
        rid=f[:-5]
        if rid not in newkt: continue
        fp=f"{p}/{f}"; obj=json.load(open(fp,encoding="utf-8"))
        if obj.get("kb_type")!=newkt[rid]:
            obj["kb_type"]=newkt[rid]; obj["kb_type_followed_l0_at_run"]=RUN
            atomic(fp, json.dumps(obj,ensure_ascii=False,indent=1)+"\n"); n+=1
print(f"  L1 产物文件: 改 {n} 个 / 23")
res["L1_artifacts"]={"changed":n}
json.dump(res,open("kb/.work/batch12/step3_result.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)

# ---------- 字段级 diff：证明只动 kb_type ----------
print("\n=== 字段级 diff（基于开工基线，非历史数字）===")
def diff_jsonl(old,new,key):
    A=[json.loads(l) for l in open(old,encoding="utf-8") if l.strip()]
    B=[json.loads(l) for l in open(new,encoding="utf-8") if l.strip()]
    assert len(A)==len(B), (len(A),len(B))
    keys=collections.Counter(); bad=0
    for a,b in zip(A,B):
        if a==b: continue
        for k in set(a)|set(b):
            if a.get(k)!=b.get(k):
                keys[k]+=1
                if k not in ("kb_type","kb_type_followed_l0_at_run"): bad+=1
    return len(A), dict(keys), bad
for old,new,key,tag in (("kb/.work/batch12/pre_l1l2/l1.index.jsonl","kb/l1/index/l1.jsonl","resource_id","L1 index"),
                        ("kb/.work/batch12/pre_l1l2/l1.manifest.jsonl","kb/l1/manifest_l1.jsonl","resource_id","L1 manifest"),
                        ("kb/.work/batch12/pre_l1l2/l2.manifest.jsonl","kb/l2/manifest_l2.jsonl","resource_id","L2 manifest")):
    n,k,bad=diff_jsonl(old,new,key)
    print(f"  {tag}: {n} 行 → 变化字段 {k}；非 kb_type 字段变化行数 = {bad}")

# L2 单元集合未变
u=[json.loads(l) for l in open("kb/l2/units.jsonl",encoding="utf-8") if l.strip()]
tot=hashlib.sha256("".join(x["text"] for x in u).encode()).hexdigest()
print(f"\nL2 单元数 {len(u)}  text 总 sha256 = {tot}")
print("L2 units.jsonl sha256 =", sha("kb/l2/units.jsonl"))
print("kb/l2/index/l2.jsonl sha256 =", sha("kb/l2/index/l2.jsonl"))
open("kb/.work/batch12/l2_units_hash.txt","w").write(f"{len(u)}\n{tot}\n{sha('kb/l2/units.jsonl')}\n")
