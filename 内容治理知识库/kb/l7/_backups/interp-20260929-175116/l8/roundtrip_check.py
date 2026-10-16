#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L8 · 六项回环验收（roundtrip）：装载位装好了没有。

判据（六项，全过才算「装好」）：
  1 文件数           —— 装载位条目数 == 载荷条目数（509），无缺件
  2 frontmatter 解析 —— 加载器 E001 == 0，且 509/509 切得出 frontmatter 与 id
  3 子库归属         —— `3_措辞表达库` 计到 509 条，未归库 0
  4 sha256 读回      —— 随机 10 个（固定种子）逐字节一致；**并且**全量 509 正文逐字比对
  5 检索可达         —— 3 个已知关键词各 ≥ 1 命中（经加载器 search()）
  6 体检             —— 健康分 ≥ 熔断线、三件套完整率 == 1.0（孤岛率如实记录）

第 4/5/6 项的读侧一律走**加载器本体**（`~/.dsh/plugins/dsh-kb/lib/kb.js`，
在 Electron 运行时里 import），不是走 python 的读通道 —— 因为要验收的正是
「加载器能不能读出来」这件事本身。

用法：python3 kb/l8/roundtrip_check.py [run_id]
输出：kb/l8/roundtrip_<run_id>.json（+ stdout 一张 12 行内的表）
"""
import json
import os
import re
import subprocess
import hashlib
import time
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))    # …/内容治理
WS = os.path.dirname(WS)                                            # kb/ 的父目录
# 库根与基准都可用环境变量覆盖：库根已改成「派生视图的明确位置」，
# 基准载荷应传「生成器刚产出的那份」（install 前的 staging 载荷），这样第 4 项验的是
# 「装进去的 == 生成器产出的」，而不是拿一份早已被外部替换的历史原文当基准。
KB = os.path.abspath(os.environ.get("L8_KB_ROOT", os.path.expanduser("~/.dsh/Momcozy知识库")))
L8 = os.path.join(WS, "kb", "l8")
PAYLOAD = os.path.abspath(os.environ.get("L8_BASELINE_PAYLOAD", os.path.join(L8, "repack_payload.json")))
PROBE = os.path.join(L8, "loader_probe.mjs")
DSH = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"
RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
KW = ["W-2.1", "乳腺组织", "合规替代"]
NOHIT = "量子纠缠配色调参"
FM = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$", re.M)
KB_CLASS_LINE = re.compile(r"^kb_class: \[措辞表达库\]\n", re.M)
sha = lambda b: hashlib.sha256(b).hexdigest()

payload = json.load(open(PAYLOAD, encoding="utf-8"))
entries = [f for f in payload["files"] if f["rel"].startswith("3_措辞表达库/")]
meta = [f for f in payload["files"] if f["rel"].startswith("_meta/")]

# ── 加载器侧探针（同一运行时 import 加载器本体）──────────────────
env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
p = subprocess.run([DSH, PROBE, KB, PAYLOAD, ",".join(KW + ["!" + NOHIT])],
                   capture_output=True, text=True, env=env, timeout=600)
if p.returncode != 0 or not p.stdout.strip().startswith("{"):
    print("探针失败：", p.returncode, p.stderr[-800:]); sys.exit(3)
probe = json.loads(p.stdout)

items = []

# ── 1 文件数 ───────────────────────────────────────────────────
on_disk = {}
for dirpath, _dirs, files in os.walk(KB):
    for fn in files:
        on_disk[os.path.relpath(os.path.join(dirpath, fn), KB)] = os.path.getsize(os.path.join(dirpath, fn))
disk_entries = [r for r in on_disk if r.startswith("3_措辞表达库/")]
missing = [f["rel"] for f in payload["files"] if f["rel"] not in on_disk]
extra = [r for r in on_disk if r not in {f["rel"] for f in payload["files"]}]
items.append({
    "n": 1, "name": "文件数",
    "expected_entries": len(entries), "disk_entries": len(disk_entries),
    "payload_files": len(payload["files"]), "missing": missing, "extra_not_in_payload": extra,
    "pass": len(disk_entries) == len(entries) and not missing,
})

# ── 2 frontmatter 解析（E001）────────────────────────────────────
e001 = probe.get("code_hist", {}).get("E001", 0)
items.append({
    "n": 2, "name": "frontmatter 解析成功数",
    "loader_E001": e001, "entries_fm_ok": probe.get("entries_fm_ok"),
    "entries_id_ok": probe.get("entries_id_ok"), "entries_total": probe.get("entries"),
    "pass": e001 == 0 and probe.get("entries_fm_ok") == len(entries) and probe.get("entries_id_ok") == len(entries),
})

# ── 3 子库归属 ─────────────────────────────────────────────────
cols = probe.get("collections") or []
c509 = next((c for c in cols if c["id"] == "3_措辞表达库"), None)
assigned = sum((c.get("count") or 0) for c in cols)
items.append({
    "n": 3, "name": "子库归属数",
    "collections": cols, "library": probe.get("library"),
    "assigned": assigned, "unassigned": (probe.get("entries") or 0) - assigned,
    "pass": bool(c509) and c509.get("count") == len(entries) and assigned == len(entries),
})

# ── 4 sha256 读回（随机 10 + 全量正文逐字）──────────────────────
body_mismatch, fm_mismatch, kb_class_ok, strip_fail = [], [], 0, []
for f in entries:
    live = os.path.join(KB, f["rel"])
    text = open(live, encoding="utf-8").read()
    m = FM.match(text)
    if not m:
        strip_fail.append(f["rel"]); continue
    if KB_CLASS_LINE.search(m.group(1)):
        kb_class_ok += 1
    # 两边都归一：基准可能是「生成器产出」（它自己也带 kb_class 行），也可能是
    # 本批早期的原始载荷（没有这一行）。归一到「无 kb_class 行」再比，才对两种基准都成立。
    live_body = m.group(2)
    want = FM.match(f["text"])
    if live_body != want.group(2):
        body_mismatch.append(f["rel"])
    live_fm = KB_CLASS_LINE.sub("", m.group(1), count=1)
    want_fm = KB_CLASS_LINE.sub("", want.group(1), count=1)
    if live_fm != want_fm:
        fm_mismatch.append(f["rel"])
items.append({
    "n": 4, "name": "sha256 读回一致（随机 10）+ 全量正文逐字",
    # 基准 = 本批写入时用的载荷（kb/l8/repack_payload.json，即迁出前原文），是**冻结**的。
    # 注意：若装载位在之后被别的生产者重新生成（本批实测发生过：2026-09-23 15:24:05），
    # 本项会自然失败 —— 那表示「基准内容已被外部替换」，不代表写入坏了。
    # 判断装载是否仍然健康，看第 2/3/5/6 项（frontmatter、归属、检索、体检）。
    "baseline": os.path.relpath(PAYLOAD, WS),
    "baseline_note": "冻结基准：本批写入时的载荷；被外部重新生成后会失配",
    "sample10": probe.get("sample10"), "sample10_all_match": probe.get("sample10_all_match"),
    "entries_verbatim_ok_loader": probe.get("entries_verbatim_ok"),
    "full_entries_checked": len(entries), "body_mismatch": body_mismatch,
    "frontmatter_mismatch_ignoring_kb_class": fm_mismatch, "kb_class_line_present": kb_class_ok,
    "unparsable": strip_fail,
    "pass": probe.get("sample10_all_match") is True
            and probe.get("entries_verbatim_ok") == len(entries)
            and not body_mismatch and not fm_mismatch and not strip_fail
            and kb_class_ok == len(entries),
})

# ── 5 检索可达（3 关键词 + 1 个零命中负例）──────────────────────
hits = [x for x in (probe.get("search") or []) if x["query"] in KW]
nohit = next((x for x in (probe.get("search") or []) if x["query"] == NOHIT), {})
items.append({
    "n": 5, "name": "关键词检索可达",
    "hits": hits, "all_hit": probe.get("search_all_hit"),
    "no_hit_negative": {"query": NOHIT, "matched": nohit.get("matched"), "expect": 0},
    "pass": probe.get("search_all_hit") is True and probe.get("search_negative_ok") is True
            and nohit.get("matched") == 0 and all(x["matched"] >= 1 for x in hits),
})

# ── 6 体检 ─────────────────────────────────────────────────────
h = probe.get("health") or {}
dims = h.get("dims") or {}
trip = dims.get("三件套完整率", {})
island = dims.get("孤岛率", {})
items.append({
    "n": 6, "name": "加载器体检",
    "health_score": h.get("score"), "floor": 60,
    "triplet": {"value": trip.get("value"), "threshold": trip.get("threshold"), "ok": trip.get("ok")},
    "island": {"value": island.get("value"), "threshold": island.get("threshold"), "ok": island.get("ok"),
               "note": "派生视图固有：条目之间不互相引用；装载修复前实测也是 1.00，与读写通道无关"},
    "other_dims": {k: v.get("value") for k, v in dims.items() if k not in ("三件套完整率", "孤岛率")},
    "pass": (h.get("score") or 0) >= 60 and trip.get("value") == 1.0,
})

all_pass = all(i["pass"] for i in items)
out = {
    "run_id": RUN, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "kb_root": KB, "loader": probe.get("loader"), "runtime": probe.get("runtime"),
    "items": items, "all_pass": all_pass,
    "loader_side_extra": {
        "errors_total": probe.get("errors_total"), "warnings_total": probe.get("warnings_total"),
        "code_hist": probe.get("code_hist"),
        "note": "上面这组码不属于六项判据：它们是 Z 修复前被 E001 整体掩盖的字段级问题，"
                "装载前一条都看不见（因为没有任何条目解析成功）。逐条影响见 runs/<run_id>.report.md 第八节。",
    },
}
dst = os.path.join(L8, f"roundtrip_{RUN}.json")
with open(dst, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)

print(f"roundtrip {RUN} · 装载位 {KB}")
for i in items:
    print(f"  {'PASS' if i['pass'] else 'FAIL'} {i['n']} {i['name']}")
print(f"  健康分 {h.get('score')} / 三件套 {trip.get('value')} / 孤岛率 {island.get('value')} / E001 {e001}")
print(f"  其它码：{json.dumps(probe.get('code_hist'), ensure_ascii=False)}")
print(f"  六项 {'全过' if all_pass else '未全过'} → {os.path.relpath(dst, WS)}")
sys.exit(0 if all_pass else 1)
