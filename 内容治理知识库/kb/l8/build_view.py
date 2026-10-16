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

## 2026-10-10 两处修复（原先本脚本会**破坏真源与基线**，同一类病）

① **生成器要显式传 `--payload-name workbench-mirror.json`**。原先没传 ⇒ 按默认名
   `manifest.json` 落进 staging ⇒ 安装时把 `<视图根>/_meta/manifest.json`
   （加载器 readManifest() 当**条目基线**读的那份，510 条 entries）**覆盖成镜像载荷**
   ⇒ 加载器读不到 entries 返回 null ⇒ 永远报 W035，且「条目被删掉」**永远发现不了**。
   生成器 `--payload-name` 的帮助原文就写着「生成 kb/view 时**必须改成别的名字**」。
② **不再 `shutil.rmtree(kb/view)`**，只清生成器**真正拥有**的东西 —— 各子库下的层目录
   （`L0-raw`/`L1-facts`/`L2-concepts`/`L3-graph`/`L4-contracts`）。其余一律保留：
   · `_meta/` 里一批**别的工具写的**文件（health / vocabulary / ranking / intake /
     boundaries / index-status / entry-schema / ledger / query-log …）；
   · `<子库>/tests/` 里**人工维护的黄金问题集**（`golden-questions-*.md`）——
     `kb_check` 的「覆盖率 / 幻觉率」两维就靠它。
   原先一删就没 ⇒ `projection_reconcile.py` exit 2「缺 view/_meta/workbench-mirror.json」，
   **闸门无法判定**；且 `kb_check` 的结构完整率 true→false、覆盖率与幻觉率双双变
   「无数据」（2026-10-10 实测两轮都踩到）。
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


#: 生成器**拥有**的层目录（tier dirs）—— 只有它们会被清掉与重装；
#: 其余（`_meta/`、`<子库>/tests/`）是别人维护的，见下方步骤 3 与文末修复说明。
TIER_DIRS = {"L0-raw", "L1-facts", "L2-concepts", "L3-graph", "L4-contracts"}


# 1) 生成到 staging ────────────────────────────────────────────
if os.path.exists(STG):
    shutil.rmtree(STG)
gen = subprocess.run([sys.executable, GEN, "--out", STG,
                      "--payload-name", "workbench-mirror.json"],
                     capture_output=True, text=True)
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
# ★ 2026-10-10 修复②：**不再整个删掉视图**。
#   原先这里是 `shutil.rmtree(OUT)`，会把 `_meta/` 一起删；而 `_meta/` 里有一批文件
#   **不是本脚本产的**（health.yaml / vocabulary.yaml / ranking.yaml / intake.yaml /
#   boundaries.yaml / evidence-groups.yaml / index-status.yaml / entry-schema.md /
#   ledger.ndjson / query-log.ndjson / workbench-mirror.json / derivation.json.bak-* …），
#   是别的工具后来写进去的。2026-10-10 实测后果：`_meta` 从 20 个掉到 7 个，
#   `kb/l8/projection_reconcile.py` 直接 exit 2「环境不完整，无法对账：缺
#   view/_meta/workbench-mirror.json」—— **闸门从此无法判定**（exit 2 绝不当作通过）。
#   现在只清生成器**自己拥有**的条目树（`<视图根>/*`，即非 `_meta` 部分）；
#   `_meta/` 原样保留，由 `repack_write.mjs` 逐文件覆盖它该管的那几个 —— 它**只写不删**。
os.makedirs(OUT, exist_ok=True)
# 生成器**拥有**的只有它自己产出的那些条目。判据 = **上一轮的镜像载荷**
# （`_meta/workbench-mirror.json` 的 `docs[].relPath`），它精确记着「上一轮派生出来的文件」：
#   · 在旧清单里、且**不在**本轮载荷里 ⇒ **过期的派生件**，删掉（不删 R3「id 集一一对应」会红）；
#   · **不在**旧清单里 ⇒ **别人放进来的**（人工 `kb_ingest` 的条目、人工维护的
#     `<子库>/tests/` 黄金问题集、`_meta/` 里别的工具写的文件）⇒ **一律保留**。
# ★ 2026-10-10 实测教训（同一类病，本脚本犯了三次）：
#   ① 原版 `shutil.rmtree(OUT)` ⇒ `_meta/` 20 个文件只剩 7 个、`projection_reconcile` exit 2；
#   ② 改成「清掉 tier 目录」⇒ 连**人工入库的条目**一起删（丢了 `ref-content-review-kb-plan-v2-5`，
#      `kb_check` 从「消失 0」变「消失 1」）；`<子库>/tests/` 的黄金问题集也没了 ⇒ 覆盖率/幻觉率变「无数据」。
_old_derived = set()
_mir = os.path.join(OUT, "_meta", "workbench-mirror.json")
if os.path.isfile(_mir):
    try:
        _old_derived = {d.get("relPath") for d in
                        (json.load(open(_mir, encoding="utf-8")).get("docs") or [])
                        if d.get("relPath")}
    except Exception:                                            # noqa: BLE001
        _old_derived = set()
