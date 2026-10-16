#!/usr/bin/env python3
"""L2 ↔ L1 陈旧性审计（只读，不落盘数据，只写一份报告）。

## 为什么要这个脚本（2026-09-30 立）

L2 台账里的「失效」是**资源级**的：`kb/l2/manifest_l2.jsonl` 只记
`result=invalidated`，而 `kb/.work/l6_scope_lib.py:_invalidated_resources()` 也只读这
一个粒度。于是出现一个**结构性漏洞**：

    资源被重切（重新抓取 / 重新 OCR）时，旧单元行**留在 `units.jsonl` 里不删**，
    而资源的最新 result 变成 `split`（不再是 `invalidated`），
    资源级护栏当场失效 → **旧文本的单元继续进 L6 索引**。

2026-09-29 那批「150 条 URL 统一重抓」和「扫描件 OCR」都走的是这个模式，实测后果：
L6 索引里 31 条单元的 `source_sha256` 已不是该资源的当前 sha（合计 88,588 字），
其中 TikTok 广告政策页 6 条 / 20,134 字、Google 广告政策页 4 条 / 14,480 字 ——
正是用户白名单决策里要挡的「整页抓取」文本，换了个 sha 就绕过来了。

本脚本把这件事**量出来**，给 `kb/l8/l2_align_stale.py`（修复侧）提供待办清单。

## 口径（每条资源一个判定）

    l1_sha       = L1 产物的 source_sha256（当前正文的权威 sha）
    man_result   = manifest_l2 里该资源最新一行的 result
    man_sha      = 该行的 source_sha256
    unit_shas    = units.jsonl 里该资源所有单元行的 source_sha256 去重集合

    current            unit_shas == {l1_sha}                 → 无事
    stale_units        unit_shas 里含 ≠ l1_sha 的 sha        → **要退役旧单元**
    missing_split      L1 有正文但一条单元都没有               → 缺口（l2_split_run.py 的活）
    manifest_mismatch  man_sha != l1_sha                     → 台账与产物不一致
    l1_no_text         L1 产物无 segments                     → 不适用

用法：
    python3 kb/l8/l2_staleness_audit.py [RUN] [--json 路径]
"""
import collections
import hashlib
import json
import os
import sys

RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), "audit")
OUT = (sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv
       else f"kb/l8/runs/{RUN}-l2-staleness.json")

L0, L1, L2 = "kb/l0", "kb/l1", "kb/l2"


