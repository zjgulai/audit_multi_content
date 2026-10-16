#!/bin/bash
# 真实进度心跳：每 90s 记录「已落盘条数 + 在跑会话数 + 会话文件最新 mtime」，不伪造完成度。
EV="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/_eval-L0L7-gap-20261003/kb-recall/evals"
while true; do
  for P in a b; do for R in 1 2 3; do
    f="$EV/rounds/$P-round$R.jsonl"
    n=$([ -f "$f" ] && wc -l < "$f" | tr -d ' ' || echo 0)
    echo "tick $(date +%H:%M:%S) $P-r$R done=$n" >> "$EV/_eval/heartbeat-tick.txt"
  done; done
  alive=$(ps aux | grep -c "[e]val-l0")
  echo "tick $(date +%H:%M:%S) live_sessions=$alive" >> "$EV/_eval/heartbeat-tick.txt"
  sleep 90
done
