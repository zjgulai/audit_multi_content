import json, hashlib, collections, sys
sys.path.insert(0,"kb")
import kb_ledger as _kl
L3="kb/l3/candidates/rules.jsonl"; L5="kb/l5/p0_patterns.jsonl"
latest={}
for l in open(L3,encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["rule_id"]]=r
d=_kl.read_last_per_key(L3.replace("candidates/rules.jsonl","manifest_l3.jsonl"),"rule_id")
print("DEBUG len(d)=",len(d))
HIST={}
for _k,row in d.items():
    if all(kk in row for kk in _kl.ENRICH_KEYS): HIST[row["rule_id"]]=row
print("DEBUG len(HIST)=",len(HIST))
