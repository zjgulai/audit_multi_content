#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三遍（决定性）：把飞书域链接逐条判到「在 L0 / 不在 L0」。

判据链（命中任一即视为在册，且记录命中了哪一环）：
  a) url 台账里有同 host+path 的 `url:` 行；
  b) URL 路径里的 token 直接命中对象注册表（base / table / wiki / docx / sheets / slides / file）；
  c) wiki 节点经 `lark-cli wiki +node-get` 解析出 obj_token 后命中注册表（**这一步不做就会全是假缺口**）。
三条都不命中 ⇒ 真缺口。
"""
import json, os, re, sys, glob, subprocess, collections

RUN = sys.argv[1]
KB = "kb"
SNAP = f"{KB}/l8/_stage/feishu-align/{RUN}"
CACHE = f"/tmp/{RUN}-node-resolve.json"
URL_RE = re.compile(r"https?://[^\s\)\(\[\]\{\}\"'，。；、）】》]+")
FEISHU = re.compile(r"^https?://[^/]*feishu\.(cn|com)", re.I)

rows = [json.loads(l) for l in open(f"{KB}/l0/manifest.jsonl", encoding="utf-8") if l.strip()]
base_t, table_t, wiki_t, misc_t = set(), set(), set(), set()
url_raw = set()
for r in rows:
    rk = r.get("resource_key") or ""
    if rk.startswith("base:"):
        base_t.add(rk[5:])
    elif rk.startswith("bitable:"):
        m = re.match(r"bitable:([^:]+):table:(.+)$", rk)
        if m:
            base_t.add(m.group(1)); table_t.add(m.group(2))
    elif rk.startswith(("wiki:", "slides:", "sheets:", "docx:", "file:")):
        wiki_t.add(rk.split(":", 1)[1].split("/")[0])
    elif rk.startswith("url:"):
        url_raw.add(rk[4:])


def hp(u):
    m = re.match(r"https?://([^/]+)(/.*)?$", u)
    if not m:
        return None
    return (m.group(1).replace("www.", "").lower(),
            re.sub(r"\?.*$", "", m.group(2) or "").rstrip("/").lower())


url_hp = {hp(u) for u in url_raw if hp(u)}

# 收集快照里的飞书域链接及其出处
feishu_urls = {}
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
                    if FEISHU.match(u):
                        feishu_urls.setdefault(u, set()).add(f"{tid}|{field}|{rid}")
            elif isinstance(v, dict):
                for k, vv in v.items():
                    scan(vv, f"{field}.{k}")
            elif isinstance(v, list):
                for vv in v:
                    scan(vv, field)
        for k, v in d.items():
            if k != "record_id":
                scan(v, k)

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
env = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))

verdicts = []
for u, ctxs in sorted(feishu_urls.items()):
    m = re.search(r"/(wiki|docx|docs|sheets|slides|base|file)/([A-Za-z0-9]+)", u)
    kind = tok = None
    if m:
        kind, tok = m.group(1), m.group(2)
    via = []
    if hp(u) in url_hp:
        via.append("url台账(host+path)")
    if kind == "base":
        tm = re.search(r"[?&]table=([A-Za-z0-9]+)", u)
        if tok in base_t:
            via.append("base注册表")
        if tm and tm.group(1) in table_t:
            via.append("table注册表")
    elif tok and tok in wiki_t:
        via.append(f"{kind}注册表")
    obj = None
    if not via and kind == "wiki":
        if tok not in cache:
            try:
                cp = subprocess.run([LARK, "wiki", "+node-get", "--node-token", tok, "--as", "bot",
                                     "--profile", "dsh-kb", "--json"],
                                    capture_output=True, text=True, timeout=60, env=env)
                raw = cp.stdout.strip() or cp.stderr.strip()
                dd = json.loads(raw)
                node = (dd.get("data") or {})   # 实测：node 字段直接摊在 data 下，没有 data.node
                cache[tok] = {"ok": dd.get("ok", True) and not dd.get("error"),
                              "obj_token": node.get("obj_token"), "obj_type": node.get("obj_type"),
                              "title": node.get("title"),
                              "error": (dd.get("error") or {}).get("code")}
            except Exception as e:
                cache[tok] = {"ok": False, "error": f"cli:{e}"}
        c = cache[tok]
        obj = c.get("obj_token")
        if c.get("ok") and obj:
            if obj in wiki_t:
                via.append("wiki→obj_token注册表")
    verdicts.append({
        "url": u, "kind": kind, "node_token": tok, "obj_token": obj,
        "in_l0_via": via, "in_l0": bool(via),
        "resolve_error": None if (not kind == "wiki" or via) else cache.get(tok, {}).get("error"),
        "resolve_ok": None if (not kind == "wiki" or via) else cache.get(tok, {}).get("ok"),
        "title": cache.get(tok, {}).get("title") if tok else None,
        "refs": sorted(ctxs),
    })

json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(verdicts, open(f"/tmp/{RUN}-feishu-link-verdicts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
real_gaps = [v for v in verdicts if not v["in_l0"]]
unresolved = [v for v in real_gaps if v["kind"] == "wiki" and v["resolve_error"]]
print(json.dumps({
    "run": RUN,
    "feishu_urls": len(verdicts),
    "in_l0": len(verdicts) - len(real_gaps),
    "real_gap": len(real_gaps),
    "real_gap_unresolved_no_permission": len(unresolved),
    "real_gaps": [{"url": v["url"], "kind": v["kind"], "obj_token": v["obj_token"],
                   "title": v["title"], "err": v["resolve_error"], "refs": v["refs"]} for v in real_gaps],
}, ensure_ascii=False, indent=1))
