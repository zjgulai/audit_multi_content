#!/bin/sh
# kb-check 体检档 · 六道闸门 + L0-L7 八层闸门（只报不改）
# 唯一写盘：门④ workflow_check.py 写 kb/l8/workflow_check_<RUN>.json（无干跑档，已声明）
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 9
RUN=CHK-20261004-1347
D="kb/.work/kbcheck-$RUN"
mkdir -p "$D"
echo "RUN=$RUN"; date "+start %F %T"
echo "=== 并发写入者快照（开始）==="
ps -eo pid,etime,command | grep -E "kbpy|kb_pipeline|workflow_check|projection_reconcile|skills_check|envelope|_gate|freshness" | grep -v grep > "$D/00-ps-before.txt"
cat "$D/00-ps-before.txt"

# 有界等待：避开别的会话正在跑的 workflow_check（同门④，避免读到移动靶）
w=0
while [ "$w" -lt 180 ]; do
  if ! pgrep -f "kb/l8/workflow_check.py" >/dev/null 2>&1; then break; fi
  sleep 5; w=$((w+5))
done
printf 'pre-wait for concurrent workflow_check: %ss\n' "$w" | tee "$D/00-prewait.txt"

# 权威库零写自证：跑前指纹
echo "=== 跑前指纹（sha256 + bytes）===" > "$D/00-pre-sha.txt"
for f in kb/l0/manifest.jsonl kb/l2/units.jsonl kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl \
         kb/l4/registry/l4.json kb/l5/p0_patterns.jsonl kb/l6/registry/l6.json \
         kb/l7/runs/index.jsonl kb/l7/registry/layers.yaml; do
  if [ -f "$f" ]; then
    printf '%s %s %s\n' "$(wc -c < "$f" | tr -d ' ')" "$(shasum -a 256 "$f" | cut -c1-16)" "$f" >> "$D/00-pre-sha.txt"
  else
    printf 'MISSING - %s\n' "$f" >> "$D/00-pre-sha.txt"
  fi
done
cat "$D/00-pre-sha.txt"

: > "$D/00-exits.txt"
run() {
  name="$1"; shift
  s=$(date +%s)
  "$@" > "$D/$name.out" 2>&1
  ec=$?
  e=$(date +%s)
  printf '%s exit=%s secs=%s\n' "$name" "$ec" "$((e-s))" | tee -a "$D/00-exits.txt"
}

echo "########## A. kb-check 六道闸门 ##########" | tee -a "$D/00-exits.txt"
run A1-skills_check        sh kb/kbpy l7/scripts/skills_check.py
run A2-layers_check        sh kb/kbpy l7/scripts/layers_check.py
run A3a-routes-noarg       sh kb/kbpy l7/scripts/routes_reconcile.py
run A3b-routes-staleinput  sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt
printf '%s\n' '--- 门④ 声明：无干跑档，将写 kb/l8/workflow_check-'"$RUN"'.json ---' >> "$D/00-exits.txt"
run A4a-workflow_check     sh kb/kbpy l8/workflow_check.py "$RUN"
run A5a-envelope_gate      python3 tools/envelope_gate.py
run A5b-envelope_census    sh kb/kbpy l8/envelope_census.py
run A6-projection_reconcile sh kb/kbpy l8/projection_reconcile.py

echo "########## B. L0-L7 八层闸门 ##########" | tee -a "$D/00-exits.txt"
for L in 0 1 2 3 4 5 6 7; do
  run "B$L-l${L}_gate" sh kb/kbpy "l7/scripts/l${L}_gate.py"
done

# 权威库零写自证：跑后指纹
echo "=== 跑后指纹（sha256 + bytes）===" > "$D/00-post-sha.txt"
for f in kb/l0/manifest.jsonl kb/l2/units.jsonl kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl \
         kb/l4/registry/l4.json kb/l5/p0_patterns.jsonl kb/l6/registry/l6.json \
         kb/l7/runs/index.jsonl kb/l7/registry/layers.yaml; do
  if [ -f "$f" ]; then
    printf '%s %s %s\n' "$(wc -c < "$f" | tr -d ' ')" "$(shasum -a 256 "$f" | cut -c1-16)" "$f" >> "$D/00-post-sha.txt"
  else
    printf 'MISSING - %s\n' "$f" >> "$D/00-post-sha.txt"
  fi
done
cat "$D/00-post-sha.txt"
echo "=== 指纹差异（预/后）===" | tee "$D/00-sha-diff.txt"
diff "$D/00-pre-sha.txt" "$D/00-post-sha.txt" >> "$D/00-sha-diff.txt" 2>&1
if [ $? -eq 0 ]; then echo "无差异：权威库数据文件逐字节未变" | tee -a "$D/00-sha-diff.txt"; fi

echo "=== 并发写入者快照（结束）==="
ps -eo pid,etime,command | grep -E "kbpy|kb_pipeline|workflow_check|projection_reconcile|skills_check|envelope|_gate|freshness" | grep -v grep > "$D/09-ps-after.txt"
cat "$D/09-ps-after.txt"
date "+end %F %T"
echo "OUTDIR=$D"
echo "DONE"