def load_jsonl(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


# ── L1 产物（按目录扫，权威正文）────────────────────────────────────────
# 连接键必须是产物的 `resource_id`（= 文件名去扩展名），**不是** `resource_key`：
# artifact 里 resource_key 是 'url:https://…' 形态，而 L2 单元的 resource_id 是
# 'url__https____…' 形态。第一版审计脚本错用了 resource_key，结果 1,906 个资源
# 全部 join 不上、报出「1,855 个缺口」这种假数字 —— 口径错一次，数字全错。
ART = {}
for d in sorted(os.listdir(L1)):
    dp = os.path.join(L1, d)
    if not (os.path.isdir(dp) and d[0].isdigit()):
        continue
    for f in os.listdir(dp):
        if f.endswith(".json"):
            try:
                o = json.load(open(os.path.join(dp, f), encoding="utf-8"))
            except Exception:
                continue
            rid = o.get("resource_id") or f[:-5]
            if rid != f[:-5]:
                raise SystemExit(f"[口径错误] {f} 的 resource_id={rid!r} 与文件名不符；"
                                 f"L2 单元按文件名连接，先对齐口径再审计")
            ART[rid] = o

# ── L2 台账 / 单元 ──────────────────────────────────────────────────────
man_latest = {}
for r in load_jsonl(f"{L2}/manifest_l2.jsonl"):
    if "resource_id" in r:
        man_latest[r["resource_id"]] = r

# L1 侧状态：与 kb/l8/l2_split_run.py 的 `E` 口径保持一致 ——
# L1 台账里 status 为 invalidated / retracted 的资源**不算缺口**（正文已作废）。
# 第一版审计漏了这层过滤，把 245 个资源报成缺口，而官方工具只认 43 个。
# 两份口径不一致就会得出两套数字，所以这里显式取齐。
l1_status = {}
for r in load_jsonl(f"{L1}/manifest_l1.jsonl"):
    if "resource_id" in r:
        l1_status[r["resource_id"]] = r.get("status")

units = load_jsonl(f"{L2}/units.jsonl")
by_res = collections.defaultdict(list)
for u in units:
    by_res[u["resource_id"]].append(u)

# ── 「有正文却没单元」里，正文本身是否真有内容字段 ─────────────────────
# 与 kb/l8/l2_split_run.py 的 split_units()/is_content() 同口径：字段角色 role != content
# 的 field_value 段不算内容，全篇都是这种段的资源**按口径就不该切**（元数据闭合）。
# 不自己算这一层，就会把 41 个「本该闭合」的资源报成「缺口」——两套口径两套数字。
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
OV, FR = reg["field_role_table_overrides"], reg["field_roles"]


def _is_content(s):
    if s.get("kind") != "field_value":
        return True
    return OV.get(f"::{s.get('field_name')}", FR.get(s.get("field_name"))) == "content"


# ── 判定 ───────────────────────────────────────────────────────────────
rows = []
for rid, art in ART.items():
    segs = art.get("segments") or []
    l1_sha = art.get("source_sha256")
    us = by_res.get(rid, [])
    ushas = {u.get("source_sha256") for u in us}
    man = man_latest.get(rid, {})
    verdicts = []
    stale = [u for u in us if u.get("source_sha256") != l1_sha]
    dead = l1_status.get(rid) in ("invalidated", "retracted")
    if dead:
        verdicts.append("l1_invalidated")
    if not segs:
        verdicts.append("l1_no_text")
    elif not us:
        n_content = sum(1 for s in segs if _is_content(s))
        if dead:
            verdicts.append("l1_invalidated_no_units")
        elif n_content == 0:
            verdicts.append("metadata_closed")
        else:
            verdicts.append("missing_split")
    elif ushas == {l1_sha}:
        verdicts.append("current")
    else:
        if stale:
            verdicts.append("stale_units")
        if l1_sha in ushas:
            verdicts.append("has_current_units")
    if man and man.get("source_sha256") and man["source_sha256"] != l1_sha:
        verdicts.append("manifest_mismatch")
    if man.get("result") == "invalidated":
        verdicts.append("resource_invalidated")
    rows.append({
        "resource_id": rid, "kb_type": art.get("kb_type"),
        "verdicts": verdicts,
        "l1_sha": l1_sha, "l1_chars": art.get("char_count") or sum(len(s.get("text") or "") for s in segs),
        "l1_segments": len(segs), "l1_observed_at": art.get("observed_at"),
        "man_result": man.get("result"), "man_sha": man.get("source_sha256"),
        "unit_count": len(us), "unit_shas": sorted(x for x in ushas if x),
        "stale_units": len(stale),
        "stale_chars": sum(len(u.get("text") or "") for u in stale),
        "stale_unit_ids": [u["unit_id"] for u in stale],
        "current_units": len([u for u in us if u.get("source_sha256") == l1_sha]),
    })

cnt = collections.Counter()
for r in rows:
    for v in r["verdicts"]:
        cnt[v] += 1
stale_rows = [r for r in rows if "stale_units" in r["verdicts"]]
need_resplit = [r for r in stale_rows if "has_current_units" not in r["verdicts"] and "l1_no_text" not in r["verdicts"]]
missing = [r for r in rows if "missing_split" in r["verdicts"]]

# 这些陈旧单元有多少真的进了 L6 索引
idx_ids = {json.loads(l)["unit_id"] for l in open("kb/l6/index/l6.jsonl", encoding="utf-8") if l.strip()} \
    if os.path.exists("kb/l6/index/l6.jsonl") else set()
scope = {l.strip() for l in open("kb/l6/SCOPE.txt", encoding="utf-8")
         if l.strip() and not l.startswith("#")} if os.path.exists("kb/l6/SCOPE.txt") else set()
stale_ids = {i for r in stale_rows for i in r["stale_unit_ids"]}
in_idx = stale_ids & idx_ids
in_scope = stale_ids & scope

summary = {
    "run": RUN,
    "kind": "l2_staleness_audit",
    "why": "资源被重切后旧单元不退役，资源级失效护栏当场失效（详见脚本头部）",
    "resources_with_artifact": len(rows),
    "verdict_counts": dict(cnt),
    "stale_resources": len(stale_rows),
    "stale_units": len(stale_ids),
    "stale_chars": sum(r["stale_chars"] for r in stale_rows),
    "stale_units_in_l6_index": len(in_idx),
    "stale_units_in_scope_file": len(in_scope),
    "stale_chars_in_l6_index": sum(len(u.get("text") or "") for u in units if u["unit_id"] in in_idx),
    "need_resplit_resources": len(need_resplit),
    "missing_split_resources": len(missing),
    "rows": sorted(rows, key=lambda r: -r["stale_chars"]),
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(summary, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"[{RUN}] L2↔L1 陈旧性审计（只读）")
print(f"  有 L1 产物的资源 {len(rows)} 个")
for k, v in sorted(cnt.items(), key=lambda kv: -kv[1]):
    print(f"    {k:<22} {v}")
print(f"  含陈旧单元的资源 {len(stale_rows)} 个；陈旧单元 {len(stale_ids)} 条 / {summary['stale_chars']} 字")
print(f"  其中真的进了 L6 索引的 {len(in_idx)} 条 / {summary['stale_chars_in_l6_index']} 字"
      f"（在 SCOPE 白名单里的 {len(in_scope)} 条）")
print(f"  单元 sha 与当前正文不符、且没有当前正文单元的资源（要重切）{len(need_resplit)} 个")
print(f"  L1 有正文却一条单元都没有的缺口 {len(missing)} 个")
if stale_rows:
    print("\n  陈旧量最大的 12 个资源：")
    for r in sorted(stale_rows, key=lambda r: -r["stale_chars"])[:12]:
        print(f"    {r['stale_chars']:>7} 字 / {r['stale_units']:>3} 条  cur={r['current_units']:>3}  "
              f"{r['kb_type']:<18} {r['resource_id'][:62]}")
print(f"\n[报告] {OUT}")
