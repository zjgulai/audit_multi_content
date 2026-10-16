#!/bin/bash
# 极端长尾补跑：420s 都没跑完的那 7 条，放到 1500s。
#
# 为什么值得单独花这一轮（判据，不是"顺手多跑"）：
#   · 这 7 条的空回复是 Output 断言 O1 失败的主要来源（O1 290/312）；
#   · `output_assertions.py` 把空回复判 O1 失败 —— 那是**限时产物**，不是行为缺陷；
#   · 文档记载正例单条 144–720s，420s 处在这个分布的中段 ⇒ 加长限时是**对症**的。
#   改的只是"等多久"，判定口径一个字没动。
set -u
cd "$(dirname "$0")"
LOG=logs/rerun-long.log
mkdir -p logs
echo "===== $(date -Iseconds) 长尾补跑启动（timeout=1500s）=====" >> "$LOG"

# (round, id) —— 来自合并后归档里仍为空回复的记录
run_one () {
  local tag="$1" id="$2"
  echo "--- $(date -Iseconds) r${tag} n=${id}" >> "$LOG"
  python3 run_round.py --paper a --round "$tag" --ids "$id" \
    --concurrency 1 --timeout 1500 \
    --outfile "a-round-${tag}.long.jsonl" --work-root /tmp/kb-l0fix-rerun-long >> "$LOG" 2>&1
  echo "    exit=$?" >> "$LOG"
}

run_one 1 2
run_one 1 15
run_one 1 18
run_one 2 12
run_one 2 24
run_one 2 88
run_one 3 15

echo "===== $(date -Iseconds) 长尾补跑结束 =====" >> "$LOG"
for f in a-round-*.long.jsonl; do echo "$f: $(wc -l < "$f") 条" >> "$LOG"; done
