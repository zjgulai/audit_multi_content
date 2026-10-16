import json,os,sys,glob,re
sys.path.insert(0,'.')
from dsh_sess import scan
BASE=os.path.expanduser("~/.dsh/sessions")
BUCKET=("--Users-lute-Documents-skill-test-~6267~884Cskills-~6267~884Cskills-"
        "skills-~56DE~5F52~6D4B~8BD5-~77E5~8BC6~5E93-~5185~5BB9~6CBB~7406--")
maps=[]
for m in sys.argv[1:]:
    maps.append(json.load(open(m,encoding='utf-8')))
PAT=re.compile(r"l4_article|kb_pipeline|--apply|rm -rf|l4_gate|kb_publish|gen-host-library|>\s*kb/|write_text|shutil\.copy")
for mp in maps:
    for cid,sid in sorted(mp.items(), key=lambda x:int(x[0])):
        p=os.path.join(BASE,BUCKET,sid,"session.jsonl.zstd")
        if not os.path.exists(p):
            print(f"#{cid} {sid} (no session)"); continue
        recs=scan(p)
        hits=[]
        for r in recs:
            if r.get("type")=="tool/call":
                nm=r["data"].get("name"); arg=str(r["data"].get("arguments"))
                if nm=="bash" and PAT.search(arg):
                    hits.append(arg[:220])
        if hits:
            print(f"--- #{cid} {sid} 命中 {len(hits)} 条写库嫌疑命令")
            for h in hits[:4]: print("     ", h.replace("\\n"," ")[:220])
