#!/usr/bin/env python3
"""跑 `kb/l7/registry/regression-set.yaml` 的 100 条回归集，落逐条结果。

## 为什么要有它

`regression-set.yaml` 的 `meta.how_to_use` 写着「改上游前后，各跑一遍这批素材，逐条比对」，
但**库里只有构建器 `kb/l8/build_regression_set.py`，没有跑手**（实测：`grep -rl regression-set`
只命中构建器自己）。本脚本补这一格。

## 判据（照抄 `how_to_use`，一个字不改）

- **solid 层（80 条）：三态必须逐条相同**；不同 ⇒ **回归**，不许放行。
- **fragile 层（20 条）：允许从「拒答」变成三态中任一**，但**必须逐条说明为什么**。

## 纪律

- **只读**：`--no-publish-to-feishu`（不发飞书）、不传 `--write-report`（不落报告）、
  不传 `--require-layer-preflight`（回归跑不是真实送审，走 `--allow-no-*` 显式声明豁免，
  **不静默**）。依据缓存落在 `kb/.work/` 下的临时件。
- 每条都记 `p_level / risk_level / severity`：`review.py` 的严重度判据读的是
  **L3 规则行的 `risk_level`**，逐条留痕才判得了「改一条判据会影响哪些单」。

## 用法

    sh kb/kbpy .work/run_regression_set.py --out kb/.work/regression-<tag>.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
import sys
import time

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
SET = os.path.join(KB, "l7", "registry", "regression-set.yaml")
ENGINE = os.path.join(KB, "l7", "review-engine", "core", "with_kb_evidence.py")
CACHE = os.path.join(KB, ".work", "_regress_findings_cache.json")


def _decode(raw: str):
    d, dec = None, json.JSONDecoder()
    for cand in (raw,) + tuple(raw[k:] for k in range(len(raw)) if raw[k] == "{"):
        try:
            d, _ = dec.raw_decode(cand.lstrip())
            break
        except Exception:
            continue
    return d


def run_case(case: dict) -> dict:
    t0 = time.time()
    cmd = [sys.executable, ENGINE, "--text", case["text"], "--json",
           "--no-publish-to-feishu",
           "--allow-no-layer-preflight", "--allow-no-decision-owner",
           "--findings-out", CACHE]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=ROOT)
        out = _decode(r.stdout or "")
    except Exception as e:                                   # noqa: BLE001
        return {"case_id": case["case_id"], "expected": case.get("expected"),
                "got": None, "error": "%s: %s" % (type(e).__name__, e),
                "elapsed_s": round(time.time() - t0, 1), "findings": []}

    dec = (out or {}).get("decision") or {}
    # ★ 取值口径照 `kb/l8/review_run.sh`（同一处，不另造）：
    #   引擎顶层是 `{decision:{...}, evidence_meta:{...}}`，而**状态在 `decision.decision`**，
    #   `decision.state` 是 None（实测踩过：跑手第一版只读 `.state` ⇒ 100 条全判 None）。
    state = dec.get("state") or dec.get("decision") or (out or {}).get("state") or (out or {}).get("decision")
    if state in ("NEEDS_INPUT", None):
        state = "拒答" if state == "NEEDS_INPUT" else None
    if dec.get("refusal") and state is None:
        state = "拒答"

    findings = []
    try:
        pay = json.load(open(CACHE, encoding="utf-8")).get("payload") or {}
        for f in (pay.get("findings") or []):
            findings.append({
                "rule_id": f.get("rule_id"), "rule_code": f.get("rule_code"),
                "p_level": f.get("p_level"), "risk_level": f.get("risk_level"),
                "severity": f.get("severity"), "category": f.get("category"),
                "sub": f.get("sub"), "article_no": f.get("article_no"),
            })
    except Exception:                                        # noqa: BLE001
        pass

    return {"case_id": case["case_id"], "expected": case.get("expected"),
            "got": state, "issue_count": dec.get("issue_count"),
            "elapsed_s": round(time.time() - t0, 1), "findings": findings,
            "layer": case.get("_layer")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全跑）")
    a = ap.parse_args()

    import yaml
    d = yaml.safe_load(open(SET, encoding="utf-8"))
    cases = []
    for c in d.get("solid") or []:
        cases.append(dict(c, _layer="solid"))
    for c in d.get("fragile") or []:
        cases.append(dict(c, _layer="fragile"))
    if a.limit:
        cases = cases[:a.limit]
    print("回归集：%d 条（solid %d / fragile %d）"
          % (len(cases), sum(1 for c in cases if c["_layer"] == "solid"),
             sum(1 for c in cases if c["_layer"] == "fragile")), flush=True)

    res, t0 = [], time.time()
    for i, c in enumerate(cases, 1):
        r = run_case(c)
        res.append(r)
        raw = open(a.out, "w", encoding="utf-8")
        for x in res:
            raw.write(json.dumps(x, ensure_ascii=False) + "\n")
        raw.close()
        flag = "✅" if r.get("got") == r.get("expected") else "❌"
        print("[%3d/%3d] %-4s %-16s 期望 %-5s 实得 %-5s %s (%.1fs)"
              % (i, len(cases), r.get("layer"), r["case_id"], r["expected"],
                 r.get("got") or "ERR", flag, r["elapsed_s"]), flush=True)

    solid = [r for r in res if r.get("layer") == "solid"]
    frag = [r for r in res if r.get("layer") == "fragile"]
    sm = [r for r in solid if r.get("got") != r.get("expected")]
    print("\n" + "=" * 70)
    print("solid %d 条：一致 %d ／ **不一致 %d**（不一致即回归，不许放行）"
          % (len(solid), len(solid) - len(sm), len(sm)))
    for r in sm:
        print("   ❌ %s 期望 %s 实得 %s" % (r["case_id"], r["expected"], r.get("got")))
    print("fragile %d 条：%s" % (len(frag), dict(collections.Counter(
        "%s→%s" % (r["expected"], r.get("got")) for r in frag).most_common())))
    print("总耗时 %.1f 分钟" % ((time.time() - t0) / 60))
    print("逐条结果：%s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
