import os,json,zstandard,glob,re
SESS=os.path.expanduser("~/.dsh/sessions")
dec=zstandard.ZstdDecompressor()
hits=[]
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
        hits.append((os.path.getmtime(fp),base,aid,fp))
hits.sort(reverse=True)
print("recent sessions:",len(hits))
for mt,base,aid,fp in hits[:6]:
    evs=[]
    with open(fp,'rb') as fh:
        txt=dec.stream_reader(fh).read().decode('utf-8','replace')
    for l in txt.split("\n"):
        if l.strip():
            try: evs.append(json.loads(l))
            except: pass
    m=next((e for e in evs if e.get('type')=='session'),{})
    ut=[];sc=[];inj=[]
    for e in evs:
        t=e.get('type');d=e.get('data') or {}
        if t=='user/message':
            c=d.get('message',{}).get('content') if isinstance(d.get('message'),dict) else None
            if isinstance(c,list):
                for part in c:
                    if isinstance(part,dict) and part.get('type')=='text':
                        ut.append(part.get('text','')[:60])
            for mm in re.finditer(r'<skill_content\s+name="([^"]+)"',json.dumps(d,ensure_ascii=False)): inj.append(mm.group(1))
        if t=='tool/call':
            if d.get('name')=='skill':
                try: a=json.loads(d.get('arguments') or '{}')
                except: a={}
                sc.append(a.get('name'))
    print("---",aid[:8],m.get('origin'),m.get('createdAt'),"events",len(evs))
    print("   skills:",sc,"injected:",sorted(set(inj)))
    print("   user0:",(ut[0] if ut else '')[:70].replace("\n"," "))
