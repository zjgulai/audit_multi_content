#!/usr/bin/env python3
"""L0 落库 · 步骤 5 第三层边界确认: 记录超深度链接、尝试外部文档读取（只读）。"""
import json, re, hashlib, subprocess, os, sys

URL = re.compile(r'https?://[^\s\)\]\>"\']+')
l1c = json.load(open("kb/.work/l1_content.json", encoding="utf-8"))
known = {t["resource_key"] for t in json.load(open("kb/.work/l1.json", encoding="utf-8"))["l1_targets"]}

def kind_of(u):
    if "feishu.cn/" not in u:
        return "url"
    m = re.search(r'feishu\.cn/(wiki|base|sheets|slides|file|docx|docs|drive/folder|record)/', u)
    if not m:
        return "url"
    return {"wiki": "feishu_wiki_node", "base": "feishu_bitable_base", "sheets": "feishu_sheet",
            "slides": "feishu_slides", "file": "feishu_file", "docx": "feishu_doc",
            "docs": "feishu_doc", "record": "feishu_bitable_record"}.get(m.group(1), "url")

d3 = []
seen = set()
for k, rc in l1c.items():
    c = rc.get("content") or ""
    if not c:
        continue
    for m in URL.finditer(c):
        u = m.group(0).rstrip(".,;")
        if u in known or f"url:{u}" in known or (k, u) in seen:
            continue
        seen.add((k, u))
        d3.append({"from": k, "url": u, "kind": kind_of(u)})

# 对非飞书的外部链接做一次读取尝试（用于判定可达性），结果写入 l3_probe
probe = {}
for item in d3:
    u = item["url"]
    if item["kind"] != "url" or u in probe:
        continue
    if any(u.startswith(p) for p in ("https://www.tiktok.com/@", "https://www.instagram.com/")):
        probe[u] = {"status": "skipped_depth_limit",
                    "reason": "超出下钻层数上限(2)，不抓取正文"}
        continue
    try:
        p = subprocess.run(["curl", "-sS", "-L", "--max-time", "20", "-o", os.devnull,
                            "-w", "%{http_code}",
                            "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120 Safari/537.36", u],
                           capture_output=True, text=True, timeout=30)
        code = p.stdout.strip()
        probe[u] = {"status": "skipped_depth_limit",
                    "reason": f"超出下钻层数上限(2)，不抓取正文；可达性探测 HTTP {code}"}
    except Exception as e:
        probe[u] = {"status": "skipped_depth_limit", "reason": f"超出下钻层数上限(2)；探测异常 {e}"}

json.dump({"depth3": d3, "probe": probe}, open("kb/.work/l3.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("depth3 链接:", len(d3), "其中飞书:", sum(1 for x in d3 if x["kind"] != "url"))
for x in d3:
    if x["kind"] != "url":
        print("   ", x["from"], "->", x["url"])
