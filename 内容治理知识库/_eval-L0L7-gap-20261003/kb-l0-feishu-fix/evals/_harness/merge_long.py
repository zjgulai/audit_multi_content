#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「长尾补跑」（`a-round-N.long.jsonl`，timeout=1500s）并回正式归档。

与 `merge_rerun.py` 同一套纪律，差别只有一个：**只在补跑版确实拿到了回复、
而现版本为空时**才替换 —— 长尾这一轮的唯一目的就是"把空回复填上"，
若它反而给出更差的结果（空回复 / 更短），**不替换**并留痕。

用法：python3 merge_long.py [--dry-run]
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = [f"a-round-{n}{s}.jsonl" for n in (1, 2, 3) for s in ("", "b")]


def read_rows(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def long_of(tag):
    out = {}
    for p in glob.glob(os.path.join(HERE, f"a-round-{tag}.long.jsonl")):
        for r in read_rows(p):
            out[int(r["n"])] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    changed, skipped = [], []
    for f in FILES:
        body = f[len("a-round-"):-len(".jsonl")]
        is_b = body.endswith("b")
        tag = body[:-1] if is_b else body
        lo, hi = (53, 104) if is_b else (1, 52)
        lg = long_of(tag)
        if not lg:
            continue
        rows = read_rows(os.path.join(HERE, f))
        new, hit = [], set()
        for r in rows:
            n = int(r["n"])
            if lo <= n <= hi and n in lg and n not in hit:
                old_has = bool((r.get("reply") or "").strip())
                new_r = lg[n]
                new_has = bool((new_r.get("reply") or "").strip())
                if (not old_has) and new_has:
                    hit.add(n)
                    changed.append({"file": f, "n": n,
                                    "reply_chars": len(new_r.get("reply") or ""),
                                    "triggered_before": bool(r.get("skill_loaded")),
                                    "triggered_after": bool(new_r.get("skill_loaded"))})
                    new.append(new_r)
                    continue
                skipped.append({"file": f, "n": n,
                                "why": "补跑仍空" if not new_has else "原记录已有回复（不覆盖）"})
            new.append(r)
        if not a.dry_run:
            dst = os.path.join(HERE, f)
            tmp = dst + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                for r in new:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(tmp, dst)

    print(f"替换 {len(changed)} 条；不替换 {len(skipped)} 条")
    for c in changed:
        print(f"  {c['file']} n={c['n']:<4} 补上 {c['reply_chars']:>5} 字  "
              f"loaded {c['triggered_before']}→{c['triggered_after']}")
    for s in skipped:
        print(f"  [skip] {s['file']} n={s['n']} —— {s['why']}")
    trig = [c for c in changed if c["triggered_before"] != c["triggered_after"]]
    print(f"触发结论变化：{len(trig)} 条")
    json.dump({"changed": changed, "skipped": skipped,
               "trigger_flips": trig},
              open(os.path.join(HERE, "merge-long-report.json"), "w"),
              ensure_ascii=False, indent=1)
    if a.dry_run:
        print("[dry-run] 未写盘")
    return 0


if __name__ == "__main__":
    sys.exit(main())
