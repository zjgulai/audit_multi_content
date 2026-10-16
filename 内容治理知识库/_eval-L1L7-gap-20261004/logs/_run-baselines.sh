#!/bin/bash
# 三个基线串行批跑（A 卷，600s，53 条 × 3 轮）。一次只跑一个，不并发。
cd "$(dirname "$0")/.."
for P in "kb-media-extractor mediabase" "kb-clause-extractor clausebase" "kb-ingest-extractor ingestbase"; do
  set -- $P
  echo "=== START $1 ($2) $(date '+%F %T') ==="
  python3 tools/run_a.py --skill "$1" --tag "$2" --cases "cases/$1" --out "runs/$2-a" 2>&1
  echo "=== END $1 ($2) exit=$? $(date '+%F %T') ==="
done
echo "=== ALL BASELINES DONE $(date '+%F %T') ==="
