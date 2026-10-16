#!/usr/bin/env python3
"""§6.5 执行：真求值 + 容器不发射已过闸门 → 23 条记录改判 kb_type、迁库目录、重建 index、台账追加。"""
import json, os, glob, collections, hashlib, shutil

RUN="20260924-1512"; L0="kb/l0"; MAN=f"{L0}/manifest.jsonl"; REG=f"{L0}/registry/kb.json"
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def atomic(p,t):
    x=p+".tmp"; open(x,"w",encoding="utf-8").write(t); open(x,encoding="utf-8").read(); os.replace(x,p)

latest_before={}
for l in open(MAN,encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest_before[r["resource_key"]]=r
reg=json.load(open(REG,encoding="utf-8")); REV=reg["dir_map_reverse"]; OV=reg["field_role_table_overrides"]; FR=reg["field_roles"]
RULES=[r for r in reg["rules"] if r.get("enabled")]
sh=json.load(open("kb/.work/batch12/container_shadow.json",encoding="utf-8"))
assert sh["gate_pass"], "闸门未通过，禁止执行"
targets={r["resource_key"]:r for r in sh["rows"]
         if r["old_kb_type"]!=r["new_kb_type"]
         and latest_before[r["resource_key"]].get("record_id")
         and latest_before[r["resource_key"]].get("field_name") is None
         and latest_before[r["resource_key"]].get("table_name")=="材料收集"}
print("待改判资源:",len(targets))

# ---- 0) 先用现有台账重建一次 index，断言与现文件逐字节一致（证明重建配方正确）----
def rebuild_index(latest):
    live={k:v for k,v in latest.items() if v["status"] not in ("gone","retracted") and not k.startswith("audit:")}
    return "".join(json.dumps({"resource_key":v["resource_key"],"kb_type":v["kb_type"],
        "source_kind":v["source_kind"],"status":v["status"],"entry_url":v["entry_url"],
        "rule_eligible":v.get("rule_eligible")},
        ensure_ascii=False,sort_keys=True)+"\n" for k,v in sorted(live.items()))
latest={}
for l in open(MAN,encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["resource_key"]]=r
cur_index=open(f"{L0}/index/l0.jsonl",encoding="utf-8").read()
probe=rebuild_index(latest)
print("重建配方自检：与现 index 逐字节一致 =", probe==cur_index,
      "| 行数", probe.count("\n"), "vs", cur_index.count("\n"))
assert probe==cur_index, "重建配方与现 index 不一致，禁止继续"

# ---- 1) 台账追加 23 行 updated（含前后对照），只追加 ----
before=sum(1 for l in open(MAN,encoding="utf-8") if l.strip())
rows=[]
for k,t in sorted(targets.items()):
    r=dict(latest[k])
    r.update({"status":"updated","kb_type":t["new_kb_type"],"matched_rule":t["new_rule"],
      "prev_kb_type":t["old_kb_type"],"prev_matched_rule":t["old_rule"],
      "change":"fix_container_kb_type","observed_at":RUN,"scanner_version":"0.7",
      "downstream_invalidated":True,
      "note":("§6 归属修正：kb_type 改由 rule_for() 真求值得到（原为发射器硬编码 unknown/R5）；"
              "同时按 container_policy(C1∧C2∧C3) 标记为容器 → 不发射 L2 单元。"
              "归属与发射解耦，L2 单元集合不变。"),
      "container":True,
      "container_policy_run":RUN,
      "ruling":f"rule_for(材料收集, hint=知识库分类) → {t['new_rule']}"})
    rows.append(r)
with open(MAN,"a",encoding="utf-8") as fh:
    for r in rows: fh.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n")
after=sum(1 for l in open(MAN,encoding="utf-8") if l.strip())
print(f"台账追加 {len(rows)} 行：{before} → {after}")

# ---- 2) 迁库目录（查 dir_map_reverse，不硬编码中文名）----
moved=[]; miss=[]
for k,t in sorted(targets.items()):
    rid=k.replace(":","__").replace("/","_")
    src=None
    for d in os.listdir(L0):
        p=f"{L0}/{d}/{rid}.json"
        if os.path.isfile(p): src=p; break
    if not src: miss.append((k,rid)); continue
    dstdir=f"{L0}/{REV[t['new_kb_type']]}"; os.makedirs(dstdir,exist_ok=True)
    dst=f"{dstdir}/{rid}.json"
    if os.path.abspath(src)==os.path.abspath(dst): continue
    # 库内资源文件内的 kb_type 也要跟着改（README：每个文件内部都带 kb_type）
    obj=json.load(open(src,encoding="utf-8"))
    old=obj.get("kb_type")
    obj["kb_type"]=t["new_kb_type"]
    obj["kb_type_prev"]=old; obj["kb_type_fixed_at_run"]=RUN
    atomic(src, json.dumps(obj,ensure_ascii=False,indent=1)+"\n")
    os.replace(src,dst)   # 脚本搬迁（非手工 mv）；分类靠重跑改
    moved.append({"resource_key":k,"from":src,"to":dst,"kb_type":t["new_kb_type"]})
print(f"迁移资源文件 {len(moved)} 个；找不到源文件 {len(miss)} 个")
for m in moved[:3]: print("   ",m["from"],"→",m["to"])

# ---- 3) 重建 index ----
latest2={}
for l in open(MAN,encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest2[r["resource_key"]]=r
atomic(f"{L0}/index/l0.jsonl", rebuild_index(latest2))
idx=[json.loads(l) for l in open(f"{L0}/index/l0.jsonl",encoding="utf-8") if l.strip()]
print("index 重建：",len(idx),"行")

# ---- 4) 判据 ----
dirs={d:len(os.listdir(f"{L0}/{d}")) for d in ("1_外部标准库","2_内部正负样本库","3_措辞表达库","4_产品描述库","9_未归类")}
print("L0 库目录:",dirs,"合计",sum(dirs.values()))
dist=collections.Counter(t["new_kb_type"] for t in targets.values())
print("改判分布:",dict(dist))
json.dump({"run_id":RUN,"changed":len(targets),"dist":dict(dist),
           "moved":moved,"missing":miss,"manifest_before":before,"manifest_after":after,
           "index_rows":len(idx),"l0_dirs":dirs,"l0_dirs_total":sum(dirs.values())},
          open("kb/.work/batch12/step2c_result.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
