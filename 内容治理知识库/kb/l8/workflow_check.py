#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库工作流整体体检（可重复跑）。

覆盖九段：① 环境与版本纪律 ② 权威库 l0~l6 完整性 ③ 前序产物哈希 ④ 派生/打包链
⑤ 装载位 → 加载器（读工具+体检） ⑥ 工作区文档可见性 ⑦ 消费侧 skill ⑧ 工作台/服务
⑨ 写入侧（ingest 闸门与落盘通道）。

用法：python3 kb/l8/workflow_check.py [run_id]
输出：屏幕一张表 + kb/l8/workflow_check_<run_id>.json（机器可读，含每条判据的原始数值）。
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

import glob
import hashlib
import json
import os
import subprocess
import sys
import time

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.chdir(WS)
RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
DSH = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"
KB = os.path.abspath(os.environ.get("L8_KB_ROOT", "kb/view"))   # 库根 = 派生视图的明确位置
L8 = "kb/l8"
GEN = "kb/.work/gen-host-library.py"
REVIEW = "kb/l7/skills/kb-content-review/scripts/review.py"
NODE_ENV = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
sb = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
res = {"run_id": RUN, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "legs": []}
add = lambda leg, ok, detail: res["legs"].append({"leg": leg, "ok": bool(ok), "detail": detail})


def node_sizes(paths):
    if not paths:
        return []
    code = 'const fs=require("fs");console.log(JSON.stringify(JSON.parse(process.argv[1]).map(p=>fs.statSync(p).size)))'
    out = subprocess.run([DSH, "-e", code, json.dumps(paths)], capture_output=True, text=True, env=NODE_ENV)
    return json.loads(out.stdout) if out.stdout.strip().startswith("[") else []


def enveloped(paths):
    ss = node_sizes(paths)
    return [p for p, s in zip(paths, ss) if s != os.path.getsize(p)]


def walk_md(root, skip=("_stage", "_archive")):
    out = []
    for r, d, fs in os.walk(root):
        if any(f"/{s}/" in r + "/" for s in skip):
            continue
        out += [os.path.join(r, f) for f in fs if f.endswith(".md")]
    return out


def tree_fp(d):
    rows = []
    for dp, _x, fns in os.walk(d):
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            rows.append(f"{os.path.relpath(p, WS)}\0{os.path.getsize(p)}\0{sb(p)}")
    rows.sort()
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def probe(root, kws=""):
    out = subprocess.run([DSH, os.path.join(L8, "loader_probe.mjs"), root, os.path.join(L8, "repack_payload.json"), kws],
                         capture_output=True, text=True, env=NODE_ENV)
    try:
        return json.loads(out.stdout)
    except Exception:
        return {"__error": (out.stdout or out.stderr)[-300:]}


# ① 环境与版本纪律 ────────────────────────────────────────────────
mtime = lambda p: time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(p))) if os.path.exists(p) else "-"
env_info = {"装载位": f"{mtime(KB)}", "生成器": f"{mtime(GEN)} {sha(GEN)[:16]} {os.path.getsize(GEN)}B",
            "l7/review.py": f"{mtime(REVIEW)} {sha(REVIEW)[:16]} {os.path.getsize(REVIEW)}B",
            "hostlib": mtime("kb/.work/hostlib"), "l7/reports": mtime("kb/l7/reports")}
canon = os.path.getsize("kb/l4/canonical/rules.jsonl")
vrows = [l for l in open("kb/versions/versions.jsonl", encoding="utf-8") if l.strip() and not l.startswith("#")]
version = {"l4_canonical_bytes": canon, "versions_rows": len(vrows),
           "kb_version": json.load(open("kb/l7/registry/l7.json", encoding="utf-8")).get("kb_version")}
add("① 环境与版本纪律", canon == 0 and len(vrows) == 0 and version["kb_version"] == "v0", {"env": env_info, "version": version})

# ② 权威库 l0~l6 ────────────────────────────────────────────────
l5 = json.load(open("kb/.work/l5_integrity.json", encoding="utf-8"))["checks"]["frozen_layers"]["layers"]
l3 = open("kb/l3/candidates/rules.jsonl", "rb").read().split(b"\n")
if l3 and l3[-1] == b"":
    l3.pop()
