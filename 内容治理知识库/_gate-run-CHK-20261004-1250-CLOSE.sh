#!/bin/sh
# kb-check 体检档：统一闸门六道 + 逐层闸门 L0–L7（只读）
# 唯一写盘：kb/l8/workflow_check_<RUN>.json（门④ 按设计写读数件，无干跑档）
set -u
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 2

RUN=CHK-20261004-1250-CLOSE
OUT="_chk-run-$RUN"
mkdir -p "$OUT"
PAT='kb_pipeline\.py|l[0-8]_gate\.py|workflow_check\.py|skills_check\.py|layers_check\.py|routes_reconcile\.py|envelope_census\.py|projection_reconcile\.py|envelope_gate\.py|l5_integrity\.py|align_l0_feishu\.py'
FILES="kb/l0/manifest.jsonl kb/l2/units.jsonl kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl kb/l4/registry/l4.json kb/l5/p0_patterns.jsonl kb/l6/registry/l6.json kb/l7/runs/index.jsonl"

snap(){
  for f in $FILES; do
    [ -f "$f" ] && printf '%s %s %s\n' "$(stat -f %z "$f")" "$(shasum -a 256 "$f" | cut -c1-16)" "$f"
  done
  echo "RUNFILES $(find kb/l7/runs -maxdepth 1 -name '*.json' | wc -l | tr -d ' ')"
}

echo "=== 阶段0 · 并发观测（不阻塞：最多等 12 轮 x 5s，只为记录读数窗口）==="
i=0; n=99
while [ "$i" -lt 12 ]; do
  n=$(ps -eo pid,command | grep -E "$PAT" | grep -v grep | grep -v "$$" | wc -l | tr -d ' ')
  [ "$n" -eq 0 ] && break
  i=$((i+1)); sleep 5
done
{ echo "阶段0 结束：此刻相关进程数=${n} ｜ 等待轮次=${i}（每轮 5 秒）"; date; } | tee "$OUT/00-quiet.txt"
ps -eo pid,etime,command | grep -E "$PAT" | grep -v grep > "$OUT/00-before-ps.txt" 2>&1
sh kb/kbpy l7/scripts/kb_loop_claim.py status > "$OUT/00-claim-before.txt" 2>&1

echo "=== 阶段A · 跑前数据指纹（零写自证 pre）==="
snap > "$OUT/pre.sha"; cat "$OUT/pre.sha"

rm -f "$OUT/00-exits.txt"
r(){ nm="$1"; shift; t0=$(date +%s); "$@" >"$OUT/$nm.txt" 2>&1; ec=$?; t1=$(date +%s); \
     printf '%s exit=%s secs=%s\n' "$nm" "$ec" "$((t1-t0))" >> "$OUT/00-exits.txt"; }

echo "=== ① 登记表自检 ② 层契约自检 ==="
r 01-skills_check sh kb/kbpy l7/scripts/skills_check.py
r 02-layers_check sh kb/kbpy l7/scripts/layers_check.py

echo "=== ③ 路由表对账（先无参，再去 passthrough 取盘上最新赢家表复跑）==="
r 03a-routes-noarg sh kb/kbpy l7/scripts/routes_reconcile.py
W="$(find _eval-kb-manage _eval-kb-check-20261004 _eval-kb-check-20261004-b -iname '*routes-winners*' 2>/dev/null | xargs ls -t 2>/dev/null | head -1)"
echo "最新赢家表候选：$W" | tee "$OUT/03b-candidate.txt"
if [ -n "$W" ]; then
  cp "$W" "$OUT/winners-used.txt"
  ls -l "$W" >> "$OUT/03b-candidate.txt"
  r 03b-routes-latest sh kb/kbpy l7/scripts/routes_reconcile.py "$W" --alias
fi

echo "=== ⑤ 信封闸门（两口径）==="
( t0=$(date +%s); python3 tools/envelope_gate.py >"$OUT/05a-envelope_gate.txt" 2>&1; ec=$?; t1=$(date +%s); \
  printf '05a-envelope_gate exit=%s secs=%s\n' "$ec" "$((t1-t0))" >> "$OUT/00-exits.txt" )
r 05b-envelope_census sh kb/kbpy l8/envelope_census.py

echo "=== 逐层闸门 L0–L7（layers.yaml 各层 gate:）==="
rm -f "$OUT/20-exits.txt"
rl(){ nm="$1"; shift; t0=$(date +%s); "$@" >"$OUT/$nm.txt" 2>&1; ec=$?; t1=$(date +%s); \
      printf '%s exit=%s secs=%s\n' "$nm" "$ec" "$((t1-t0))" >> "$OUT/20-exits.txt"; }
for g in l0 l1 l2 l3 l4 l5 l6 l7; do
  rl "${g}_gate" sh kb/kbpy "l7/scripts/${g}_gate.py"
done
rl pipeline_check sh kb/kbpy l7/scripts/kb_pipeline.py --check

echo "=== 阶段A · 跑后数据指纹（零写自证 post）==="
snap > "$OUT/post.sha"
if diff "$OUT/pre.sha" "$OUT/post.sha" > "$OUT/sha-diff.txt" 2>&1; then
  echo "阶段A 零写自证：✅ 8 项库文件 + run 文件数 全未变" | tee -a "$OUT/00-exits.txt"
else
  echo "阶段A 零写自证：❌ 有变化（归因见 sha-diff）" | tee -a "$OUT/00-exits.txt"
  cat "$OUT/sha-diff.txt" | tee -a "$OUT/00-exits.txt"
fi

echo "=== ④ 链路收口核验（★唯一写盘：kb/l8/workflow_check_$RUN.json）==="
snap > "$OUT/pre4.sha"
r 04-workflow_check sh kb/kbpy l8/workflow_check.py "$RUN"
snap > "$OUT/post4.sha"
diff "$OUT/pre4.sha" "$OUT/post4.sha" > "$OUT/sha4-diff.txt" 2>&1 && echo "阶段④ 归因：✅ 库文件未变" >> "$OUT/00-exits.txt" || cat "$OUT/sha4-diff.txt" >> "$OUT/00-exits.txt"

echo "=== ⑥ 投影一致性（只读复核）==="
r 06-projection_reconcile sh kb/kbpy l8/projection_reconcile.py

ps -eo pid,etime,command | grep -E "$PAT" | grep -v grep > "$OUT/09-after-ps.txt" 2>&1
sh kb/kbpy l7/scripts/kb_loop_claim.py status > "$OUT/09-claim-after.txt" 2>&1
date
echo "=== done ==="
echo "--- 阶段A/① ② ③ ⑤ ---"; cat "$OUT/00-exits.txt"
echo "--- 逐层 ---"; cat "$OUT/20-exits.txt"
