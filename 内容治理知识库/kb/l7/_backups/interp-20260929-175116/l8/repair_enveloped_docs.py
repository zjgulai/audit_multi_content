#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L8 续修：把「该被人/agent 读、却是信封态」的 .md 改成明文落盘（内容逐字不变）。

范围（本轮）：
  · kb/l7/**/*.md           —— 消费侧 skill 的参考文件与输出模板 + l7 证据/报告
  · kb/versions/VERSIONS.md —— 版本纪律说明
**不含** kb/l0…kb/l6（冻结层）、kb/.work/**（他人产物）。这两类只在报告里登记。

做法：python 读逻辑内容（明文）+ dd 存旧物理字节到 kb/l8/_archive/ → 交给 node 明文写盘
（复用 kb/l8/repack_write.mjs，内含逐文件读回断言）→ 逐条对账：
  ① node 侧 size == python 侧 size（不再是信封）
  ② 逻辑内容 sha256 前后一致
  ③ 若该文件在 kb/l7/runs/20260923-1500.json 的 artifacts 里留了哈希，必须仍然相等
"""
import hashlib
import json
import os
import subprocess
import sys
import time

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
KB = os.path.expanduser("~/.dsh/Momcozy知识库")
RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
DSH = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"
L8 = os.path.join(WS, "kb", "l8")
ARCH = os.path.join(L8, "_archive", f"enveloped-docs-{RUN}")
PAYLOAD = os.path.join(L8, "_stage", f"docs_payload_{RUN}.json")
sha = lambda b: hashlib.sha256(b).hexdigest()
os.chdir(WS)


def env_node_size(paths):
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
    code = 'const fs=require("fs");console.log(JSON.stringify(JSON.parse(process.argv[1]).map(p=>fs.statSync(p).size)))'
    out = subprocess.run([DSH, "-e", code, json.dumps(paths)], capture_output=True, text=True, env=env)
    return json.loads(out.stdout)


def raw_via_dd(path):
    out = subprocess.run(["dd", f"if={path}", "bs=65536"], capture_output=True)
    return out.stdout


targets = []
for root in ("kb/l7", "kb/versions"):
    for dp, _d, fns in os.walk(root):
        for fn in sorted(fns):
            if fn.endswith(".md"):
                targets.append(os.path.join(dp, fn))
recs = {}
for rp in ("kb/l7/runs/20260923-1500.json",):
    if os.path.exists(rp):
        for a in json.load(open(rp, encoding="utf-8")).get("artifacts", []):
            recs[a["path"]] = a["sha256"]

sizes = env_node_size(targets)
enveloped = [p for p, s in zip(targets, sizes) if s != os.path.getsize(p)]
print(f"[扫描] kb/l7 + kb/versions 下 .md 共 {len(targets)} 个；信封态 {len(enveloped)} 个")

payload, rows = [], []
for p in enveloped:
    logical = open(p, encoding="utf-8").read()
    lb = logical.encode("utf-8")
    old = raw_via_dd(p)
    dst = os.path.join(ARCH, p)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as fh:
        fh.write(old)
    payload.append({"rel": os.path.relpath(p, WS), "text": logical, "logical_sha256": sha(lb),
                    "logical_bytes": len(lb), "physical_bytes": os.path.getsize(p)})
    rows.append({"path": p, "recorded_sha256": recs.get(p), "logical_sha256_before": sha(lb),
                 "logical_bytes": len(lb), "envelope_bytes": sizes[targets.index(p)],
                 "archived_raw": os.path.relpath(dst, WS), "archived_raw_bytes": len(old)})
print(f"[归档] 旧物理字节 {sum(r['archived_raw_bytes'] for r in rows)} 字节 → {os.path.relpath(ARCH, WS)}")
print(f"[留痕] 其中在 l7/runs 里有哈希记录的：{sum(1 for r in rows if r['recorded_sha256'])} 个，"
      f"与当前逻辑内容一致：{sum(1 for r in rows if r['recorded_sha256'] == r['logical_sha256_before'])} 个")

os.makedirs(os.path.dirname(PAYLOAD), exist_ok=True)
json.dump({"run_id": RUN, "kb_root": WS, "files": payload}, open(PAYLOAD, "w", encoding="utf-8"), ensure_ascii=False)
print(f"[载荷] {os.path.relpath(PAYLOAD, WS)}（{os.path.getsize(PAYLOAD)} 字节，{len(payload)} 条）")

env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
rep = subprocess.run([DSH, os.path.join(L8, "repack_write.mjs"), "--payload", PAYLOAD, "--root", WS,
                      "--out", os.path.join(L8, f"docs_write_report_{RUN}.json")],
                     capture_output=True, text=True, env=env)
print("[写入] " + (rep.stdout.strip().splitlines()[-1] if rep.stdout.strip() else rep.stderr[-200:]))
if rep.returncode != 0:
    print("[写入] 失败：", rep.stdout[-400:], rep.stderr[-400:]); sys.exit(2)

sizes2 = env_node_size([r["path"] for r in rows])
bad_size = [r["path"] for r, s in zip(rows, sizes2) if s != os.path.getsize(r["path"])]
bad_sha, rec_ok = [], 0
for r in rows:
    after = sha(open(r["path"], "rb").read())
    if after != r["logical_sha256_before"]:
        bad_sha.append(r["path"])
    r["logical_sha256_after"] = after
    r["envelope_after"] = next(s for p, s in zip([x["path"] for x in rows], sizes2) if p == r["path"]) != os.path.getsize(r["path"])
    if r["recorded_sha256"]:
        r["recorded_still_matches"] = r["recorded_sha256"] == after
        rec_ok += 1 if r["recorded_still_matches"] else 0
report = {"run_id": RUN, "scanned": len(targets), "repaired": len(rows),
          "still_enveloped_after": bad_size, "content_changed": bad_sha,
          "recorded_hash_checked": sum(1 for r in rows if r["recorded_sha256"]),
          "recorded_hash_still_matching": rec_ok,
          "archived_raw_bytes": sum(r["archived_raw_bytes"] for r in rows),
          "files": rows,
          "verdict": "PASS" if not bad_size and not bad_sha else "FAIL"}
out = os.path.join(L8, f"docs_repair_{RUN}.json")
json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[对账] 仍是信封 {len(bad_size)} 个 | 内容变了 {len(bad_sha)} 个 | "
      f"留痕哈希仍相等 {rec_ok}/{report['recorded_hash_checked']} → {report['verdict']}")
print(f"[产物] {os.path.relpath(out, WS)}")
sys.exit(0 if report["verdict"] == "PASS" else 1)
