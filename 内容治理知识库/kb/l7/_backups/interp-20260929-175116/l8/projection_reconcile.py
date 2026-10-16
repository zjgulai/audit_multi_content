#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L8 · 投影对账：检测「派生视图 `kb/view`」与「权威分层库」之间的漂移（修复计划 F9）。

## 为什么要有它

`kb/view` 是 `kb/l3…l6` 的**只读投影**。此前两边只在**生成那一刻**对过一次，
之后无人对账 —— 实测后果（2026-09-29）：

  · 62 条 `rule_verification` 仍写着旧标签「已归纳」，权威库早已是「已支持」
  · 11 条 `p_level` 与权威库不一致（视图 P1，权威 P3/P2）
  · 2 条正文的「处理方式」还是旧的长串（权威库后续批次改短了）

**而且没有任何东西会报出来** —— 视图看起来一切正常，`kb_check` 也照样 100 分。
所以需要一件常驻的对账工具，而不是一次性脚本。

## 检查项

| # | 检查 | 判据 |
|---|---|---|
| R1 | 源文件指纹 | `derivation.sources.*.sha256` vs 权威库当前文件 sha256 |
| R2 | 条目级指纹 | `derivation.entries[*].fingerprint` vs 重算（`sha256(head 规则行)[:32]`）—— **任一 L3 字段变了就会变** |
| R3 | 集合对齐 | 视图条目 id ↔ L3 记录 id **一一对应**，无多余、无缺失 |
| R4 | 治理字段传导 | md 的 `owner`/`half_life_days`/`valid_until`/`effective_from` vs L3 行 |
| R5 | 落盘完整性 | md 的 bytes/sha256 vs `_meta/workbench-mirror.json` 的 `docs[]` 记录 |
| R6 | 层与目录 | md 的 `tier` ↔ 所在目录名（加载器 E019 的前置自检） |

## 退出码

`0` 全过 / `1` 有漂移 / `2` 环境或输入缺失（无法判定，**绝不当作通过**）

用法：
    python3 kb/l8/projection_reconcile.py                 # 人对读
    python3 kb/l8/projection_reconcile.py --json          # 机器读（供巡检/CI）
    python3 kb/l8/projection_reconcile.py --json-out F    # 同时落盘
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)                       # …/kb
VIEW = os.path.join(KB, "view")
META = os.path.join(VIEW, "_meta")
L3_RULES = os.path.join(KB, "l3", "candidates", "rules.jsonl")
MIRROR_FILE = "workbench-mirror.json"   # workbench 镜像负载（原误占 _meta/manifest.json，见 W035）
L3_P0 = os.path.join(KB, "l5", "p0_patterns.jsonl")
L2_UNITS = os.path.join(KB, "l2", "units.jsonl")

# tier ↔ 层目录（与加载器 TIER_DIR 一致）
TIER_DIR = {"L0": "L0-raw", "L1": "L1-facts", "L2": "L2-concepts",
            "L3": "L3-graph", "L4": "L4-contracts"}
