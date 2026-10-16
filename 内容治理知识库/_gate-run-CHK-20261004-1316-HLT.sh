#!/bin/sh
# kb-check 体检档 · 六道闸门一次性跑（只报不改）
# 唯一写盘：门④ workflow_check.py 写 kb/l8/workflow_check_<RUN>.json（无干跑档，已声明）
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 9
RUN=CHK-20261004-1316-HLT
D="kb/.work/kbcheck-$RUN"
mkdir -p "$D"
echo "RUN=$RUN"; date "+start %F %T"
echo "=== 并发写入者快照（开始）==="
ps -eo pid,etime,command | grep -E "kbpy|kb_pipeline|workflow_check|projection_reconcile|skills_check|envelope" | grep -v grep > "$D/00-ps-before.txt"
cat "$D/00-ps-before.txt"
# 有界等待：避开别的会话正在跑的 workflow_check（同门④，避免读到移动靶）
w=0
while [ "$w" -lt 180 ]; do
  if ! pgrep -f "kb/l8/workflow_check.py" >/dev/null 2>&1; then break; fi
  sleep 5; w=$((w+5))
done
printf 'pre-wait for concurrent workflow_check: %ss\n' "$w" | tee "$D/00-prewait.txt"
if pgrep -f "kb/l8/workflow_check.py" >/dev/null 2>&1; then
  printf 'WARN 仍有并发 workflow_check 在跑 —— 本轮为带重叠跑，结论按移动靶读\n' | tee -a "$D/00-prewait.txt"
fi

printf 'index.jsonl bytes before: %s\n' "$(wc -c < kb/l7/runs/index.jsonl 2>/dev/null)" | tee "$D/00-index-before.txt"
printf 'runfiles before: %s\n' "$(ls kb/l7/runs/ 2>/dev/null | wc -l)" >> "$D/00-index-before.txt"

: > "$D/00-exits.txt"
run() {
  name="$1"; shift
  s=$(date +%s)
  "$@" > "$D/$name.out" 2>&1
  ec=$?
  e=$(date +%s)
  printf '%s exit=%s secs=%s\n' "$name" "$ec" "$((e-s))" | tee -a "$D/00-exits.txt"
}

run 01-skills_check sh kb/kbpy l7/scripts/skills_check.py
run 02-layers_check sh kb/kbpy l7/scripts/layers_check.py
run 03a-routes-noarg sh kb/kbpy l7/scripts/routes_reconcile.py
run 03b-routes-stale sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt
printf '%s\n' '--- 门④ 声明：无干跑档，将写 kb/l8/workflow_check_'"$RUN"'.json ---' | tee -a "$D/00-exits.txt"
run 04-workflow_check sh kb/kbpy l8/workflow_check.py "$RUN"
run 05a-envelope_gate python3 tools/envelope_gate.py
run 05b-envelope_census sh kb/kbpy l8/envelope_census.py
run 06-projection_reconcile sh kb/kbpy l8/projection_reconcile.py

printf 'index.jsonl bytes after: %s\n' "$(wc -c < kb/l7/runs/index.jsonl 2>/dev/null)" | tee "$D/00-index-after.txt"
printf 'runfiles after: %s\n' "$(ls kb/l7/runs/ 2>/dev/null | wc -l)" >> "$D/00-index-after.txt"
echo "=== 并发写入者快照（结束）==="
ps -eo pid,etime,command | grep -E "kbpy|kb_pipeline|workflow_check|projection_reconcile|skills_check|envelope" | grep -v grep > "$D/09-ps-after.txt"
cat "$D/09-ps-after.txt"
date "+end %F %T"
echo "OUTDIR=$D"
