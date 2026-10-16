#!/bin/bash
# kb-check 体检档 —— 6 道闸门逐条跑，逐条记退出码
ROOT="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
cd "$ROOT" || exit 9
RUN="$1"
OUT="_chk-run-$RUN"
mkdir -p "$OUT"

run() {
  n="$1"; label="$2"; shift 2
  echo "===== $n $label ====="
  sh kb/kbpy "$@" > "$OUT/$n-$label.out" 2>&1
  rc=$?
  printf '%s\n' "$rc" > "$OUT/$n-$label.exit"
  echo ">>> $n $label  exit=$rc"
}

run 1 skills_check      l7/scripts/skills_check.py
run 2 layers_check      l7/scripts/layers_check.py
run 3 routes_reconcile  l7/scripts/routes_reconcile.py "kb/l7/reports/$RUN-routes-winners.json"
run 5b envelope_census  l8/envelope_census.py
run 6 projection        l8/projection_reconcile.py

echo "===== 5a envelope_gate (python3, 库自带 tools) ====="
python3 tools/envelope_gate.py > "$OUT/5a-envelope_gate.out" 2>&1
rc=$?; printf '%s\n' "$rc" > "$OUT/5a-envelope_gate.exit"; echo ">>> 5a envelope_gate  exit=$rc"

echo "===== 4 workflow_check (RUN=$RUN) ====="
sh kb/kbpy l8/workflow_check.py "$RUN" > "$OUT/4-workflow_check.out" 2>&1
rc=$?; printf '%s\n' "$rc" > "$OUT/4-workflow_check.exit"; echo ">>> 4 workflow_check  exit=$rc"

echo "===== ALL DONE ====="
for f in "$OUT"/*.exit; do printf '%s\t%s\n' "$(cat "$f")" "$(basename "$f" .exit)"; done