GOV_FIELDS = ("owner", "half_life_days", "valid_until", "effective_from")
FM_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_jsonl(p: str) -> list[dict]:
    with open(p, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def fm_field(fm: str, key: str):
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", fm, re.M)
    if not m:
        return None
    v = m.group(1).strip()
    if v.startswith('"') and v.endswith('"'):
        v = v[1:-1]
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    ap.add_argument("--json-out", default=None, help="把 JSON 另存到该路径")
    a = ap.parse_args()

    for p in (L3_RULES, L3_P0, os.path.join(META, "derivation.json"),
              os.path.join(META, MIRROR_FILE)):
        if not os.path.exists(p):
            print(f"环境不完整，无法对账：缺 {os.path.relpath(p, KB)}", file=sys.stderr)
            return 2

    source = "kb/l3/candidates/rules.jsonl"
    der = json.load(open(os.path.join(META, "derivation.json"), encoding="utf-8"))
    man = json.load(open(os.path.join(META, MIRROR_FILE), encoding="utf-8"))
    rules = load_jsonl(L3_RULES)

    res = {"checked_at": None, "view_root": VIEW, "checks": {}, "drift": []}

    # ── 复现生成器的分组与 head（口径必须与 gen-host-library.py 逐字一致）──
    grouped: collections.OrderedDict[str, list[dict]] = collections.OrderedDict()
    for row in sorted(rules, key=lambda r: (r.get("article_no") or "zzz", r.get("rule_id", ""))):
        grouped.setdefault(row["rule_id"], []).append(row)
    heads = {}
    for rid, rows in grouped.items():
        heads[rid] = next((r for r in rows if r.get("article_no")), rows[0])

    # ── R1 源文件指纹 ────────────────────────────────────────────────────
    r1 = []
    for key, path in (("rules", L3_RULES), ("p0", L3_P0)):
        rec = (der.get("sources") or {}).get(key) or {}
        cur = sha256_file(path)
        if rec.get("sha256") in (None, ""):
            continue
        same = rec["sha256"] == cur
        r1.append({"source": key, "path": os.path.relpath(path, KB),
                   "recorded": rec["sha256"][:16], "current": cur[:16], "same": same})
        if not same:
            res["drift"].append({
                "check": "R1", "what": f"源文件 {key} 在视图生成后变过",
                "detail": f"{rec['sha256'][:16]}… → {cur[:16]}…",
                "fix": "重跑 kb/.work/gen-host-library.py 到 staging 后回填（见 projection_reconcile 文档）",
            })
    res["checks"]["R1_source_sha256"] = {"ok": all(x["same"] for x in r1), "items": r1}

    # ── R2 条目级指纹 ────────────────────────────────────────────────────
    r2_bad = []
    for e in der.get("entries") or []:
        rid = e.get("rule_id")
        head = heads.get(rid)
        if head is None:
            r2_bad.append({"id": e.get("id"), "why": "权威库已无此 rule_id"})
            continue
        want = sha256_text(json.dumps(head, ensure_ascii=False, sort_keys=True))[:32]
        if want != e.get("fingerprint"):
            r2_bad.append({"id": e.get("id"), "rule_id": rid,
                           "recorded": e.get("fingerprint"), "current": want})
    if r2_bad:
        res["drift"].append({
            "check": "R2", "what": f"{len(r2_bad)} 条条目的权威规则已变（任一字段）",
            "detail": [x["id"] for x in r2_bad[:10]],
            "fix": "同 R1：重新生成并回填",
        })
    res["checks"]["R2_entry_fingerprint"] = {
        "ok": not r2_bad, "entries": len(der.get("entries") or []), "stale": len(r2_bad),
        "samples": r2_bad[:10],
    }

    # ── R3 集合对齐 ──────────────────────────────────────────────────────
    view_ids = {e.get("id") for e in der.get("entries") or []}
    want_ids = {f"cg-{rid}" for rid in grouped}
    only_view = sorted(view_ids - want_ids)
    only_auth = sorted(want_ids - view_ids)
    if only_view or only_auth:
        res["drift"].append({
            "check": "R3", "what": "视图条目集合与权威库不一致",
            "detail": {"only_in_view": only_view[:10], "only_in_authority": only_auth[:10]},
            "fix": "重新生成并回填",
        })
    res["checks"]["R3_id_set"] = {
        "ok": not (only_view or only_auth),
        "view": len(view_ids), "authority": len(want_ids),
        "only_in_view": len(only_view), "only_in_authority": len(only_auth),
    }

    # ── R4 治理字段传导 / R6 层与目录（同一遍读文件）──────────────────────
    r4_bad, r6_bad, r5_bad = [], [], []
    man_by_rel = {d["relPath"]: d for d in (man.get("docs") or [])}
    for e in der.get("entries") or []:
        rid = e.get("rule_id")
        head = heads.get(rid) or {}
        rel = e.get("path")
        p = os.path.join(VIEW, rel)
        if not os.path.isfile(p):
            r5_bad.append({"rel": rel, "why": "文件不存在"})
            continue
        txt = open(p, encoding="utf-8").read()
        m = FM_RE.match(txt)
        if not m:
            r5_bad.append({"rel": rel, "why": "frontmatter 读不到"})
            continue
        fm = m.group(1)
        # R4
        for f in GOV_FIELDS:
            got, want = fm_field(fm, f), head.get(f)
            want_s = "" if want in (None, "") else str(want)
            if got != want_s:
                r4_bad.append({"id": e.get("id"), "field": f, "view": got, "authority": want_s})
        # R6
        tier = fm_field(fm, "tier")
        dirname = os.path.basename(os.path.dirname(rel))
        if TIER_DIR.get(tier) != dirname:
            r6_bad.append({"id": e.get("id"), "tier": tier, "dir": dirname})
        # R5
        doc = man_by_rel.get(rel)
        if doc is None:
            r5_bad.append({"rel": rel, "why": "manifest 无此条目"})
        else:
            raw = open(p, "rb").read()
            if hashlib.sha256(raw).hexdigest() != doc.get("sha256"):
                r5_bad.append({"rel": rel, "why": "sha256 不一致"})
            elif len(raw) != doc.get("bytes"):
                r5_bad.append({"rel": rel, "why": "bytes 不一致"})

    if r4_bad:
        byfield = collections.Counter(x["field"] for x in r4_bad)
        res["drift"].append({
            "check": "R4", "what": f"{len(r4_bad)} 处治理字段未从权威库传导",
            "detail": dict(byfield), "samples": r4_bad[:5],
            "fix": "确认投影生成器是否从规则行读这 4 个字段（F8）",
        })
    res["checks"]["R4_governance_passthrough"] = {
        "ok": not r4_bad, "mismatches": len(r4_bad),
        "by_field": dict(collections.Counter(x["field"] for x in r4_bad)), "samples": r4_bad[:5],
    }
    if r5_bad:
        res["drift"].append({
            "check": "R5", "what": f"{len(r5_bad)} 条落盘与 manifest 记录不符",
            "detail": r5_bad[:5], "fix": "重跑生成器回填；核对 manifest 是否指向真实 root",
        })
    res["checks"]["R5_manifest_bytes"] = {"ok": not r5_bad, "bad": len(r5_bad), "samples": r5_bad[:5]}
    if r6_bad:
        res["drift"].append({
            "check": "R6", "what": f"{len(r6_bad)} 条 tier 与所在目录不符（加载器会报 E019）",
            "detail": r6_bad[:5], "fix": "修投影生成器的 TIER_BY_FORM / TIER_VALUE_BY_DIR",
        })
    res["checks"]["R6_tier_dir"] = {"ok": not r6_bad, "bad": len(r6_bad), "samples": r6_bad[:5]}

    res["ok"] = all(v.get("ok") for v in res["checks"].values())
    res["summary"] = {
        "checks": len(res["checks"]),
        "passed": sum(1 for v in res["checks"].values() if v.get("ok")),
        "drift_items": len(res["drift"]),
    }

    if a.json_out:
        json.dump(res, open(a.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("投影对账：kb/view ⇄ 权威分层库")
        print(f"  视图根：{VIEW}")
        for k, v in res["checks"].items():
            print(f"  {'✅' if v.get('ok') else '❌'} {k}")
        print(f"\n  {res['summary']['passed']}/{res['summary']['checks']} 项通过，"
              f"漂移项 {res['summary']['drift_items']}")
        if res["drift"]:
            print("\n  ── 漂移明细")
            for d in res["drift"]:
                print(f"    [{d['check']}] {d['what']}")
                det = d.get("detail")
                print(f"          detail: {json.dumps(det, ensure_ascii=False)[:200]}")
                print(f"          修法  : {d.get('fix')}")
        else:
            print("\n  ✅ 视图与权威库一致（六项全过）")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
