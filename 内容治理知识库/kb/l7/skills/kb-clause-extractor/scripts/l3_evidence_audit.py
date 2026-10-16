#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l3_evidence_audit.py — L3 证据回指只读抽检（红线③ / A1 的轻量自测）。

做一件事：从候选里抽样 `evidence_units[]`，逐条核它能不能回指到 L2 单元：

    unit_id 存在？ source_sha256 与 L2 单元一致？ anchor 非空？

只读：不写库、不改候选、不动台账。全量核验仍以 `kb/l7/scripts/l3_gate.py` 为准；
本脚本用于跑批后快速定位「哪几条悬空」，以及在没有闸门的环境里做抽检。

退出码：0=抽样全过；3=发现悬空；1=用法/输入错误。

用法：
  python3 l3_evidence_audit.py --kb-root ~/.dsh/Momcozy知识库 --sample 50
  python3 l3_evidence_audit.py --rules <rules.jsonl> --units <units.jsonl> --sample 0 --json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield ln, json.loads(line)
            except json.JSONDecodeError as exc:
                yield ln, {"__bad_json__": str(exc)}


def load_units(units: Path) -> dict:
    idx = {}
    for _, obj in iter_jsonl(units):
        uid = obj.get("unit_id")
        if uid:
            idx[uid] = obj
    return idx


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="l3_evidence_audit.py",
        description="L3 候选的 evidence_units 回指抽检（只读）。")
    ap.add_argument("--kb-root", default=None,
                    help="知识库根目录（kb/ 的上一级）；给了就按默认路径找 rules.jsonl / units.jsonl")
    ap.add_argument("--rules", default=None, help="候选文件（默认 <kb-root>/kb/l3/candidates/rules.jsonl）")
    ap.add_argument("--units", default=None, help="L2 单元文件（默认 <kb-root>/kb/l2/units.jsonl）")
    ap.add_argument("--sample", type=int, default=50, help="抽样条数；0 表示全量（默认 50）")
    ap.add_argument("--seed", type=int, default=20260930, help="抽样随机种子（默认固定，便于复现）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    if args.sample < 0:
        print("[error] --sample 不能为负", file=sys.stderr)
        return 1
    if not args.kb_root and not (args.rules and args.units):
        print("[error] 需要 --kb-root，或同时给 --rules 与 --units", file=sys.stderr)
        return 1

    root = Path(args.kb_root).expanduser() if args.kb_root else None
    rules = Path(args.rules).expanduser() if args.rules else root / "kb" / "l3" / "candidates" / "rules.jsonl"
    units = Path(args.units).expanduser() if args.units else root / "kb" / "l2" / "units.jsonl"
    for p in (rules, units):
        if not p.is_file():
            print(f"[error] 文件不存在: {p}", file=sys.stderr)
            return 1

    idx = load_units(units)
    refs = []
    for ln, obj in iter_jsonl(rules):
        if "__bad_json__" in obj:
            refs.append({"rule_line": ln, "bad": obj["__bad_json__"]})
            continue
        for ev in (obj.get("evidence_units") or []):
            refs.append({
                "rule_id": obj.get("rule_id"),
                "rule_line": ln,
                "unit_id": ev.get("unit_id"),
                "source_sha256": ev.get("source_sha256"),
                "anchor": ev.get("anchor"),
            })

    if not refs:
        print("[warn] 候选里没有 evidence_units 可核（要么候选为空，要么结构不同）", file=sys.stderr)
        return 1

    picked = refs if args.sample == 0 or args.sample >= len(refs) else \
        random.Random(args.seed).sample(refs, args.sample)

    bad = []
    for r in picked:
        if r.get("bad"):
            bad.append({**r, "why": "候选行不是合法 JSON"})
            continue
        u = idx.get(r["unit_id"])
        if r["unit_id"] is None:
            bad.append({**r, "why": "缺 unit_id（悬空引用）"})
        elif u is None:
            bad.append({**r, "why": "unit_id 在 L2 里不存在（单元被重切或跨库引用）"})
        elif r.get("source_sha256") and u.get("source_sha256") \
                and r["source_sha256"] != u["source_sha256"]:
            bad.append({**r, "why": "source_sha256 与 L2 单元不一致（源被改写）"})
        elif not (r.get("anchor") or u.get("anchor")):
            bad.append({**r, "why": "anchor 缺失（回指不到原文位置）"})

    out = {"rules": str(rules), "units": str(units), "units_indexed": len(idx),
           "refs_total": len(refs), "sampled": len(picked), "bad": len(bad),
           "pass_rate": round((len(picked) - len(bad)) / len(picked), 4) if picked else 0.0,
           "samples_of_failure": bad[:20]}

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"== L3 证据回指抽检 ==")
        print(f"  候选引用 {len(refs)} 条，抽样 {len(picked)} 条，L2 索引 {len(idx)} 单元")
        print(f"  不通过 {len(bad)} 条，抽样通过率 {out['pass_rate']:.2%}")
        for b in bad[:10]:
            print(f"   - rule={b.get('rule_id')} unit={b.get('unit_id')} :: {b['why']}")
        print("\n  说明：抽检不是闸门。全量核验以 `kb/kbpy l7/scripts/l3_gate.py` 退出 0 为准。")
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
