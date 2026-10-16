#!/usr/bin/env python3
"""§6.5 补：按 dir_map_reverse 把 23 条记录的资源文件迁到正确库目录。
文件名规律：<source_kind>__<table_id>__<record_id>.json（不是 resource_key 的 : → __）。"""
import json, os, glob, collections, hashlib
RUN="20260924-1512"; L0="kb/l0"; REG=f"{L0}/registry/kb.json"
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def atomic(p,t):
    x=p+".tmp"; open(x,"w",encoding="utf-8").write(t); open(x,encoding="utf-8").read(); os.replace(x,p)
res=json.load(open("kb/.work/batch12/step2c_result.json",encoding="utf-8"))
reg=json.load(open(REG,encoding="utf-8")); REV=reg["dir_map_reverse"]
latest={}
for l in open(f"{L0}/manifest.jsonl",encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["resource_key"]]=r
targets={r["resource_key"]:r for r in json.load(open("kb/.work/batch12/container_shadow.json",encoding="utf-8"))["rows"]
         if r["old_kb_type"]!=r["new_kb_type"]
         and latest[r["resource_key"]].get("record_id") and latest[r["resource_key"]].get("field_name") is None
         and latest[r["resource_key"]].get("table_name")=="材料收集"}
# 用台账最新行（已是改判后的 kb_type）
targets={k:{"new_kb_type":latest[k]["kb_type"]} for k in targets}
print("待迁移:",len(targets))

# 建立「record_id → 文件路径」索引（只扫库目录 1_/2_/3_/4_/9_）
libdirs=[f"{L0}/{d}" for d in os.listdir(L0) if os.path.isdir(f"{L0}/{d}") and d[0].isdigit()]
byrec={}
for d in libdirs:
    for f in os.listdir(d):
        if not f.endswith(".json"): continue
        parts=f[:-5].split("__")
        if len(parts)>=3 and parts[0]=="feishu_bitable_record":
            byrec.setdefault(parts[-1], []).append(os.path.join(d,f))
moved=[]; miss=[]
for k,t in sorted(targets.items()):
    rec=latest[k]["record_id"]
    hits=byrec.get(rec,[])
    if len(hits)!=1: miss.append((k,rec,hits)); continue
    src=hits[0]
    dst=f"{L0}/{REV[t['new_kb_type']]}/{os.path.basename(src)}"
    if os.path.abspath(src)==os.path.abspath(dst): continue
    obj=json.load(open(src,encoding="utf-8"))
    prev=obj.get("kb_type"); obj["kb_type"]=t["new_kb_type"]
    obj["kb_type_prev"]=prev; obj["kb_type_fixed_at_run"]=RUN
    obj["container"]=True; obj["container_policy_run"]=RUN
    atomic(src, json.dumps(obj,ensure_ascii=False,indent=1)+"\n")
    os.makedirs(os.path.dirname(dst),exist_ok=True)
    os.replace(src,dst)
    moved.append({"resource_key":k,"record_id":rec,"from":src,"to":dst,
                  "kb_type_prev":prev,"kb_type":t["new_kb_type"]})
print(f"已迁移 {len(moved)} 个；未找到唯一源文件 {len(miss)} 个")
for m in miss[:5]: print("   MISS",m)
for m in moved[:3]: print("   ",m["from"],"→",m["to"])
dirs={d:len(os.listdir(f"{L0}/{d}")) for d in ("1_外部标准库","2_内部正负样本库","3_措辞表达库","4_产品描述库","9_未归类")}
print("L0 库目录:",dirs,"合计",sum(dirs.values()))
res.update({"moved":moved,"missing":miss,"l0_dirs":dirs,"l0_dirs_total":sum(dirs.values())})
json.dump(res,open("kb/.work/batch12/step2c_result.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
