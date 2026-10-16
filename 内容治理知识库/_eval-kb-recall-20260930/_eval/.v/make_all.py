# -*- coding: utf-8 -*-
"""一键组装：adjudicate → YAML → test-cases.html → process.html → final-report.html"""
import os, sys, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); WB = os.path.dirname(HERE)
EVAL = "/Users/lute/.dsh/skills/root-skills-eval/scripts"
PY = "/usr/bin/python3"
def run(cmd, **kw):
    print("$", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    print((r.stdout or "")[-4000:]); 
    if r.returncode: print("[stderr]", (r.stderr or "")[-2000:])
    return r

name = "kb-recall"
papers = ["a"] + (["b"] if os.path.exists(os.path.join(HERE, "adjudicated-b.json")) or
                  os.path.exists(os.path.join(HERE, "b-round-1.jsonl")) else [])
for p in papers:
    if os.path.exists(os.path.join(HERE, "a-round-1.jsonl" if p == "a" else "b-round-1.jsonl")):
        run([PY, os.path.join(HERE, "adjudicate.py"), p])

run([PY, os.path.join(HERE, "make_yaml.py")])
y = os.path.join(WB, "%s-evaluation-report.yaml" % name)
run([PY, os.path.join(EVAL, "build-testcases-html.py"), "--name", name,
     "--results", os.path.join(HERE, "cases-a.json"),
     "--output", os.path.join(WB, "%s-test-cases.html" % name)] +
    (["--b-results", os.path.join(HERE, "cases-b.json")] if len(papers) > 1 else []))
run([PY, os.path.join(HERE, "build_process.py")])
# 输出前闸门（root-skills-check 的硬校验入口）
run([PY, os.path.join(EVAL, "build-final-report.py"), "--validate-only", "--name", name,
     "--version", "工作台副本 v1.2.0", "--yaml", y,
     "--cases", os.path.join(WB, "%s-test-cases.html" % name)])
run([PY, os.path.join(EVAL, "build-testcases-html.py"), "--check-only", "--name", name,
     "--results", os.path.join(HERE, "cases-a.json")] +
    (["--b-results", os.path.join(HERE, "cases-b.json")] if len(papers) > 1 else []))
