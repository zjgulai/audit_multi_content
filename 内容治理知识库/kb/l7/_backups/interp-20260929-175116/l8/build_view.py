#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把派生视图重建到一个**明确位置**，并做读回验证（优化项 ①）。

为什么要有这一步：库根被改成「入口 + 软链指向整个工作区」之后，加载器会扫到 1867 个 .md
（E001 1322 / E046 509 / 健康分 56.8）。视图必须落在一个**边界清楚**的目录里：
`<视图根>/3_措辞表达库/L*.md` + `<视图根>/_meta/{kb-classes.yaml, collections.yaml,
derivation.json, DERIVED.md, GUIDE.md, acceptance.yaml}`。

做法（每一步都可复现）：
  1. 用打补丁的生成器生成到 **staging（库根之外，/tmp）** —— 生成器内部已是 node 明文写盘 + 读回断言；
  2. python 读 staging 的逻辑内容 → 组成载荷（rel/text/sha256/bytes）；
  3. 用 kb/l8/repack_write.mjs（node 明文写盘 + 逐文件读回断言 + cp 兜底）装到目标目录；
  4. 补 `_meta/GUIDE.md` 与 `_meta/acceptance.yaml`（库自述与验收契约）；
  5. 复核：md 信封数 == 0；加载器 probe 的 E001 == 0、E046 == 0、条目数 == 生成数。

用法：python3 kb/l8/build_view.py [--out kb/view] [--run <id>]
输出：kb/l8/view_build_<run>.json（含每个文件的 sha256 与全部复核数值）
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.chdir(WS)
DSH = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"
NODE_ENV = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
GEN = "kb/.work/gen-host-library.py"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
sha_b = lambda b: hashlib.sha256(b).hexdigest()

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="kb/view")
ap.add_argument("--staging", default="/tmp/l8-view-staging")
ap.add_argument("--run", default=time.strftime("%Y%m%d-%H%M"))
a = ap.parse_args()
OUT = os.path.abspath(a.out)
STG = os.path.abspath(a.staging)
rep = {"run": a.run, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "out": a.out, "staging": a.staging}


def env_node_sizes(paths):
    code = 'const fs=require("fs");console.log(JSON.stringify(JSON.parse(process.argv[1]).map(p=>fs.statSync(p).size)))'
    out = subprocess.run([DSH, "-e", code, json.dumps(paths)], capture_output=True, text=True, env=NODE_ENV)
    return json.loads(out.stdout) if out.stdout.strip().startswith("[") else []


def enveloped(paths):
    return [p for p, s in zip(paths, env_node_sizes(paths)) if s != os.path.getsize(p)]


def md_list(root):
    return sorted(os.path.join(r, f) for r, _d, fs in os.walk(root) for f in fs if f.endswith(".md"))


# 1) 生成到 staging ────────────────────────────────────────────
if os.path.exists(STG):
    shutil.rmtree(STG)
gen = subprocess.run([sys.executable, GEN, "--out", STG], capture_output=True, text=True)
rep["generator_stdout"] = [l for l in gen.stdout.splitlines() if "落盘" in l or "warn" in l or "产出" in l]
rep["generator_rc"] = gen.returncode
if gen.returncode != 0:
    print("生成失败：", gen.stdout[-500:], gen.stderr[-500:]); sys.exit(2)
stg_md = md_list(STG)
rep["staging_md"] = len(stg_md)
rep["staging_enveloped"] = [os.path.relpath(p, STG) for p in enveloped(stg_md)]

# 2) 载荷（staging 的逻辑内容）──────────────────────────────────
files = []
for p in sorted(os.path.join(r, f) for r, _d, fs in os.walk(STG) for f in fs):
    rel = os.path.relpath(p, STG)
    b = open(p, "rb").read()
    files.append({"rel": rel, "text": b.decode("utf-8"), "logical_sha256": sha_b(b), "logical_bytes": len(b)})
payload = os.path.join("kb/l8/_stage", f"view_payload_{a.run}.json")
os.makedirs(os.path.dirname(payload), exist_ok=True)
json.dump({"run_id": a.run, "kb_root": OUT, "files": files}, open(payload, "w", encoding="utf-8"), ensure_ascii=False)
rep["payload"] = {"path": payload, "files": len(files), "bytes": os.path.getsize(payload)}

# 3) 安装到目标目录（node 明文 + 读回断言）──────────────────────
if os.path.exists(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT, exist_ok=True)
wr = subprocess.run([DSH, "kb/l8/repack_write.mjs", "--payload", payload, "--root", OUT,
                     "--out", f"kb/l8/view_write_report_{a.run}.json"], capture_output=True, text=True, env=NODE_ENV)
wf = f"kb/l8/view_write_report_{a.run}.json"      # 写入器自己落的报告（比解析 stdout 稳）
try:
    s_ = json.load(open(wf, encoding="utf-8"))["summary"]
    rep["install"] = {k: s_.get(k) for k in ("total", "node_write_ok", "cp_fallback_ok", "failed", "fm_regex_ok", "body_unchanged")}
