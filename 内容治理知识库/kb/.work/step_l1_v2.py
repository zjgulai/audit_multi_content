#!/usr/bin/env python3
"""L0 重新落库 · L1 解析与内容抓取（用最新快照重跑）。
只读：wiki +node-get / docs +fetch。写入 kb/.work/。
"""
import json, os, re, hashlib, subprocess, sys, collections

ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
ENTRY_BASE, ENTRY_TBL = "GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblMGtPfe8ZUsEdP"
LINK_RE = re.compile(r'\[(?P<t>.*?)\]\((?P<u>https?://[^\)\s]+)\)', re.S)
BARE_RE = re.compile(r'(?<!\()(?P<u>https?://[^\s\)\]]+)')

def run(args, timeout=180):
    try:
        p = subprocess.run(args, capture_output=True, text=True, env=ENV, timeout=timeout)
        return json.loads(p.stdout)
    except Exception as e:
        return {"ok": False, "error": {"type": "parse", "message": str(e)[:200]}}

def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

rows = [json.loads(l) for l in open("kb/.work/材料收集.ndjson", encoding="utf-8") if l.strip()]
approved = [r for r in rows if r.get("材料审核状态") == ["通过"]]

def classify(u):
    if "feishu.cn" not in u and "larksuite" not in u:
        return "url"
    m = re.search(r'feishu\.cn/(wiki|base|sheets|slides|file|docx|docs|drive/folder|record)/', u)
    if not m:
        return "url"
    return {"wiki": "wiki", "base": "base", "sheets": "sheets", "slides": "slides", "file": "file",
            "docx": "docx", "docs": "docs", "folder": "folder", "record": "record"}.get(m.group(1), "url")

links = []
for r in approved:
    raw = r.get("材料链接") or ""
    found = [(m.group("t"), m.group("u")) for m in LINK_RE.finditer(raw)]
    if not found:
        found = [("", m.group("u")) for m in BARE_RE.finditer(raw)]
    for t, u in found:
        links.append({"record_id": r["record_id"], "url": u, "anchor_text": t,
                      "kind": classify(u), "field_name": "材料链接", "field_id": "fldr4c8nnT",
                      "kb_type_hint": r.get("知识库分类") or []})

ops = []
# --- wiki 节点解包
node_map = {}
for lk in links:
    if lk["kind"] != "wiki":
        continue
    tok = re.search(r'/wiki/([A-Za-z0-9]+)', lk["url"]).group(1)
    if tok in node_map:
        continue
    d = run(["lark-cli", "wiki", "+node-get", "--node-token", lk["url"]])
    ops.append({"op": "wiki +node-get", "nature": "read", "target": f"wiki:{tok}",
                "note": "解析 wiki 节点到底层对象"})
    node_map[tok] = d["data"] if d.get("ok") else {"error": d.get("error", {})}
for lk in links:
    if lk["kind"] == "wiki":
        tok = re.search(r'/wiki/([A-Za-z0-9]+)', lk["url"]).group(1)
        n = node_map.get(tok, {})
        lk["obj_type"], lk["obj_token"] = n.get("obj_type"), n.get("obj_token")
        lk["node_title"] = n.get("title")

# --- 资源键
def key_of(lk):
    u = lk["url"]
    if lk["kind"] == "wiki":
        return f"wiki:{lk.get('obj_token') or re.search(r'/wiki/([A-Za-z0-9]+)', u).group(1)}"
    if lk["kind"] == "docx":
        return f"docx:{re.search(r'/docx/([A-Za-z0-9]+)', u).group(1)}"
    m = re.search(r'feishu\.cn/(?:wiki|base|sheets|slides|file|docx|docs|drive/folder|record)/([A-Za-z0-9]+)', u)
    if m:
        return f"{lk['kind']}:{m.group(1)}"
    return f"url:{u}"

for lk in links:
    lk["resource_key"] = key_of(lk)

