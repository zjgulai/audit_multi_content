#!/usr/bin/env python3
"""第 3/4 项：放开截断，拉取两张表的全量记录 + URL 字段全量边。只读，写入 kb/.work/。"""
import json, os, re, subprocess, collections, sys

ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
OUT = "kb/.work/full"
os.makedirs(OUT, exist_ok=True)
URL_RE = re.compile(r'https?://[^\s\)\]\>"\']+')

TARGETS = [
    ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblcbk4XiW6471YN", "广告文案明细", 291, "广告文案风控库"),
    ("SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tbl8AI00JZO1iZtp", "专家修订汇总表", 395, "内容公式与专家修订库"),
]

def run(args, timeout=300):
    p = subprocess.run(args, capture_output=True, text=True, env=ENV, timeout=timeout)
    return p

ops, results = [], {}
for bt, tid, tname, total, label in TARGETS:
    rows, offset, page = [], 0, 0
    while offset < total:
        page += 1
        out = f"{OUT}/{tid}.p{page}.ndjson"
        p = run(["lark-cli", "base", "+record-list", "--base-token", bt, "--table-id", tid,
                 "--limit", "200", "--offset", str(offset), "--format", "ndjson", "--output", out])
        ops.append({"op": "base +record-list", "nature": "read",
                    "target": f"bitable:{bt}:table:{tid}",
                    "note": f"{tname} 全量第 {page} 页（offset={offset}）"})
        if not os.path.exists(out):
            print(f"  !! 第 {page} 页未产出：{p.stdout[-200:]}")
            break
        got = [json.loads(l) for l in open(out, encoding="utf-8") if l.strip()]
        rows += got
        print(f"  {tname} 第 {page} 页 offset={offset} 取到 {len(got)} 条，累计 {len(rows)}/{total}")
        if len(got) == 0:
            break
        offset += 200
    # 去重（按 record_id）
    seen, ded = set(), []
    for r in rows:
        if r["record_id"] in seen:
            continue
        seen.add(r["record_id"]); ded.append(r)
    results[tname] = {"base_token": bt, "table_id": tid, "label": label,
                      "total_expected": total, "fetched": len(ded),
                      "records": ded}
    print(f"  ✅ {tname} 全量 {len(ded)} 条（期望 {total}）")

json.dump(results, open("kb/.work/full_records.json", "w", encoding="utf-8"), ensure_ascii=False)

# ---------- URL 字段全量（不设上限）
base_enum = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))
FIELDS = {"广告文案明细": ["落地页URL"], "品线内容边界规则库": ["依据来源"],
          "数据表": ["资料名称", "文件/链接"]}
url_rows, uniq = [], {}
for bt, e in base_enum.items():
    for t in e["tables"]:
        for fn in FIELDS.get(t["table_name"], []):
            for r in t["records"]:
                v = r.get(fn)
                if not v:
                    continue
                for m in URL_RE.finditer(str(v)):
                    u = m.group(0).rstrip(".,;")
                    url_rows.append({"record_id": r["record_id"], "table": t["table_name"],
                                     "field": fn, "url": u, "base_token": bt})
                    uniq.setdefault(u, {"url": u, "first_seen": {"record_id": r["record_id"],
                                                                 "table": t["table_name"], "field": fn},
                                        "ref_count": 0})
                    uniq[u]["ref_count"] += 1
# 规则库来源链接也一并纳入（此前已全量，这里保持）
rules = [json.loads(l) for l in open("kb/.work/规则库.ndjson", encoding="utf-8") if l.strip()]
for r in rules:
    for m in URL_RE.finditer(str(r.get("来源链接") or "")):
        u = m.group(0)
        url_rows.append({"record_id": r["record_id"], "table": "规则库", "field": "来源链接",
                         "url": u, "base_token": "GnRZbIuXraCzf0sGr2UcmZ62nfc"})
        uniq.setdefault(u, {"url": u, "first_seen": {"record_id": r["record_id"], "table": "规则库",
                                                     "field": "来源链接"}, "ref_count": 0})
        uniq[u]["ref_count"] += 1

bad = [u for u in uniq if not re.match(r'^https?://[A-Za-z0-9.\-]+/', u)]
json.dump({"url_rows": url_rows, "unique": uniq, "malformed": bad},
          open("kb/.work/full_urls.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ops, open("kb/.work/ops_full.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"URL 边 {len(url_rows)} 条 / 唯一 {len(uniq)} 个 / 格式异常 {len(bad)} 个")
hosts = collections.Counter(re.sub(r'^https?://([^/]+).*', r'\1', u) for u in uniq)
for h, n in hosts.most_common(12):
    print(f"   {n:4d}  {h}")
