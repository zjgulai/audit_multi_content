#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从评测 YAML **现读**生成 score.json（禁止手工转录）。

为什么要有它：`score.json` 上一版是**手工转录**的（README 原文写"修复评分转录"），
转录必然漂移 —— 本轮已实测到两处（挂载位路径指向不存在的目录、track_c 公式把封顶值当相加结果）。
现读生成后，YAML 与 score.json 不可能再互相矛盾。

用法：python3 make_score_json.py [<yaml路径>]   # 默认取 ../kb-l0-feishu-fix-evaluation-report.yaml
"""
import datetime
import json
import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)


def main():
    yp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        EVAL, "kb-l0-feishu-fix-evaluation-report.yaml")
    d = yaml.safe_load(open(yp, encoding="utf-8"))
    tc, tb, ta, ei = d["track_c"], d["track_b"], d["track_a"], d["eval_info"]
    dims = {k: v["score"] for k, v in tc["dimensions"].items()}
    out = {
        "skill": ei["skill_name"],
        "fix_version": str(ei["version"]),
        "evaluated_at": str(ei.get("evaluated_at")),
        # 封顶后的值（放行判定看这个）
        "composite_100": tc["total"],
        # 封顶前的实算和（六维相加；与 composite_100 不等时**必须两个都印**）
        "composite_100_uncapped": round(sum(dims.values()), 1),
        "cap": tc.get("cap"),
        "grade": tc["grade"],
        "market_ready": tc["market_ready"],
        "track_a_static": ta["total"],
        "track_b": {
            "a_paper_total": tb.get("a_paper_total"),
            "average": tb.get("average"),
            "per_round": tb.get("per_round"),
            "flaky": tb.get("flaky"),
            "flaky_count": len(tb.get("flaky") or []),
            "security_tag": tb.get("security_tag"),
            "combo_tag": tb.get("combo_tag"),
            "call_tag": tb.get("call_tag"),
            "pass_call_gate": tb.get("pass_call_gate"),
            "output_assertions": tb.get("output_assertions"),
            "b_paper_gate": tb.get("b_paper_gate"),
        },
        "track_c_dimensions": dims,
        "gate_result": d.get("status"),
        "recommendation": d.get("recommendation"),
        "generated_from": os.path.relpath(yp, EVAL),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "generator": "make_score_json.py（现读生成，禁手工转录）",
    }
    dst = os.path.join(EVAL, "score.json")
    json.dump(out, open(dst, "w"), ensure_ascii=False, indent=2, default=str)
    print(f"written {dst}")
    print(f"composite_100(封顶后)={out['composite_100']}  "
          f"实算={out['composite_100_uncapped']}  grade={out['grade']}  "
          f"market_ready={out['market_ready']}")
    if abs(out["composite_100"] - out["composite_100_uncapped"]) > 0.05:
        print(f"  ⇒ 已封顶：{out['composite_100_uncapped']} → {out['composite_100']}"
              f"（{out['cap']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
