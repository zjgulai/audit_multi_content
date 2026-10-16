#!/bin/sh
# kb-check §1 体检档 —— 六道统一闸门（+新鲜度前置），逐条落退出码
# cwd = 库根；只报不改；④ 无干跑档会写 kb/l8/（用户点名要跑）
D="$1"; RUN="$2"
cd "$(dirname "$0")/.." || exit 9
run() { # name, cmd...
  n="$1"; shift
  { printf '%s\n' "### $n"; printf 'CMD: %s\n' "$*"; } > "$D/$n.cmd"
  "$@" > "$D/$n.out" 2>&1
  echo $? > "$D/$n.exit"
  printf '%-14s exit=%s\n' "$n" "$(cat "$D/$n.exit")"
}
run 00-freshness   sh kb/kbpy l7/scripts/freshness.py
run 01-skills      sh kb/kbpy l7/scripts/skills_check.py
run 02-layers      sh kb/kbpy l7/scripts/layers_check.py
run 03-routes      sh kb/kbpy l7/scripts/routes_reconcile.py "kb/l7/reports/$RUN-routes-winners.json"
run 04-workflow    sh kb/kbpy l8/workflow_check.py "$RUN"
run 05a-envgate    python3 tools/envelope_gate.py
run 05b-envcensus  sh kb/kbpy l8/envelope_census.py
run 06-projection  sh kb/kbpy l8/projection_reconcile.py
