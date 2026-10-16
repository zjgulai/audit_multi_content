#!/bin/sh
# kb-check §1 体检档：六道闸门一次性跑完，逐条记退出码与证据
# RUN = CHK-20261004-0212   只报不改（④ 除外：无干跑档，落 kb/l8/workflow_check_<RUN>.json）
RUN=CHK-20261004-0212
OUT=_chk-run-$RUN
cd "$(dirname "$0")" || exit 9

run_gate () {
  tag=$1; shift
  echo "############ $tag ############"
  echo "CMD: $*"
  "$@" > "$OUT/$tag.out" 2> "$OUT/$tag.err"
  code=$?
  echo "exit=$code" > "$OUT/$tag.exit"
  echo "[$tag exit=$code]"
  echo "--- stdout tail ---"; tail -20 "$OUT/$tag.out"
  echo "--- stderr tail ---"; tail -10 "$OUT/$tag.err"
  echo
}

run_gate 01-skills    sh kb/kbpy l7/scripts/skills_check.py
run_gate 02-layers    sh kb/kbpy l7/scripts/layers_check.py
run_gate 03-routes     sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_after_r4.winners.txt
run_gate 03b-routes-alias sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_after_r4.winners.txt --alias
run_gate 04-workflow  sh kb/kbpy l8/workflow_check.py $RUN
run_gate 05a-envelope python3 tools/envelope_gate.py
run_gate 05b-census   sh kb/kbpy l8/envelope_census.py
run_gate 06-projection sh kb/kbpy l8/projection_reconcile.py

date '+%Y-%m-%d %H:%M:%S' > "$OUT/99-end.txt"
echo "======== 汇总 ========"
for f in "$OUT"/*.exit; do printf '%s = %s\n' "$(basename "$f" .exit)" "$(cat "$f")"; done
