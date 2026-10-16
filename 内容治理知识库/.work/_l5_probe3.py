import json, hashlib, collections, sys
sys.path.insert(0,"kb")
import kb_ledger as _kl
L3="kb/l3"; LF=f"{L3}/candidates/rules.jsonl"; L5="kb/l5"; MF=f"{L3}/manifest_l3.jsonl"
latest={}
for l in open(LF,encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["rule_id"]]=r
print("=== 输入现状 ===")
print("rules.jsonl 行数(非空):", sum(1 for l in open(LF,encoding="utf-8") if l.strip()), "| 唯一 rule_id:", len(latest))
print("生行缺三键的比例:", sum(1 for r in latest.values() if not all(k in r for k in _kl.ENRICH_KEYS)), "/", len(latest))
H={}
for _k,row in _kl.read_last_per_key(MF,"rule_id").items():
    if all(kk in row for kk in _kl.ENRICH_KEYS): H[row["rule_id"]]=row
print("manifest 富化行 rule_id 数:", len(H), "| 覆盖 rules.jsonl 的:", len(set(H)&set(latest)))

print("\n=== 复现 l5_export.py 的富化兜底（路径与代码逐字一致）===")
_hist={}
for _k,_row in _kl.read_last_per_key(f"{L3}/manifest_l3.jsonl","rule_id").items():
    if all(kk in _row for kk in _kl.ENRICH_KEYS): _hist[_row["rule_id"]]=_row
print("_hist 条数:", len(_hist))
_exc=None
try:
    _hist2 = _kl.read_last_per_key(f"{L3}/manifest_l3.jsonl","rule_id")
except Exception as e:
    _exc=e
print("文件存在?", __import__("os").path.exists(f"{L3}/manifest_l3.jsonl"), "| 读异常:", _exc)

for label, fill in (("兜底失效(按现状跑)", False), ("兜底生效(修路径后)", True)):
    lat = {k: dict(v) for k,v in latest.items()}
    bf=0
    if fill:
        for rid,row in list(lat.items()):
            h=_hist.get(rid)
            if not h: continue
            if not all(kk in row for kk in _kl.ENRICH_KEYS):
                m=dict(row)
                for x in _kl.ENRICH_KEYS:
                    if x in h: m[x]=h[x]
                lat[rid]=m; bf+=1
    P0=[r for r in lat.values() if r.get("p_level")=="P0"]
    base=[r for r in P0 if r.get("rule_kind")=="atomic" and r.get("authority") in ("expert","legal")]
    extra=[r for r in P0 if r.get("rule_kind")=="atomic" and (r.get("rule_code") or "") in {"H06"} and r not in base]
    sel=base+extra
    exc=collections.Counter()
    for r in lat.values():
        c=(r.get("rule_code") or "").strip()
        if r.get("p_level")!="P0": exc["non_P0"]+=1
        elif r.get("rule_kind")!="atomic": exc["P0_but_inductive"]+=1
        elif r.get("authority") not in ("expert","legal"):
            exc["P0_admitted_by_allowlist" if c in {"H06"} else "P0_but_authority_insufficient"]+=1
    ids=[("p-"+hashlib.sha1(("l5-0.1|"+r["rule_id"]).encode()).hexdigest()[:16], r["rule_id"]) for r in sel]
    print(f"\n--- {label} ---")
    print(" 富化补齐:", bf, "| P0:", len(P0), "→ 入选:", len(sel), "(白名单", len(extra), ") | 排除:", dict(exc))
    print(" pattern_id:", [a for a,_ in ids])
    if label.startswith("兜底生效"):
        cur=[json.loads(l) for l in open(f"{L5}/p0_patterns.jsonl",encoding="utf-8") if l.strip()]
        cs=[(d["pattern_id"],d["rule_id"]) for d in cur]
        print(" 现行模式表", len(cur), "条 | 集合相等:", set(ids)==set(cs), "| 顺序相同:", ids==cs)
        print(" 仅重算有:", set(ids)-set(cs), "| 仅现行有:", set(cs)-set(ids))