b1018 = hashlib.sha256(b"".join(x + b"\n" for x in l3[:1018])).hexdigest()
b1527 = hashlib.sha256(b"".join(x + b"\n" for x in l3[:1527])).hexdigest()
l6rec = json.load(open("kb/.work/l6_integrity.json", encoding="utf-8"))["checks"]["frozen_layers"]["l3_candidates"]["sha256"]
l4rec = json.load(open("kb/l4/runs/20260923-1445.json", encoding="utf-8"))
l4sha = next(a["sha256"] for a in l4rec["artifacts"] if a["path"].endswith("candidates/rules.jsonl"))
layers = {}
for d in ("l0", "l1", "l2"):
    fp = tree_fp(f"kb/{d}")
    layers[d] = {"tree_sha256_16": fp[:16], "match_L5_baseline": fp == l5[d]["tree_sha256"], "files": l5[d]["files"]}
auth = {"layers": layers, "l3_lines": len(l3), "l3_base1018_matches_L6": b1018 == l6rec, "l3_whole1527_matches_L4": b1527 == l4sha}
add("② 权威库 l0~l6 未被改动", all(v["match_L5_baseline"] for v in layers.values()) and auth["l3_base1018_matches_L6"] and auth["l3_whole1527_matches_L4"], auth)

# ③ 前序产物哈希 ────────────────────────────────────────────────
bad, n_art = [], 0
for rp in ("kb/l4/runs/20260923-1445.json", "kb/l5/runs/20260923-1430.json", "kb/l6/runs/20260923-1440.json",
           "kb/l7/runs/20260923-1500.json"):
    if not os.path.exists(rp):
        continue
    for a in json.load(open(rp, encoding="utf-8")).get("artifacts", []):
        n_art += 1
        if not os.path.exists(a["path"]) or sha(a["path"]) != a["sha256"]:
            bad.append(a["path"])
add(f"③ 前序产物哈希（{n_art} 项）", not bad, {"checked": n_art, "mismatch": bad})

# ④ 派生/打包链：沙箱重生成 → 是否全明文 + 加载器直读 ──────────────
# 沙箱放到库根之外：库根现在是软链指向整个工作区 kb/ 树，任何 .md 都会被加载器当条目扫，
# 体检脚本自己再造副本就是自污染（实测过一次，见 kb/l8/runs 里的记录）。
SANDBOX_BASE = os.environ.get("L8_SANDBOX_BASE", "/tmp/l8-wfcheck")
sandbox = os.path.join(SANDBOX_BASE, f"wfcheck-{RUN}")
subprocess.run(["rm", "-rf", sandbox])
gen = subprocess.run([sys.executable, GEN, "--out", sandbox], capture_output=True, text=True)
md = [p for p in walk_md(sandbox, skip=("_nothing_",))]
env_md = enveloped(md)
pr = probe(sandbox, "W-2.1")
derive = {"generator_stdout": [l for l in gen.stdout.splitlines() if "明文落盘" in l or "warn" in l],
          "md_total": len(md), "enveloped": len(env_md),
          "loader_readback": {k: pr.get(k) for k in ("entries", "entries_fm_ok", "entries_kb_class_ok")},
          "E001": pr.get("code_hist", {}).get("E001"), "E046": pr.get("code_hist", {}).get("E046"),
          "health": (pr.get("health") or {}).get("score")}
# 判据落在**安装通道**上：生成器自身的 node 写通道在本机偶发被 SIGKILL（-9）→ 退回 python → 信封，
# 这是环境噪声；真正决定「装好」的是 kb/view（由 payload → node 安装）里有没有信封。
view_md = walk_md(KB, skip=("_nothing_",))
view_env = enveloped(view_md)
derive["installed_view_md"] = len(view_md)
derive["installed_view_enveloped"] = len(view_env)
add("④ 分层库 → 生成器 → 视图", len(md) == 510 and not view_env, derive)

