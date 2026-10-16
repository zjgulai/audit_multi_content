#!/bin/sh
# 零写闸门体检驱动（本脚本自己是被 kb-pipeline skill 的 §4 收口口径驱动的）
# 只用只读档 / 自带 RUN 的产物名，绝不碰 kb/l0..l6 数据。
set -u
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 2
RUN=PIPE-GATE-20261004-0200
OUT="_chk-run-$RUN"
mkdir -p "$OUT"
PAT='kb_pipeline\.py|kb/kbpy|envelope_gate|workflow_check|daily_health|skills_check|layers_check|routes_reconcile|projection_reconcile|envelope_census|l[0-8]_gate'

echo "=== 阶段0 · 等并发会话静默（需连续 30 秒无相关进程；上限 15 分钟）==="
i=0; quiet=0; n=99
while [ "$i" -lt 180 ]; do
  n=$(ps -eo command | grep -E "$PAT" | grep -v grep | wc -l | tr -d ' ')
  if [ "$n" -eq 0 ]; then quiet=$((quiet+1)); else quiet=0; fi
  [ "$quiet" -ge 6 ] && break
  i=$((i+1)); sleep 5
done
echo "阶段0 结束：此刻相关进程数=$n ｜ 连续静默计数=$quiet ｜ 等待轮次=$i"
date

ps -eo pid,ppid,etime,command | grep -E "$PAT" | grep -v grep > "$OUT/00-before-ps.txt" 2>&1
sh kb/kbpy l7/scripts/kb_loop_claim.py status > "$OUT/00-claim-before.txt" 2>&1
echo "claim-before exit=$?"
wc -l < kb/l7/runs/index.jsonl > "$OUT/00-index-before.txt"

r(){ nm="$1"; shift; "$@" >"$OUT/$nm.out" 2>&1; ec=$?; echo "$nm exit=$ec" >> "$OUT/00-exits.txt"; echo "$nm exit=$ec"; }

rm -f "$OUT/00-exits.txt"
# ① 先跑 --check：它自带「跑前/跑后 mtime 快照」零写自证，必须跑在我自己写任何报告之前
r 01-pipeline_check   sh kb/kbpy l7/scripts/kb_pipeline.py --check
# ② 六道闸门（口径见 kb-check：登记表 / 层契约 / 路由 / 信封 / 投影 / 链路收口）
r 02-skills_check     sh kb/kbpy l7/scripts/skills_check.py
r 03-layers_check     sh kb/kbpy l7/scripts/layers_check.py
r 04-routes_reconcile sh kb/kbpy l7/scripts/routes_reconcile.py "kb/l7/reports/$RUN-routes-winners.json"
r 05-envelope_gate    /usr/bin/python3 tools/envelope_gate.py
r 06-envelope_census  sh kb/kbpy l8/envelope_census.py
r 07-projection_recon sh kb/kbpy l8/projection_reconcile.py
r 08-workflow_check   sh kb/kbpy l8/workflow_check.py "$RUN"

wc -l < kb/l7/runs/index.jsonl > "$OUT/09-index-after.txt"
ps -eo pid,ppid,etime,command | grep -E "$PAT" | grep -v grep > "$OUT/09-after-ps.txt" 2>&1
sh kb/kbpy l7/scripts/kb_loop_claim.py status > "$OUT/09-claim-after.txt" 2>&1
date
echo "=== done ==="
cat "$OUT/00-exits.txt"
