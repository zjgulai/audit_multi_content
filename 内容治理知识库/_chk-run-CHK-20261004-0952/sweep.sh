#!/bin/bash
# kb-check 体检档 —— 六道闸门 sweep（可复跑）
# RUN = CHK-20261004-0952   cwd = 库根
# 纪律：只报不改。唯一写盘动作 = 门④ workflow_check 的 kb/l8/workflow_check_<RUN>.json（已先声明）。
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 9
RUN=CHK-20261004-0952
D="$PWD/_chk-run-$RUN"
mkdir -p "$D"
: > "$D/exitcodes.txt"

echo "== 环境 =="
date '+%Y-%m-%d %H:%M:%S'
echo "kb/kbpy: $(ls -l kb/kbpy 2>&1 | head -1)"
echo "tools/envelope_gate.py: $(ls -l tools/envelope_gate.py 2>&1 | head -1)"
echo "winners(规范路径): $(ls -l kb/l7/reports/$RUN-routes-winners.json 2>&1 | head -1)"
echo "-- 全工作区 *routes-winners* 现存文件（按时间倒序）--"
find . -name '*routes-winners*' -type f -not -path './.git/*' -exec stat -f '%Sm %z %N' -t '%Y-%m-%d %H:%M:%S' {} \; 2>/dev/null | sort -r | head -20
echo "-- 会话级认领 --"
cat kb/.work/.kb-loop-claim.json 2>&1 | head -20
echo "-- 工作区实时写入者（近5分钟 kb/ 改动文件数）--"
find kb -type f -newermt '-5 minutes' 2>/dev/null | wc -l

run() {
  local name="$1"; shift
  local t0; t0=$(date '+%H:%M:%S')
  "$@" >"$D/$name.out" 2>"$D/$name.err"
  local rc=$?
  local t1; t1=$(date '+%H:%M:%S')
  printf '%s|%s|%s|%s\n' "$name" "$rc" "$t0" "$t1" >> "$D/exitcodes.txt"
  echo "[$name] exit=$rc  ($t0 -> $t1)"
}

# ① 登记表自检
run ①-skills_check        sh kb/kbpy l7/scripts/skills_check.py
run ①-skills_check-json   sh kb/kbpy l7/scripts/skills_check.py --json
# ② 层契约
run ②-layers_check        sh kb/kbpy l7/scripts/layers_check.py
# ③ 路由表对账（三种输入/口径）
run ③a-canonical-missing  sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/$RUN-routes-winners.json
WINNER=$(find . -name '*routes-winners*' -type f -not -path './.git/*' -exec stat -f '%m %N' {} \; 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
echo "③ 采用输入: ${WINNER:-<none>}" | tee "$D/③-input.txt"
if [ -n "$WINNER" ]; then
  run ③b-strict           sh kb/kbpy l7/scripts/routes_reconcile.py "$WINNER"
  run ③c-alias            sh kb/kbpy l7/scripts/routes_reconcile.py "$WINNER" --alias
else
  echo "none|9|--|--" >> "$D/exitcodes.txt"
fi
# ④ 链路收口（无干跑档，写 kb/l8/workflow_check_<RUN>.json —— 已声明）
run ④-workflow_check      sh kb/kbpy l8/workflow_check.py $RUN
# ⑤ 信封闸门（两个覆盖面不同的工具）
run ⑤a-envelope_gate      python3 tools/envelope_gate.py
run ⑤b-envelope_census    sh kb/kbpy l8/envelope_census.py
# ⑥ 投影一致性（不加写参数）
run ⑥-projection          sh kb/kbpy l8/projection_reconcile.py

echo "== 汇总 =="
cat "$D/exitcodes.txt"
echo "== 收尾：本会话写盘清点（kb/l8 近10分钟） =="
find kb/l8 -maxdepth 1 -newermt '-10 minutes' -exec stat -f '%Sm %z %N' -t '%H:%M:%S' {} \; 2>/dev/null | sort -r | head
date '+%Y-%m-%d %H:%M:%S'