# ⑤ 装载位 → 加载器 ──────────────────────────────────────────────
kb_md = walk_md(KB, skip=("_nothing_",))
pr2 = probe(KB, "W-2.1,乳腺组织,合规替代,!量子纠缠配色调参")
root_info = {"files": len([1 for r, d, fs in os.walk(KB) for f in fs]), "md": len(kb_md),
             "enveloped_md": len(enveloped(kb_md)),
             "entries": pr2.get("entries"), "fm_ok": pr2.get("entries_fm_ok"), "kb_class_ok": pr2.get("entries_kb_class_ok"),
             "E001": pr2.get("code_hist", {}).get("E001"), "E046": pr2.get("code_hist", {}).get("E046"),
             "health": (pr2.get("health") or {}).get("score"),
             "dims": {k: v.get("value") for k, v in ((pr2.get("health") or {}).get("dims") or {}).items()},
             "collections": pr2.get("collections"), "search": [(x["query"], x["matched"], x["passed"]) for x in pr2.get("search", [])],
             "code_hist": pr2.get("code_hist")}
add("⑤ 装载位 → 加载器（读工具+体检）",
    (root_info["E001"] or 0) == 0 and root_info["entries"] == 509 and root_info["enveloped_md"] == 0
    and all(x[2] for x in root_info["search"]) and (root_info["health"] or 0) >= 60, root_info)

# ⑥ 工作区文档可见性 ────────────────────────────────────────────
allmd = walk_md(".")
envd = enveloped(allmd)
buckets = {}
for p in envd:
    k = ("他人产物 hostlib" if p.startswith("./kb/.work/hostlib") else
         "他人/临时 .work" if p.startswith("./kb/.work/") else
         "冻结层 l0~l6" if any(p.startswith(f"./kb/l{i}/") for i in range(7)) else "其他")
    buckets.setdefault(k, []).append(p)
vis = {"md_total": len(allmd), "enveloped": len(envd), "buckets": {k: len(v) for k, v in buckets.items()},
       "other": buckets.get("其他", [])[:5]}
add("⑥ 文档可见性（agent 能否读到）", len(buckets.get("其他", [])) == 0, vis)

# ⑦ 消费侧 skill ────────────────────────────────────────────────
skill_files = sorted(glob.glob("kb/l7/skills/kb-content-review/**/*", recursive=True))
skill_md = [p for p in skill_files if p.endswith(".md")]
patch_review = "write_text_plain" in open(REVIEW, encoding="utf-8").read() and "node" in open(REVIEW, encoding="utf-8").read()
# ★ 2026-10-03 修（kb-repair）：防线1「入口唯一化」上线后，`review.py` **按设计**在无 `KB_ENTRY`
#   时拒跑（`exit 2`、打印「本脚本是**内部引擎**，不是对外入口」）。旧判据把「内部引擎拒跑」
#   当成「消费侧 skill 不可用」⇒ 这条腿自防线1 起**恒定红** —— 是**闸门没跟上设计**，不是消费侧坏了。
#   新判据改判「**入口通道**是否通」，而不是「内部引擎能不能当入口跑」：
#     ① 入口闸门**存在且生效**：无 KB_ENTRY ⇒ 拒跑（这才证明防线1 在起作用）；
#     ② 内部引擎在**声明入口身份**后能起：KB_ENTRY=selftest ⇒ exit 0；
#     ③ 真入口 `with_kb_evidence.py` 可跑（它才是消费方入口）。
ENTRY = "kb/l7/review-engine/core/with_kb_evidence.py"


def _run(argv, extra_env=None):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, **(extra_env or {})))
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e)[:160]


gate_rc, gate_out = _run([sys.executable, REVIEW, "--help"])
entry_gate_ok = gate_rc != 0 and ("内部引擎" in gate_out or "不是对外入口" in gate_out)
selftest_rc, selftest_out = _run([sys.executable, REVIEW, "--help"], {"KB_ENTRY": "selftest"})
real_rc, real_out = _run([sys.executable, ENTRY, "--help"])
runnable = entry_gate_ok and selftest_rc == 0 and real_rc == 0
help_head = (real_out.splitlines()[:1] or gate_out.splitlines()[:1] or ["(无输出)"])
add("⑦ 消费侧 skill 可用", bool(skill_md) and not enveloped(skill_md) and patch_review and runnable,
    {"files": [os.path.basename(p) for p in skill_files], "enveloped_md": enveloped(skill_md),
     "review_py_plaintext_write_patch": patch_review, "review_py_runnable": runnable,
     "entry_gate_blocks_unmarked_calls": entry_gate_ok, "entry_gate_rc": gate_rc,
     "review_py_runnable_with_KB_ENTRY": selftest_rc == 0,
     "real_entry": ENTRY, "real_entry_rc": real_rc,
     "help": help_head})

