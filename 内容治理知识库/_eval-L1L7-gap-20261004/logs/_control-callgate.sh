#!/bin/bash
# 对照实验（修正版）：**原始版**在那 3 条调用题上过不过？
# ★ --ids 只认单值或 lo-hi 区间，**不认逗号列表**（2026-10-04 踩过）
cd "$(dirname "$0")/.."
H=harness/run_round.py
run() { # $1=skill $2=tag $3=cases $4=ids区间 $5=outprefix
  for r in 1 2 3; do
    python3 "$H" --round $r --skill "$1" --profile "eval-$2" --cases "$3" \
      --concurrency 3 --timeout 600 --ids "$4" \
      --work-root "/tmp/kb-l1l7-control-$2" \
      --outfile "_control-callgate/$5-round-$r.jsonl" 2>&1 | tail -3
  done
}
echo "=== media 原始 v1.1.0（调用题 51-53）==="
run kb-media-extractor  mediabase  cases/kb-media-extractor  51-53   media-base
echo "=== clause 原始 v2.1.0（调用题 101-103）==="
run kb-clause-extractor clausebase cases/kb-clause-extractor 101-103 clause-base
echo "=== DONE ==="
