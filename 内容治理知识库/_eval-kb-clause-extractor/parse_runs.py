#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析盲测产出：runs/roundN/rN_pNN.txt → 每轮每条的 route / 结论 / 回复原文。

- 只把「提示词」原文发给被测会话；ROUTE 行是 harness 级插桩，单独取用，不写进回复原文。
- 结论判定：route 命中 kb-clause-extractor → 触发；否则不触发。
- 编号纠偏：投递清单用【消息 N】编号，若被测会话改写成了 CASE 1..n，则按位置重映射回
  分片 index.json 里的消息编号（并在日志里留痕），避免串位。
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def parse_file(p: Path):
    txt = p.read_text(encoding="utf-8")
    parts = re.split(r"^===CASE (\d+)===\s*$", txt, flags=re.M)
    out = {}
    for i in range(1, len(parts), 2):
        cid = int(parts[i])
        body = parts[i + 1]
        m = re.search(r"^===ROUTE %d:\s*(.*?)\s*=*\s*$" % cid, body, re.M)
        route = m.group(1).strip() if m else ""
        if m:
            body = body[:m.start()] + body[m.end():]
        m2 = re.search(r"^===ROUTE %d:\s*(.*?)\s*=*\s*$" % cid, body, re.M)
        if m2:
            route = m2.group(1).strip()
            body = body[:m2.start()] + body[m2.end():]
        body = re.sub(r"^===\s*$", "", body, flags=re.M).strip()
        out[cid] = {"route": route, "reply": body}
    return out


def norm(route: str, name="kb-clause-extractor"):
    r = (route or "").strip().upper()
    if r == "NONE":
        return False
    return name in (route or "")


def main(round_no, runs_root="/tmp/kbce_out", out_dir=None):
    runs_root = Path(runs_root)
    out_dir = Path(out_dir) if out_dir else HERE
    index = json.loads((HERE / "shard_index.json").read_text(encoding="utf-8"))
    d = runs_root / f"round{round_no}"
    files = sorted(d.glob(f"r{round_no}_p*.txt"))
    merged, remaps = {}, []
    for f in files:
        key = f.name.split("_", 1)[1].split(".")[0]          # p03
        shard = "shard_" + key[1:]
        expect = index.get(shard, [])
        got = parse_file(f)
        ids = sorted(got)
        if ids != sorted(expect):
            if ids == list(range(1, len(expect) + 1)):
                got = {expect[i - 1]: got[i] for i in ids}
                remaps.append(f"{f.name}: CASE 1..{len(ids)} → 消息 {expect[0]}..{expect[-1]}")
            else:
                print(f"  [warn] {f.name} 编号既不匹配也不连续: got={ids[:6]}... expect={expect[:6]}...")
        for cid, v in got.items():
            if cid in merged:
                print(f"  [warn] 重复 id {cid}: {f.name}")
            merged[cid] = v
        print(f"  {f.name}: {len(got)} 条")
    missing = sorted(set(range(1, 104)) - set(merged))
    print(f"[round{round_no}] 解析 {len(merged)} 条，缺 {missing}")
    for r in remaps:
        print(f"  [编号纠偏] {r}")
    out = {}
    for cid, v in sorted(merged.items()):
        out[str(cid)] = {
            "route": v["route"],
            "triggered": norm(v["route"]),
            "head": re.sub(r"\s+", " ", v["reply"])[:140],
            "reply": v["reply"],
        }
    p = out_dir / f"parsed_round{round_no}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] {p}")
    return out


if __name__ == "__main__":
    main(int(sys.argv[1]), *(sys.argv[2:4] if len(sys.argv) > 3 else []))
