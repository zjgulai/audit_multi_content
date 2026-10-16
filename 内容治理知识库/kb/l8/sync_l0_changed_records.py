#!/usr/bin/env python3
"""把对账发现的「内容已变」记录同步进 L0（L0 = 飞书副本）。

输入：kb/l8/runs/<RUN>-l0-align.json 的 changed_detail + 快照 kb/l8/_stage/feishu-align/<RUN>/<tid>.ndjson
动作：旧文件归档到 kb/l0/_archive/<表名>-pre-refresh-<RUN>/ → 按飞书最新值重写 L0 记录文件
     → 复验（逐字段重比）→ 写运行记录。
不删除任何文件；不改字段集合（只改值，字段名集合变了要人工看）。
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import json
import os
import shutil
import sys

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1200"
APPLY = "--apply" in sys.argv
rep = json.load(open(f"kb/l8/runs/{RUN}-l0-align.json", encoding="utf-8"))
STAGE = f"kb/l8/_stage/feishu-align/{RUN}"

synced = []
for tid, ent in rep["tables"].items():
    if ent.get("status") != "ok" or not ent.get("changed_detail"):
        continue
    snap = {}
    for line in open(f"{STAGE}/{tid}.ndjson", encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            snap[r["record_id"]] = r
    tname = ent["table"]
    for item in ent["changed_detail"]:
        rid = item["record_id"]
        fs = snap.get(rid)
        if not fs:
            continue
        # 定位 L0 文件
        found = None
        for root, _d, files in os.walk("kb/l0/records"):
            for fn in files:
                if fn == f"{rid}.json":
                    found = os.path.join(root, fn)
        if not found:
            continue
        old = json.load(open(found, encoding="utf-8"))
        new = json.loads(json.dumps(old, ensure_ascii=False))  # deep copy
        changed_names = []
        for name in item["fields"]:
            if name not in new["fields"]:
                print(f"  [跳过] {rid} 字段 {name} 在 L0 里不存在（字段集合变化，需人工看）")
                continue
            v = fs.get(name)
            new["fields"][name]["value"] = v
            new["fields"][name]["raw_verbatim"] = v
            changed_names.append(name)
        new["raw_record"] = {k: v for k, v in fs.items() if k != "record_id"}
        new["observed_at"] = RUN
        new["note"] = (old.get("note") or "") + f" | {RUN} 按飞书侧最新值刷新（字段：{'、'.join(changed_names)}）"
        rec = {"run": RUN, "table": tname, "table_id": tid, "record_id": rid, "path": found,
               "fields_changed": changed_names,
               "before": {n: item["fields"][n]["l0"] for n in changed_names},
               "after": {n: item["fields"][n]["feishu"] for n in changed_names}}
        synced.append(rec)
        if APPLY:
            arch = f"kb/l0/_archive/{tname}-pre-refresh-{RUN}"
            os.makedirs(arch, exist_ok=True)
            shutil.copy2(found, f"{arch}/{rid}.json")
            tmp = found + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(new, fh, ensure_ascii=False, indent=1)
            json.load(open(tmp, encoding="utf-8"))      # 读回断言
            os.replace(tmp, found)

print(f"[{'已同步' if APPLY else '预演'}] 记录数 {len(synced)}")
for s in synced:
    print("  ·", s["table"], s["record_id"], s["fields_changed"])
    for k in s["fields_changed"]:
        print(f"      {k}: {s['before'][k]!r}  →  {s['after'][k]!r}")

# 复验
if APPLY:
    ok = True
    for s in synced:
        cur = json.load(open(s["path"], encoding="utf-8"))
        fs = None
        for line in open(f"{STAGE}/{s['table_id']}.ndjson", encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                if r["record_id"] == s["record_id"]:
                    fs = r
        for name in s["fields_changed"]:
            if cur["fields"][name]["value"] != fs.get(name):
                ok = False
                print(f"  ✗ 复验失败 {s['record_id']} {name}")
    print("复验:", "全部一致 ✓" if ok else "有不一致 ✗")
out = {"run": RUN, "synced": synced, "verified": bool(APPLY)}
json.dump(out, open(f"kb/l8/runs/{RUN}-l0-content-sync.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("运行记录:", f"kb/l8/runs/{RUN}-l0-content-sync.json")
