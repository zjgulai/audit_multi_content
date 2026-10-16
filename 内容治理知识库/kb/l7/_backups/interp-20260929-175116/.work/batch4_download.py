#!/usr/bin/env python3
"""batch4 · 下载「正面和负面样本」新 schema 下的 240 个附件（只读）。最多重试 2 次。"""
import json, os, subprocess, sys, hashlib, time
from concurrent.futures import ThreadPoolExecutor

ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
BASE, TBL = "GnRZbIuXraCzf0sGr2UcmZ62nfc", "tbld8qE92YaY38Yz"
OUT = "kb/.work/batch4/att"
os.makedirs(OUT, exist_ok=True)
recs = [json.loads(l) for l in open("kb/.work/batch4/正面和负面样本.ndjson", encoding="utf-8") if l.strip()]
tasks = []
for r in recs:
    for fld in ("图片素材", "视频素材"):
        for a in (r.get(fld) or []):
            if isinstance(a, dict) and a.get("file_token"):
                tasks.append((r["record_id"], fld, a["file_token"], a.get("name"),
                              os.path.splitext(a.get("name") or "")[1] or ".bin"))
print("待下载附件:", len(tasks))
ops, fail = [], []
t0 = time.time()
lock = __import__("threading").Lock()

def one(task):
    rid, fld, tok, nm, ext = task
    dst = f"{OUT}/{tok}{ext}"
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return ("cached", None)
    last = None
    for attempt in range(3):
        p = subprocess.run(["lark-cli", "base", "+record-download-attachment",
                            "--base-token", BASE, "--table-id", TBL, "--record-id", rid,
                            "--file-token", tok, "--output", dst, "--overwrite"],
                           capture_output=True, text=True, env=ENV, timeout=600)
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            return ("ok", {"op": "base +record-download-attachment", "nature": "read",
                           "target": f"attachment:{tok}", "note": f"{nm}（record={rid} field={fld}）"})
        last = {"record_id": rid, "field": fld, "file_token": tok, "name": nm,
                "rc": p.returncode, "stderr": (p.stderr or "")[:200]}
    return ("fail", last)

done = 0
with ThreadPoolExecutor(max_workers=8) as ex:
    for status, payload in ex.map(one, tasks):
        done += 1
        if status == "fail":
            fail.append(payload)
        elif status == "ok":
            ops.append(payload)
        if done % 40 == 0:
            print(f"  {done}/{len(tasks)} fail={len(fail)} {time.time()-t0:.0f}s", flush=True)
ok = sum(1 for _ in range(0)) + len(ops) + sum(1 for f in os.listdir(OUT))
ok = len([f for f in os.listdir(OUT) if os.path.getsize(os.path.join(OUT, f)) > 0])
json.dump({"total": len(tasks), "ok": ok, "fail": fail, "ops": ops},
          open("kb/.work/batch4/dl_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"完成: ok={ok} fail={len(fail)} 用时 {time.time()-t0:.0f}s")
if fail:
    print(json.dumps(fail[:5], ensure_ascii=False, indent=1))
