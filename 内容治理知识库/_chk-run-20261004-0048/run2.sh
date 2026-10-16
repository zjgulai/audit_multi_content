#!/bin/bash
# 等 launchd 那一轮 ci/run_gates.py 跑完，再用本会话自己的 RUN 独立复跑一遍（可复现对照）
ROOT="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
OUT="$ROOT/_chk-run-20261004-0048"
PID="$1"

echo "=== 等 launchd run_gates (pid=$PID) 退出 ==="
n=0
while kill -0 "$PID" 2>/dev/null; do sleep 10; n=$((n+1)); if [ "$n" -gt 180 ]; then echo "等待超时"; break; fi; done
echo "launchd 那一轮已结束（等了 $((n*10)) 秒）"
sleep 5

cd "$ROOT" || exit 9

echo "===== 本会话独立复跑 12 把闸门 ====="
python3 ci/run_gates.py --outdir "$OUT/ci-out" --json > "$OUT/ci-runner.out" 2>&1
rc=$?
printf '%s\n' "$rc" > "$OUT/ci-runner.exit"
echo ">>> ci/run_gates.py exit=$rc"

echo "===== ③ 路由对账：用现存最新赢家表（09-29）复核 ====="
sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_after_r4.winners.txt --alias \
  > "$OUT/3b-routes-with-old-table.out" 2>&1
rc=$?
printf '%s\n' "$rc" > "$OUT/3b-routes-with-old-table.exit"
echo ">>> 3b routes(old table, --alias) exit=$rc"

echo "===== ALL DONE (job2) ====="
