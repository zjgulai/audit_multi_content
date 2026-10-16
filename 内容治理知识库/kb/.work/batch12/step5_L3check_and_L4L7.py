#!/usr/bin/env python3
"""§8.3 判据 + §9 L4/L7 计数同步（条款号一律不动）。"""
import json, os, hashlib, collections
RUN="20260924-1512"; L3="kb/l3"; L4="kb/l4"; L7="kb/l7"
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def n(p): return sum(1 for l in open(p,encoding="utf-8") if l.strip())
def atomic(p,t):
    x=p+".tmp"; open(x,"w",encoding="utf-8").write(t); open(x,encoding="utf-8").read(); os.replace(x,p)
def load(p): return [json.loads(l) for l in open(p,encoding="utf-8") if l.strip()]

print("=== §8.3 L3 判据 ===")
SC=load(f"{L3}/candidates/sample_cases.jsonl")
cids=[s["case_id"] for s in SC]
print(f"  行数 {len(SC)}（期望 358）；case_id 唯一 {len(set(cids))}（期望 358）")
print(f"  rules.jsonl {n(f'{L3}/candidates/rules.jsonl')} 行 {sha(f'{L3}/candidates/rules.jsonl')[:16]}（期望 509 / a17552e1a0fabde5）")
print(f"  scoped_clauses.jsonl {n(f'{L3}/candidates/scoped_clauses.jsonl')} 行 {sha(f'{L3}/candidates/scoped_clauses.jsonl')[:16]}（期望 375 / 81f74b85b410d6de）")

CAN=load(f"{L4}/canonical/sample_case.jsonl")
print(f"\n  canonical/sample_case.jsonl {len(CAN)} 行")
ADDED={"article_no","kb_version","status","promoted_from","promoted_at_run","promotion_basis","cite_check"}
bymap={c["case_id"]:c for c in CAN}
assert len(bymap)==len(CAN)==358
diff_fields=collections.Counter(); missing=[]; dropped=[]
for s in SC:
    c=bymap.get(s["case_id"])
    if c is None: missing.append(s["case_id"]); continue
    for k,v in s.items():
        if k=="status":                       # 候选 provisional / 定稿 stable —— 晋升就是改这个
            if v!="provisional" or c.get("status")!="stable": diff_fields["status(异常)"]+=1
            continue
        if c.get(k)!=v: diff_fields[k]+=1
    extra=set(c)-set(s)-ADDED
    if extra: diff_fields["canonical 多出未声明字段"]+=1
print(f"  去重后 358 行 ↔ canonical 358 行：字段级 diff = {dict(diff_fields) or '全 0 ✔'}")
print(f"  候选里 canonical 找不到的 {len(missing)} 条；canonical 独有字段（晋升新增）= {sorted(ADDED)}")

print("\n=== §9 L4 / L7 计数同步 ===")
reg=json.load(open(f"{L4}/registry/l4.json",encoding="utf-8"))
A_before=dict(reg["assignments"]); t=reg["numbering"]["totals"]
print("  L4 改前：output_rows",t["output_rows"],"duplicate_rows",t["duplicate_rows"],"assigned_total",t["assigned_total"])
t["output_rows"]=1242; t["duplicate_rows"]=0
t["output_rows_note"]=("20260924-1512：L3 candidates/sample_cases.jsonl 已源头去重 562→358（见 kb/l3/registry/l3.json 的 dedup），"
                       "故原本「1446 行含 204 行逐字节重复」的口径作废：输出行 = 1242 = 509 规则 + 358 sample_case + 375 scoped_clause，重复 0。")
atomic(f"{L4}/registry/l4.json", json.dumps(reg,ensure_ascii=False,indent=1)+"\n")
reg2=json.load(open(f"{L4}/registry/l4.json",encoding="utf-8"))
print("  L4 改后：output_rows",reg2["numbering"]["totals"]["output_rows"],
      "duplicate_rows",reg2["numbering"]["totals"]["duplicate_rows"],
      "assigned_total",reg2["numbering"]["totals"]["assigned_total"])
print("  assignments 逐条未变:", reg2["assignments"]==A_before, f"({len(reg2['assignments'])} 条)")

l7=json.load(open(f"{L7}/registry/l7.json",encoding="utf-8"))
a7=l7["article_no_source"]
print("\n  L7 改前：candidate_rows",a7.get("candidate_rows"),"total_outputs",a7.get("total_outputs"))
a7["candidate_rows"]=1242
a7["total_outputs_note"]=("全部带条款号的定稿记录数 = 509 规则 + 358 sample_case + 375 scoped_clause。"
                          "候选文件原 1446 行中的 204 行同 case_id 逐字节重复行已于 run 20260924-1512 "
                          "在 L3 源头去重（kb/l3/registry/l3.json 的 dedup），现候选行数 = 1242，不再有重复行。")
a7["read_at"]="2026-09-24 15:20:00"
a7["read_at_previous"]="2026-09-24 13:35:00"
import time
atomic(f"{L7}/registry/l7.json", json.dumps(l7,ensure_ascii=False,indent=1)+"\n")
l72=json.load(open(f"{L7}/registry/l7.json",encoding="utf-8"))["article_no_source"]
print("  L7 改后：candidate_rows",l72["candidate_rows"],"total_outputs",l72["total_outputs"],"read_at",l72["read_at"])

print("\n=== §9 判据 ===")
eq = (l72["candidate_rows"]==l72["total_outputs"]==reg2["numbering"]["totals"]["assigned_total"]==1242)
print("  candidate_rows == total_outputs == assigned_total == 1242 :", eq)
print("  实际候选行数（磁盘）:",n(f"{L3}/candidates/sample_cases.jsonl")+n(f"{L3}/candidates/rules.jsonl")+n(f"{L3}/candidates/scoped_clauses.jsonl"))
can_no={c["article_no"] for c in CAN}
print("  canonical 四文件 article_no 数:",sum(len(load(f"{L4}/canonical/{f}")) for f in
      ("wording_entry.jsonl","wording_revision_pair.jsonl","sample_case.jsonl","scoped_clause.jsonl")))
json.dump({"l3":{"sample_cases":len(SC),"case_id_unique":len(set(cids)),
                 "rules":n(f"{L3}/candidates/rules.jsonl"),"rules_sha":sha(f"{L3}/candidates/rules.jsonl"),
                 "scoped":n(f"{L3}/candidates/scoped_clauses.jsonl"),"scoped_sha":sha(f"{L3}/candidates/scoped_clauses.jsonl"),
                 "canonical_sample_case":len(CAN),"field_diff":dict(diff_fields)},
           "l4":{"output_rows":reg2["numbering"]["totals"]["output_rows"],
                 "duplicate_rows":reg2["numbering"]["totals"]["duplicate_rows"],
                 "assigned_total":reg2["numbering"]["totals"]["assigned_total"],
                 "assignments_unchanged":reg2["assignments"]==A_before},
           "l7":{"candidate_rows":l72["candidate_rows"],"total_outputs":l72["total_outputs"],"read_at":l72["read_at"]},
           "three_way_equal":eq},
          open("kb/.work/batch12/step5_result.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