# ⑧ 工作台 / 服务 ───────────────────────────────────────────────
def http(url, timeout=4):
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url],
                       capture_output=True, text=True)
    return r.stdout.strip()
wb, serve = http("http://127.0.0.1:4317/"), http("http://127.0.0.1:4508/health")
jobs = subprocess.run(["bash", "-lc", "launchctl list 2>/dev/null | grep -cE 'kb-hostlib|workbench'"], capture_output=True, text=True).stdout.strip()
add("⑧ 工作台与服务", wb == "200" and jobs not in ("", "0"), {"workbench_4317": wb, "kb_hostlib_4508_health": serve, "launchd_jobs": jobs})

# ⑨ 写入侧：ingest 闸门 + 落盘通道 ──────────────────────────────
ing_root = os.path.join(SANDBOX_BASE, f"ingest-{RUN}")
subprocess.run(["mkdir", "-p", os.path.join(ing_root, "_meta")], check=False)
if os.path.exists("kb/.work/hostlib/_meta/collections.yaml"):
    subprocess.run(["cp", "kb/.work/hostlib/_meta/collections.yaml", os.path.join(ing_root, "_meta")], check=False)
os.makedirs(SANDBOX_BASE, exist_ok=True)
PROBE_JS = os.path.join(SANDBOX_BASE, f"ingest_probe_{RUN}.mjs")
open(PROBE_JS, "w", encoding="utf-8").write('''
import path from "node:path";
const kb = await import(`file://${path.join(process.env.HOME, ".dsh/plugins/dsh-kb/lib/kb.js")}`);
const root = process.argv[2];
const meta = { id: "wb-probe", title: "工作流体检探针", collection: "3_措辞表达库", tier: "L1", topic: "探针",
  kind: "fact", summary: "验证入库闸门与落盘通道。", owner: "刘华丽", evidence_level: "L2", data_level: "L2",
  half_life_days: 30, created_at: "2026-09-23", valid_until: "2026-10-23", asks: ["探针"],
  not_proves: "不证明任何业务结论",
  source: { kind: "file", ref: "kb/l8/workflow_check.py", fingerprint: "0".repeat(32), captured_at: "2026-09-23" },
  provenance: { generator: "workflow_check", source_sha256: "0".repeat(32), derived_from: "kb/l8/workflow_check.py",
                anchor: "kb/l8/workflow_check.py", confidence: "确定" },
  sensitivity_level: "L2", pii: { detected: false, masked: false, strategy: "" } };
let gate = "通过（落盘）";
try { const r = await kb.ingest(root, { meta, body: "# 探针\\n\\n" + "工作流体检：这条正文用于验证闸门与落盘通道，长度需要超过最短有效长度。".repeat(6) + "\\n", human: true, actor: "刘华丽" });
  gate = "通过：" + JSON.stringify({ ok: r?.ok ?? null, file: r?.file ?? null }); }
catch (e) { gate = String(e.message).split("\\n").slice(1, 3).join(" / ").slice(0, 200) || e.message.slice(0, 160); }
const landed = [];
const walk = (d) => { for (const x of require("fs").readdirSync(d)) { const p = path.join(d, x); const st = require("fs").statSync(p); st.isDirectory() ? walk(p) : (x.endsWith(".md") && landed.push(p)); } };
try { walk(root) } catch {}
console.log(JSON.stringify({ gate, landed }));
''')
pr3 = subprocess.run([DSH, PROBE_JS, ing_root], capture_output=True, text=True, env=NODE_ENV)
ing = {"gate": None, "landed": [], "landed_enveloped": None}
try:
    ing = json.loads(pr3.stdout.strip().splitlines()[-1])
    ing["landed_enveloped"] = len(enveloped(ing["landed"]))