_new_rels = {f["rel"] for f in files}
rep["stale_removed"] = sorted(r for r in _old_derived - _new_rels
                              if os.path.isfile(os.path.join(OUT, r)))
for _rel in rep["stale_removed"]:
    os.remove(os.path.join(OUT, _rel))
rep["preserved_foreign"] = sorted(
    rel for rel in (os.path.relpath(os.path.join(r, f), OUT)
                    for r, _d, fs in os.walk(OUT) for f in fs)
    if rel not in _new_rels and rel not in _old_derived)
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
# 计数口径（2026-10-10 修复②的配套）：`_meta/` 里那批**不是本脚本产的** md
# （如 `entry-schema.md`）现在会被**保留**，所以「装了几个条目」只数**条目树**
# （`_meta/` 之外）。否则保留件会被算成本次产物，裁决恒为 FAIL。
def entry_md(root):
    """「条目」= **层目录（tier dirs）下**的 md。
    `_meta/` 与 `<子库>/tests/` 都不是条目 —— 它们由别的工具 / 人维护、现在会被保留，
    算进来会让裁决恒为 FAIL（2026-10-10 实测：512≠511、513≠509 两轮）。"""
    out = []
    for p in md_list(root):
        parts = os.path.relpath(p, root).split(os.sep)
        if len(parts) >= 2 and parts[1] in TIER_DIRS:
            out.append(p)
    return out


out_md = md_list(OUT)
rep["installed_md"] = len(out_md)
rep["installed_entries_md"] = len(entry_md(OUT))
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
md_in_payload = len([f for f in files if f["rel"].endswith(".md")
                     and not f["rel"].startswith("_meta/")])
rep["expected_md"] = md_in_payload   # 本轮**该装**的条目 md 数（只算层目录）
# 判据改用**子集 + 精确期望**，不再用「总数等号」：
#   视图里允许有**不是生成器产的**条目 —— 人工 `kb_ingest` 的条目、`<子库>/tests/` 的
#   黄金问题集。用等号会让裁决恒为 FAIL（2026-10-10 实测 512≠511、513≠509 两轮）。
rep["missing_entries"] = [f["rel"] for f in files
                          if f["rel"].endswith(".md") and not f["rel"].startswith("_meta/")
                          and not os.path.isfile(os.path.join(OUT, f["rel"]))]
_foreign_entry_md = [r for r in rep["preserved_foreign"]
                     if r.endswith(".md") and len(r.split("/")) >= 2
                     and r.split("/")[0] != "_meta" and r.split("/")[1] in TIER_DIRS]
rep["foreign_entry_md"] = _foreign_entry_md
# `expected_entries` 只比**本轮载荷**的条目数：加载器 `entries` 数是「可加载的有效条目」，
# 外来条目（如人工入库那条 `kb_class: []`）**不计入**它 —— 实测：视图 510 个条目 md、
# 加载器仍报 509。所以这里与载荷对齐，外来条目另行记录（`foreign_entry_md`）备查。
rep["expected_entries"] = md_in_payload
rep["ok"] = (not rep["missing_entries"] and not rep["installed_enveloped"]
             and (rep["loader"].get("E001") or 0) == 0 and (rep["loader"].get("E046") or 0) == 0
             and rep["loader"].get("entries") == rep["expected_entries"])
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
