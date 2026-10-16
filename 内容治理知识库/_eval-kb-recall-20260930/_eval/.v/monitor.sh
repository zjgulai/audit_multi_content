#!/bin/bash
WB="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/_eval-kb-recall-20260930"
while true; do
  r1=$(wc -l < "$WB/_eval/a-round-1.jsonl" 2>/dev/null || echo 0)
  r2=$(wc -l < "$WB/_eval/a-round-2.jsonl" 2>/dev/null || echo 0)
  echo "$(date +%H:%M:%S) r1=$r1/53 r2=$r2/53 load=$(uptime | sed 's/.*load averages: //')"
  if [ "$r1" -ge 53 ] && [ "$r2" -ge 53 ]; then echo "ROUNDS 1+2 DONE"; exit 0; fi
  if ! pgrep -f "run-round.py" >/dev/null; then echo "ALL RUNNERS EXITED r1=$r1 r2=$r2"; exit 1; fi
  sleep 120
done
