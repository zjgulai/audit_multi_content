#!/bin/bash
# 验证改后的 other 用例（A′）：**原始版与修复版都跑**，证明用例不是只对修复版有利
cd "$(dirname "$0")/.."
H=harness/run_round.py
run() { # $1=skill $2=tag $3=cases $4=ids $5=out
  for r in 1 2 3; do
    python3 "$H" --round $r --skill "$1" --profile "eval-$2" --cases "$3" \
      --concurrency 3 --timeout 600 --ids "$4" \
      --work-root "/tmp/kb-l1l7-ctl2-$2" \
      --outfile "_control-callgate2/$5-round-$r.jsonl" 2>&1 | tail -2
  done
}
echo "### media 修复 v1.2.0"; run kb-media-extractor  mediafix   cases/kb-media-extractor  51-53   media-fix
echo "### media 原始 v1.1.0"; run kb-media-extractor  mediabase  cases/kb-media-extractor  51-53   media-base
echo "### clause 修复 v2.2.0"; run kb-clause-extractor clausefix  cases/kb-clause-extractor 101-103 clause-fix
echo "### clause 原始 v2.1.0"; run kb-clause-extractor clausebase cases/kb-clause-extractor 101-103 clause-base
echo "=== DONE ==="