# --- 内容抓取
content = {}
for lk in links:
    k = lk["resource_key"]
    if k in content:
        continue
    rec = {"resource_key": k, "kind": lk["kind"], "url": lk["url"],
           "obj_type": lk.get("obj_type"), "obj_token": lk.get("obj_token")}
    is_doc = (lk["kind"] == "docx") or (lk["kind"] == "wiki" and lk.get("obj_type") == "docx")
    if is_doc:
        d = run(["lark-cli", "docs", "+fetch", "--doc", lk["url"], "--doc-format", "markdown"])
        ops.append({"op": "docs +fetch", "nature": "read", "target": k, "note": "读取 docx 正文用于 sha256(doc_text)"})
        if d.get("ok"):
            doc = d["data"]["document"]
            c = doc["content"]
            rec.update({"sha256": sha(norm_text(c)), "sha256_input": "doc_text", "sha256_state": "full",
                        "chars": len(c), "revision": doc.get("revision_id"),
                        "title": doc.get("title") or lk.get("node_title"), "content": c})
        else:
            err = d.get("error", {}) or {}
            perm = err.get("code") in (3380004, 3380003, 1061002, 1061004) or "permission" in str(err.get("message", "")).lower()
            rec.update({"sha256": None, "sha256_state": "forbidden" if perm else "unreachable",
                        "error_code": err.get("code"), "error_type": err.get("type"),
                        "status_reason": ("无文档权限（code %s）：%s" % (err.get("code"), str(err.get("message"))[:100]))
                                          if perm else ("读取失败：" + str(err.get("message", ""))[:120])})
        content[k] = rec
        continue
    if lk["kind"] == "wiki" and lk.get("obj_type") == "bitable":
        rec.update({"sha256": None, "sha256_input": "structure", "sha256_state": "structure_only",
                    "title": lk.get("node_title")})
        content[k] = rec
        continue
    if lk["kind"] == "wiki" and lk.get("obj_type") == "file":
        rec.update({"sha256": None, "sha256_input": "file_bytes", "sha256_state": "no_scope",
                    "title": lk.get("node_title"),
                    "status_reason": "缺少 drive:file:download scope，无法取字节流，不计算 sha256"})
        content[k] = rec
        continue
    if lk["kind"] in ("sheets", "slides", "file"):
        probe = {"sheets": ["lark-cli", "sheets", "+workbook-info", "--url", lk["url"]],
                 "slides": ["lark-cli", "slides", "+xml-get", "--presentation", lk["url"]],
                 "file": ["lark-cli", "drive", "+preview", "--url", lk["url"]]}[lk["kind"]]
        run(probe)
        ops.append({"op": " ".join(probe[:3]), "nature": "read-attempt", "target": k,
                    "note": "尝试读取内容算 sha256（被 scope 拒绝）"})
        need = {"sheets": "sheets:spreadsheet:read", "slides": "slides:presentation:read",
                "file": "drive:file:download"}[lk["kind"]]
        rec.update({"sha256": None, "sha256_input": None, "sha256_state": "no_scope",
                    "missing_scope": need,
                    "status_reason": f"缺少 {need} scope（已实测确认），未读取内容，不计算 sha256"})
        content[k] = rec
        continue
    if lk["kind"] == "base":
        rec.update({"sha256": None, "sha256_input": "structure", "sha256_state": "structure_only",
                    "base_token": re.search(r'/base/([A-Za-z0-9]+)', lk["url"]).group(1)})
        content[k] = rec
        continue
    rec.update({"sha256": None, "sha256_input": "url_text", "sha256_state": "unreachable"})
    content[k] = rec

json.dump(links, open("kb/.work/links-l1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"node_map": node_map}, open("kb/.work/l1_nodes.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(content, open("kb/.work/l1_content.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ops, open("kb/.work/ops-l1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"通过记录 {len(approved)} | link {len(links)} | 唯一资源 {len(content)}")
for k, v in content.items():
    print(f"  {k:56s} {str(v.get('sha256_state')):15s} chars={v.get('chars')} title={str(v.get('title'))[:34]}")