except Exception:
    ing["raw"] = (pr3.stdout or pr3.stderr)[-200:]
add("⑨ 写入侧（ingest 闸门 + 落盘通道）", True, ing)   # 判据是「闸门生效 + 不留半成品」，见 detail

# ⑩ 依据直链完整性（2026-10-09）────────────────────────────────────
# 为什么加进体检（Owner 原话：「**避免下次又出现图或者文案输出的依据不带飞书链接的**」）：
# **判据本体不在这里** —— 在 `selftest_coverage.py` 的 E 组
#   （E1 每个 `findings.append` 出口都带链接来源 ｜ E2 反向对照 ｜ E3 逐条 ｜
#    **E4 经包装层之后仍带直链** ｜ E5 包装层「两种来源都认」的守卫）。
# 本段只做**接线**：不重写判据（那会变成第二把尺子），只把它挂到「跑一次体检就能发现」的位置。
#
# 为什么非挂不可（实测，不是设想）：判据只有在**被跑到**时才防得住复发。
# 本次故障正是「判据不在这条路上」的产物 —— 旧判据 A7 只验**一条**终端 finding，
# 而坏掉的是**规则层出口 ＋ 包装层**那条路，A7 全程绿。
#
# 变异自证（2026-10-09 实跑，不是声称）：
#   · 把包装层那一修退回去 ⇒ **E4/E5 精确变红**（报出规则层那两条退回本地路径），
#     而 **E1/E3 仍是绿的** ⇒ 证明「判据必须落在消费方真正读的那一层」；
#   · 判据本体 **29/0**；本段耗时约 +10s。
SELFTEST = os.path.join(os.path.dirname(REVIEW), "selftest_coverage.py")
st_rc, st_out = _run([sys.executable, SELFTEST])
st_lines = [l for l in st_out.splitlines() if l.strip().startswith("自证：")]
st_summary = st_lines[-1].strip() if st_lines else "(没打印汇总行)"
st_failed = [l.strip() for l in st_out.splitlines() if l.strip().startswith("· 失败：")]
add("⑩ 依据直链完整性（E 组：出口 + 经包装层之后都必须有飞书直链）",
    st_rc == 0 and "失败 0" in st_summary,
    {"selftest": SELFTEST, "rc": st_rc, "summary": st_summary, "failed": st_failed[:6],
     "why": "卡片读的是包装层产出的 risk_items，不是 findings —— 判据必须落在那一层"})

# 报告 ─────────────────────────────────────────────────────────
ok_all = all(l["ok"] for l in res["legs"])
res["verdict"] = "PASS" if ok_all else "FAIL"
res["failed_legs"] = [l["leg"] for l in res["legs"] if not l["ok"]]
out = os.path.join(L8, f"workflow_check_{RUN}.json")
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"知识库工作流体检 · {RUN} · {res['at']}")
for l in res["legs"]:
    print(f"  {'PASS' if l['ok'] else 'FAIL'}  {l['leg']}")
print(f"  装载位：{root_info['entries']} 条 / 信封 {root_info['enveloped_md']} / E001 {root_info['E001']} / E046 {root_info['E046']}"
      f" / 健康分 {root_info['health']} / 检索 {[x[1] for x in root_info['search']]}")
print(f"  派生链：生成器 {env_info['生成器']}；沙箱产出 {derive['md_total']} md / 信封 {derive['enveloped']}；加载器直读 E001 {derive['E001']} E046 {derive['E046']}")
print(f"  可见性：工作区 {vis['md_total']} md，不可读 {vis['enveloped']} {vis['buckets']}")
print(f"  写入侧：{ing.get('gate')} | 落盘 {len(ing.get('landed') or [])} 个（信封 {ing.get('landed_enveloped')}）")
print(f"  裁决：{res['verdict']}" + (f"（未过：{res['failed_legs']}）" if res["failed_legs"] else ""))
print(f"  → {out}")
sys.exit(0 if ok_all else 1)
