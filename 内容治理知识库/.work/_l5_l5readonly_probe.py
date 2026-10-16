import json, hashlib, collections, sys
sys.path.insert(0,"kb")
import kb_ledger as _kl
L3="kb/l3/candidates/rules.jsonl"; L5="kb/l5/p0_patterns.jsonl"
latest={}
for l in open(L3,encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["rule_id"]]=r
d=_kl.read_last_per_key(f"{L3}/manifest_l3.jsonl","rule_id")
print("DEBUG len(d)=",len(d))
HIST={}
for _k,row in d.items() if False else d.items()
for _k,row in list(d.items())(f"{L3}/manifest_l3.jsonl","rule_id").items():
    if all(kk in row for kk in _kl.ENRICH_KEYS): HIST[row["rule_id"]]=row
bf=0
for rid,row in list(latest.items()):
    h=HIST.get(rid)
    if not h: continue
    if not all(kk in row for kk in _kl.ENRICH_KEYS):
        m=dict(row)
        for x in _kl.ENRICH_KEYS:
            if x in h: m[x]=h[x]
        latest[rid]=m; bf+=1
print("latest 规则数:",len(latest),"| 富化兜底补齐:",bf,"| manifest 富化行:",len(HIST))
print("补齐后仍缺三键:",sum(1 for r in latest.values() if not all(k in r for k in _kl.ENRICH_KEYS)))
P0=[r for r in latest.values() if r.get("p_level")=="P0"]
base=[r for r in P0 if r.get("rule_kind")=="atomic" and r.get("authority") in ("expert","legal")]
extra=[r for r in P0 if r.get("rule_kind")=="atomic" and (r.get("rule_code") or "") in {"H06"} and r not in base]
sel=base+extra
exc=collections.Counter()
for r in latest.values():
    c=(r.get("rule_code") or "").strip()
    if r.get("p_level")!="P0": exc["non_P0"]+=1
    elif r.get("rule_kind")!="atomic": exc["P0_but_inductive"]+=1
    elif r.get("authority") not in ("expert","legal"):
        exc["P0_admitted_by_allowlist" if c in {"H06"} else "P0_but_authority_insufficient"]+=1
print("P0",len(P0),"→ 入选",len(sel),"(其中白名单准入",len(extra),") | 排除",dict(exc))
print("入选 rule_code 唯一性:", "PASS" if len({(r.get('rule_code') or '') for r in sel})==len(sel) else "FAIL")
ids=[("p-"+hashlib.sha1(("l5-0.1|"+r["rule_id"]).encode()).hexdigest()[:16], r["rule_id"], (r.get("rule_code") or "").strip()) for r in sel]
for p,rid,rc in ids: print("   ",p,"|",rid,"|",rc)
cur=[json.loads(l) for l in open(L5,encoding="utf-8") if l.strip()]
curset=[(d["pattern_id"],d["rule_id"]) for d in cur]
newset=[(a,b) for a,b,_ in ids]
print("现行模式表",len(cur),"条 | 集合相等:",set(newset)==set(curset),"| 顺序相同:",newset==curset)
print("仅重算有:",set(newset)-set(curset),"| 仅现行有:",set(curset)-set(newset))
