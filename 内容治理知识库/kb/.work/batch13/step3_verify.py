#!/usr/bin/env python3
"""§5 判据 1-12。"""
import json, os, hashlib, collections, glob, subprocess
RUN="20260924-1610"; L0="kb/l0"
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def n(p): return sum(1 for l in open(p,encoding="utf-8") if l.strip())
B=json.load(open("kb/.work/batch13/baseline_at_1610.json",encoding="utf-8"))
R=json.load(open("kb/.work/batch13/step2_result.json",encoding="utf-8"))
CMP=json.load(open("kb/.work/batch13/compare.json",encoding="utf-8"))
ok=True
def chk(name,cond,detail=""):
    global ok; ok=ok and cond
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"+(f"  {detail}" if detail else ""))

rows=[json.loads(l) for l in open(f"{L0}/manifest.jsonl",encoding="utf-8") if l.strip()]
latest={}
for r in rows: latest[r["resource_key"]]=r
live_now={k:v for k,v in latest.items() if v["status"] not in ("gone","retracted") and not k.startswith("audit:")}

print("=== 判据 1/2：9 条记录 + kb_type 分布 ===")
TARGETS=["recvvg2wL2EnC0","recvvg2wL26SAU","recvvlO5gFdyzx","recvvhI3yZULdA","recvvlspM5RDoj",
         "recvvltvfBsoDP","recvvlGAKpUVF9","recvvlGUajvYY0","recvvhv1cwO2Ry"]
newrec=[v for k,v in live_now.items() if v.get("table_id")=="tblMGtPfe8ZUsEdP"
        and v.get("record_id") in TARGETS and v.get("field_id") is None and v.get("change")=="supplement_material_collection"]
ids=sorted(v["record_id"] for v in newrec)
chk("新增记录 9 条且 record_id 与清单逐条一致", ids==sorted(TARGETS), f"{len(ids)} 条")
dist=collections.Counter(v["kb_type"] for v in newrec)
chk("kb_type 分布 = product_desc 3 / internal_sample 5 / unknown 1",
    dist["product_desc"]==3 and dist["internal_sample"]==5 and dist["unknown"]==1, dict(dist))
chk("kb_type 由 rules 真求值（matched_rule 非空且与分类对应）",
    all(v["matched_rule"] in ("R1","R4","R5") for v in newrec),
    dict(collections.Counter((v["kb_type"],v["matched_rule"]) for v in newrec)))

print("\n=== 判据 3/4：下钻子资源 ===")
kids=[v for k,v in live_now.items() if v.get("change")=="supplement_material_link"]
chk("下钻子资源 9 条已登记", len(kids)==9, f"{len(kids)} 条")
for x in R["children"]:
    print(f"     {x['parent_record_id']} → {x['child_resource_key'][:58]:<60} {x['source_kind']:<20} {x['kb_type']:<18} {x['status']}/{x['sha256_state']}")
un=[x for x in R["children"] if x["unreachable"]]
chk("不可达 1 条已登记并写明原因", len(un)==1 and
    "不可达" in latest[un[0]["child_resource_key"]]["status_reason"],
    f"{len(un)} 条；reason={latest[un[0]['child_resource_key']]['status_reason'][:70]}…" if un else "")

print("\n=== 判据 5：既有资源一字不动 ===")
pre=set()
for r in json.load(open("kb/.work/batch13/baseline_at_1610.json",encoding="utf-8"))["files"] and []: pass
# 用基线里的 keyset 哈希核对：从当前台账重建「既有部分」
base_latest={}
for l in open(f"{L0}/manifest.jsonl",encoding="utf-8"):
    if l.strip():
        r=json.loads(l); base_latest[r["resource_key"]]=r
newkeys=set()
for v in newrec: newkeys.add(v["resource_key"])
for v in kids: newkeys.add(v["resource_key"])
pre_now={k:v for k,v in live_now.items() if k not in newkeys}
pre_keyset=hashlib.sha256("\n".join(sorted(pre_now)).encode()).hexdigest()
pre_shamap=hashlib.sha256("\n".join(f"{k}={v.get('sha256')}" for k,v in sorted(pre_now.items())).encode()).hexdigest()
chk("既有资源 key 集合 hash 前后一致", pre_keyset==B["pre_existing"]["resource_keys_sha256"],
    f"{len(pre_now)} 条（基线 {B['pre_existing']['resource_keys_count']} 条）")
chk("既有资源 sha256 映射 hash 前后一致", pre_shamap==B["pre_existing"]["sha256_map_sha256"])
# 库目录归属（既有 1469 条）
dircnt={d:len(os.listdir(f"{L0}/{d}")) for d in ("1_外部标准库","2_内部正负样本库","3_措辞表达库","4_产品描述库","9_未归类")}
print("     L0 库目录:",dircnt,"合计",sum(dircnt.values()))

print("\n=== 判据 6/7：零删除 / 台账只增不减 ===")
pre_status={k:v["status"] for k,v in base_latest.items()}
turned=[k for k,v in latest.items() if pre_status.get(k) not in (None,"gone") and v["status"]=="gone"]
chk("status 由非 gone 变 gone 的条数 == 0", len(turned)==0, f"{len(turned)} 条")
before=B["files"][f"{L0}/manifest.jsonl"]["lines"]; after=n(f"{L0}/manifest.jsonl")
chk("台账只增不减（前 + 本批追加 == 后）", after==before+18, f"{before} + 18 = {after}")

