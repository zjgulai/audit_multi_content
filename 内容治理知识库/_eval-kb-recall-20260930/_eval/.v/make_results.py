# -*- coding: utf-8 -*-
"""adjudicated-*.json → results.json（score-trigger-eval.py 输入格式）"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
paper = sys.argv[1] if len(sys.argv) > 1 else "a"
rows = json.load(open(os.path.join(HERE, "adjudicated-%s.json" % paper), encoding="utf-8"))
out = dict(skill_name="kb-recall", results=[
    dict(id=r["id"], type=r["type"], expected=r["expect"], tags=r["tags"],
         title=r["title"], rounds=r["rounds"]) for r in rows])
p = os.path.join(HERE, "results-%s.json" % paper)
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", p, len(out["results"]), "条")
