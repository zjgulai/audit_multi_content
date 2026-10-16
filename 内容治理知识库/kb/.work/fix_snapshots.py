#!/usr/bin/env python3
"""第 6 项：为已下钻到的飞书 docx 落存正文快照。
kb/l0/snapshots/<resource_key>@<sha256>.md
文件名带 sha256，多版并存不覆盖；锚点靠它才能核对（行号会随文档编辑漂移）。
"""
import json, os, re, hashlib, collections, subprocess, sys

RUN = sys.argv[1]
L0 = "kb/l0"
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
SNAP = f"{L0}/snapshots"
os.makedirs(SNAP, exist_ok=True)

latest = {}
for line in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        latest[r["resource_key"]] = r
l1c = json.load(open("kb/.work/l1_content.json", encoding="utf-8"))
gdoc = json.load(open("kb/.work/gdoc.json", encoding="utf-8"))

def safe(k):
    return re.sub(r'[^0-9A-Za-z._\-]+', '_', k.replace(":", "__").replace("/", "_"))[:130]

docs = [r for r in latest.values() if r["source_kind"] == "feishu_doc"]
print(f"飞书文档资源 {len(docs)} 条")

made, skipped, failed = [], [], []
for r in docs:
    rk, sha = r["resource_key"], r["sha256"]
    c = l1c.get(rk, {})
    content = c.get("content")
    title = c.get("title") or ""
    if not content:
        # 不可读的（forbidden 等）登记原因，不静默跳过
        failed.append({"resource_key": rk, "sha256": sha, "sha256_state": r["sha256_state"],
                       "status_reason": r["status_reason"], "entry_url": r["entry_url"],
                       "title": title})
        continue
    # 校验：快照正文规范化后的 sha256 必须等于台账 sha256
    txt = content.replace("\r\n", "\n").replace("\r", "\n")
    txt = "\n".join(l.rstrip() for l in txt.split("\n"))
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    calc = hashlib.sha256(txt.encode("utf-8")).hexdigest()
    fn = f"{safe(rk)}@{sha}.md"
    p = f"{SNAP}/{fn}"
    hdr = (f"<!-- L0 正文快照\n"
           f"resource_key: {rk}\n"
           f"source_kind: {r['source_kind']}\n"
           f"kb_type: {r['kb_type']}\n"
           f"title: {title}\n"
           f"entry_url: {r['entry_url']}\n"
           f"sha256: {sha}\n"
           f"sha256_input: {r['sha256_input']}\n"
           f"sha256_recomputed: {calc}\n"
           f"sha256_match: {str(calc == sha).lower()}\n"
           f"observed_at: {RUN}\n"
           f"note: 快照用于核对 L1 锚点（行号 + 标题路径）；行号会随文档编辑漂移，故文件名带 sha256、多版并存。\n"
           f"-->\n\n")
    existed = os.path.exists(p)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(hdr + content.rstrip() + "\n")
    made.append({"resource_key": rk, "file": fn, "sha256": sha, "sha256_recomputed": calc,
                 "match": calc == sha, "chars": len(content), "title": title,
                 "kb_type": r["kb_type"], "existed_before": existed,
                 "depth": r["depth"], "entry_url": r["entry_url"]})

json.dump({"snapshots": made, "unreadable": failed, "skipped": skipped,
           "dir": SNAP}, open("kb/.work/snapshots.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"新增/更新快照 {len(made)} 个 | 不可读 {len(failed)} 条")
for m in made:
    print(f"  {'✅' if m['match'] else '❌'} {m['file'][:74]:76s} {m['chars']:7d} 字  {m['title'][:26]}")
for f in failed:
    print(f"  ⛔ {f['resource_key'][:40]:42s} {f['sha256_state']:10s} {f['status_reason'][:56]}")
