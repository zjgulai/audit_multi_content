#!/usr/bin/env python3
"""Read-only reader/summariser for DSH session transcripts (zstd jsonl)."""
import sys, json, zstandard, os

def read(path):
    with open(path,'rb') as f:
        d = zstandard.ZstdDecompressor()
        data = d.stream_reader(f).read()
    out=[]
    for line in data.decode('utf-8',errors='replace').splitlines():
        line=line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out

def types(recs):
    from collections import Counter
    return Counter(r.get('type') for r in recs)

if __name__=='__main__':
    mode = sys.argv[1]
    for p in sys.argv[2:]:
        recs = read(p)
        sid = os.path.basename(os.path.dirname(p))
        if mode=='types':
            print(f"### {sid} n={len(recs)}")
            for k,v in types(recs).most_common(): print(f"   {k}: {v}")
        elif mode=='dump':
            print(f"### {sid} n={len(recs)}")
            for i,r in enumerate(recs):
                print(i, json.dumps(r, ensure_ascii=False)[:900])
