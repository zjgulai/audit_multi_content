#!/bin/bash
# 端到端 canned 实测（S1+S2 后的新流程）：
#   等 kb/.work/.kb.lock 释放（不撬锁）→ 计时跑 四层前置 → 出结论 → 报告落盘
# 输出：_perf-20261005/after/e2e-run.log（人读）+ e2e-result.json（机读）
set -uo pipefail
ROOT="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
cd "$ROOT" || exit 2
OUT="_perf-20261005/after"
mkdir -p "$OUT"
LOG="$OUT/e2e-run.log"
: > "$LOG"
BASE="PERF-E2E-01"
SID="dsh-e2e-20261005"
PY=/usr/bin/python3

log() { echo "[e2e $(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

log "等锁（最多 20 分钟，绝不删锁/撬锁）…"
DEADLINE=$(( $(date +%s) + 1200 ))
while [ -f kb/.work/.kb.lock ]; do
  LPID=$("$PY" -c "import json;print(json.load(open('kb/.work/.kb.lock')).get('pid',''))" 2>/dev/null || true)
  if [ -n "${LPID:-}" ] && kill -0 "$LPID" 2>/dev/null; then
    if [ "$(date +%s)" -gt "$DEADLINE" ]; then
      log "⛔ 等待超时（20 min）：锁仍被活着的 pid=$LPID 持有。本次不跑（并发互斥优先）。"
      exit 3
    fi
    sleep 15; continue
  fi
  log "锁在但 pid=${LPID:-?} 已不在 → lock.held_dead，交给 kb_pipeline 自己处置，继续"
  break
done
[ -f kb/.work/.kb.lock ] || log "锁已释放 ✅"

# ── 计时跑 ────────────────────────────────────────────────────────────────
T1a=$(date +%s)
bash kb/l8/review_preflight.sh --base "$BASE" --session "$SID" >"$OUT/e2e-preflight.log" 2>&1
RCP=$?
T1b=$(date +%s)
log "M1 四层前置 exit=$RCP  用时 $((T1b-T1a)) s"

if [ "$RCP" != "0" ]; then
  log "⛔ 四层前置未全绿 —— 如实停下，不硬出结论。尾部："
  tail -8 "$OUT/e2e-preflight.log" | tee -a "$LOG"
  exit 4
fi

T2a=$(date +%s)
sh kb/kbpy l7/review-engine/core/with_kb_evidence.py \
  --text "$(cat _rt-img-20261005/rt-img-02-text.txt)" \
  --content-type image --question "审一下这张图能过吗？" \
  --require-layer-preflight "$BASE" \
  --decision-owner 图片安全审查 --loaded-skill 图片安全审查 \
  --loaded-skill kb-canonical-lookup --loaded-skill kb-p0-check \
  --loaded-skill kb-recall --loaded-skill kb-check \
  --no-publish-to-feishu --json > "$OUT/e2e-engine.json" 2>"$OUT/e2e-engine.err"
RCE=$?
T2b=$(date +%s)
log "M2 出结论 exit=$RCE  用时 $((T2b-T2a)) s"

T3a=$(date +%s)
RID=$("$PY" -c "import json;print(json.load(open('$OUT/e2e-engine.json')).get('evidence_meta',{}).get('review_id',''))" 2>/dev/null || true)
if [ -n "${RID:-}" ] && [ -f "kb/l7/reports/$RID.review.md" ]; then
  node -e "require('fs').copyFileSync(process.argv[1],process.argv[2])" \
    "kb/l7/reports/$RID.review.md" "$OUT/$RID.review.md" && log "M3 报告落盘 $OUT/$RID.review.md"
else
  log "M3 引擎未产出报告文件（review_id='${RID:-}'）"
fi
T3b=$(date +%s)

TOTAL=$((T3b-T1a))
"$PY" - "$OUT/e2e-result.json" "$T1a" "$T1b" "$T2a" "$T2b" "$T3a" "$T3b" "$RCP" "$RCE" "$BASE" <<'PYEOF'
import json, sys
out, t1a, t1b, t2a, t2b, t3a, t3b, rcp, rce, base = sys.argv[1:11]
d = {"base": base,
     "M1_preflight_s": int(t1b) - int(t1a), "M1_exit": int(rcp),
     "M2_engine_s": int(t2b) - int(t2a), "M2_exit": int(rce),
     "M3_report_s": int(t3b) - int(t3a),
     "total_scripted_s": int(t3b) - int(t1a)}
json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("=== 端到端 canned 实测（新流程）===")
for k, v in d.items():
    print(f"  {k} = {v}")
PYEOF
log "完成"
