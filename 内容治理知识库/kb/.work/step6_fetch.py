#!/usr/bin/env python3
"""L0 落库 · 步骤 6: 抓取 L1 资源内容并算 sha256（只读）。"""
import json, os, re, hashlib, subprocess, sys

RUN = sys.argv[1]
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
os.makedirs("kb/.work/content", exist_ok=True)
os.makedirs("kb/.work/bases", exist_ok=True)

def run(args, timeout=180):
    try:
        p = subprocess.run(args, capture_output=True, text=True, env=ENV, timeout=timeout)
        return json.loads(p.stdout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"type": "timeout", "message": "cli timeout"}}
    except Exception as e:
        return {"ok": False, "error": {"type": "parse", "message": str(e)[:300]}}

def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

L = json.load(open("kb/.work/l1.json", encoding="utf-8"))
ops = json.load(open("kb/.work/ops-l1.json", encoding="utf-8"))
out = {}

for t in L["l1_targets"]:
    key = t["resource_key"]
    if key in out:
        continue
    rec = {"resource_key": key, "kind": t["kind"], "url": t["url"],
           "obj_type": t.get("obj_type"), "obj_token": t.get("obj_token")}
    # ---- docx（含 wiki 包裹的 docx）
    if t["kind"] == "wiki" and t.get("obj_type") == "docx":
        d = run(["lark-cli", "docs", "+fetch", "--doc", t["url"], "--doc-format", "markdown"])
        ops.append({"op": "docs +fetch", "nature": "read", "target": key, "note": "读取 docx 正文用于 sha256"})
        if d.get("ok"):
            content = d["data"]["document"]["content"]
            doc = d["data"]["document"]
            rev = doc.get("revision_id") or d["data"].get("revision_id")
            rec.update({"sha256": sha(norm_text(content)), "sha256_input": "doc_text",
                        "sha256_state": "full", "chars": len(content),
                        "revision": rev, "title": doc.get("title") or (t.get("node") or {}).get("title"),
                        "content": content})
        else:
            rec.update({"sha256": None, "sha256_state": "fetch_failed",
                        "error": d.get("error", {})})
        out[key] = rec
        continue
    # ---- wiki 包裹的 bitable
    if t["kind"] == "wiki" and t.get("obj_type") == "bitable":
        rec.update({"sha256_input": "structure", "sha256": None, "sha256_state": "structure_only",
                    "title": (t.get("node") or {}).get("title"),
                    "note": "wiki 指向 bitable；结构由 base 枚举补充"})
        out[key] = rec
        continue
    # ---- wiki 包裹的 file
    if t["kind"] == "wiki" and t.get("obj_type") == "file":
        rec.update({"sha256": None, "sha256_state": "no_scope", "sha256_input": "file_bytes",
                    "title": (t.get("node") or {}).get("title"),
                    "status_reason": "缺少 drive:file:download scope，无法下载文件字节流"})
        ops.append({"op": "drive +download", "nature": "read-attempt", "target": key,
                    "note": "尝试下载文件算 sha256，被 scope 拒绝"})
        out[key] = rec
        continue
    # ---- sheets / slides / file（无 scope）
    if t["kind"] in ("sheets", "slides", "file"):
        probe = []
        if t["kind"] == "sheets":
            probe = ["lark-cli", "sheets", "+workbook-info", "--url", t["url"]]
        elif t["kind"] == "slides":
            probe = ["lark-cli", "slides", "+xml-get", "--presentation", t["url"]]
        else:
            probe = ["lark-cli", "drive", "+preview", "--url", t["url"]]
        d = run(probe)
        ops.append({"op": " ".join(probe[:3]), "nature": "read-attempt", "target": key,
                    "note": "尝试读取内容算 sha256"})
        err = d.get("error", {}) if not d.get("ok") else {}
        rec.update({"sha256": None, "sha256_input": None,
                    "sha256_state": "no_scope" if err.get("subtype") == "missing_scope" else "fetch_failed",
                    "status_reason": err.get("message", "")[:200],
                    "error_type": err.get("type"), "error_subtype": err.get("subtype")})
        out[key] = rec
        continue
    # ---- base
    if t["kind"] == "base":
        bt = t.get("base_token") or re.search(r'/base/([A-Za-z0-9]+)', t["url"]).group(1)
        rec.update({"base_token": bt, "sha256_input": "structure"})
        out[key] = rec
        continue
    # ---- 外部 URL
    if t["kind"] == "url":
        rec.update({"sha256_input": "url_text"})
        out[key] = rec
        continue
    out[key] = rec

json.dump(out, open("kb/.work/l1_content.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ops, open("kb/.work/ops-l1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in out.items():
    print(f"{k:52s} state={str(v.get('sha256_state')):16s} sha={(v.get('sha256') or '')[:16]} chars={v.get('chars')}")
