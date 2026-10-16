#!/usr/bin/env bash
# A 卷全量 3 轮 × 2 分片（每分片 concurrency 3 ⇒ 全局 18 并发）
set -u
cd "$(dirname "$0")"
mkdir -p logs
for r in 1 2 3; do
  python3 run_round.py --round $r --concurrency 3 --timeout 600 --ids 1-52  --work-root /tmp/kb-l0fix-blind-v7 \
        --outfile a-round-$r.jsonl  > logs/a${r}-A.log 2>&1 &
  python3 run_round.py --round $r --concurrency 3 --timeout 600 --ids 53-104 --work-root /tmp/kb-l0fix-blind-v7 \
        --outfile a-round-${r}b.jsonl > logs/a${r}-B.log 2>&1 &
done
wait
echo "=== 全部分片结束 ==="
for f in a-round-*.jsonl; do echo -n "$f: "; wc -l < "$f"; done
python3 - <<'PY'
import json,glob
tot=empty=nos=0
for f in glob.glob('a-round-*.jsonl'):
    for l in open(f,encoding='utf-8'):
        if l.strip():
            o=json.loads(l); tot+=1
            if not o.get('reply'): empty+=1
            if not o.get('session_found'): nos+=1
print(f"总记录 {tot}/312 | 空回复 {empty} | 会话缺失 {nos}")
PY
