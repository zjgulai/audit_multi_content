import os,json,zstandard,re
SESS=os.path.expanduser("~/.dsh/sessions")
dec=zstandard.ZstdDecompressor()
NEEDLE="召回一下婴幼儿睡眠安全相关的知识单元"
for base in os.listdir(SESS):
    if "~5185~5BB9~6CBB~7406" not in base: continue
    d=os.path.join(SESS,base)
    for aid in os.listdir(d):
        p=os.path.join(d,aid)
        if not os.path.isdir(p): continue
        fs=[os.path.join(p,f) for f in os.listdir(p) if f.endswith(".jsonl.zstd")]
        if not fs: continue
        fp=max(fs,key=os.path.getmtime)
        if os.path.getmtime(fp)<1780000000: continue
        with open(fp,'rb') as fh: raw=dec.stream_reader(fh).read().decode('utf-8','replace')
        if NEEDLE not in raw: continue
        print("FOUND",aid[:8],os.path.getmtime(fp),len(raw))
        evs=[json.loads(l) for l in raw.split("\n") if l.strip()]
        m=next((e for e in evs if e.get('type')=='session'),{})
        print(" session meta keys:",list(m.keys()))
        print(" meta:",json.dumps({k:v for k,v in m.items() if k!='data'},ensure_ascii=False)[:400])
        cnt={}
        for e in evs: cnt[e.get('type')]=cnt.get(e.get('type'),0)+1
        print(" types:",cnt)
        for e in evs[:4]:
            print("  EV",e.get('type'),json.dumps(e.get('data'),ensure_ascii=False)[:300])
        break
    else: continue
    break
