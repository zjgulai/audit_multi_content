#!/usr/bin/env python3
"""L0 落库 · 步骤 5/6: 下钻抓取 + 资源登记数据准备。
只读：docs/wiki/base 读接口；输出统一写入 kb/。
"""
import json, os, re, hashlib, subprocess, sys, collections

RUN = sys.argv[1]
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
BASE = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
TBL_ENTRY = "tblMGtPfe8ZUsEdP"

def run(args, timeout=120):
    p = subprocess.run(args, capture_output=True, text=True, env=ENV, timeout=timeout)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"ok": False, "error": {"type": "parse", "message": (p.stdout or p.stderr)[:400]}}

def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

LINK_RE = re.compile(r'\[(?P<t>.*?)\]\((?P<u>https?://[^\)\s]+)\)', re.S)

# ------------------------------------------------------------------ 1) 入口记录 + 兄弟表
parent_records = [json.loads(l) for l in open("kb/.work/材料收集.ndjson", encoding="utf-8") if l.strip()]
approved = [r for r in parent_records if r.get("材料审核状态") == ["通过"]]
link_l1 = json.load(open("kb/.work/links-l1.json", encoding="utf-8"))

resources = []      # 资源登记条目
edges = []          # 边表
ops = []            # 外部调用台账

SIBLINGS = [("tblZP8jG4tiUL98C", "知识库分类说明"), ("tbld8qE92YaY38Yz", "正面和负面样本"), ("tblXsrMVkDNZ3oW8", "规则库")]
sibling_tables = {}
for tid, tname in SIBLINGS:
    d = json.load(open(f"kb/.work/fields-{tid}.json", encoding="utf-8"))
    fields = [{"field_id": f["id"], "field_name": f["name"], "type": f["type"],
               "options": [o.get("name") for o in (f.get("options") or [])] or None,
               "multiple": f.get("multiple"),
               "lookup_from": f.get("from"), "lookup_field": f.get("select"),
               "lookup_where": f.get("where")} for f in d["data"]["fields"]]
    sibling_tables[tname] = {"table_id": tid, "fields": fields}
    ops.append({"op": "base +field-list", "nature": "read", "target": f"bitable:{BASE}:table:{tid}",
                "note": f"{tname} 字段 schema"})
    ops.append({"op": "base +record-list", "nature": "read", "target": f"bitable:{BASE}:table:{tid}",
                "note": f"{tname} 记录读取（用于结构统计）"})

# ------------------------------------------------------------------ 2) 入口记录资源
for r in parent_records:
    rid = r["record_id"]
    matched = rid in {x["record_id"] for x in link_l1} or r.get("材料审核状态") == ["通过"]
    resources.append({
        "resource_key": f"bitable:{TBL_ENTRY}:{rid}",
        "source_kind": "feishu_bitable_record",
        "table_name": "材料收集", "record_id": rid, "field_name": None, "field_id": None,
        "entry_url": f"https://momcozy-in.feishu.cn/base/{BASE}?table={TBL_ENTRY}&record={rid}",
        "path": "[内容治理/材料收集]", "depth": 1,
        "kb_type": None, "matched_rule": None, "kb_type_source": "record_self",
        "sha256_input": "record_fields", "sha256_state": "full",
        "revision": None, "dup_of": None, "moved_from": None,
        "status": "registered", "status_reason": "",
        "payload": {"fields": r, "field_id_list": None},
        "in_filter": matched,
    })

# ------------------------------------------------------------------ 3) 下钻第一层：入口 link 字段
def classify(url):
    if "feishu.cn" not in url and "larksuite" not in url:
        return "url"
    m = re.search(r'feishu\.cn/(wiki|base|sheets|slides|file|docx|docs|drive/folder|record)/', url)
    if not m:
        return "url"
    s = m.group(1)
    return {"wiki": "wiki", "base": "base", "sheets": "sheets", "slides": "slides",
            "file": "file", "docx": "docx", "docs": "docs", "folder": "folder", "record": "record"}.get(s, "url")

l1_targets = []
for it in link_l1:
    rid, url = it["record_id"], it["url"]
    kind = classify(url)
    l1_targets.append({"record_id": rid, "url": url, "kind": kind,
                       "anchor_text": it["anchor_text"], "kb_type_hint": it["kb_type_hint"],
                       "field_id": it["field_id"], "field_name": it["field_name"]})

# 3a) wiki -> node-get 解包
wiki_targets = [t for t in l1_targets if t["kind"] == "wiki"]
node_map = {}
for t in wiki_targets:
    tok = re.search(r'/wiki/([A-Za-z0-9]+)', t["url"]).group(1)
    if tok in node_map:
        continue
    d = run(["lark-cli", "wiki", "+node-get", "--node-token", t["url"]])
    ops.append({"op": "wiki +node-get", "nature": "read", "target": f"wiki:{tok}",
                "note": "解析 wiki 节点到底层对象"})
    if d.get("ok"):
        node_map[tok] = d["data"]
    else:
        node_map[tok] = {"error": d.get("error", {})}

for t in l1_targets:
    if t["kind"] != "wiki":
        continue
    tok = re.search(r'/wiki/([A-Za-z0-9]+)', t["url"]).group(1)
    t["node"] = node_map.get(tok, {})
    t["obj_type"] = (t["node"] or {}).get("obj_type")
    t["obj_token"] = (t["node"] or {}).get("obj_token")

# 3b) base -> 表结构
base_targets = {}
for t in l1_targets:
    if t["kind"] != "base":
        continue
    m = re.search(r'/base/([A-Za-z0-9]+)', t["url"])
    q = re.search(r'table=([A-Za-z0-9]+)', t["url"])
    t["base_token"] = m.group(1) if m else None
    t["table_id"] = q.group(1) if q else None

# 3c) 建立 L1 资源条目
def make_key(t):
    tok = None
    if t["kind"] == "wiki":
        tok = t.get("obj_token") or re.search(r'/wiki/([A-Za-z0-9]+)', t["url"]).group(1)
    else:
        m = re.search(r'feishu\.cn/(?:wiki|base|sheets|slides|file|docx|docs|drive/folder|record)/([A-Za-z0-9]+)', t["url"])
        tok = m.group(1) if m else hashlib.sha256(t["url"].encode()).hexdigest()[:24]
    return f"{t['kind']}:{tok}"

l1_resources = {}
for t in l1_targets:
    key = make_key(t)
    t["resource_key"] = key
    if key not in l1_resources:
        l1_resources[key] = t

print(f"L1 资源去重后: {len(l1_resources)}（原始 link {len(l1_targets)}）")
json.dump({"l1_targets": l1_targets, "node_map": {k: v for k, v in node_map.items()},
           "sibling_tables": sibling_tables},
          open("kb/.work/l1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ops, open("kb/.work/ops-l1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok")
