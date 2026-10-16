#!/bin/bash
# 定向冒烟：验证「欠定 → 不加载 + 必须回一句追问范围」是否让边界题 3 轮收敛、且正例不掉。
# 集合 = 8 正例 + 12 边界 = 20 条 × 3 轮（60 会话）。限时 180s（正例中位 ~180s，故放宽）。
set -u
cd "$(dirname "$0")"
LOG=logs/smoke-ask.log
mkdir -p logs
echo "===== $(date -Iseconds) 冒烟启动（20 条 × 3 轮）=====" >> "$LOG"
for R in 1 2 3; do
  echo "--- $(date -Iseconds) round $R" >> "$LOG"
  python3 run_round.py --paper a --round $R --ids 1-8 --concurrency 6 --timeout 180 \
    --outfile "a-round-${R}.smokeask.jsonl" --work-root /tmp/kb-l0-smoke-ask >> "$LOG" 2>&1
  python3 run_round.py --paper a --round $R --ids 89-100 --concurrency 6 --timeout 180 \
    --outfile "a-round-${R}.smokeask.jsonl" --work-root /tmp/kb-l0-smoke-ask >> "$LOG" 2>&1
done
echo "===== $(date -Iseconds) 冒烟结束 =====" >> "$LOG"
for f in a-round-*.smokeask.jsonl; do echo "$f: $(wc -l < "$f") 条" >> "$LOG"; done
