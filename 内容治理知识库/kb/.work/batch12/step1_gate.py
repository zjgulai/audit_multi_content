#!/usr/bin/env python3
"""§5 判据（全过才可进 §6）。"""
import json, os, re, hashlib, collections
L0="kb/l0"; REG=f"{L0}/registry/kb.json"; MAN=f"{L0}/manifest.jsonl"
def h(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
ok=True
def chk(name, cond, detail=""):
    global ok
    ok = ok and cond
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))

print("=== §5 判据 ===")
rows=[json.loads(l) for l in open(MAN,encoding="utf-8") if l.strip()]
chk("① 台账只增不减", len(rows)>=3651, f"3651 → {len(rows)}（追加 {len(rows)-3651} 行）")

reg=json.load(open(REG,encoding="utf-8"))
print("\n② 悬空引用核对清单")
live=[("source_kind_retired[0].archived_to",reg["source_kind_retired"][0]["archived_to"]),
      ("excluded_scope.archived_to",reg["excluded_scope"]["archived_to"])]
for who,p in live:
    chk(f"   live 指针 {who}", os.path.exists(p), p)
latest={}
for r in rows: latest[r["resource_key"]]=r
hist_bad=[]; hist_superseded=0; hist_ok=0
for r in rows:
    mt=r.get("moved_to")
    if not mt: continue
    if os.path.exists(mt): hist_ok+=1; continue
    l=latest[r["resource_key"]]
    if l["status"] in ("gone","retracted"): hist_bad.append((r["resource_key"],mt,l["status"]))
    else: hist_superseded+=1
chk("   历史指针 moved_to（未被取代且解析失败 == 0）", not hist_bad,
    f"解析成功 {hist_ok}；已被后续行取代 {hist_superseded}；真悬空 {len(hist_bad)}")
for k,mt,s in hist_bad[:5]: print("      MISS",k,mt,s)

print("\n③ changes 引用的键核对清单")
keys=set(reg); bad=[]
for i,c in enumerate(reg["changes"]):
    for k in (c.get("keys") or ([c["key"]] if c.get("key") else [])):
        b=re.split(r"[\[（(]",k)[0].strip()
        if b and b not in keys: bad.append((i,c.get("run_id"),k,b))
chk("   被 changes 引用的顶层键全部存在", not bad, f"changes {len(reg['changes'])} 条，引用键缺失 {len(bad)}")
for i,run,k,b in bad: print(f"      MISS changes[{i}] run={run} '{k}' → '{b}'")

print("\n④ 恢复件")
REC="kb/.work/batch11/recovered_ledger_rows.jsonl"
n=sum(1 for l in open(REC,encoding="utf-8") if l.strip())
for l in open(REC,encoding="utf-8"):
    if l.strip(): json.loads(l)
chk("   已存档且可解析", n==12, f"{n} 行  sha256={h(REC)}")
SRC="kb/.work/batch12/recovered_ledger_rows.sources.md"
chk("   重建依据来源清单已落盘", os.path.exists(SRC), f"{os.path.getsize(SRC)} B")

print("\n⑤ L0↔L1 分叉结论")
c=reg.get("ledger_divergence_conclusion") or {}
chk("   已写进 registry 且含依据", bool(c.get("verdict")) and len(c.get("basis") or [])>=3,
    f"basis {len(c.get('basis') or [])} 条；verdict='{(c.get('verdict') or '')[:40]}…'")

print("\n=== §5 总判：", "全过 ✔ 可进 §6" if ok else "未过 ✘ 停工", "===")
json.dump({"pass":ok,"rows_before":3651,"rows_after":len(rows),
           "live_pointers":[(w,p,os.path.exists(p)) for w,p in live],
           "hist_ok":hist_ok,"hist_superseded":hist_superseded,"hist_dangling":hist_bad,
           "changes_key_missing":bad,"recovery_rows":n,"recovery_sha256":h(REC)},
          open("kb/.work/batch12/step1_gate.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
