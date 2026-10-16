#!/bin/bash
# 唯一 driver（带独占锁，防两实例互相覆盖同一批 round 文件）
set -u
cd "$(dirname "$0")"
LOCK=/tmp/kbrecall-fix-runA.lock
if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "!!! 已有 driver 在跑 (pid $(cat "$LOCK"))，拒绝启动第二个"; exit 3
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
export KB_RECALL_FIX_CWD_ROOT=/tmp/kbrecall-fix-cwd-v130c
export KB_RECALL_EVAL_CWD_ROOT=/tmp/kbrecall-fix-cwd-v130c
PAPER="${1:-a}"
for R in 1 2 3; do
  echo "===== $(date -Iseconds) $PAPER round $R ====="
  python3 rt2.py --paper "$PAPER" --round $R --concurrency 8 --timeout 120
  echo "===== $(date -Iseconds) rerun invalid $PAPER round $R ====="
  python3 rerun2.py --paper "$PAPER" --round $R --timeout 420 --concurrency 6
done
echo "===== $(date -Iseconds) ALL $PAPER ROUNDS DONE ====="
