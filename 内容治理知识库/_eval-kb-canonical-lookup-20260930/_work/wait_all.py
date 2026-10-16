import json,os,sys,time
sys.path.insert(0,'.')
from dsh_sess import scan
BASE=os.path.expanduser("~/.dsh/sessions")
BUCKET=("--Users-lute-Documents-skill-test-~6267~884Cskills-~6267~884Cskills-"
        "skills-~56DE~5F52~6D4B~8BD5-~77E5~8BC6~5E93-~5185~5BB9~6CBB~7406--")
maps=[]
for m in ("map_r1.json","map_r2.json","map_r3.json"):
    maps.append(json.load(open(m,encoding='utf-8')))
deadline=time.time()+int(sys.argv[1] if len(sys.argv)>1 else 480)
while True:
    done=tot=0; pending=[]
    for mi,mp in enumerate(maps,1):
        for cid,sid in mp.items():
            tot+=1
            p=os.path.join(BASE,BUCKET,sid,"session.jsonl.zstd")
            ok=False
            if os.path.exists(p):
                try:
                    recs=scan(p)
                    ok=any(r.get("type")=="turn/end" for r in recs)
                except Exception: ok=False
            if ok: done+=1
            else: pending.append(f"R{mi}#{cid}")
    print(f"[{time.strftime('%H:%M:%S')}] 已收尾 {done}/{tot}", flush=True)
    if done==tot or time.time()>deadline:
        print("pending:", pending, flush=True); break
    time.sleep(30)
