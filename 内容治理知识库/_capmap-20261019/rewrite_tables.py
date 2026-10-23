#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把当前表内容整体替换成本地成稿（读当前 record_id → 删除 → 重写）。
与 write_to_feishu.py 的区别：那个按 t1.ndjson（Emily 旧 ID）删，这个按「表里现在是什么」删。
"""
import json, subprocess, sys, os

BASE = "IBo8bQjdIaRvx4s40E5cSzZSnsg"
T1, T2 = "tblG3bXeVXCuRixT", "tblyvhZAL2lStYwQ"
CLI = os.path.expanduser("~/.dsh/bin/lark-cli")
COMMON = ["--profile","dsh-kb","--as","bot"]

def run(args):
    env = dict(os.environ); env["PATH"] = os.path.expanduser("~/.dsh/bin") + ":" + env.get("PATH","")
    p = subprocess.run([CLI]+args, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        print("FAILED:", " ".join(args)[:140]); print(p.stdout[-800:]); print(p.stderr[-800:]); sys.exit(1)
    try: return json.loads(p.stdout)
    except Exception: return {"raw": p.stdout}

def sel(v): return [v] if v else []

def current_ids(tbl):
    r = run(["base","+record-list","--base-token",BASE,"--table-id",tbl,
             "--limit","200","--format","json"]+COMMON)
    d = r.get("data") or {}
    if isinstance(d, dict):
        if d.get("record_id_list"): return list(d["record_id_list"])
        recs = d.get("records") or d.get("items") or []
        return [x.get("record_id") or x.get("recordId") for x in recs]
    return []

n1 = json.load(open("t1_shouheng_records.json", encoding="utf-8"))
n2 = json.load(open("t2_shouheng_records.json", encoding="utf-8"))
for r in n1:
    r["L1底座"], r["状态"], r["案例类型"] = sel(r["L1底座"]), sel(r["状态"]), sel(r["案例类型"])
for r in n2:
    r["当前状态"] = sel(r["当前状态"])

for tbl, rows, label in [(T1, n1, "①"), (T2, n2, "②")]:
    ids = [i for i in current_ids(tbl) if i]
    print(f"[{label}] 当前 {len(ids)} 行 → 删除后写入 {len(rows)} 行")
    for i in range(0, len(ids), 200):
        r = run(["base","+record-delete","--base-token",BASE,"--table-id",tbl,
                 "--json", json.dumps({"record_id_list": ids[i:i+200]}), "--yes"]+COMMON)
    for i in range(0, len(rows), 100):
        run(["base","+record-batch-create","--base-token",BASE,"--table-id",tbl,
             "--json", json.dumps({"create_records": rows[i:i+100]}, ensure_ascii=False)]+COMMON)
    print(f"[{label}] 完成")
print("✅ 重写完成")
