#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ①能力图谱 / ②底座健康 的旧数据删掉，写入守衡数据。
用法: python3 write_to_feishu.py [--dry-run]
"""
import json, subprocess, sys, os

BASE = "IBo8bQjdIaRvx4s40E5cSzZSnsg"
T1, T2 = "tblG3bXeVXCuRixT", "tblyvhZAL2lStYwQ"
CLI = os.path.expanduser("~/.dsh/bin/lark-cli")
COMMON = ["--profile","dsh-kb","--as","bot"]
DRY = "--dry-run" in sys.argv

def run(args, inp=None):
    env = dict(os.environ); env["PATH"] = os.path.expanduser("~/.dsh/bin") + ":" + env.get("PATH","")
    p = subprocess.run([CLI]+args, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        print("FAILED:", " ".join(args)[:140]); print(p.stdout[-800:]); print(p.stderr[-800:]); sys.exit(1)
    try: return json.loads(p.stdout)
    except Exception: return {"raw": p.stdout}

def sel(v):        # 单选字段写数组
    return [v] if v else []

# ---------- 1. 旧记录 ID ----------
old1 = [json.loads(l)["record_id"] for l in open("t1.ndjson", encoding="utf-8") if l.strip()]
old2 = [json.loads(l)["record_id"] for l in open("t2.ndjson", encoding="utf-8") if l.strip()]
print(f"[1] 待删旧行：① {len(old1)} 行 · ② {len(old2)} 行")

# ---------- 2. 新记录 ----------
n1 = json.load(open("t1_shouheng_records.json", encoding="utf-8"))
n2 = json.load(open("t2_shouheng_records.json", encoding="utf-8"))
for r in n1:
    r["L1底座"]   = sel(r["L1底座"])
    r["状态"]     = sel(r["状态"])
    r["案例类型"] = sel(r["案例类型"])
for r in n2:
    r["当前状态"] = sel(r["当前状态"])
print(f"[2] 待写新行：① {len(n1)} 行 · ② {len(n2)} 行")

if DRY:
    print("[dry-run] 只打印，不写")
    print(json.dumps(n1[0], ensure_ascii=False)[:400])
    sys.exit(0)

# ---------- 3. 删除 ----------
for tbl, ids, label in [(T1, old1, "①"), (T2, old2, "②")]:
    for i in range(0, len(ids), 200):
        chunk = ids[i:i+200]
        r = run(["base","+record-delete","--base-token",BASE,"--table-id",tbl,
                 "--json", json.dumps({"record_id_list": chunk}), "--yes"]+COMMON)
        print(f"[3] {label} 删除 {i+len(chunk)}/{len(ids)} → ok={r.get('ok')}")

# ---------- 4. 写入 ----------
for tbl, rows, label in [(T1, n1, "①"), (T2, n2, "②")]:
    for i in range(0, len(rows), 100):   # 保守：每次 100 条
        chunk = rows[i:i+100]
        r = run(["base","+record-batch-create","--base-token",BASE,"--table-id",tbl,
                 "--json", json.dumps({"create_records": chunk}, ensure_ascii=False)]+COMMON)
        got = len((r.get("data") or {}).get("records") or [])
        print(f"[4] {label} 写入 {i+len(chunk)}/{len(rows)} → ok={r.get('ok')} 返回 {got} 条")

print("\n✅ 完成。接着跑 verify.py 回读校验。")
