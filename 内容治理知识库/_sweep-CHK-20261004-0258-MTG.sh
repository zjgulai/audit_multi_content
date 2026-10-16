#!/bin/sh
# kb-check 体检档：六道闸门一次性扫，逐条记 时间戳 + 退出码（只报不改）
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 9
RUN=CHK-20261004-0258-MTG
OUT=_chk-run-$RUN
mkdir -p "$OUT"
SUM="$OUT/00-summary.tsv"
: > "$SUM"

run() {
  label="$1"; shift
  f="$OUT/$label.txt"
  t0=$(date '+%Y-%m-%d %H:%M:%S')
  "$@" > "$f" 2>&1
  ec=$?
  t1=$(date '+%Y-%m-%d %H:%M:%S')
  printf '%s\t%s\t%s\t%s\n' "$label" "$ec" "$t0" "$t1" >> "$SUM"
  echo "[$label] exit=$ec  $t0 -> $t1"
}

run 01-skills_check      sh kb/kbpy l7/scripts/skills_check.py
run 02-layers_check      sh kb/kbpy l7/scripts/layers_check.py
run 03-routes-strict     sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_after_r4.winners.txt
run 03b-routes-alias     sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_after_r4.winners.txt --alias
run 05a-envelope_gate    python3 tools/envelope_gate.py
run 05b-envelope_census  sh kb/kbpy l8/envelope_census.py
run 06-projection        sh kb/kbpy l8/projection_reconcile.py
run 04-workflow          sh kb/kbpy l8/workflow_check.py "$RUN"

echo "=== SUMMARY ==="
cat "$SUM"
