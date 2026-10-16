import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle import bucket_name
HERE=os.path.dirname(os.path.abspath(__file__)); WB=os.path.dirname(HERE)
base=os.path.expanduser('~/.dsh/sessions')
for ns in sys.argv[1:] or ['a1']:
    tag = "_eval-kb-recall-20260930-_eval-work-%s-item-" % ns
    ds=[d for d in os.listdir(base) if tag in d]
    print("%s: 会话桶 %d 个" % (ns, len(ds)))
    for d in sorted(ds)[:3]:
        fs=glob.glob(os.path.join(base,d,'*','session.jsonl.zstd'))
        if fs: print("   ", d[-13:], os.path.getsize(fs[0]), "B")
