#!/bin/sh
# 零写闸门体检（kb-pipeline）—— 复刻 _gate-run-20261004-1024 口径 + 有界并发等待 + 前后 sha 自证
# 只跑只读档：kb/l7/scripts/l0_gate.py … l7_gate.py、kb_pipeline.py --check
# 绝不碰 kb/l0..l7 数据；所有产物落在 _gate-run-<RUN>/
set -u
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 2

RUN=GATE-20261004-1142
OUT="_gate-run-$RUN"
mkdir -p "$OUT"
PAT='kb_pipeline\.py|l[0-8]_gate\.py|workflow_check\.py|skills_check\.py|layers_check\.py|routes_reconcile\.py|envelope_census\.py|projection_reconcile\.py|skill_conformance\.py'

echo "=== 阶段0 · 有界等并发静默（连续 15 秒无相关进程；上限 3 分钟）==="
i=0; quiet=0; n=99
while [ "$i" -lt 36 ]; do
  n=$(ps -eo command | grep -E "$PAT" | grep -v grep | grep -v "$$" | wc -l | tr -d ' ')
  if [ "$n" -eq 0 ]; then quiet=$((quiet+1)); else quiet=0; fi
  [ "$quiet" -ge 3 ] && break
  i=$((i+1)); sleep 5
done
echo "阶段0 结束：此刻相关进程数=${n} ｜ 连续静默计数=${quiet} ｜ 等待轮次=${i}（每轮 5 秒）"
date
ps -eo pid,etime,command | grep -E "$PAT" | grep -v grep > "$OUT/00-before-ps.txt" 2>&1
sh kb/kbpy l7/scripts/kb_loop_claim.py status > "$OUT/00-claim-before.txt" 2>&1

echo "=== 跑前数据指纹（零写自证 pre）==="
for f in kb/l0/manifest.jsonl kb/l2/units.jsonl kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl \
         kb/l4/registry/l4.json kb/l5/p0_patterns.jsonl kb/l6/registry/l6.json kb/l7/runs/index.jsonl; do
  if [ -f "$f" ]; then printf '%s %s %s\n' "$(stat -f %z "$f")" "$(shasum -a 256 "$f" | cut -c1-16)" "$f"; fi
done > "$OUT/pre.sha"
cat "$OUT/pre.sha"

rm -f "$OUT/00-exits.txt"
r(){ nm="$1"; shift; t0=$(date +%s); "$@" >"$OUT/$nm.txt" 2>&1; ec=$?; t1=$(date +%s); \
     echo "$nm exit=$ec secs=$((t1-t0))" | tee -a "$OUT/00-exits.txt"; }

echo "=== 八层闸门（layers.yaml 各层 gate:）==="
r l0_gate sh kb/kbpy l7/scripts/l0_gate.py
r l1_gate sh kb/kbpy l7/scripts/l1_gate.py
r l2_gate sh kb/kbpy l7/scripts/l2_gate.py
r l3_gate sh kb/kbpy l7/scripts/l3_gate.py
r l4_gate sh kb/kbpy l7/scripts/l4_gate.py
r l5_gate sh kb/kbpy l7/scripts/l5_gate.py
r l6_gate sh kb/kbpy l7/scripts/l6_gate.py
r l7_gate sh kb/kbpy l7/scripts/l7_gate.py

echo "=== kb_pipeline.py --check（零写体检，不跑层引擎）==="
r pipeline_check sh kb/kbpy l7/scripts/kb_pipeline.py --check

echo "=== 跑后数据指纹（零写自证 post）==="
for f in kb/l0/manifest.jsonl kb/l2/units.jsonl kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl \
         kb/l4/registry/l4.json kb/l5/p0_patterns.jsonl kb/l6/registry/l6.json kb/l7/runs/index.jsonl; do
  if [ -f "$f" ]; then printf '%s %s %s\n' "$(stat -f %z "$f")" "$(shasum -a 256 "$f" | cut -c1-16)" "$f"; fi
done > "$OUT/post.sha"
if diff "$OUT/pre.sha" "$OUT/post.sha" > "$OUT/sha-diff.txt" 2>&1; then
  echo "零写自证：✅ 8 项库文件 sha 完全一致（本跑未改任何库数据）" | tee -a "$OUT/00-exits.txt"
else
  echo "零写自证：❌ 有文件变化，见 $OUT/sha-diff.txt" | tee -a "$OUT/00-exits.txt"
fi

ps -eo pid,etime,command | grep -E "$PAT" | grep -v grep > "$OUT/09-after-ps.txt" 2>&1
date
echo "=== done ==="
cat "$OUT/00-exits.txt"