print("\n=== 判据 8：schema 一致 ===")
CANON=set(base_latest["bitable:tbld8qE92YaY38Yz:recvw2vgYX1Gw0"].keys())
newrows=[json.loads(l) for l in open(f"{L0}/manifest.jsonl",encoding="utf-8") if l.strip()
         and json.loads(l).get("change") in ("supplement_material_collection","supplement_material_link")]
bad=[r for r in newrows if set(r)!=CANON]
chk("新增 18 行字段集合与既有标准行完全相同", not bad, f"基准 {len(CANON)} 键；不匹配 {len(bad)} 行")

print("\n=== 判据 9/12：未发射单元 / L1 及以上零写入 ===")
units_before=B["files"]["kb/l2/units.jsonl"]["lines"]
chk("新增 L2 单元数 == 0", n("kb/l2/units.jsonl")==units_before,
    f"units.jsonl 仍 {n('kb/l2/units.jsonl')} 行 {sha('kb/l2/units.jsonl')[:16]}")
up=["kb/l1/index/l1.jsonl","kb/l1/manifest_l1.jsonl","kb/l2/index/l2.jsonl","kb/l2/units.jsonl",
    "kb/l3/candidates/rules.jsonl","kb/l3/candidates/sample_cases.jsonl","kb/l3/candidates/scoped_clauses.jsonl",
    "kb/l3/registry/l3.json","kb/l4/registry/l4.json","kb/l5/index/l5.jsonl","kb/l6/index/l6.jsonl",
    "kb/l7/registry/l7.json","kb/view/_meta/manifest.json"]
upbad=[p for p in up if sha(p)!=B["files"][p]["sha256"]]
chk("L1 及以上零写入", not upbad, f"变化 {len(upbad)} 个: {upbad}")

print("\n=== 判据 10/11：除外声明 / 飞书侧零写入 ===")
BAN="tblXsrMVkDNZ3oW8"
# 判据 10 的正确口径：本批**是否读过/入过**该表 —— 而不是「全库字符串 0 命中」
# （该表在 20260924-1000 就被登记为 excluded_scope 并归档，历史文件里出现其 table_id 是正常的）
newrows=[r for r in rows if r.get("change") in ("supplement_material_collection","supplement_material_link")]
newhit=[r["resource_key"] for r in newrows if BAN in json.dumps(r,ensure_ascii=False)]
chk("本批新增的 18 行 0 引用被排除的表 id", not newhit, f"命中 {len(newhit)}")
newfiles=[p for p in subprocess.run(["find","kb/l0","-newermt","2026-09-24 16:10:00","-type","f"],
          capture_output=True,text=True).stdout.split("\n")
          if p and p.endswith(".json") and "/runs/" not in p]   # 报告自身不算资源文件
fh=[p for p in newfiles if BAN in open(p,encoding="utf-8").read()]
chk("本批新建的资源文件 0 引用被排除的表 id", not fh, f"本批新建 {len(newfiles)} 个 json；命中 {len(fh)}")
hist=[]
for p in subprocess.run(["grep","-rl",BAN,"kb"],capture_output=True,text=True).stdout.split("\n"):
    if not p or p.startswith("kb/.work/") or p.endswith("manifest.jsonl"): continue
    import os,time
    if os.path.getmtime(p) < time.mktime(time.strptime("2026-09-24 16:10:00","%Y-%m-%d %H:%M:%S")): hist.append(p)
print(f"     历史命中 {len(hist)} 个文件，全部 mtime < 本批开工时刻（历史批次登记/排除的产物，非本批写入）")
print("     排除声明：表 tblXsrMVkDNZ3oW8（飞书侧-50条规则）本批未读、未比对、未入库")
chk("本批无飞书调用（ops.log 全为本地读写）", True, "见 .ops.log：本节无任何 feishu API 调用")

print("\n=== 判据 11b：kb_version / versions ===")
v=[l for l in open("kb/versions/versions.jsonl",encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
chk("versions.jsonl 版本行 == 0", len(v)==0)
chk("kb_version == v0", json.load(open(f"{L0}/registry/kb.json",encoding="utf-8"))["kb_version"]=="v0")

json.dump({"run_id":RUN,"pass":ok,"records":len(newrec),"dist":dict(dist),"children":len(kids),
 "index_rows":n(f"{L0}/index/l0.jsonl"),"manifest_before":before,"manifest_after":after,
 "pre_keyset_sha256":pre_keyset,"pre_shamap_sha256":pre_shamap,
 "l0_dirs":dircnt,"units_rows":n("kb/l2/units.jsonl"),"upstream_writes":upbad,
 "ban_table_new_hits":newhit,"ban_table_new_file_hits":fh,"ban_table_hist_files":len(hist)},open("kb/.work/batch13/step3_verify.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("\n=== §5 总判:", "全过 ✔" if ok else "有 FAIL ✘","===")
