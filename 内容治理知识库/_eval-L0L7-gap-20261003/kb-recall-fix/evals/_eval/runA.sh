#!/bin/bash
# A 卷 3 轮（最终 fix 版 v1.3.0 冻结）+ 无效记录补跑
cd "$(dirname "$0")"
export KB_RECALL_FIX_CWD_ROOT=/tmp/kbrecall-fix-cwd-v130b
export KB_RECALL_EVAL_CWD_ROOT=/tmp/kbrecall-fix-cwd-v130b
for R in 1 2 3; do
  echo "===== $(date -Iseconds) A round $R ====="
  python3 rt2.py --paper a --round $R --concurrency 8 --timeout 120
  echo "===== $(date -Iseconds) rerun invalid A round $R ====="
  python3 rerun2.py --paper a --round $R --timeout 420 --concurrency 6
done
echo "===== $(date -Iseconds) ALL A ROUNDS DONE ====="
