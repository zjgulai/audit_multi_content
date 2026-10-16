import zstandard, json, os, sys, glob
BASE="/Users/lute/.dsh/sessions"
def load(p):
    try:
        d=zstandard.ZstdDecompressor().stream_reader(open(p,'rb')).read()
    except Exception:
        d=zstandard.ZstdDecompressor().decompressobj().decompress(open(p,'rb').read())
    return d.decode('utf-8',errors='replace')
def sessions_for(cwd):
    esc=cwd.replace('/','-').replace('\u4e2d','~4E2D')  # not used
    return []
def scan(path):
    out=[]
    for l in load(path).splitlines():
        try: out.append(json.loads(l))
        except: pass
    return out
if __name__=="__main__":
    recs=scan(sys.argv[1])
    head=recs[0]
    print(json.dumps({k:head.get(k) for k in ('id','parentSession','origin','cwd')},ensure_ascii=False))
    for r in recs:
        if r.get("type")=="tool/call" and r.get("data",{}).get("name")=="skill":
            print("SKILL CALL:", r["data"]["arguments"])
        if r.get("type")=="user/message":
            print("USER:", json.dumps(r.get("data"),ensure_ascii=False)[:200])
