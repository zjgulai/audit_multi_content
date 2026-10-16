#!/bin/sh
# 「跑一遍闸门」—— kb-pipeline 口径（复刻 _gate-run-20261004-1142 两段式：八层闸门 + 收口四件套）
# 只读档：l0_gate..l7_gate + kb_pipeline.py --check + workflow_check/skills_check/envelope_census/skill_conformance
# 绝不碰 kb/l0..l7 数据；产物落 _gate-run-<RUN>/；前后 sha 自证 + 变化归因
set -u
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 2

RUN=GATE-20261004-1234
OUT="_gate-run-$RUN"
mkdir -p "$OUT"
PAT='kb_pipeline\.py|l[0-8]_gate\.py|workflow_check\.py|skills_check\.py|layers_check\.py|routes_reconcile\.py|envelope_census\.py|projection_reconcile\.py|skill_conformance\.py'
FILES="kb/l0/manifest.jsonl kb/l2/units.jsonl kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl kb/l4/registry/l4.json kb/l5/p0_patterns.jsonl kb/l6/registry/l6.json kb/l7/runs/index.jsonl"

snap(){
  for f in $FILES; do
    [ -f "$f" ] && printf '%s %s %s\n' "$(stat -f %z "$f")" "$(shasum -a 256 "$f" | cut -c1-16)" "$f"
  done
  echo "RUNFILES $(find kb/l7/runs -maxdepth 1 -name '*.json' | wc -l | tr -d ' ')"
}

echo "=== 阶段0 · 有界等并发静默（连续 15 秒无相关进程；上限 3 分钟）==="
i=0; quiet=0; n=99
while [ "$i" -lt 36 ]; do
  n=$(ps -eo pid,command | grep -E "$PAT" | grep -v grep | grep -v "$$" | wc -l | tr -d ' ')
  if [ "$n" -eq 0 ]; then quiet=$((quiet+1)); else quiet=0; fi
  [ "$quiet" -ge 3 ] && break
  i=$((i+1)); sleep 5
done
echo "阶段0 结束：此刻相关进程数=${n} ｜ 连续静默计数=${quiet} ｜ 等待轮次=${i}（每轮 5 秒）" | tee "$OUT/00-quiet.txt"
date | tee -a "$OUT/00-quiet.txt"
ps -eo pid,etime,command | grep -E "$PAT" | grep -v grep > "$OUT/00-before-ps.txt" 2>&1
sh kb/kbpy l7/scripts/kb_loop_claim.py status > "$OUT/00-claim-before.txt" 2>&1

echo "=== 阶段A · 跑前数据指纹（零写自证 pre）==="
snap > "$OUT/pre.sha"; cat "$OUT/pre.sha"

rm -f "$OUT/00-exits.txt"
r(){ nm="$1"; shift; t0=$(date +%s); "$@" >"$OUT/$nm.txt" 2>&1; ec=$?; t1=$(date +%s); \
     printf '%s exit=%s secs=%s\n' "$nm" "$ec" "$((t1-t0))" >> "$OUT/00-exits.txt"; }

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

echo "=== 阶段A · 跑后数据指纹（零写自证 post）==="
snap > "$OUT/post.sha"
if diff "$OUT/pre.sha" "$OUT/post.sha" > "$OUT/sha-diff.txt" 2>&1; then
  echo "阶段A 零写自证：✅ 8 项库文件 + run 文件数 全未变" | tee -a "$OUT/00-exits.txt"
else
  echo "阶段A 零写自证：❌ 有变化（归因见下）" | tee -a "$OUT/00-exits.txt"
  cat "$OUT/sha-diff.txt" | tee -a "$OUT/00-exits.txt"
  echo "--- 本窗口内 kb/ 下被改/新建的文件（归因用）---" | tee -a "$OUT/00-exits.txt"
  find kb -newermt "$(date -v-15M '+%Y-%m-%d %H:%M:%S')" -type f 2>/dev/null | head -20 | tee -a "$OUT/00-exits.txt"
fi

echo "=== 阶段B · 收口四件套（kb-pipeline §4）==="
snap > "$OUT/pre4.sha"
rm -f "$OUT/10-exits.txt"
r 10-workflow_check sh kb/kbpy l8/workflow_check.py "$RUN"
r 11-skills_check sh kb/kbpy l7/scripts/skills_check.py
r 12-envelope_census sh kb/kbpy l8/envelope_census.py
r 13-skill_conformance sh kb/kbpy l7/scripts/skill_conformance.py

snap > "$OUT/post4.sha"
if diff "$OUT/pre4.sha" "$OUT/post4.sha" > "$OUT/sha4-diff.txt" 2>&1; then
  echo "阶段B 归因：✅ 8 项库文件 + run 文件数 全未变" | tee -a "$OUT/10-exits.txt"
else
  echo "阶段B 归因：⚠️ 有变化（逐行如下）" | tee -a "$OUT/10-exits.txt"; cat "$OUT/sha4-diff.txt" | tee -a "$OUT/10-exits.txt"
fi

ps -eo pid,etime,command | grep -E "$PAT" | grep -v grep > "$OUT/09-after-ps.txt" 2>&1
sh kb/kbpy l7/scripts/kb_loop_claim.py status > "$OUT/09-claim-after.txt" 2>&1
date
echo "=== done ==="
echo "--- 阶段A ---"; cat "$OUT/00-exits.txt"
echo "--- 阶段B ---"; cat "$OUT/10-exits.txt"
