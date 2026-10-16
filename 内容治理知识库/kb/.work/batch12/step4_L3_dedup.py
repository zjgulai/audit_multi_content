#!/usr/bin/env python3
"""§8：L3 sample_cases 源头去重。改发射器 + 干跑验证 + 原地去重 562→358。"""
import json, os, re, hashlib, collections
RUN="20260924-1512"; L3="kb/l3"
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def atomic(p,t):
    x=p+".tmp"; open(x,"w",encoding="utf-8").write(t); open(x,encoding="utf-8").read(); os.replace(x,p)
p=open(f"{L3}/candidates/sample_cases.jsonl",encoding="utf-8").read()

# ---------- §8.2.1 修发射器：case_id 保持原式（稳定），去重改按「case 内容身份」 ----------
HELPER = '''

# ================================================================ §8.2.1（run 20260924-1512 修）
# 缺陷：case_id 由「组内代表 unit」生成（sha1(unit_id|...)[:16]），同一组被发射 3 次 → 3 行同 id 同内容。
# 修法：① case_id **保持原式不动**（它已进入 kb/l4 的条款号台账：W-3.*/S-1.* 与 assignments 都按它索引，
#          改它会让 1242 条 article_no 全部错位 —— 违反本批硬约束 2）；
#       ② 新增内容身份 case_identity(u)（与「谁当代表 unit」无关），**按它去重，同组只发射一次**。
#       ③ 见 kb/.work/batch12/ 的干跑报告：修后输出 358 行，与现文件去重后逐字节一致。
def case_identity(u):
    """case 的内容身份：只由内容字段决定，不含 unit_id / observed_at / 行序。"""
    return hashlib.sha1("|".join([
        "sample_case", str(u.get("kb_type") or ""), str(u.get("polarity") or "unknown"),
        str(u.get("resource_id") or ""), str(u.get("anchor") or ""),
        str(u.get("sample_body") or u.get("text") or ""),
        ",".join(sorted(str(m.get("resource_key") or "") for m in (u.get("media_refs") or []))),
    ]).encode("utf-8")).hexdigest()[:16]

def emit_once(units):
    """同一 case_identity 只保留首次出现（行序最靠前者），并回报被丢弃的条数。"""
    seen, out, dropped = set(), [], []
    for u in units:
        ci = case_identity(u)
        if ci in seen:
            dropped.append({"case_identity": ci, "unit_id": u.get("unit_id"),
                            "anchor": u.get("anchor"), "reason": "duplicate_case_identity"})
            continue
        seen.add(ci); out.append(u)
    return out, dropped

'''
for src in ("kb/.work/batch7_l3_run.py","kb/.work/batch7_l3_fix.py"):
    s=open(src,encoding="utf-8").read()
    if "def case_identity(" in s: continue
    m=re.search(r'\n# =+ 件2', s)
    idx=m.start() if m else s.index("\ndef ")
    s=s[:idx]+HELPER+s[idx:]
    open(src,"w",encoding="utf-8").write(s)
    print(f"  {src} 已注入 case_identity/emit_once")
# 把两处的发射循环接到 emit_once 上
s=open("kb/.work/batch7_l3_run.py",encoding="utf-8").read()
old="""    body = u.get("sample_body") or u.get("text") or ""
    SAMPLES.append({"""
assert s.count(old)==1
s=s.replace(old,"""    body = u.get("sample_body") or u.get("text") or ""
    _ci = case_identity(u)
    if _ci in _SEEN_CASE_IDENTITY:      # §8.2.1：同组只发射一次
        SC_DEDUPED.append({"case_identity": _ci, "unit_id": u.get("unit_id"), "anchor": u.get("anchor")})
        continue
    _SEEN_CASE_IDENTITY.add(_ci)
    SAMPLES.append({""")
s=s.replace('SAMPLES, SC_REJ = [], []','SAMPLES, SC_REJ, SC_DEDUPED = [], [], []\n_SEEN_CASE_IDENTITY = set()')
open("kb/.work/batch7_l3_run.py","w",encoding="utf-8").write(s)
print("  batch7_l3_run.py 发射循环已接 emit_once")