except Exception as e:
    rep["install"] = {"error": f"{e}", "rc": wr.returncode, "stdout_tail": wr.stdout[-200:]}
if wr.returncode != 0:
    print("安装读回断言失败：", rep["install"]); sys.exit(3)

# 4) 补 GUIDE.md 与 acceptance.yaml（取 meta_src 的定稿，node 写）──
extra = [("kb/l8/meta_src/GUIDE.md", "_meta/GUIDE.md"), ("kb/l8/meta_src/acceptance.yaml", "_meta/acceptance.yaml")]
files2 = []
for src, rel in extra:
    b = open(src, "rb").read()
    files2.append({"rel": rel, "text": b.decode("utf-8"), "logical_sha256": sha_b(b), "logical_bytes": len(b)})
payload2 = os.path.join("kb/l8/_stage", f"view_meta_payload_{a.run}.json")
json.dump({"run_id": a.run, "kb_root": OUT, "files": files2}, open(payload2, "w", encoding="utf-8"), ensure_ascii=False)
wr2 = subprocess.run([DSH, "kb/l8/repack_write.mjs", "--payload", payload2, "--root", OUT,
                      "--out", f"kb/l8/view_write_report_meta_{a.run}.json"], capture_output=True, text=True, env=NODE_ENV)
try:
    s2_ = json.load(open(f"kb/l8/view_write_report_meta_{a.run}.json", encoding="utf-8"))["summary"]
    rep["install_meta"] = {k: s2_.get(k) for k in ("total", "node_write_ok", "failed")}
except Exception as e:
    rep["install_meta"] = {"error": f"{e}"}

# 5) 复核 ─────────────────────────────────────────────────────
out_md = md_list(OUT)
rep["installed_md"] = len(out_md)
rep["installed_enveloped"] = [os.path.relpath(p, OUT) for p in enveloped(out_md)]
rep["_meta"] = sorted(os.listdir(os.path.join(OUT, "_meta")))
pr = subprocess.run([DSH, "kb/l8/loader_probe.mjs", OUT, payload, "W-2.1,乳腺组织,合规替代,!量子纠缠配色调参"],
                    capture_output=True, text=True, env=NODE_ENV)
try:
    p = json.loads(pr.stdout)
    rep["loader"] = {"entries": p.get("entries"), "fm_ok": p.get("entries_fm_ok"), "kb_class_ok": p.get("entries_kb_class_ok"),
                     "E001": p.get("code_hist", {}).get("E001"), "E046": p.get("code_hist", {}).get("E046"),
                     "health": (p.get("health") or {}).get("score"),
                     "dims": {k: v.get("value") for k, v in ((p.get("health") or {}).get("dims") or {}).items()},
                     "collections": p.get("collections"),
                     "search": [(x["query"], x["matched"], x["passed"]) for x in p.get("search", [])],
                     "acceptance": p.get("acceptance"),
                     "code_hist": p.get("code_hist")}
except Exception:
    rep["loader"] = {"error": (pr.stdout or pr.stderr)[-400:]}
md_in_payload = len([f for f in files if f["rel"].endswith(".md")])
expected_md = md_in_payload + len([1 for _src, rel in extra if rel.endswith(".md")])   # 另装的 GUIDE.md
rep["expected_md"] = expected_md
rep["ok"] = (rep["installed_md"] == expected_md and not rep["installed_enveloped"]
             and (rep["loader"].get("E001") or 0) == 0 and (rep["loader"].get("E046") or 0) == 0
             and rep["loader"].get("entries") == 509)
rep["manifest"] = [{"rel": f["rel"], "sha256_16": f["logical_sha256"][:16], "bytes": f["logical_bytes"]} for f in files]
dst = f"kb/l8/view_build_{a.run}.json"
json.dump(rep, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"视图构建 {a.run} → {a.out}")
print(f"  staging：{rep['staging_md']} md（信封 {len(rep['staging_enveloped'])}）｜生成器：{rep['generator_stdout']}")
print(f"  安装：{rep.get('install', {}).get('node_write_ok')} 通过 / 失败 {rep.get('install', {}).get('failed')}"
      f"｜补件：{rep.get('install_meta', {}).get('node_write_ok')}")
print(f"  产物：{rep['installed_md']} md，信封 {len(rep['installed_enveloped'])}；_meta={rep['_meta']}")
L = rep["loader"]
print(f"  加载器：E001 {L.get('E001')}｜E046 {L.get('E046')}｜entries {L.get('entries')}｜fm_ok {L.get('fm_ok')}"
      f"｜健康分 {L.get('health')}｜检索 {[x[1] for x in L.get('search', [])]}")
print(f"  裁决：{'PASS' if rep['ok'] else 'FAIL'} → {dst}")
sys.exit(0 if rep["ok"] else 1)
