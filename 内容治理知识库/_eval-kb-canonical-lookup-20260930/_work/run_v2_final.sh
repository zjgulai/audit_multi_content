#!/bin/bash
# v1.3.0 修后复测：一键重跑「回填 → 评分 → 产物」全链。
# 用法：bash _work/run_v2_final.sh
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
PY=/usr/bin/python3
export KB_INTERP_OK=1
EVAL=~/.dsh/skills/root-skills-eval/scripts

echo "===== 1/8 回填三轮（口径无关，含追问原文） ====="
for r in 1 2 3; do
  $PY collect_v2.py --map v2/map_r$r.json --round $r --cases cases_a.json --out v2/round$r.json | head -1
done

echo "===== 2/8 score-input + 评分（口径 A / B，两侧同尺） ====="
for c in A B; do
  $PY make_results_v2.py --rounds v2/round1.json v2/round2.json v2/round3.json \
      --cases cases_a.json --out v2/score-input-$c.json --conv $c --dump v2/detail-$c.json >/dev/null
  $PY $EVAL/score-trigger-eval.py v2/score-input-$c.json --json v2/summary-$c.json >/dev/null
  $PY - <<EOF
import json
s=json.load(open("v2/summary-$c.json",encoding="utf-8"))
print("口径 $c:", [(r["TP"],r["FP"],r["FN"],r["TN"],r["precision"],r["f1"]) for r in s["per_round"]])
print("   avg:",s["average"],"flaky:",s["flaky"],"call:",s["call_tag"]["passed"],"/",s["call_tag"]["judged"])
EOF
done

echo "===== 3/8 v1.2.0 基线重算（口径 A / B） ====="
for c in A B; do
  $PY make_results_v2.py --rounds v2/recheck_v12_r1.json v2/recheck_v12_r2.json v2/recheck_v12_r3.json \
      --cases cases_a.json --out v2/base12/score-input-$c.json --conv $c --dump v2/base12/detail-$c.json >/dev/null
  $PY $EVAL/score-trigger-eval.py v2/base12/score-input-$c.json --json v2/base12/summary-$c.json >/dev/null
  $PY - <<EOF
import json
s=json.load(open("v2/base12/summary-$c.json",encoding="utf-8"))
print("基线口径 $c:", s["average"], "flaky:", s["flaky"])
EOF
done

echo "===== 4/8 results.json（原文回复）+ Excel 回填 ====="
$PY make_results_full_v2.py --rounds v2/round1.json v2/round2.json v2/round3.json \
    --cases cases_a.json --out v2/results.json --xlsx "$ROOT/kb-canonical-lookup.xlsx"

echo "===== 5/8 测试用例 HTML ====="
$PY $EVAL/build-testcases-html.py --name kb-canonical-lookup --results v2/results.json \
    --output "$ROOT/kb-canonical-lookup-test-cases.html"
$PY $EVAL/build-testcases-html.py --name kb-canonical-lookup --results v2/results.json \
    --output /tmp/_tc_check.html --check-only

echo "===== 6/8 评测过程 HTML ====="
$PY build_process_html_v2.py --out "$ROOT/kb-canonical-lookup-evaluation-process.html" \
    --note "$(cat v2/source_writes_note.txt)"

echo "===== 7/8 评测 YAML ====="
$PY make_yaml_v2.py

echo "===== 8/8 最终报告 HTML（多版本合并，含修前/修后对比） ====="
$PY $EVAL/build-final-report.py --name kb-canonical-lookup \
    --version "源 v1.2.0" --yaml "$ROOT/kb-canonical-lookup-evaluation-report-v1.2.0-baseline.yaml" \
    --note "修前基线：轨道 A 92.0；A 卷口径 A F1=0.616（P=0.445 R=1.000）；轨道 C 66.9（D）；调用门槛未过；轨道 A 有 2 条 error" \
    --version "修复后 v1.3.0（最终）" --yaml "$ROOT/kb-canonical-lookup-evaluation-report.yaml" \
    --note "修后：轨道 A 93.3（error 清零）；A 卷口径 A F1=0.586 / 口径 B F1=0.658；边界追问 9/9（修前 3/9）；调用门槛仍未过" \
    --cases "$ROOT/kb-canonical-lookup-test-cases.html" \
    --process "$ROOT/kb-canonical-lookup-evaluation-process.html" \
    --output "$ROOT/kb-canonical-lookup-final-report.html"

echo "===== done ====="
ls -la "$ROOT"
