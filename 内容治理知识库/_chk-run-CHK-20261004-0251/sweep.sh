#!/bin/bash
# kb-check 体检档 · 六道闸门 + 附两把
RUN="$1"; OUT="$2"
W=_eval-kb-manage/blind_after_r4.winners.txt
: > "$OUT/00-exitcodes.txt"

run() { # run <tag> <cmd...>
  local tag="$1"; shift
  echo "===== $tag :: $* =====" >> "$OUT/00-exitcodes.txt"
  "$@" > "$OUT/$tag.out" 2>&1
  local rc=$?
  echo "exit=$rc" >> "$OUT/00-exitcodes.txt"
  echo "[$tag] exit=$rc"
  return $rc
}

run 01-skills_check          sh kb/kbpy l7/scripts/skills_check.py
run 02-layers_check          sh kb/kbpy l7/scripts/layers_check.py
run 03a-routes-noinput       sh kb/kbpy l7/scripts/routes_reconcile.py
run 03b-routes-strict        sh kb/kbpy l7/scripts/routes_reconcile.py "$W"
run 03c-routes-alias         sh kb/kbpy l7/scripts/routes_reconcile.py "$W" --alias
run 04-workflow_check        sh kb/kbpy l8/workflow_check.py "$RUN"
run 05a-envelope_gate        python3 tools/envelope_gate.py
run 05b-envelope_census      sh kb/kbpy l8/envelope_census.py
run 06-projection_reconcile  sh kb/kbpy l8/projection_reconcile.py
run 07-l0-align-check        sh kb/kbpy l8/align_l0_feishu.py --check
run 08-lark-auth-status      ~/.dsh/bin/lark-cli auth status --profile dsh-kb

echo "===== DONE $(date +%H:%M:%S) =====" >> "$OUT/00-exitcodes.txt"
