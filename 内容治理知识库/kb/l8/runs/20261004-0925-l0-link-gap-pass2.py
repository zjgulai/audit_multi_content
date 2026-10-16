#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二遍：把「链接没登记」判准 —— 用 host+path 规范化 + 对象 token 注册表双判据。

判据（与 kb-l0-feishu §阶段8 / coverage-matrix ⑨⑩⑪ 对齐）：
  1) url 台账命中：manifest 里 `url:<...>` 行，按 host+path（去 scheme/www/query/尾斜杠）比；
  2) 对象注册表命中：按 URL 路径类型取 token，与 manifest 里
     base: / bitable:<base>:table:<tbl> / wiki: / slides: / sheets: / docx: / file: 的 token 比。
命中任一 ⇒ 不算缺口。两者都不命中 ⇒ 真缺口（待复核）。
"""
import json, os, re, sys, glob, collections

RUN = sys.argv[1]
KB = "kb"
SNAP = f"{KB}/l8/_stage/feishu-align/{RUN}"
URL_RE = re.compile(r"https?://[^\s\)\(\[\]\{\}\"'，。；、）】》]+")
FEISHU = re.compile(r"^https?://[^/]*feishu\.(cn|com)", re.I)

rows = [json.loads(l) for l in open(f"{KB}/l0/manifest.jsonl", encoding="utf-8") if l.strip()]
base_tokens, table_tokens, wiki_tokens, misc_tokens = set(), set(), set(), set()
url_ledger_hp = {}
url_raw = set()
for r in rows:
    rk = r.get("resource_key") or ""
    if rk.startswith("base:"):
        base_tokens.add(rk[5:])
    elif rk.startswith("bitable:"):
        m = re.match(r"bitable:([^:]+):table:(.+)$", rk)
        if m:
            base_tokens.add(m.group(1)); table_tokens.add(m.group(2))
    elif rk.startswith("wiki:"):
        wiki_tokens.add(rk[5:].split("/")[0])
    elif rk.startswith(("slides:", "sheets:", "docx:", "file:")):
        misc_tokens.add(rk.split(":", 1)[1].split("/")[0])
    elif rk.startswith("url:"):
        url_raw.add(rk[4:])

def hp(u):
    m = re.match(r"https?://([^/]+)(/.*)?$", u)
    if not m:
        return None
    host = m.group(1).replace("www.", "").lower()
    path = (m.group(2) or "")
    path = re.sub(r"\?.*$", "", path).rstrip("/").lower()
    return (host, path)

def path_kind(tok):
    for pref, name in (("/wiki/", "wiki"), ("/docx/", "docx"), ("/docs/", "docx"),
                       ("/sheets/", "sheets"), ("/slides/", "slides"),
                       ("/base/", "base"), ("/file/", "file")):
        if pref in tok:
            return name
    return "unknown"

for u in url_raw:
    kk = hp(u)
    if kk:
        url_ledger_hp.setdefault(kk, set()).add(u)

_seen = set()
buckets = collections.defaultdict(list)
for p in sorted(glob.glob(f"{SNAP}/*.ndjson")):
    tid = os.path.basename(p)[:-7]
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        rid = d.get("record_id")
        def scan(v, field):
            if isinstance(v, str):
                for m in URL_RE.findall(v):
                    u = m.rstrip(".,);]")
                    k = hp(u)
                    want = (FEISHU.match(u) is not None)
                    hit_url = k in url_ledger_hp
                    kind, tok = None, None
                    mm = re.search(r"/(wiki|docx|docs|sheets|slides|base|file)/([A-Za-z0-9]+)", u)
                    if mm:
                        kind, tok = mm.group(1), mm.group(2)
                        if kind == "docs":
                            kind = "docx"
                        # /base/<token> 的下一段可能是 table=
                        if kind == "base":
                            tm = re.search(r"[?&]table=([A-Za-z0-9]+)", u)
                            hit_obj = (tok in base_tokens) or (tm and tm.group(1) in table_tokens)
                        else:
                            reg = {"wiki": wiki_tokens, "docx": misc_tokens, "sheets": misc_tokens,
                                   "slides": misc_tokens, "file": misc_tokens}[kind]
                            hit_obj = tok in reg
                    else:
                        hit_obj = False
                    if not hit_url and not hit_obj:
                        seen_key = (tid, field, want, u)
                        if seen_key in _seen:
                            return
                        _seen.add(seen_key)
                        buckets[(tid, field, want)].append({
                            "url": u, "record_id": rid, "kind": kind, "token": tok,
                            "host_path": k, "feishu": want,
                            "tok_len_ok": bool(tok and len(tok) >= 20),
                        })
            elif isinstance(v, dict):
                for kk, vv in v.items():
                    scan(vv, f"{field}.{kk}")
            elif isinstance(v, list):
                for vv in v:
                    scan(vv, field)
        for k, v in d.items():
            if k != "record_id":
                scan(v, k)

out = {}
for (tid, field, is_feishu), items in sorted(buckets.items()):
    label = f"{tid}|{field}|{'feishu' if is_feishu else 'external'}"
    out[label] = items

print(json.dumps({
    "run": RUN,
    "registry": {"base": len(base_tokens), "table": len(table_tokens), "wiki": len(wiki_tokens),
                 "misc": len(misc_tokens), "url_hostpath": len(url_ledger_hp)},
    "unregistered_groups": {k: len(v) for k, v in out.items()},
    "unregistered_total": sum(len(v) for v in out.values()),
}, ensure_ascii=False, indent=1))
with open(f"/tmp/{RUN}-link-gap-pass2.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("detail ->", f"/tmp/{RUN}-link-gap-pass2.json")
