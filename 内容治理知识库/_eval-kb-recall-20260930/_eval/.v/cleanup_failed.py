# -*- coding: utf-8 -*-
"""剔除 exit_code!=0（被 kill）的记录，让 --resume 重跑这些 id。"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
for f in sys.argv[1:]:
    p = os.path.join(HERE, f)
    if not os.path.exists(p): print("skip", f); continue
    keep, drop = [], []
    for l in open(p, encoding="utf-8"):
        if not l.strip(): continue
        r = json.loads(l)
        (keep if r.get("exit_code") == 0 else drop).append((l, r["id"]))
    with open(p, "w", encoding="utf-8") as fh:
        for l, _ in keep: fh.write(l)
    print("%s: 保留 %d，剔除 %d（%s）" % (f, len(keep), len(drop), [d for _, d in drop]))
