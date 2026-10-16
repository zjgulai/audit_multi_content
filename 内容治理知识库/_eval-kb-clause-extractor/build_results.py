#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三轮盲测产出 → results.json（score-trigger-eval.py 输入格式）。

结论取值：触发 / 不触发 / 追问（调用场景：加载 / 未加载）。
- 四类主类型：route 命中 kb-clause-extractor → 触发，否则不触发。
- 调用：命中 → 加载；命中别的 skill 或 NONE → 未加载（主语是本 Skill）。
- 边界：先按 route 判，再用 verdicts_manual.json 里的人工复核覆盖为「追问」。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "kb-clause-extractor"


def main(tag="source"):
    A = json.loads((HERE / "cases_a.json").read_text(encoding="utf-8"))
    meta = {c["id"]: c for c in A["cases"] + A["call_cases"]}
    rounds = {n: json.loads((HERE / f"parsed_round{n}.json").read_text(encoding="utf-8"))
              for n in (1, 2, 3)}
    man_file = HERE / "verdicts_manual.json"
    manual = json.loads(man_file.read_text(encoding="utf-8")) if man_file.exists() else {}

    out = {"skill_name": NAME, "results": [], "replies": {}}
    for cid in sorted(meta):
        c = meta[cid]
        if c["type"] == "调用":
            r = []
            for n in (1, 2, 3):
                d = rounds[n].get(str(cid))
                if not d:
                    r.append("")
                    continue
                r.append("加载" if d["triggered"] else "未加载")
        else:
            r = []
            for n in (1, 2, 3):
                d = rounds[n].get(str(cid))
                if not d:
                    r.append("")
                    continue
                v = "触发" if d["triggered"] else "不触发"
                ov = manual.get(f"{cid}:{n}")
                if ov:
                    v = ov
                r.append(v)
        out["results"].append({
            "id": cid, "type": c["type"], "expected": c["expected"],
            "tags": c["tags"], "title": c["title"], "priority": c["priority"],
            "rounds": r,
        })
        out["replies"][str(cid)] = {
            "prompt": c["prompt"],
            "routes": [rounds[n].get(str(cid), {}).get("route", "") for n in (1, 2, 3)],
            "replies": [rounds[n].get(str(cid), {}).get("reply", "") for n in (1, 2, 3)],
            "conclusions": r,
        }
    p = HERE / f"results_{tag}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n_empty = sum(1 for v in out["replies"].values() for x in v["replies"] if not x.strip())
    print(f"[ok] {p.name}：{len(out['results'])} 条；空回复 {n_empty} 处")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "source")
