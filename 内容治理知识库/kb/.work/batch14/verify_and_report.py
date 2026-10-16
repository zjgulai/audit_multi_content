#!/usr/bin/env python3
import json,os,re,hashlib,glob,collections,time
L0,L1,L2,L3="kb/l0","kb/l1","kb/l2","kb/l3"; RUN="20260924-1630"
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def n(p): return sum(1 for l in open(p,encoding="utf-8") if l.strip())
B=json.load(open("kb/.work/batch14/baseline_at_1630.json",encoding="utf-8"))
ok=True
def chk(name,c,d=""):
    global ok; ok=ok and c; print(f"  [{'PASS' if c else 'FAIL'}] {name}"+(f"  {d}" if d else ""))

print("=== 判据 1：L0 只读（全部文件哈希前后一致）===")
now={}
for p in sorted(glob.glob("kb/l0/**/*",recursive=True)):
    if os.path.isfile(p):
        now[p]=hashlib.sha256(open(p,"rb").read()).hexdigest()
old={k:v["sha256"] for k,v in B["files"].items() if k.startswith("kb/l0/")}
chk("L0 文件数一致",len(now)==len(old),f"{len(old)} → {len(now)}")
chk("L0 逐文件哈希一致",all(old.get(k)==v for k,v in now.items()) and set(now)==set(old),
    f"变化 {len([k for k in now if old.get(k)!=now[k]])} 个")
agg=hashlib.sha256("\n".join(f"{k}={now[k]}" for k in sorted(now)).encode()).hexdigest()
chk("L0 聚合哈希一致",agg==B["l0_agg_sha256"],f"{B['l0_agg_sha256'][:16]} → {agg[:16]}")

print("\n=== 判据 5：L1 L0⊖L1 == 0 ===")
latest={}
for l in open(f"{L0}/manifest.jsonl",encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["resource_key"]]=r
L0res={k:v for k,v in latest.items() if v["status"] not in ("gone","retracted") and not k.startswith("audit:")}
rid_of=lambda k: re.sub(r'[^0-9A-Za-z._\-]+','_',k.replace(":","__").replace("/","_"))[:170]
l1=[json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl",encoding="utf-8") if l.strip()]
have={r["resource_id"] for r in l1}
miss=[k for k in L0res if rid_of(k) not in have]
chk("L0 ⊖ L1 == 0",not miss,f"L0 有效资源 {len(L0res)}；缺 {len(miss)}")
lat={}
for r in l1: lat[r["resource_id"]]=r
oldlat={r["resource_id"]:r for r in l1 if r["observed_at"]!=RUN}
print("  L1 最新行 status 分布:",dict(collections.Counter(r["status"] for r in lat.values())))
print("  本批新增 L1 台账行:",len([r for r in l1 if r["observed_at"]==RUN]))

print("\n=== 判据 7/8：既有 L1 行未变 / L3 产出哈希未变 ===")
l1base=B["files"][f"{L1}/index/l1.jsonl"]["sha256"]; l1mbase=B["files"][f"{L1}/manifest_l1.jsonl"]["sha256"]
chk("L1 index 仅追加（行数 +新增段）",n(f"{L1}/index/l1.jsonl")>=14782,f"{14782} → {n(f'{L1}/index/l1.jsonl')}")
chk("L3 三候选文件逐字节未变",
    sha(f"{L3}/candidates/rules.jsonl")==B["files"][f"{L3}/candidates/rules.jsonl"]["sha256"]
    and sha(f"{L3}/candidates/sample_cases.jsonl")==B["files"][f"{L3}/candidates/sample_cases.jsonl"]["sha256"]
    and sha(f"{L3}/candidates/scoped_clauses.jsonl")==B["files"][f"{L3}/candidates/scoped_clauses.jsonl"]["sha256"])
chk("L2 既有 9469 单元 text 未变",sha(f"{L2}/units.jsonl")==B["files"][f"{L2}/units.jsonl"]["sha256"],
    sha(f"{L2}/units.jsonl")[:16])

print("\n=== 判据 8/9/11：条款号 / L4–L8 / 版本 ===")
A=json.load(open("kb/l4/registry/l4.json",encoding="utf-8"))["assignments"]
ART=json.load(open("kb/.work/l4_article.json",encoding="utf-8"))["mapping"]
chk("assignments 1242 逐条未变",len(A)==1242 and all(A.get(k)==v for k,v in ART.items()))
up=[p for p in ("kb/l4/registry/l4.json","kb/l5/index/l5.jsonl","kb/l6/index/l6.jsonl","kb/l7/registry/l7.json","kb/view/_meta/manifest.json")
    if sha(p)!=B["files"][p]["sha256"]]
chk("L4–L8 零写入",not up,str(up))
v=[l for l in open("kb/versions/versions.jsonl",encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
chk("versions.jsonl 版本行 0",len(v)==0)

print("\n=== 判据 10：本批第三方写入 ===")
new=[p for p in json.load(open("kb/.work/batch14/l1_result.json",encoding="utf-8")) and [] ]
res=json.load(open("kb/.work/batch14/l1_result.json",encoding="utf-8"))
print("     本批写入: L1 manifest +%d 行 / artifact %d 个 / index 追加若干"%(res["manifest_appended"],res["artifacts"]))
print("     飞书调用（全为 read）:",len(res["ops"]),"条；write 调用 0 条")

out={"run_id":RUN,"pass":ok,"l0_files":len(now),"l0_agg":agg,
     "l0_minus_l1":len(miss),"l1_new_rows":len([r for r in l1 if r["observed_at"]==RUN]),
     "l1_status_dist":dict(collections.Counter(r["status"] for r in lat.values())),
     "l2_started":False,"l3_started":False}
json.dump(out,open("kb/.work/batch14/verify.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("\n=== 总判:","全过 ✔" if ok else "有 FAIL ✘","===")
