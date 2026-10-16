import json,os,sys,time
sys.path.insert(0,'.')
from dsh_sess import scan
BASE=os.path.expanduser("~/.dsh/sessions")
B=("--Users-lute-Documents-skill-test-~6267~884Cskills-~6267~884Cskills-"
   "skills-~56DE~5F52~6D4B~8BD5-~77E5~8BC6~5E93-~5185~5BB9~6CBB~7406--")
maps=[json.load(open("v2/map_r%d.json"%i,encoding='utf-8')) for i in (1,2,3)]
dl=time.time()+int(sys.argv[1])
while True:
    done=tot=0; pend=[]
    for mi,mp in enumerate(maps,1):
        for cid,sid in mp.items():
            tot+=1
            p=os.path.join(BASE,B,sid,"session.jsonl.zstd"); ok=False
            if os.path.exists(p):
                try: ok=any(r.get("type")=="turn/end" for r in scan(p))
                except Exception: ok=False
            if ok: done+=1
            else: pend.append("R%d#%s"%(mi,cid))
    print("[%s] 收尾 %d/%d"%(time.strftime('%H:%M:%S'),done,tot),flush=True)
    if done==tot or time.time()>dl:
        print("pending:",pend,flush=True); break
    time.sleep(30)
