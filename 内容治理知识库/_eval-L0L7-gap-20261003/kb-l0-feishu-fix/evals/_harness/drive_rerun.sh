#!/bin/bash
# L0 v1.3.0 证据不足补跑驱动器（2026-10-04 重起；可中断续跑）
#
# 为什么要有这个文件（一次真实事故）：
#   上一版由 python 直接 fork 多个 run_round.py 子进程，会话一终止、子进程随父被带走，
#   79 条一条没落盘（`a-round-*.rerun.jsonl` 全不存在）。本驱动器由**受管后台任务**跑，
#   每步独立进程 + 日志落盘 ⇒ 断了能看断在哪、能续。
#
# 纪律：
#   · 只补 `rerun_insufficient.py` 算出的并集（79 条 = 队列 67 ∪ 又超时 12），不碰已成立的 233 条；
#   · 限时 420s（120s 版实测 79 条被截），补的是**回复**，不重判触发；
#   · 落盘 `a-round-N.rerun.jsonl`，最后由 merge_rerun.py 合并，不直接覆盖正式归档。
set -u
cd "$(dirname "$0")"
LOG=logs/rerun-driver.log
mkdir -p logs
echo "===== $(date -Iseconds) 补跑驱动器启动 =====" >> "$LOG"

run_group () {
  local tag="$1"; shift
  local ids="$1"; shift
  local out="a-round-${tag}.rerun.jsonl"
  # 逐区间跑（区间由 python 侧算好，这里只消费）
  for range in $ids; do
    echo "--- $(date -Iseconds) r${tag} ids=${range} → ${out}" >> "$LOG"
    python3 run_round.py --paper a --round "$tag" --ids "$range" \
      --concurrency 6 --timeout 420 \
      --outfile "$out" --work-root /tmp/kb-l0fix-rerun-v130 >> "$LOG" 2>&1
    echo "    exit=$? 累计 $( [ -f "$out" ] && wc -l < "$out" || echo 0 ) 条" >> "$LOG"
  done
}

# 区间划分 = 证据不足并集（run_round 的 --ids 只吃「单条」或「连续区间」）
run_group 1 "1-2 6 12-15 18-19 24 27 30 34 36 38 44 46-47 51 58 68 78 82-85 99"
run_group 2 "6-7 11-13 15-20 24 26-27 30 37-39 44 49-52 71 78 81 83 85 88 99"
run_group 3 "3 9 11 13-15 18 26 32 34 37-39 44 47-49 51 81 83 85 87 99"

echo "===== $(date -Iseconds) 补跑驱动器结束 =====" >> "$LOG"
for f in a-round-*.rerun.jsonl; do
  echo "$f: $(wc -l < "$f") 条" >> "$LOG"
done
echo "下一步：python3 merge_rerun.py" >> "$LOG"