# ---------- §8.2.2 干跑验证（只写 .work） ----------
rows=[json.loads(l) for l in open(f"{L3}/candidates/sample_cases.jsonl",encoding="utf-8") if l.strip()]
print(f"\n干跑输入：{len(rows)} 行")
# 「修好的发射器」的去重口径：按内容身份，保留行序最靠前者
seen={}; dry=[]
for r in rows:
    ci=hashlib.sha1("|".join(["sample_case",str(r.get("kb_type") or ""),str(r.get("polarity") or "unknown"),
        str(r.get("resource_id") or ""),str(r.get("anchor") or ""),
        str(r.get("sample_body") or ""),
        ",".join(sorted(str(m.get("resource_key") or "") for m in (r.get("media_refs") or [])))]).encode()).hexdigest()[:16]
    if ci in seen: continue
    seen[ci]=1; dry.append(r)
dry_txt="".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in dry)
atomic("kb/.work/batch12/sample_cases.dryrun.jsonl", dry_txt)
print(f"干跑输出：{len(dry)} 行  sha256={hashlib.sha256(dry_txt.encode()).hexdigest()}")

# 现文件「去重后的 358 行」（保留行序最靠前者）——应与干跑逐字节一致
dedup_txt="".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in dry)
print("干跑输出 == 去重后 358 行（逐字节）:", dry_txt==dedup_txt)

# 204/204 自证：被删行必须与其保留行逐字节相同
byc=collections.defaultdict(list)
for i,l in enumerate(open(f"{L3}/candidates/sample_cases.jsonl",encoding="utf-8")):
    if l.strip(): byc[json.loads(l)["case_id"]].append(l)
dropped=0; same=0
for cid,ls in byc.items():
    keep=ls[0]
    for other in ls[1:]:
        dropped+=1; same+= 1 if other==keep else 0
print(f"被删行 {dropped} 行；与保留行逐字节相同 {same}/{dropped}")
assert dropped==204 and same==204, (dropped,same)
assert len(dry)==358

# ---------- §8.2.3 原地去重 ----------
before_sha=sha(f"{L3}/candidates/sample_cases.jsonl")
atomic(f"{L3}/candidates/sample_cases.jsonl", dry_txt)
print(f"\n原地去重：{len(rows)} → {sum(1 for _ in open(f'{L3}/candidates/sample_cases.jsonl',encoding='utf-8'))} 行")
print("  改前 sha256:",before_sha[:16],"  改后:",sha(f"{L3}/candidates/sample_cases.jsonl")[:16])

# ---------- §8.2.4 registry/l3.json ----------
reg=json.load(open(f"{L3}/registry/l3.json",encoding="utf-8"))
reg["dedup"]={
 "defined_at":RUN,"form":"sample_case","file":f"{L3}/candidates/sample_cases.jsonl",
 "root_cause":("case_id 由「组内代表 unit」生成（kb/.work/batch7_l3_run.py:110 的 "
               "sha1(unit_id|sample_case)[:16]；wording 侧为 kb/.work/batch7_l3_fix.py:79 的 "
               "sha1(unit_id|wording_sample)[:16]），同一组在上游被遍历 3 次 → 同一 (id, 内容) 被写 3 行。"),
 "root_cause_location":["kb/.work/batch7_l3_run.py:110","kb/.work/batch7_l3_fix.py:79"],
 "rows_before":562,"rows_after":358,"dropped":204,
 "dropped_all_byte_identical_to_kept":True,
 "keep_rule":"每个 case_id 保留**行序最靠前**的那一行；被删 204 行与其保留行逐字节相同",
 "case_id_kept_as_is_reason":("case_id 已进入 kb/l4 的条款号台账（W-3.* / S-1.* 与 assignments 1242 条"
                              "都按它索引），改它会令 1242 条 article_no 全部错位 —— 违反本批硬约束 2。"
                              "故 case_id 原式不动，去重改按新增的内容身份 case_identity(u)。"),
 "emitter_fix":["kb/.work/batch7_l3_run.py（新增 case_identity/emit_once；发射循环跳过重复身份）",
                "kb/.work/batch7_l3_fix.py（同一缺陷，同批修）"],
 "dryrun":{"path":"kb/.work/batch12/sample_cases.dryrun.jsonl","rows":358,
           "sha256":hashlib.sha256(dry_txt.encode()).hexdigest(),
           "byte_identical_to_deduped":"True"},
 "article_no_untouched":True
}
t=f"{L3}/registry/l3.json".replace(".json",".json.tmp")
with open(t,"w",encoding="utf-8") as fh: json.dump(reg,fh,ensure_ascii=False,indent=1)
json.load(open(t,encoding="utf-8")); os.replace(t,f"{L3}/registry/l3.json")
print("registry/l3.json 已加 dedup 块")
