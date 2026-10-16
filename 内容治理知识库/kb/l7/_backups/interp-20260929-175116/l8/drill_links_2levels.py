#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则②：材料链接**下钻两层**读取 —— 产物落 L1，不动 L0。

用户 2026-09-29 口径：
  ① L0 只跟飞书侧对齐；优化 L1–L7 时**不得动 L0** → 所以下钻产物写 `kb/l1/sources/`，
     不写既有的 `kb/l0/snapshots/`、也不追加 `kb/l0/links/graph.jsonl`（那两处属 L0 口径）。
  ② 链接要下钻两层：level 1 = 记录里的「材料链接」；level 2 = level-1 正文里出现的链接。

读法（与既有 L1 的 feishu_ops 一致）：
  · wiki:<node_token>   → `lark-cli wiki +node-get` 取 obj_token → 再按类型读
  · docx:<token>        → `lark-cli docs +fetch`
  · sheets:<token>      → `lark-cli sheets +meta` + `+read`（读首个工作表）
  · base/share 链接     → `HTTP GET`（curl）
  · 其他 URL            → `HTTP GET`（curl）
身份：应用身份（--as bot --profile dsh-kb），只读。

用法：python3 kb/l8/drill_links_2levels.py <run_id>
产物：kb/l1/sources/<run>.md（每份 level-1/2 正文快照）
      kb/l1/sources/<run>.jsonl（边表：record → level1 → level2，含 sha256/字节/host）
      kb/l1/sources/<run>.report.json（统计）
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.chdir(WS)
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
OUT = "kb/l1/sources"
os.makedirs(OUT, exist_ok=True)
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
sha = lambda b: hashlib.sha256(b).hexdigest()
URL_RE = re.compile(r"https?://[^\s)\]\"'<>）】，。；]+")
edges, stats = [], {"level1_ok": 0, "level1_fail": 0, "level2_ok": 0, "level2_fail": 0, "records": 0}


def cli(*args):
    p = subprocess.run([LARK, *args, "--as", "bot", "--profile", "dsh-kb"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    return p.returncode, p.stdout + p.stderr


def curl(url):
    p = subprocess.run(["curl", "-sL", "--max-time", "25", "-A", "Mozilla/5.0", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    return p.returncode, p.stdout


def link_kind(url):
    m = re.search(r"/(wiki|docx|docs|sheets|base|file|drive)/([A-Za-z0-9]+)", url)
    if m:
        return m.group(1), m.group(2)
    if "feishu.cn" in url or "larksuite" in url:
        return "feishu-other", ""
    return "web", ""


def fetch(url):
    """读一份链接 → (kind, title, text, token)。全部只读。"""
    kind, token = link_kind(url)
    if kind == "wiki":
        rc, out = cli("wiki", "+node-get", "--node-token", token)   # 修正：--token 已废弃
        obj = ""
        try:
            d = json.loads(out[out.index("{"):])
            obj = (d.get("data") or {}).get("node", {}).get("obj_token") or ""
            otype = (d.get("data") or {}).get("node", {}).get("obj_type") or ""
            title = (d.get("data") or {}).get("node", {}).get("title") or ""
        except Exception:
            otype, title = "", ""
        if obj and otype in ("docx", "doc"):
            rc2, out2 = cli("docs", "+fetch", "--token", obj)
            return "wiki→docx", title, out2, obj
        if obj:
            return f"wiki→{otype or '?'}", title, out, obj
        return "wiki", title, out, token
    if kind in ("docx", "docs"):
        rc, out = cli("docs", "+fetch", "--token", token)
        return "docx", "", out, token
    if kind == "sheets":
        # 修正：lark-cli sheets 没有 +meta；--token 已废弃 → 用 --spreadsheet-token / --node-token
        rc, meta = cli("sheets", "+workbook-meta", "--spreadsheet-token", token)
        rc2, body = cli("sheets", "+read", "--spreadsheet-token", token, "--range", "A1:Z200")
        return "sheets", "", meta + "\n" + body, token
    rc, out = curl(url)
    return kind, "", out, token


def save(tag, url, kind, title, text):
    b = text.encode("utf-8")
    name = f"{RUN}__{tag}.md"
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(f"---\nsource_url: {url}\nkind: {kind}\ntitle: {title}\nfetched_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                 f"sha256: {sha(b)}\nbytes: {len(b)}\nrun: {RUN}\n---\n\n{text}\n")
    return os.path.relpath(p, WS), sha(b), len(b)


records = []
for p in sorted(__import__("glob").glob("kb/l0/records/材料收集/*.json")):
    d = json.load(open(p, encoding="utf-8"))
    val = ((d.get("fields") or {}).get("材料链接") or {}).get("value")
    if val:
        records.append((d["record_id"], val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)))
stats["records"] = len(records)
print(f"[下钻] 待处理记录 {len(records)} 条（材料收集）")

for rid, raw in records:
    m = URL_RE.search(raw)
    if not m:
        continue
    url1 = m.group(0)
    kind, title, text, token = fetch(url1)
    ok = len(text.strip()) > 0 and "error" not in text[:200].lower()
    stats["level1_ok" if ok else "level1_fail"] += 1
    f1, h1, b1 = save(f"L1-{rid}", url1, kind, title, text)
    edges.append({"run": RUN, "depth": 1, "from_id": f"record:{rid}", "from_kind": "feishu_bitable_record",
                  "label": "材料链接", "field_id": "fldr4c8nnT", "to_id": f"{kind}:{token or url1}",
                  "url": url1, "status": "ok" if ok else "fail", "sha256": h1, "bytes": b1,
                  "artifact": f1, "observed_at": RUN})
    # level 2：从 level-1 正文里再取链接（最多 5 条，去重、排除自身）
    seen, n2 = set(), 0
    for url2 in URL_RE.findall(text):
        if url2 == url1 or url2 in seen or n2 >= 5:
            continue
        seen.add(url2)
        k2, t2, txt2, tok2 = fetch(url2)
        ok2 = len(txt2.strip()) > 0 and "error" not in txt2[:200].lower()
        stats["level2_ok" if ok2 else "level2_fail"] += 1
        f2, h2, b2 = save(f"L2-{rid}-{n2+1}", url2, k2, t2, txt2)
        edges.append({"run": RUN, "depth": 2, "from_id": f"{kind}:{token or url1}", "from_kind": kind,
                      "label": "正文内链接", "field_id": None, "to_id": f"{k2}:{tok2 or url2}",
                      "url": url2, "status": "ok" if ok2 else "fail", "sha256": h2, "bytes": b2,
                      "artifact": f2, "observed_at": RUN})
        n2 += 1

with open(os.path.join(OUT, f"{RUN}.jsonl"), "w", encoding="utf-8") as fh:
    for e in edges:
        fh.write(json.dumps(e, ensure_ascii=False) + "\n")
rep = {"run": RUN, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "rule": "链接下钻两层（用户 2026-09-29 口径②）",
       "l0_untouched": True, "output_dir": OUT, "stats": stats, "edges": len(edges),
       "by_status": {s: sum(1 for e in edges if e["status"] == s) for s in ("ok", "fail")}}
json.dump(rep, open(os.path.join(OUT, f"{RUN}.report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[下钻] 完成：记录 {stats['records']} | level1 ok/fail {stats['level1_ok']}/{stats['level1_fail']} "
      f"| level2 ok/fail {stats['level2_ok']}/{stats['level2_fail']} | 边 {len(edges)}")
print(f"       产物 → {OUT}/{RUN}.jsonl 与 {OUT}/{RUN}.report.json（L0 未改动）")
