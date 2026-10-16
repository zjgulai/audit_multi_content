#!/usr/bin/env python3
"""收工终检：条款号零漂移 / 未动层 / 版本纪律 / 第三方写入自证 / 台账增量自证。"""
import json, os, hashlib, collections, time
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def n(p): return sum(1 for l in open(p,encoding="utf-8") if l.strip())
B=json.load(open("kb/.work/batch12/baseline_at_1512.json",encoding="utf-8"))
ok=True
def chk(name,cond,detail=""):
    global ok; ok = ok and cond
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))

print("=== 8. 条款号零漂移 ===")
A=json.load(open("kb/l4/registry/l4.json",encoding="utf-8"))["assignments"]
ART=json.load(open("kb/.work/l4_article.json",encoding="utf-8"))["mapping"]
chk("assignments 1242 条逐条未变", len(A)==1242 and all(A.get(k)==v for k,v in ART.items()),
    f"{len(A)} 条；与 20260923-1445 台账不一致 {sum(1 for k,v in ART.items() if A.get(k)!=v)} 条")
CAND={}
for c in (json.loads(l) for l in open("kb/.work/batch9/article_map.json",encoding="utf-8") if l.strip()):
    pass
am=json.load(open("kb/.work/batch9/article_map.json",encoding="utf-8"))["row_map"]
can={}
tot=0
for f in ("wording_entry.jsonl","wording_revision_pair.jsonl","sample_case.jsonl","scoped_clause.jsonl"):
    for c in (json.loads(l) for l in open(f"kb/l4/canonical/{f}",encoding="utf-8") if l.strip()):
        tot+=1
        key=("rule::"+c["rule_id"]) if "rule_id" in c else (("sample_case::"+c["case_id"]) if "case_id" in c else ("scoped_clause::"+c["clause_id"]))
        can[key]=c["article_no"]
drift=[k for k,v in can.items() if am.get(k)!=v]
chk("canonical 1242 条 article_no 逐条未变", tot==1242 and not drift, f"{tot} 条；漂移 {len(drift)} 条")

print("\n=== 9. 未动层（L5/L6/L8）===")
for p in ("kb/l5/index/l5.jsonl","kb/l6/index/l6.jsonl","kb/view/_meta/manifest.json"):
    now=sha(p); base=B["files"][p]["sha256"]
    chk(f"{p}", now==base, f"{now[:16]} vs 基线 {base[:16]}")

print("\n=== 11. 版本纪律 ===")
v=[l for l in open("kb/versions/versions.jsonl",encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
chk("versions.jsonl 版本行 == 0", len(v)==0, f"{len(v)} 行")
regs=[json.load(open(p,encoding="utf-8")) for p in ("kb/l0/registry/kb.json","kb/l3/registry/l3.json","kb/l4/registry/l4.json","kb/l7/registry/l7.json")]
chk("kb_version 全为 v0", all(r.get("kb_version")=="v0" for r in regs),
    str({r.get("kb_version") for r in regs}))

print("\n=== 3. L0 台账只增不减 + 增量自证 ===")
rows=[json.loads(l) for l in open("kb/l0/manifest.jsonl",encoding="utf-8") if l.strip()]
chk("台账只增不减", len(rows)==3675, f"开工 3651 → 收工 {len(rows)}（+1 audit +23 updated）")
c=collections.Counter(r.get("change") for r in rows if r.get("change"))
print("     change 增量:", {k:c[k] for k in ("ledger_rows_unauthorizedly_deleted","fix_container_kb_type","add_field_rule_eligible")})
rc=[r for r in rows if str(r.get("resource_key","")).startswith("local:review-case:")]
chk("被删 12 行未回填（无 local:review-case:* 资源行）", not rc, f"台账内 local:review-case:* 行数 = {len(rc)}（与开工一致）")

print("\n=== 10. 第三方写入自证 ===")
import subprocess
new=[p for p in subprocess.run(["find","kb","-newermt","2026-09-24 15:11:00","-type","f"],
     capture_output=True,text=True).stdout.split("\n") if p and "/.work/" not in p]
expected={"kb/l0/manifest.jsonl","kb/l0/index/l0.jsonl","kb/l0/registry/kb.json",
 "kb/l0/_archive/eval-material-excluded-20260924-1210/local__review-case__img-1.json",
 "kb/l0/_archive/eval-material-excluded-20260924-1210/local__review-case__img-2.json",
 "kb/l0/_archive/eval-material-excluded-20260924-1210/local__review-case__img-3.json",
 "kb/l0/_archive/eval-material-excluded-20260924-1210/local__review-case__img-4.json",
 "kb/l1/index/l1.jsonl","kb/l1/manifest_l1.jsonl","kb/l2/manifest_l2.jsonl",
 "kb/l3/candidates/sample_cases.jsonl","kb/l3/registry/l3.json",
 "kb/l4/registry/l4.json","kb/l7/registry/l7.json"}
moveddest={f"kb/l0/{d}/feishu_bitable_record__tblMGtPfe8ZUsEdP__{r}.json"
           for d in ("1_外部标准库","2_内部正负样本库","3_措辞表达库","4_产品描述库")
           for r in __import__("json").load(open("kb/.work/batch12/step2c_result.json",encoding="utf-8"))["targets_records"] } if False else set()
import json as _j
res=_j.load(open("kb/.work/batch12/step2c_result.json",encoding="utf-8"))
moveddest={m["to"] for m in res["moved"]}
expected |= moveddest
# 本批三件套报告（§11 要求）
expected |= {f"kb/{L}/runs/20260924-1512.{e}" for L in ("l0","l3") for e in ("report.md","json","ops.log")}
# 本批按 §7 就地改了这 23 个 L1 产物的 kb_type 字段（不搬文件——§2 只授权改字段）
_l1r=[json.loads(l) for l in open("kb/l0/manifest.jsonl",encoding="utf-8") if l.strip()]
_rids={r["resource_key"].replace(":","__").replace("/","_") for r in _l1r
       if r.get("table_name")=="材料收集" and r.get("record_id") and r.get("field_name") is None}
expected |= {f"kb/l1/9_未归类/{x}.json" for x in _rids}
unexp=sorted(set(new)-expected)
chk("开工后无第三方写入（新写入全为本批预期文件）", not unexp, f"非预期 {len(unexp)} 个: {unexp[:5]}")
print("     本批写入文件数:",len(new))
json.dump({"article_no_drift":len(drift),"assignments":len(A),"canonical":tot,
           "l5_l6_l8_untouched":all(sha(p)==B['files'][p]['sha256'] for p in
             ("kb/l5/index/l5.jsonl","kb/l6/index/l6.jsonl","kb/view/_meta/manifest.json")),
           "versions_rows":len(v),"ledger_rows":len(rows),
           "files_written":sorted(new),"unexpected_writes":unexp,"pass":ok},
          open("kb/.work/batch12/step6_verify.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("\n=== 终检:", "全过 ✔" if ok else "有 FAIL ✘","===")
