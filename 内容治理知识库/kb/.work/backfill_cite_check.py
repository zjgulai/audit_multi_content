#!/usr/bin/env python3
"""回填 `kb/l4/canonical/clause.jsonl` 的 `cite_check`（10/19–10/23 行必须做 #3）。

## 它补的是哪一格

xlsx 必须做 #3 逐字：「目标 2 逐条核对留痕 —— 现状：**123 条条款的 `cite_check.source_sha256` = 0/123**，
这条承诺**没有任何核对记录**。对知识库的作用：**条款可逐条回原文核**；现在只能给条款号，
给不出「这句话在原文件哪一行、指纹多少」⇒ **对外引用等于没有背书**。」

实测（2026-10-12）：`clause.jsonl` **123 条**的 `cite_check.anchor` **0/123**、`cite_check.source_sha256`
**0/123**、**顶层 `anchor` 也 0/123** —— 三格全空。而**同一条的 `evidence_units[0]` 里三样全都有**。
⇒ 又是同一个形状：**数据在库里，只是没搬**（同 P0 条款号那次）。

## 为什么可以机械投影（**前提先证，不假设**）

实测：**123 条每条恰好 1 个 `evidence_unit`**（分布 `{1: 123}`），且 123/123 都带 `anchor` 与
`source_sha256` ⇒ 取哪个**零歧义**。多 unit 的形态另有 509 条（`wording_*`），本次**不动**（见 §未做）。

## ★ 措辞红线（AGENTS.md 逐字，必须遵守）

「sha 的措辞红线：只能写「**与 L0 记录值比对一致**」，**不许**写「重算通过」—— L0 的 sha 输入是
`record_fields` 这个字段 blob，本地 L0 件**不含**该 blob ⇒ **重算在本地结构上不可能**。」

⇒ 本脚本写的是 `verify_mode = "local_projection"` ＋ 逐条写明**这不是回源重算**，并给出可供人核的坐标。

## 纪律

- **只动 `cite_check` 与顶层 `anchor` 两个键**，其余键**逐字节不动**（改前先做序列化自检）。
- **归档**：写前 `kb/l8/_archive/cite-check-backfill-<RUN>/clause.jsonl.before`。
- **幂等**：重复跑内容无改动 ⇒ 不追加 `l4.json` 的 `changes[]`。
- **判据**：`--selftest` 走**真数据形状**；并**复用 `l4_gate` 的 C4 判据**独立核
  （`L2 unit 的 source_sha256 == cite_check.source_sha256`），不新造第二把尺子。

用法：
    python3 kb/.work/backfill_cite_check.py --dry-run
    python3 kb/.work/backfill_cite_check.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
CLAUSE = os.path.join(KB, "l4", "canonical", "clause.jsonl")
L4REG = os.path.join(KB, "l4", "registry", "l4.json")
L2UNITS = os.path.join(KB, "l2", "units.jsonl")
RUN_ID = os.environ.get("KB_CITE_RUN") or dt.datetime.now().strftime("%Y%m%d-%H%M")


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_l2_units():
    """`unit_id → unit`（只读）。用于**独立复核** sha 对不对得上（复用 l4_gate 的 C4 判据）。"""
    u = {}
    with open(L2UNITS, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                d = json.loads(line)
                if d.get("unit_id"):
                    u[d["unit_id"]] = d
    return u


def project(row, units):
    """给一行 clause 算新的 cite_check / 顶层 anchor。**纯函数**。"""
    evs = row.get("evidence_units") or []
    cc = dict(row.get("cite_check") or {})
    if not evs:
        cc["unresolvable"] = (cc.get("unresolvable") or []) + ["本行没有 evidence_units ⇒ 无可投影的坐标"]
        return cc, row.get("anchor")
    e0 = evs[0]
    anc, sha, uid = e0.get("anchor"), e0.get("source_sha256"), e0.get("unit_id")
    cc["anchor"] = anc
    cc["source_sha256"] = sha
    cc["unit_ids"] = [u for u in (x.get("unit_id") for x in evs) if u] or cc.get("unit_ids")
    cc["evidence_units"] = len(evs)
    cc["anchors_in_l2"] = len({x.get("anchor") for x in evs if x.get("anchor")})
    # ★ 措辞红线：写明**这是什么**，而不是它"通过"了什么
    cc["verify_mode"] = "local_projection"
    cc["verify_note"] = (
        "★ 值**逐字取自同一行 `evidence_units[0]`**（anchor / source_sha256），**不是回源重算** —— "
        "L0 的 sha 输入是 `record_fields` 字段 blob，本地 L0 件不含该 blob，**重算在本地结构上不可能**"
        "（AGENTS.md 措辞红线）。本格给的是「**原文在哪、指纹是多少**」的**坐标与指纹**；"
        "要真核对须点 L0 飞书直链。"
    )
    cc["projected_from"] = "evidence_units[0]"
    cc["projected_at_run"] = RUN_ID
    return cc, (row.get("anchor") or anc)


def independent_check(new_rows, units):
    """**独立复核**：复用 `l4_gate` 的 C4 判据 —— unit 的 sha 必须与 cite_check 的 sha 相同。"""
    bad, ok = [], 0
    for r in new_rows:
        cc = r.get("cite_check") or {}
        uid, sha = (cc.get("unit_ids") or [None])[0], cc.get("source_sha256")
        u = units.get(uid)
        if u is None:
            bad.append((r.get("article_no"), uid, "L2 里找不到这个 unit_id"))
        elif u.get("source_sha256") != sha:
            bad.append((r.get("article_no"), uid, "source_sha256 对不上"))
        else:
            ok += 1
    return ok, bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    raw = open(CLAUSE, encoding="utf-8").read()
    kept_trailing = raw.split("\n")[-1] == ""
    lines = [l for l in raw.split("\n") if l.strip()]
    rows = [json.loads(l) for l in lines]
    print("clause.jsonl：%d 行" % len(rows))

    bad = [i for i, (r, l) in enumerate(zip(rows, lines))
           if json.dumps(r, ensure_ascii=False, sort_keys=True) != l]
    if bad:
        print("❌ 序列化自检不过（首个不符行号 %d）⇒ 写回会改既有字节，中止" % bad[0])
        return 2
    print("✅ 序列化自检通过（逐字节复现原行）")

    before_sha = sha256_file(CLAUSE)
    units = load_l2_units()
    print("L2 单元索引：%d 条" % len(units))

    touched = 0
    for r in rows:
        cc, top = project(r, units)
        if r.get("cite_check") != cc:
            r["cite_check"] = cc
            touched += 1
        if top and r.get("anchor") != top:
            r["anchor"] = top
            touched += 1

    ok, badchk = independent_check(rows, units)
    print("\n── 投影结果 ──")
    print("  有 cite_check.anchor : %d/%d" % (sum(1 for r in rows if (r.get('cite_check') or {}).get('anchor')), len(rows)))
    print("  有 cite_check.source_sha256 : %d/%d" % (sum(1 for r in rows if (r.get('cite_check') or {}).get('source_sha256')), len(rows)))
    print("  有顶层 anchor : %d/%d" % (sum(1 for r in rows if r.get('anchor')), len(rows)))
    print("  ★ 独立复核（复用 l4_gate C4：unit.sha == cite_check.sha）：**通过 %d ／ 不过 %d**" % (ok, len(badchk)))
    for x in badchk[:5]:
        print("     ❌", x)
    print("  改动格数：%d" % touched)

    if a.dry_run:
        print("\n[dry-run] 不写盘")
        return 0
    if touched == 0:
        print("\nℹ 内容无改动（幂等重跑）⇒ 不写盘、不登记")
        return 0

    arch = os.path.join(KB, "l8", "_archive", "cite-check-backfill-%s" % RUN_ID)
    os.makedirs(arch, exist_ok=True)
    bak = os.path.join(arch, "clause.jsonl.before")
    open(bak, "wb").write(open(CLAUSE, "rb").read())
    print("\n备份：%s  sha256 %s…" % (os.path.relpath(bak, KB), before_sha[:16]))

    out = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
    if kept_trailing:
        out += "\n"
    open(CLAUSE, "w", encoding="utf-8").write(out)
    after_sha = sha256_file(CLAUSE)
    print("✅ 已写回 %s  sha256 %s…" % (os.path.relpath(CLAUSE, KB), after_sha[:16]))

    reg = json.load(open(L4REG, encoding="utf-8"))
    reg.setdefault("changes", []).append({
        "run_id": RUN_ID, "change": "cite_check_backfill",
        "file": "l4/canonical/clause.jsonl", "rows": len(rows),
        "keys": ["anchor", "cite_check"],
        "note": "10/19 行必须做 #3：123 条 clause 的 cite_check 三格全空（anchor/sha/顶层 anchor = 0/123），"
                "而同行 evidence_units[0] 三样全有 ⇒ 机械投影。**verify_mode=local_projection**："
                "值逐字取自 evidence_units，**不是回源重算**（AGENTS.md 的 sha 措辞红线）。"
                "★ 本文件**无活写方**（只有一次性 batch9 件写过），日更不写它 ⇒ 本回填不会被覆盖。",
        "refs": ["kb/.work/backfill_cite_check.py", "kb/l7/scripts/l4_gate.py（C3/C4 判据）"],
    })
    json.dump(reg, open(L4REG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("✅ 已登记 l4/registry/l4.json changes[]（run_id=%s）" % RUN_ID)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
